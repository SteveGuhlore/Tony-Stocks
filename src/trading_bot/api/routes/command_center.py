"""GET /api/command-center — second-layer ("Tony Stocks" / Command Center) data.

Maps the two CC-written report files to ``CommandCenterResponse`` for the
dashboard's right side. Read-only: this endpoint never writes either file.

Producer files (the Command Center owns these — pure separation):
- ``reports/tony_stocks_verdicts.json`` (override ``TONY_VERDICTS_FILE``): an
  array of per-symbol verdicts → ``picks`` keyed by uppercase symbol.
- ``reports/tony_stocks_record.json`` (override ``TONY_RECORD_FILE``): the
  graded scorecard → ``record`` + ``agreement``.

Resilient by design: a missing or malformed file degrades to empty/None so the
dashboard renders "⋯ awaiting" rather than erroring (see
docs/CONTRACTS/command-center-bridge.md).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from trading_bot.api.schemas import (
    CommandCenterAgreement,
    CommandCenterPick,
    CommandCenterRecord,
    CommandCenterResponse,
)

router = APIRouter(tags=["command-center"])


# ── Path resolution ──────────────────────────────────────────────────────────

def _verdicts_path(reports_dir: Path) -> Path:
    env = os.environ.get("TONY_VERDICTS_FILE")
    return Path(env) if env else reports_dir / "tony_stocks_verdicts.json"


def _record_path(reports_dir: Path) -> Path:
    env = os.environ.get("TONY_RECORD_FILE")
    return Path(env) if env else reports_dir / "tony_stocks_record.json"


def _teaching_path(reports_dir: Path) -> Path:
    env = os.environ.get("TONY_TEACHING_FILE")
    return Path(env) if env else reports_dir / "tony_teaching_log.json"


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return None


# ── Coercion helpers (NaN/inf → None so the JSON stays valid) ────────────────

def _to_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    out: list[float] = []
    for v in value:
        f = _to_float(v)
        if f is not None:
            out.append(f)
    return out


# ── Pure mappers (unit-tested directly) ──────────────────────────────────────

def build_picks(verdicts: Any) -> dict[str, CommandCenterPick]:
    """Map the verdicts array to picks keyed by uppercase symbol.

    Dedup key is symbol+date; on collision the later row in the file wins.
    `verdict` is passed through verbatim (the frontend tolerates unknowns).
    """
    picks: dict[str, CommandCenterPick] = {}
    if not isinstance(verdicts, list):
        return picks
    for row in verdicts:
        if not isinstance(row, dict):
            continue
        raw_symbol = row.get("symbol")
        if not raw_symbol:
            continue
        symbol = str(raw_symbol).upper()
        date = str(row.get("date") or "")
        # verdicts carry a date but no time; normalize to an ISO instant the
        # dashboard can slice/display ("YYYY-MM-DDT00:00:00Z").
        if date and "T" not in date:
            returned_at = f"{date}T00:00:00Z"
        else:
            returned_at = date
        picks[symbol] = CommandCenterPick(
            symbol=symbol,
            score=_to_float(row.get("tony_score")) or 0.0,
            verdict=str(row.get("verdict") or ""),
            reasoning=str(row.get("thesis") or ""),
            returned_at=returned_at,
        )
    return picks


def build_record(record: Any) -> CommandCenterRecord | None:
    """Map the record file's scorecard to CommandCenterRecord.

    ``tony_win_rate`` is a 0–100 percentage in the producer file but the
    contract (and the dashboard's ``pct()`` helper) expects a 0–1 fraction.
    """
    if not isinstance(record, dict):
        return None
    wr = _to_float(record.get("tony_win_rate"))
    return CommandCenterRecord(
        win_rate=wr / 100.0 if wr is not None else None,
        avg_pl_per_trade=_to_float(record.get("avg_pl_per_trade")),
        target_hits=_to_int(record["target_hits"]) if "target_hits" in record else None,
        stop_hits=_to_int(record["stop_hits"]) if "stop_hits" in record else None,
        equity_curve=_float_list(record.get("equity_curve")),
    )


def build_agreement(record: Any) -> CommandCenterAgreement | None:
    """Map the record file's agreement tallies, renaming override_* → cc_overrode_*.

    Accepts either spelling (override_saved / cc_overrode_saved) for resilience.
    """
    if not isinstance(record, dict):
        return None
    agr = record.get("agreement")
    if not isinstance(agr, dict):
        return None
    return CommandCenterAgreement(
        agreed_right=_to_int(agr.get("agreed_right")),
        agreed_wrong=_to_int(agr.get("agreed_wrong")),
        cc_overrode_saved=_to_int(agr.get("override_saved", agr.get("cc_overrode_saved"))),
        cc_overrode_missed=_to_int(agr.get("override_missed", agr.get("cc_overrode_missed"))),
    )


def build_agreement_from_teaching(teaching: Any) -> CommandCenterAgreement | None:
    """Bot-side fallback: derive the agreement tally from the Tony divergence ledger
    (``tony_teaching_log.json``) when the CC's own record file has no agreement block.

    The ledger already uses the cc_overrode_* spelling (see
    ``trading_bot.analytics.tony_divergence``), so this is a straight read.
    """
    if not isinstance(teaching, dict):
        return None
    agr = teaching.get("agreement")
    if not isinstance(agr, dict):
        return None
    return CommandCenterAgreement(
        agreed_right=_to_int(agr.get("agreed_right")),
        agreed_wrong=_to_int(agr.get("agreed_wrong")),
        cc_overrode_saved=_to_int(agr.get("cc_overrode_saved")),
        cc_overrode_missed=_to_int(agr.get("cc_overrode_missed")),
    )


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("/command-center", response_model=CommandCenterResponse)
def get_command_center(request: Request) -> CommandCenterResponse:
    reports_dir = Path(getattr(request.app.state, "reports_dir", "reports"))
    verdicts = _load_json(_verdicts_path(reports_dir))
    record_raw = _load_json(_record_path(reports_dir))
    # Prefer the bot-side Tony divergence ledger (tony_teaching_log.json): it grades every
    # verdict against the symbol's reviewed pick once resolved, so the "does the 2nd pass
    # help?" matrix populates from real outcomes. Fall back to the CC's record-file tally.
    agreement = build_agreement_from_teaching(_load_json(_teaching_path(reports_dir)))
    if agreement is None:
        agreement = build_agreement(record_raw)
    return CommandCenterResponse(
        picks=build_picks(verdicts),
        record=build_record(record_raw),
        agreement=agreement,
    )
