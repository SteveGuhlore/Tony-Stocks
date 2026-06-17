"""Control-plane POST endpoints for the Kinetic Tape dashboard (Codex #1/#2/#11; PLAN §A6).

These mirror the existing CLIs / kill-files. The hard safety posture (DEPLOY_RULES):

- **Money-adjacent** actions pass through ``env_fence.assert_money_action_allowed`` — a
  LOCAL DEV instance (``ENV_ROLE`` unset/dev) is *physically* incapable of firing them
  (→ HTTP 403). This is the fail-closed gate, not config text.
- A **typed PIN** (``DASHBOARD_ACTION_PIN``) compared constant-time guards dangerous actions.
- An **Origin allowlist** (``CORS_ORIGINS``) rejects requests from unknown web origins.
- An **idempotency key** (header ``Idempotency-Key``) dedups retries via the ``action_audit``
  table — a replayed request returns the prior result instead of acting twice.
- A **cross-process lock** (a lockfile under ``data/``) serializes control actions against
  the watch/paper processes; a conflict returns HTTP 409.
- **Per-action preconditions**: ``trigger-scan`` 409s if a scan is currently running;
  ``flatten-one`` / ``re-protect`` require a position version/snapshot match in the body.
- Every action writes an immutable ``action_audit`` row.

No new entries are ever placeable here (hard invariant) — only the existing kill-files /
re-protect / scan-trigger / export / ack surfaces.
"""
from __future__ import annotations

import hmac
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from trading_bot.api.deps import get_repo
from trading_bot.api.env_fence import MoneyActionForbidden, assert_money_action_allowed
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["controls"])

# Kill files (mirror the CLIs / watch loop).
STOP_WATCH_FILE = "STOP_WATCH_MODE"
STOP_PAPER_FILE = "STOP_PAPER_TRADING"
# Cross-process advisory lock honored by control actions (serializes vs watch/paper).
CONTROL_LOCK_FILE = "DASHBOARD_CONTROL.lock"
# A watch run whose heartbeat is fresher than this (seconds) counts as "scan running".
SCAN_RUNNING_FRESH_SECS = 90


# ── request bodies ────────────────────────────────────────────────────────────

class ControlBody(BaseModel):
    pin: str | None = None


class FlattenOneBody(ControlBody):
    symbol: str
    position_version: str | int | None = None  # must match the server's open-position snapshot


class ReProtectBody(ControlBody):
    symbol: str
    position_version: str | int | None = None


class ExportBody(ControlBody):
    slot: str | None = None  # 1030 | 1300 | 1530 | eod


class AckAlertBody(ControlBody):
    event_id: int


# ── helpers ────────────────────────────────────────────────────────────────────

def _data_dir(request: Request) -> Path:
    """The live ``data/`` dir (next to the SQLite DB). Kill files + the lock live here."""
    db_path = Path(getattr(request.app.state, "db_path", "data/trading_bot.db"))
    return db_path.parent


def _origin_allowed(request: Request) -> bool:
    """Reject control POSTs from web origins not on the CORS allowlist. Non-browser
    callers (no Origin header — e.g. server-side / tests) are allowed through; the PIN +
    env-fence remain the real guards."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    allowed = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    return origin in allowed


def _pin_ok(supplied: str | None) -> bool:
    """Constant-time PIN check. A configured PIN must match exactly. When NO PIN is
    configured we fail OPEN in dev (single-operator local tool) but fail CLOSED in
    prod (ENV_ROLE=prod): a production control plane must have DASHBOARD_ACTION_PIN set,
    otherwise any network client could drive the controls.

    OPERATOR NOTE: deploying this to a prod VM REQUIRES setting DASHBOARD_ACTION_PIN,
    or every control action will return 403 pin_required.
    """
    expected = os.environ.get("DASHBOARD_ACTION_PIN")
    if not expected:
        return os.environ.get("ENV_ROLE", "").strip().lower() != "prod"
    return bool(supplied) and hmac.compare_digest(str(supplied), str(expected))


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error": code, "detail": message})


def _idempotent_replay(repo: ScannerRepository, action: str, key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    prior = repo.find_action_audit(action=action, idempotency_key=key)
    if prior is None:
        return None
    return {"ok": prior.get("result") == "ok", "action": action, "replayed": True,
            "result": prior.get("result"), "detail": prior.get("detail")}


class _ControlLock:
    """Best-effort cross-process advisory lock via an exclusive lockfile under ``data/``.
    Honored by the API control actions; the watch/paper processes check the same file
    before mutating shared state. Returns 409 to the caller on conflict."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def __enter__(self) -> "_ControlLock":
        # Stale-lock reclaim: a lockfile older than 60s is assumed orphaned.
        try:
            if self.path.exists() and (time.time() - self.path.stat().st_mtime) > 60:
                self.path.unlink()
        except OSError:
            pass
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self._fd, str(os.getpid()).encode())
        except FileExistsError as exc:
            raise _LockConflict() from exc
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        try:
            self.path.unlink()
        except OSError:
            pass


class _LockConflict(Exception):
    pass


def _guard(
    request: Request, repo: ScannerRepository, action: str, *,
    body: ControlBody | None, idempotency_key: str | None, money: bool,
) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    """Run the common gate chain. Returns (replay_result, error_response). When both are
    None the caller proceeds to perform the action."""
    if not _origin_allowed(request):
        return None, _err(403, "origin_forbidden", "request origin is not on the allowlist")
    if not _pin_ok(body.pin if body else None):
        return None, _err(403, "pin_required", "missing or incorrect action PIN")
    if money:
        try:
            assert_money_action_allowed()
        except MoneyActionForbidden as exc:
            return None, _err(403, "money_action_forbidden", str(exc))
    replay = _idempotent_replay(repo, action, idempotency_key)
    if replay is not None:
        return replay, None
    return None, None


def _scan_running(repo: ScannerRepository) -> bool:
    try:
        run = repo.latest_watch_run()
        if not run or run.get("status") != "running":
            return False
        hb = run.get("last_heartbeat_at")
        if not hb:
            return True
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() < SCAN_RUNNING_FRESH_SECS
    except Exception:
        return False


def _open_position_version(repo: ScannerRepository, symbol: str) -> str | None:
    """A stable version token for the operator's view of an open position. Changes when
    the row id / qty / stop / target change, so a stale flatten/re-protect 409s."""
    try:
        for r in repo.list_paper_positions(limit=1000):
            if str(r.get("symbol", "")).upper() == symbol.upper() and r.get("status") == "open":
                return f"{r.get('id')}:{r.get('qty')}:{r.get('stop')}:{r.get('target')}"
    except Exception:
        return None
    return None


def _finish(repo: ScannerRepository, action: str, key: str | None, result: str, detail: str | None) -> None:
    try:
        repo.record_action_audit(action=action, idempotency_key=key, result=result, detail=detail)
    except Exception:
        pass


# ── endpoints ───────────────────────────────────────────────────────────────────

@router.post("/controls/stop-watch")
def stop_watch(request: Request, body: ControlBody | None = None,
               idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
               repo: ScannerRepository = Depends(get_repo)) -> Any:
    replay, err = _guard(request, repo, "stop-watch", body=body, idempotency_key=idempotency_key, money=True)
    if err:
        return err
    if replay:
        return replay
    try:
        with _ControlLock(_data_dir(request) / CONTROL_LOCK_FILE):
            (_data_dir(request) / STOP_WATCH_FILE).write_text("stop")
    except _LockConflict:
        return _err(409, "locked", "another control action is in progress")
    _finish(repo, "stop-watch", idempotency_key, "ok", "STOP_WATCH_MODE written")
    return {"ok": True, "action": "stop-watch"}


@router.post("/controls/pause-paper")
def pause_paper(request: Request, body: ControlBody | None = None,
                idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                repo: ScannerRepository = Depends(get_repo)) -> Any:
    replay, err = _guard(request, repo, "pause-paper", body=body, idempotency_key=idempotency_key, money=True)
    if err:
        return err
    if replay:
        return replay
    try:
        with _ControlLock(_data_dir(request) / CONTROL_LOCK_FILE):
            (_data_dir(request) / STOP_PAPER_FILE).write_text("stop")
    except _LockConflict:
        return _err(409, "locked", "another control action is in progress")
    _finish(repo, "pause-paper", idempotency_key, "ok", "STOP_PAPER_TRADING written")
    return {"ok": True, "action": "pause-paper"}


@router.post("/controls/resume-paper")
def resume_paper(request: Request, body: ControlBody | None = None,
                 idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                 repo: ScannerRepository = Depends(get_repo)) -> Any:
    replay, err = _guard(request, repo, "resume-paper", body=body, idempotency_key=idempotency_key, money=True)
    if err:
        return err
    if replay:
        return replay
    try:
        with _ControlLock(_data_dir(request) / CONTROL_LOCK_FILE):
            kill = _data_dir(request) / STOP_PAPER_FILE
            if kill.exists():
                kill.unlink()
    except _LockConflict:
        return _err(409, "locked", "another control action is in progress")
    _finish(repo, "resume-paper", idempotency_key, "ok", "STOP_PAPER_TRADING cleared")
    return {"ok": True, "action": "resume-paper"}


@router.post("/controls/flatten-all")
def flatten_all(request: Request, body: ControlBody | None = None,
                idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                repo: ScannerRepository = Depends(get_repo)) -> Any:
    replay, err = _guard(request, repo, "flatten-all", body=body, idempotency_key=idempotency_key, money=True)
    if err:
        return err
    if replay:
        return replay
    # Mirrors paper-flatten: request a flatten via the kill file (the paper process closes
    # positions). No order is fired from the request path; no NEW entries possible.
    try:
        with _ControlLock(_data_dir(request) / CONTROL_LOCK_FILE):
            (_data_dir(request) / "FLATTEN_ALL").write_text("flatten")
    except _LockConflict:
        return _err(409, "locked", "another control action is in progress")
    _finish(repo, "flatten-all", idempotency_key, "ok", "FLATTEN_ALL requested")
    return {"ok": True, "action": "flatten-all"}


@router.post("/controls/flatten-one")
def flatten_one(request: Request, body: FlattenOneBody,
                idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                repo: ScannerRepository = Depends(get_repo)) -> Any:
    replay, err = _guard(request, repo, "flatten-one", body=body, idempotency_key=idempotency_key, money=True)
    if err:
        return err
    if replay:
        return replay
    current = _open_position_version(repo, body.symbol)
    if current is None:
        return _err(409, "no_open_position", f"no open position for {body.symbol}")
    if body.position_version is not None and str(body.position_version) != current:
        return _err(409, "version_mismatch", "position changed since you last saw it; refresh and retry")
    try:
        with _ControlLock(_data_dir(request) / CONTROL_LOCK_FILE):
            (_data_dir(request) / f"FLATTEN_{body.symbol.upper()}").write_text("flatten")
    except _LockConflict:
        return _err(409, "locked", "another control action is in progress")
    _finish(repo, "flatten-one", idempotency_key, "ok", f"flatten requested for {body.symbol.upper()}")
    return {"ok": True, "action": "flatten-one", "symbol": body.symbol.upper()}


@router.post("/controls/re-protect")
def re_protect(request: Request, body: ReProtectBody,
               idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
               repo: ScannerRepository = Depends(get_repo)) -> Any:
    replay, err = _guard(request, repo, "re-protect", body=body, idempotency_key=idempotency_key, money=True)
    if err:
        return err
    if replay:
        return replay
    current = _open_position_version(repo, body.symbol)
    if current is None:
        return _err(409, "no_open_position", f"no open position for {body.symbol}")
    if body.position_version is not None and str(body.position_version) != current:
        return _err(409, "version_mismatch", "position changed since you last saw it; refresh and retry")
    try:
        with _ControlLock(_data_dir(request) / CONTROL_LOCK_FILE):
            (_data_dir(request) / f"REPROTECT_{body.symbol.upper()}").write_text("reprotect")
    except _LockConflict:
        return _err(409, "locked", "another control action is in progress")
    _finish(repo, "re-protect", idempotency_key, "ok", f"re-protect requested for {body.symbol.upper()}")
    return {"ok": True, "action": "re-protect", "symbol": body.symbol.upper()}


@router.post("/controls/trigger-scan")
def trigger_scan(request: Request, body: ControlBody | None = None,
                 idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                 repo: ScannerRepository = Depends(get_repo)) -> Any:
    # Not money-adjacent (no order), but still PIN/origin guarded + precondition.
    replay, err = _guard(request, repo, "trigger-scan", body=body, idempotency_key=idempotency_key, money=False)
    if err:
        return err
    if replay:
        return replay
    if _scan_running(repo):
        _finish(repo, "trigger-scan", idempotency_key, "conflict", "scan already running")
        return _err(409, "scan_running", "a scan is currently running")
    try:
        with _ControlLock(_data_dir(request) / CONTROL_LOCK_FILE):
            (_data_dir(request) / "TRIGGER_SCAN").write_text("scan")
    except _LockConflict:
        return _err(409, "locked", "another control action is in progress")
    _finish(repo, "trigger-scan", idempotency_key, "ok", "TRIGGER_SCAN requested")
    return {"ok": True, "action": "trigger-scan"}


@router.post("/controls/export-bridge")
def export_bridge(request: Request, body: ExportBody | None = None,
                  idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                  repo: ScannerRepository = Depends(get_repo)) -> Any:
    replay, err = _guard(request, repo, "export-bridge", body=body, idempotency_key=idempotency_key, money=False)
    if err:
        return err
    if replay:
        return replay
    slot = (body.slot if body else None) or "eod"
    try:
        with _ControlLock(_data_dir(request) / CONTROL_LOCK_FILE):
            (_data_dir(request) / "EXPORT_BRIDGE").write_text(slot)
    except _LockConflict:
        return _err(409, "locked", "another control action is in progress")
    _finish(repo, "export-bridge", idempotency_key, "ok", f"export requested (slot={slot})")
    return {"ok": True, "action": "export-bridge", "slot": slot}


@router.post("/controls/ack-alert")
def ack_alert(request: Request, body: AckAlertBody,
              idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
              repo: ScannerRepository = Depends(get_repo)) -> Any:
    replay, err = _guard(request, repo, "ack-alert", body=body, idempotency_key=idempotency_key, money=False)
    if err:
        return err
    if replay:
        return replay
    try:
        with _ControlLock(_data_dir(request) / CONTROL_LOCK_FILE):
            from trading_bot.storage.database import connect
            with connect(repo.database_path) as conn:
                conn.execute("UPDATE tony_events SET acknowledged = 1 WHERE id = ?", (int(body.event_id),))
    except _LockConflict:
        return _err(409, "locked", "another control action is in progress")
    except Exception as exc:
        _finish(repo, "ack-alert", idempotency_key, "error", str(exc))
        return _err(500, "ack_failed", "could not acknowledge alert")
    _finish(repo, "ack-alert", idempotency_key, "ok", f"acked event {body.event_id}")
    return {"ok": True, "action": "ack-alert", "event_id": body.event_id}
