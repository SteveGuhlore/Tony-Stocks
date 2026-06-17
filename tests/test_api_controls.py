"""Control-endpoint tests: env-fence 403 in dev, idempotency dedup, preconditions 409."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trading_bot.api.main import app
from trading_bot.storage.database import initialize_database
from trading_bot.storage.repositories import ScannerRepository


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    initialize_database(str(db))
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    # Default: dev role (money actions forbidden). No PIN configured.
    monkeypatch.delenv("ENV_ROLE", raising=False)
    monkeypatch.delenv("TRADINGBOT_PROD_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("DASHBOARD_ACTION_PIN", raising=False)
    with TestClient(app) as c:
        yield c, db


# ── env-fence: dev role forbids money actions ────────────────────────────────

def test_stop_watch_forbidden_in_dev(client):
    c, _ = client
    r = c.post("/api/controls/stop-watch", json={})
    assert r.status_code == 403
    assert r.json()["error"] == "money_action_forbidden"


def test_flatten_all_forbidden_in_dev(client):
    c, _ = client
    r = c.post("/api/controls/flatten-all", json={})
    assert r.status_code == 403


def test_pause_paper_forbidden_in_dev(client):
    c, _ = client
    r = c.post("/api/controls/pause-paper", json={})
    assert r.status_code == 403


# ── prod role: money actions allowed (fence satisfied) ───────────────────────

class _PinClient:
    """Wraps TestClient so prod control POSTs carry the configured PIN by default
    (prod now fails closed without one). An explicit pin in the body is preserved."""

    def __init__(self, c, pin):
        self._c = c
        self._pin = pin

    def post(self, url, **kw):
        body = kw.get("json")
        if isinstance(body, dict) and "pin" not in body:
            kw["json"] = {**body, "pin": self._pin}
        return self._c.post(url, **kw)

    def __getattr__(self, name):
        return getattr(self._c, name)


@pytest.fixture()
def prod_client(client, monkeypatch):
    c, db = client
    monkeypatch.setenv("ENV_ROLE", "prod")
    monkeypatch.setenv("TRADINGBOT_PROD_ACCOUNT_ID", "ACCT1")
    monkeypatch.setenv("DASHBOARD_ACTION_PIN", "testpin")  # prod must have a PIN
    # Inject the runtime account id so the fence resolves without a broker.
    import trading_bot.api.routes.controls as controls_mod
    monkeypatch.setattr(controls_mod, "assert_money_action_allowed",
                        lambda runtime_account_id=None: None)
    return _PinClient(c, "testpin"), db


def test_prod_without_pin_fails_closed(client, monkeypatch):
    # Regression (B2): in prod, an unconfigured PIN must reject control actions
    # rather than fail open. trigger-scan is non-money, so this isolates the PIN gate.
    c, _ = client
    monkeypatch.setenv("ENV_ROLE", "prod")
    monkeypatch.delenv("DASHBOARD_ACTION_PIN", raising=False)
    r = c.post("/api/controls/trigger-scan", json={})
    assert r.status_code == 403
    assert r.json()["error"] == "pin_required"


def test_dev_without_pin_still_open(client, monkeypatch):
    # Dev convenience preserved: no ENV_ROLE, no PIN -> PIN gate passes (money fence
    # is the guard in dev). trigger-scan is non-money so it should succeed.
    c, _ = client
    monkeypatch.delenv("ENV_ROLE", raising=False)
    monkeypatch.delenv("DASHBOARD_ACTION_PIN", raising=False)
    r = c.post("/api/controls/trigger-scan", json={})
    assert r.status_code == 200


def test_stop_watch_ok_in_prod_writes_kill_file(prod_client):
    c, db = prod_client
    r = c.post("/api/controls/stop-watch", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert (db.parent / "STOP_WATCH_MODE").exists()


def test_idempotency_dedup(prod_client):
    c, _ = prod_client
    h = {"Idempotency-Key": "abc-123"}
    r1 = c.post("/api/controls/stop-watch", json={}, headers=h)
    assert r1.status_code == 200
    assert r1.json().get("replayed") is not True
    r2 = c.post("/api/controls/stop-watch", json={}, headers=h)
    assert r2.status_code == 200
    assert r2.json().get("replayed") is True
    # exactly one audit row for this action+key
    repo = ScannerRepository(c.app.state.db_path)
    assert repo.find_action_audit(action="stop-watch", idempotency_key="abc-123") is not None
    rows = [a for a in repo.list_action_audit() if a["idempotency_key"] == "abc-123"]
    assert len(rows) == 1


def test_pin_required_when_configured(prod_client, monkeypatch):
    c, _ = prod_client
    monkeypatch.setenv("DASHBOARD_ACTION_PIN", "4242")
    r = c.post("/api/controls/stop-watch", json={"pin": "wrong"})
    assert r.status_code == 403
    assert r.json()["error"] == "pin_required"
    r_ok = c.post("/api/controls/stop-watch", json={"pin": "4242"})
    assert r_ok.status_code == 200


# ── preconditions ─────────────────────────────────────────────────────────────

def test_trigger_scan_409_when_scan_running(client, monkeypatch):
    c, db = client
    repo = ScannerRepository(db)
    repo.create_watch_run(provider="demo", interval_minutes=5, market_hours_only=False)
    # fresh heartbeat -> scan running. trigger-scan is NOT money-adjacent (no fence).
    r = c.post("/api/controls/trigger-scan", json={})
    assert r.status_code == 409
    assert r.json()["error"] == "scan_running"


def test_trigger_scan_ok_when_no_run(client):
    c, db = client
    r = c.post("/api/controls/trigger-scan", json={})
    assert r.status_code == 200
    assert (db.parent / "TRIGGER_SCAN").exists()


def test_flatten_one_409_no_open_position(prod_client):
    c, _ = prod_client
    r = c.post("/api/controls/flatten-one", json={"symbol": "NVDA"})
    assert r.status_code == 409
    assert r.json()["error"] == "no_open_position"


def test_flatten_one_version_mismatch_409(prod_client):
    c, db = prod_client
    repo = ScannerRepository(db)
    repo.open_paper_position(account_label="tony", symbol="NVDA", qty=10, entry_price=120.0,
                             stop=114.0, target=130.0, broker_order_id="o1", snapshot_id=1,
                             opened_at="2026-06-02T14:32:00+00:00")
    r = c.post("/api/controls/flatten-one", json={"symbol": "NVDA", "position_version": "stale"})
    assert r.status_code == 409
    assert r.json()["error"] == "version_mismatch"


def test_flatten_one_ok_with_matching_version(prod_client):
    c, db = prod_client
    repo = ScannerRepository(db)
    repo.open_paper_position(account_label="tony", symbol="NVDA", qty=10, entry_price=120.0,
                             stop=114.0, target=130.0, broker_order_id="o1", snapshot_id=1,
                             opened_at="2026-06-02T14:32:00+00:00")
    rows = repo.list_paper_positions(limit=10)
    pos = next(p for p in rows if p["symbol"] == "NVDA")
    version = f"{pos['id']}:{pos['qty']}:{pos['stop']}:{pos['target']}"
    r = c.post("/api/controls/flatten-one", json={"symbol": "NVDA", "position_version": version})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_re_protect_409_no_open_position(prod_client):
    c, _ = prod_client
    r = c.post("/api/controls/re-protect", json={"symbol": "MU"})
    assert r.status_code == 409


def test_export_bridge_ok_not_money(client):
    # export-bridge is not money-adjacent -> works in dev.
    c, db = client
    r = c.post("/api/controls/export-bridge", json={"slot": "1030"})
    assert r.status_code == 200
    assert r.json()["slot"] == "1030"


def test_ack_alert_marks_acknowledged(client):
    c, db = client
    repo = ScannerRepository(db)
    eid = repo.create_tony_event(event_type="near_entry", severity="info", title="t", message="m")
    r = c.post("/api/controls/ack-alert", json={"event_id": eid})
    assert r.status_code == 200
    df = repo.list_tony_events(limit=10)
    row = df[df["id"] == eid].iloc[0]
    assert int(row["acknowledged"]) == 1
