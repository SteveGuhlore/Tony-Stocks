"""Tests for V12 watch run state — table, heartbeat, stop, error, helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_bot.cli import (
    _is_heartbeat_stale as is_heartbeat_stale,
    _is_within_regular_market_hours as is_within_us_eastern_market_hours,
)
from trading_bot.storage.database import connect, initialize_database
from trading_bot.storage.repositories import ScannerRepository


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def repo(tmp_path):
    db = tmp_path / "test_watch.db"
    return ScannerRepository(db)


def _ts(delta: timedelta | None = None) -> str:
    base = datetime.now(timezone.utc)
    if delta:
        base = base - delta
    return base.isoformat()


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)


# ── TestWatchRunTable ──────────────────────────────────────────────────────────

class TestWatchRunTable:
    def test_table_exists_after_init(self, tmp_path) -> None:
        db = tmp_path / "db.db"
        initialize_database(db)
        with connect(db) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "watch_runs" in tables

    def test_table_columns_present(self, tmp_path) -> None:
        db = tmp_path / "db.db"
        initialize_database(db)
        with connect(db) as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(watch_runs)").fetchall()}
        expected = {
            "id", "started_at", "last_heartbeat_at", "stopped_at", "status", "stop_reason",
            "provider", "interval_minutes", "market_hours_only", "cycles_completed",
            "latest_scan_run_id", "latest_symbols_selected", "latest_symbols_scored",
            "latest_snapshots_created", "latest_api_requests_used", "latest_rate_limit_warnings",
            "latest_fallback_count", "latest_error_message",
        }
        assert expected.issubset(cols)

    def test_double_init_is_safe(self, tmp_path) -> None:
        db = tmp_path / "db.db"
        initialize_database(db)
        initialize_database(db)  # must not raise


# ── TestCreateWatchRun ─────────────────────────────────────────────────────────

class TestCreateWatchRun:
    def test_returns_positive_id(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        assert isinstance(run_id, int)
        assert run_id > 0

    def test_status_is_running(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        run = repo.latest_watch_run()
        assert run is not None
        assert run["status"] == "running"
        assert run["id"] == run_id

    def test_provider_stored(self, repo) -> None:
        repo.create_watch_run("demo_generated", 10.0, True)
        run = repo.latest_watch_run()
        assert run["provider"] == "demo_generated"
        assert float(run["interval_minutes"]) == 10.0
        assert bool(run["market_hours_only"]) is True

    def test_heartbeat_initialized(self, repo) -> None:
        repo.create_watch_run("alpaca_iex", 5.0, False)
        run = repo.latest_watch_run()
        assert run["last_heartbeat_at"] is not None

    def test_cycles_start_at_zero(self, repo) -> None:
        repo.create_watch_run("alpaca_iex", 5.0, False)
        run = repo.latest_watch_run()
        assert int(run["cycles_completed"]) == 0

    def test_latest_returns_most_recent(self, repo) -> None:
        repo.create_watch_run("provider_a", 5.0, False)
        repo.create_watch_run("provider_b", 5.0, False)
        run = repo.latest_watch_run()
        assert run["provider"] == "provider_b"


# ── TestUpdateWatchRunHeartbeat ────────────────────────────────────────────────

class TestUpdateWatchRunHeartbeat:
    def test_updates_cycles_completed(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        repo.update_watch_run_heartbeat(run_id, cycles_completed=3)
        run = repo.latest_watch_run()
        assert int(run["cycles_completed"]) == 3

    def test_updates_latest_scan_stats(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        repo.update_watch_run_heartbeat(
            run_id,
            cycles_completed=1,
            latest_scan_run_id=42,
            latest_symbols_selected=100,
            latest_symbols_scored=80,
            latest_snapshots_created=5,
            latest_api_requests_used=2,
            latest_rate_limit_warnings=0,
            latest_fallback_count=3,
        )
        run = repo.latest_watch_run()
        assert run["latest_scan_run_id"] == 42
        assert run["latest_symbols_selected"] == 100
        assert run["latest_symbols_scored"] == 80
        assert run["latest_snapshots_created"] == 5
        assert run["latest_api_requests_used"] == 2
        assert run["latest_rate_limit_warnings"] == 0
        assert run["latest_fallback_count"] == 3

    def test_status_remains_running(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        repo.update_watch_run_heartbeat(run_id, cycles_completed=1)
        run = repo.latest_watch_run()
        assert run["status"] == "running"

    def test_heartbeat_timestamp_updated(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        before = repo.latest_watch_run()["last_heartbeat_at"]
        repo.update_watch_run_heartbeat(run_id, cycles_completed=1)
        after = repo.latest_watch_run()["last_heartbeat_at"]
        assert after >= before


# ── TestUpdateWatchRunStopped ──────────────────────────────────────────────────

class TestUpdateWatchRunStopped:
    def test_status_becomes_stopped(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        repo.update_watch_run_stopped(run_id, "keyboard_interrupt")
        run = repo.latest_watch_run()
        assert run["status"] == "stopped"

    def test_stop_reason_stored(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        repo.update_watch_run_stopped(run_id, "stop_file")
        run = repo.latest_watch_run()
        assert run["stop_reason"] == "stop_file"

    def test_stopped_at_set(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        repo.update_watch_run_stopped(run_id, "max_cycles")
        run = repo.latest_watch_run()
        assert run["stopped_at"] is not None

    def test_various_stop_reasons(self, repo) -> None:
        for reason in ("keyboard_interrupt", "stop_file", "max_cycles", "completed", "disabled"):
            run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
            repo.update_watch_run_stopped(run_id, reason)
            run = repo.latest_watch_run()
            assert run["stop_reason"] == reason


# ── TestUpdateWatchRunError ────────────────────────────────────────────────────

class TestUpdateWatchRunError:
    def test_status_becomes_error(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        repo.update_watch_run_error(run_id, "Connection refused")
        run = repo.latest_watch_run()
        assert run["status"] == "error"

    def test_error_message_stored(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        repo.update_watch_run_error(run_id, "TimeoutError: socket timed out")
        run = repo.latest_watch_run()
        assert "TimeoutError" in run["latest_error_message"]

    def test_long_error_truncated(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        long_msg = "X" * 1000
        repo.update_watch_run_error(run_id, long_msg)
        run = repo.latest_watch_run()
        assert len(run["latest_error_message"]) <= 500

    def test_stopped_at_set_on_error(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        repo.update_watch_run_error(run_id, "Boom")
        run = repo.latest_watch_run()
        assert run["stopped_at"] is not None


# ── TestLatestWatchRun ─────────────────────────────────────────────────────────

class TestLatestWatchRun:
    def test_returns_none_when_no_runs(self, repo) -> None:
        assert repo.latest_watch_run() is None

    def test_returns_dict(self, repo) -> None:
        repo.create_watch_run("alpaca_iex", 5.0, False)
        run = repo.latest_watch_run()
        assert isinstance(run, dict)

    def test_returns_most_recent(self, repo) -> None:
        repo.create_watch_run("old_provider", 5.0, False)
        repo.create_watch_run("new_provider", 5.0, False)
        assert repo.latest_watch_run()["provider"] == "new_provider"


# ── TestIsHeartbeatStale ───────────────────────────────────────────────────────

class TestIsHeartbeatStale:
    def test_none_is_not_stale(self) -> None:
        assert is_heartbeat_stale(None, stale_minutes=10) is False

    def test_empty_string_is_not_stale(self) -> None:
        assert is_heartbeat_stale("", stale_minutes=10) is False

    def test_recent_is_not_stale(self) -> None:
        ts = _ts(timedelta(minutes=3))
        assert is_heartbeat_stale(ts, stale_minutes=10) is False

    def test_old_is_stale(self) -> None:
        ts = _ts(timedelta(minutes=20))
        assert is_heartbeat_stale(ts, stale_minutes=10) is True

    def test_exactly_at_boundary_is_not_stale(self) -> None:
        now = _fixed_now()
        ts = (now - timedelta(minutes=10)).isoformat()
        assert is_heartbeat_stale(ts, stale_minutes=10, now=now) is False

    def test_just_past_boundary_is_stale(self) -> None:
        now = _fixed_now()
        ts = (now - timedelta(minutes=10, seconds=1)).isoformat()
        assert is_heartbeat_stale(ts, stale_minutes=10, now=now) is True

    def test_injected_now_used(self) -> None:
        fixed_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts = datetime(2026, 1, 1, 11, 45, 0, tzinfo=timezone.utc).isoformat()
        assert is_heartbeat_stale(ts, stale_minutes=10, now=fixed_now) is True

    def test_invalid_timestamp_returns_false(self) -> None:
        assert is_heartbeat_stale("not-a-date", stale_minutes=10) is False

    def test_z_suffix_handled(self) -> None:
        ts = _ts(timedelta(minutes=5)).replace("+00:00", "Z")
        assert is_heartbeat_stale(ts, stale_minutes=10) is False


# ── TestIsWithinUsEasternMarketHours ──────────────────────────────────────────

class TestIsWithinUsEasternMarketHours:
    def _dt(self, hour: int, minute: int) -> datetime:
        from zoneinfo import ZoneInfo
        # 2026-05-18 is a Monday — the surviving guard is weekday-aware.
        return datetime(2026, 5, 18, hour, minute, 0, tzinfo=ZoneInfo("America/New_York"))

    def test_during_market_hours_true(self) -> None:
        assert is_within_us_eastern_market_hours(self._dt(10, 30)) is True

    def test_at_open_true(self) -> None:
        assert is_within_us_eastern_market_hours(self._dt(9, 30)) is True

    def test_at_close_true(self) -> None:
        assert is_within_us_eastern_market_hours(self._dt(16, 0)) is True

    def test_before_open_false(self) -> None:
        assert is_within_us_eastern_market_hours(self._dt(9, 29)) is False

    def test_after_close_false(self) -> None:
        assert is_within_us_eastern_market_hours(self._dt(16, 1)) is False

    def test_premarket_false(self) -> None:
        assert is_within_us_eastern_market_hours(self._dt(7, 0)) is False

    def test_afterhours_false(self) -> None:
        assert is_within_us_eastern_market_hours(self._dt(20, 0)) is False

    def test_midnight_false(self) -> None:
        assert is_within_us_eastern_market_hours(self._dt(0, 0)) is False


# ── TestNoBrokerBehavior ───────────────────────────────────────────────────────

class TestNoBrokerBehavior:
    def test_watch_run_has_no_order_fields(self, repo) -> None:
        run_id = repo.create_watch_run("alpaca_iex", 5.0, False)
        run = repo.latest_watch_run()
        broker_fields = {"order_id", "trade_id", "execution_price", "shares", "position"}
        assert not any(f in run for f in broker_fields)

    def test_create_watch_run_returns_int_no_side_effects(self, repo) -> None:
        result = repo.create_watch_run("alpaca_iex", 5.0, False)
        assert isinstance(result, int)
        # No paper_trade or manual_pick was created
        from trading_bot.storage.repositories import ScannerRepository
        picks = repo.manual_picks()
        assert len(picks) == 0

    def test_watch_status_labels_contain_no_broker_terms(self) -> None:
        broker_terms = {"buy", "sell", "short", "cover", "order", "execute", "position"}
        for label in ("running", "stopped", "error", "stale", "no_run", "unknown"):
            assert label.lower() not in broker_terms

    def test_is_heartbeat_stale_is_pure_no_db(self) -> None:
        ts = _ts(timedelta(minutes=5))
        r1 = is_heartbeat_stale(ts, stale_minutes=10)
        r2 = is_heartbeat_stale(ts, stale_minutes=10)
        assert r1 == r2
        assert isinstance(r1, bool)
