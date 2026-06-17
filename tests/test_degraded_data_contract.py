"""Prod-shaped DEGRADED-DATA contract harness for the trading-bot FastAPI.

Codex review #12: "the prod breakages this operator keeps hitting are empty CC
files, stale watch runs, 503 prices, env drift — recorded-real-fixture E2E
against a VM-shaped API." The operator is at work during market hours and CANNOT
fix anything, so this harness proves the API NEVER 500s on degraded / empty /
malformed real-world inputs.

We drive the *real* app (`trading_bot.api.main:app`) through `TestClient`, which
runs the lifespan that wires `app.state.db_path / vault_dir / reports_dir /
price_cache` from env vars (the established pattern in `test_api_smoke.py` and
`test_api_command_center.py`). Each scenario sets up a degraded world and asserts
every read endpoint returns a NON-500 (200, or a documented 503 for the
keyless price endpoints) with a schema-valid body.

Scenarios (per the review):
  1. Empty database (fresh temp DB, no scans/snapshots) -> empty lists, no crash.
  2. Missing reports dir entirely (CC files absent) -> CC/cockpit degrade.
  3. Malformed JSON in the CC files (garbage bytes) -> degrade to empty, no 500.
  4. Unknown CC verdict value ("pass", "frobnicate") -> passed through verbatim.
  5. No Alpaca keys -> /prices 503 OK; cockpit/paper still 200, price unavailable.
  6. Stale/old watch-run heartbeat -> system/today report it, no crash.

STRICT SCOPE: this file + tests/fixtures/prod_shaped/ are the only new artifacts;
no src/ route is edited here. A genuine 500 on degraded data is recorded as an
xfail with a precise reason and surfaced in the final report as a market-hours bug.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trading_bot.api.main import app
from trading_bot.storage.database import initialize_database

FIXTURES = Path(__file__).parent / "fixtures" / "prod_shaped"

# ── The full read surface under test ─────────────────────────────────────────
# (path, expected non-500 status codes). Symbol routes use a symbol with no data.
READ_ENDPOINTS: list[tuple[str, set[int]]] = [
    ("/api/health", {200}),
    ("/api/today", {200}),
    ("/api/picks", {200}),
    ("/api/tracking", {200}),
    ("/api/outcomes", {200}),
    ("/api/scan/latest", {200}),
    ("/api/scan/overview", {200}),
    ("/api/analytics/backtest", {200}),
    ("/api/system/health", {200}),
    ("/api/symbols/NVDA/detail", {200}),
    ("/api/symbols/NVDA/chart", {200}),
    ("/api/vault/bridge", {200}),
    ("/api/command-center", {200}),
    ("/api/morning-prep", {200}),
    ("/api/cockpit", {200}),
    ("/api/paper/positions", {200}),
    ("/api/paper/equity-curve", {200}),
]

# Price endpoints with NO Alpaca keys: 503 is the documented degraded contract.
PRICE_ENDPOINTS_NO_KEYS: list[tuple[str, set[int]]] = [
    ("/api/prices", {503}),
    ("/api/prices/NVDA", {503}),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_world(tmp_path: Path, *, with_reports: bool = True, with_db: bool = True):
    """Build a degraded VM-shaped world: temp db + (optional) reports/vault dirs."""
    db = tmp_path / "trading_bot.db"
    if with_db:
        initialize_database(str(db))
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    reports = tmp_path / "reports"
    if with_reports:
        reports.mkdir(exist_ok=True)
    return db, vault, reports


def _wire_env(monkeypatch, db: Path, vault: Path, reports: Path, *, keys: bool = False):
    """Wire app.state via env (lifespan reads these). No Alpaca keys by default."""
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("VAULT_DIR", str(vault))
    monkeypatch.setenv("REPORTS_DIR", str(reports))
    # Don't let a developer's real overrides leak in.
    monkeypatch.delenv("TONY_VERDICTS_FILE", raising=False)
    monkeypatch.delenv("TONY_RECORD_FILE", raising=False)
    monkeypatch.delenv("TONY_TEACHING_FILE", raising=False)
    if keys:
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    else:
        # The app's lifespan reloads .env via load_dotenv_if_present, which uses
        # os.environ.setdefault — so deleting these would let the developer's real
        # .env keys re-populate and the "no keys" scenario would silently pass with
        # live data. Setting them to EMPTY (present-but-falsy) is honored by
        # setdefault and makes prices._has_keys() correctly report no keys.
        monkeypatch.setenv("ALPACA_API_KEY", "")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "")


def _assert_non_500(client: TestClient, path: str, ok: set[int]) -> dict | list:
    """Hit an endpoint; fail loudly if it 500s. Returns the parsed JSON body."""
    r = client.get(path)
    assert r.status_code != 500, (
        f"DEGRADED-DATA 500 (market-hours risk): GET {path} -> 500\n{r.text[:600]}"
    )
    assert r.status_code in ok, (
        f"GET {path} -> {r.status_code}, expected one of {sorted(ok)}\n{r.text[:300]}"
    )
    # Body must be valid JSON (no NaN/inf leaking out, etc.).
    return r.json()


def _insert_stale_watch_run(db: Path) -> None:
    """Insert a watch_runs row whose heartbeat is ~3 days old (a stale/dead run)."""
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """
            INSERT INTO watch_runs (started_at, last_heartbeat_at, status, provider,
                                    interval_minutes, market_hours_only, cycles_completed,
                                    latest_symbols_scored, latest_api_requests_used)
            VALUES (?, ?, 'running', 'alpaca', 5, 1, 17, 950, 4200)
            """,
            ("2026-06-04T13:30:00Z", "2026-06-04T13:30:05Z"),
        )
        conn.commit()


# ── Scenario 1: empty database ───────────────────────────────────────────────

def test_empty_database_no_endpoint_500s(tmp_path, monkeypatch):
    """Fresh temp DB, empty reports dir, no keys: every read endpoint is non-500."""
    db, vault, reports = _make_world(tmp_path)
    _wire_env(monkeypatch, db, vault, reports)
    with TestClient(app) as c:
        for path, ok in READ_ENDPOINTS:
            _assert_non_500(c, path, ok)


def test_empty_database_returns_empty_collections(tmp_path, monkeypatch):
    db, vault, reports = _make_world(tmp_path)
    _wire_env(monkeypatch, db, vault, reports)
    with TestClient(app) as c:
        assert c.get("/api/scan/latest").json()["results"] == []
        assert c.get("/api/picks").json()["picks"] == []
        tracking = c.get("/api/tracking").json()
        assert tracking["active"] == [] and tracking["watching"] == []
        assert c.get("/api/cockpit").json()["rows"] == []
        assert c.get("/api/paper/positions").json()["open"] == []
        cc = c.get("/api/command-center").json()
        assert cc["picks"] == {} and cc["record"] is None and cc["agreement"] is None


# ── Scenario 2: missing reports dir entirely (CC files absent) ───────────────

def test_missing_reports_dir_cc_and_cockpit_degrade(tmp_path, monkeypatch):
    """No reports/ dir at all -> CC and cockpit degrade to empty/awaiting, no 500."""
    db, vault, reports = _make_world(tmp_path, with_reports=False)
    assert not reports.exists()
    _wire_env(monkeypatch, db, vault, reports)
    with TestClient(app) as c:
        for path, ok in READ_ENDPOINTS:
            _assert_non_500(c, path, ok)
        cc = c.get("/api/command-center").json()
        assert cc["picks"] == {} and cc["record"] is None and cc["agreement"] is None
        mp = c.get("/api/morning-prep").json()
        assert mp["shortlist"] == []
        # cockpit still assembles (from snapshots, which are also empty here)
        assert c.get("/api/cockpit").json()["rows"] == []


# ── Scenario 3: malformed JSON in the CC producer files ──────────────────────

def test_malformed_cc_json_degrades_no_500(tmp_path, monkeypatch):
    """Garbage bytes in tony_stocks_verdicts.json / _record.json -> empty, no crash."""
    db, vault, reports = _make_world(tmp_path)
    (reports / "tony_stocks_verdicts.json").write_text("{ this is not json", encoding="utf-8")
    (reports / "tony_stocks_record.json").write_text("[1, 2, ", encoding="utf-8")
    (reports / "tony_teaching_log.json").write_text("\x00\xff garbage", encoding="utf-8")
    _wire_env(monkeypatch, db, vault, reports)
    with TestClient(app) as c:
        for path, ok in READ_ENDPOINTS:
            _assert_non_500(c, path, ok)
        cc = c.get("/api/command-center").json()
        assert cc["picks"] == {} and cc["record"] is None and cc["agreement"] is None
        # cockpit reads the same (malformed) verdicts file -> no tony overlay, no 500
        assert c.get("/api/cockpit").json()["rows"] == []


def test_malformed_morning_prep_degrades_no_500(tmp_path, monkeypatch):
    """Corrupt + empty morning-prep report files -> empty MorningPrepResponse, no 500."""
    db, vault, reports = _make_world(tmp_path)
    mp_dir = reports / "morning_prep"
    mp_dir.mkdir()
    (mp_dir / "2026-06-05.json").write_text("", encoding="utf-8")           # empty
    (mp_dir / "2026-06-06.json").write_text("{ broken json :::", encoding="utf-8")  # latest, corrupt
    _wire_env(monkeypatch, db, vault, reports)
    with TestClient(app) as c:
        body = _assert_non_500(c, "/api/morning-prep", {200})
        assert body["shortlist"] == []
        assert body["phase"] == ""


# ── Scenario 4: unknown CC verdict values pass through verbatim ──────────────

def test_unknown_verdict_passthrough_no_500(tmp_path, monkeypatch):
    """Verdicts like 'pass' / 'frobnicate' (outside the dashboard enum) survive
    verbatim through /command-center and /cockpit, never crashing."""
    db, vault, reports = _make_world(tmp_path)
    verdicts = json.loads((FIXTURES / "tony_stocks_verdicts_unknown_verdict.json").read_text())
    (reports / "tony_stocks_verdicts.json").write_text(json.dumps(verdicts), encoding="utf-8")
    _wire_env(monkeypatch, db, vault, reports)
    with TestClient(app) as c:
        cc = _assert_non_500(c, "/api/command-center", {200})
        picks = cc["picks"]
        assert set(picks) == {"AAPL", "NVDA", "TSLA"}  # 'nvda' uppercased
        assert picks["AAPL"]["verdict"] == "pass"          # unknown, verbatim
        assert picks["NVDA"]["verdict"] == "frobnicate"    # unknown, verbatim
        assert picks["TSLA"]["verdict"] == "reaffirm"
        # cockpit consumes the same picks without an enum guard crash
        _assert_non_500(c, "/api/cockpit", {200})


# ── Scenario 5: no Alpaca keys (503 prices, cockpit/paper still 200) ─────────

def test_no_keys_prices_503_but_aggregates_200(tmp_path, monkeypatch):
    """Without keys: /prices and /prices/{sym} are 503 (documented), but the
    price-consuming aggregates (cockpit, paper) still return 200 with prices
    marked unavailable / unrealized P/L absent."""
    db, vault, reports = _make_world(tmp_path)
    _wire_env(monkeypatch, db, vault, reports, keys=False)
    with TestClient(app) as c:
        for path, ok in PRICE_ENDPOINTS_NO_KEYS:
            _assert_non_500(c, path, ok)
        # cockpit must still serve; with no snapshots there are no rows, but the
        # contract (price_status default 'unavailable') is exercised in unit tests.
        cockpit = _assert_non_500(c, "/api/cockpit", {200})
        assert "rows" in cockpit
        paper = _assert_non_500(c, "/api/paper/positions", {200})
        assert paper["open"] == []
        _assert_non_500(c, "/api/paper/equity-curve", {200})


def test_no_keys_full_surface_non_500(tmp_path, monkeypatch):
    """Belt-and-suspenders: the whole read surface is non-500 with no keys."""
    db, vault, reports = _make_world(tmp_path)
    _wire_env(monkeypatch, db, vault, reports, keys=False)
    with TestClient(app) as c:
        for path, ok in READ_ENDPOINTS:
            _assert_non_500(c, path, ok)


def test_keys_present_but_empty_cache_non_500(tmp_path, monkeypatch):
    """Env drift: keys ARE configured but the PriceCache hasn't polled yet (market
    closed / cold start). /prices is then 200 with an empty symbol list, and the
    aggregates that mark-to-live must not 500 against an empty cache."""
    db, vault, reports = _make_world(tmp_path)
    _wire_env(monkeypatch, db, vault, reports, keys=True)
    with TestClient(app) as c:
        prices = _assert_non_500(c, "/api/prices", {200})
        assert prices["symbols"] == []          # configured but not yet polled
        # 404 (not 500) for a symbol absent from a freshly-started cache.
        _assert_non_500(c, "/api/prices/NVDA", {404})
        for path, ok in READ_ENDPOINTS:
            _assert_non_500(c, path, ok)


# ── Scenario 6: stale / old watch-run heartbeat ──────────────────────────────

def test_stale_watch_run_reported_no_500(tmp_path, monkeypatch):
    """A watch_runs row with a 3-day-old heartbeat must NOT crash /system/health
    or /today; the stale heartbeat is reported through for the UI to flag."""
    db, vault, reports = _make_world(tmp_path)
    _insert_stale_watch_run(db)
    _wire_env(monkeypatch, db, vault, reports)
    with TestClient(app) as c:
        for path, ok in READ_ENDPOINTS:
            _assert_non_500(c, path, ok)
        sysh = c.get("/api/system/health").json()
        assert sysh["watch"]["status"] == "running"
        assert sysh["watch"]["last_heartbeat_at"] == "2026-06-04T13:30:05Z"
        assert sysh["watch"]["cycles_completed"] == 17
        today = c.get("/api/today").json()
        assert today["watch"]["last_heartbeat_at"] == "2026-06-04T13:30:05Z"


# ── Combined worst-case: everything degraded at once ─────────────────────────

def test_everything_degraded_at_once_no_500(tmp_path, monkeypatch):
    """Empty DB except a stale watch row, malformed CC files, missing morning-prep,
    no keys — the simultaneous-failure case closest to a real bad morning."""
    db, vault, reports = _make_world(tmp_path)
    _insert_stale_watch_run(db)
    (reports / "tony_stocks_verdicts.json").write_text("not json at all", encoding="utf-8")
    (reports / "tony_stocks_record.json").write_text("}{", encoding="utf-8")
    _wire_env(monkeypatch, db, vault, reports, keys=False)
    with TestClient(app) as c:
        for path, ok in READ_ENDPOINTS + PRICE_ENDPOINTS_NO_KEYS:
            _assert_non_500(c, path, ok)
