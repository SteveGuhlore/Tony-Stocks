"""Safety guard: run_off_hours_prep and run_off_hours_watch must NEVER reference
execution tokens (run_paper_cycle, paper_engine, submit_bracket, broker).

Also verifies that run_off_hours_watch short-circuits (performs no prep) when
the phase is MARKET_HOURS.
"""
from __future__ import annotations

import inspect
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch
from zoneinfo import ZoneInfo

import pytest

import trading_bot.cli


# ---------------------------------------------------------------------------
# Source-inspection guard
# ---------------------------------------------------------------------------

FORBIDDEN_TOKENS = [
    "run_paper_cycle",
    "paper_engine",
    "submit_bracket",
    "broker",
]


def _get_source(fn_name: str) -> str:
    fn = getattr(trading_bot.cli, fn_name)
    return inspect.getsource(fn)


class TestNoExecutionTokens:
    def test_run_off_hours_prep_no_paper_cycle(self):
        src = _get_source("run_off_hours_prep")
        assert "run_paper_cycle" not in src, (
            "run_off_hours_prep must NEVER reference run_paper_cycle"
        )

    def test_run_off_hours_prep_no_paper_engine(self):
        src = _get_source("run_off_hours_prep")
        assert "paper_engine" not in src, (
            "run_off_hours_prep must NEVER reference paper_engine"
        )

    def test_run_off_hours_prep_no_submit_bracket(self):
        src = _get_source("run_off_hours_prep")
        assert "submit_bracket" not in src, (
            "run_off_hours_prep must NEVER reference submit_bracket"
        )

    def test_run_off_hours_prep_no_broker(self):
        src = _get_source("run_off_hours_prep")
        assert "broker" not in src, (
            "run_off_hours_prep must NEVER reference broker"
        )

    def test_run_off_hours_watch_no_paper_cycle(self):
        src = _get_source("run_off_hours_watch")
        assert "run_paper_cycle" not in src, (
            "run_off_hours_watch must NEVER reference run_paper_cycle"
        )

    def test_run_off_hours_watch_no_paper_engine(self):
        src = _get_source("run_off_hours_watch")
        assert "paper_engine" not in src, (
            "run_off_hours_watch must NEVER reference paper_engine"
        )

    def test_run_off_hours_watch_no_submit_bracket(self):
        src = _get_source("run_off_hours_watch")
        assert "submit_bracket" not in src, (
            "run_off_hours_watch must NEVER reference submit_bracket"
        )

    def test_run_off_hours_watch_no_broker(self):
        src = _get_source("run_off_hours_watch")
        assert "broker" not in src, (
            "run_off_hours_watch must NEVER reference broker"
        )


# ---------------------------------------------------------------------------
# Watch loop: MARKET_HOURS tick performs no prep
# ---------------------------------------------------------------------------

def _make_sandbox_config_watch(tmp_path: Path) -> Path:
    db = tmp_path / "scan.db"
    cfg = tmp_path / "sandbox.yaml"
    cfg.write_text(
        f"database_path: {db.as_posix()}\n"
        "off_hours:\n"
        "  enabled: true\n"
        "  cadence_minutes: 0\n"
        "  earnings_blackout_days: 5\n"
        "  shortlist_size: 5\n"
        "  full_universe_scan: false\n"
        '  premarket_provider: "null"\n'
        "  enrich_budget: 0\n",
        encoding="utf-8",
    )
    return cfg


class TestOffHoursWatchMarketHoursShortCircuit:
    def test_market_hours_tick_does_not_call_prep(self, tmp_path):
        """When phase is MARKET_HOURS, the watch loop must NOT call run_off_hours_prep."""
        cfg = _make_sandbox_config_watch(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            max_cycles=1,
            cadence_minutes=None,
        )

        # Freeze clock at MARKET_HOURS (10:00 ET on a weekday — June 9 is Tuesday)
        market_hours_et = datetime(2026, 6, 9, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        prep_calls = []

        def fake_prep(prep_args):
            prep_calls.append(prep_args)
            return {"phase": "market_hours", "et_date": "2026-06-06",
                    "sinks_written": [], "errors": [], "shortlist_size": 5}

        with patch("trading_bot.cli._now_et", return_value=market_hours_et):
            with patch("trading_bot.cli.run_off_hours_prep", side_effect=fake_prep):
                trading_bot.cli.run_off_hours_watch(args)

        assert len(prep_calls) == 0, (
            f"run_off_hours_prep must NOT be called during MARKET_HOURS; "
            f"it was called {len(prep_calls)} time(s)"
        )

    def test_off_hours_tick_calls_prep(self, tmp_path):
        """When phase is PRE_OPEN, the watch loop SHOULD call run_off_hours_prep."""
        cfg = _make_sandbox_config_watch(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            max_cycles=1,
            cadence_minutes=0,
        )

        # Freeze clock at PRE_OPEN (07:00 ET on a weekday — June 9 is Tuesday)
        pre_open_et = datetime(2026, 6, 9, 7, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        prep_calls = []

        def fake_prep(prep_args):
            prep_calls.append(prep_args)
            return {"phase": "pre_open", "et_date": "2026-06-06",
                    "sinks_written": [], "errors": [], "shortlist_size": 5}

        # Also patch _off_hours_idempotency_key_seen to return False (not yet run)
        with patch("trading_bot.cli._now_et", return_value=pre_open_et):
            with patch("trading_bot.cli.run_off_hours_prep", side_effect=fake_prep):
                with patch("trading_bot.cli._off_hours_prep_already_run", return_value=False):
                    with patch("trading_bot.cli._mark_off_hours_prep_run"):
                        trading_bot.cli.run_off_hours_watch(args)

        assert len(prep_calls) == 1, (
            f"run_off_hours_prep should be called once during PRE_OPEN; "
            f"called {len(prep_calls)} time(s)"
        )

    def test_watch_exits_via_max_cycles(self, tmp_path):
        """run_off_hours_watch exits cleanly after max_cycles iterations."""
        cfg = _make_sandbox_config_watch(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            max_cycles=2,
            cadence_minutes=0,
        )

        # June 9, 2026 is Tuesday — 10:00 ET = MARKET_HOURS (no prep runs)
        market_hours_et = datetime(2026, 6, 9, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        # Should return (exit 0) without raising
        with patch("trading_bot.cli._now_et", return_value=market_hours_et):
            result = trading_bot.cli.run_off_hours_watch(args)

        # Ran exactly max_cycles market-hours ticks, then stopped for that reason.
        assert result["cycles_completed"] == 2
        assert result["stopped_by"] == "max_cycles"

    def test_watch_stop_file_halts_loop(self, tmp_path):
        """run_off_hours_watch respects a STOP file and exits cleanly."""
        cfg = _make_sandbox_config_watch(tmp_path)
        stop_file = tmp_path / "STOP_OFF_HOURS"
        stop_file.touch()

        args = SimpleNamespace(
            config=str(cfg),
            max_cycles=None,   # unlimited — but stop file present
            cadence_minutes=0,
        )

        market_hours_et = datetime(2026, 6, 9, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("trading_bot.cli._now_et", return_value=market_hours_et):
            with patch("trading_bot.cli._OFF_HOURS_STOP_FILE", stop_file):
                # Should complete quickly (stop file present on first check)
                result = trading_bot.cli.run_off_hours_watch(args)

        # Stop file present before the first cycle → zero cycles, stopped by stop_file.
        assert result["cycles_completed"] == 0
        assert result["stopped_by"] == "stop_file"

    def test_idempotency_prevents_double_prep(self, tmp_path):
        """The watch loop does NOT run prep twice for the same <date>:<phase> key."""
        cfg = _make_sandbox_config_watch(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            max_cycles=2,
            cadence_minutes=0,
        )

        # June 9, 2026 is Tuesday — 07:00 ET = PRE_OPEN
        pre_open_et = datetime(2026, 6, 9, 7, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        prep_calls = []

        def fake_prep(prep_args):
            prep_calls.append(prep_args)
            return {"phase": "pre_open", "et_date": "2026-06-06",
                    "sinks_written": [], "errors": [], "shortlist_size": 5}

        # First call: not yet run; second call: already run
        already_run_sequence = [False, True]
        call_count = [0]

        def fake_already_run(*_a, **_kw):
            idx = min(call_count[0], len(already_run_sequence) - 1)
            call_count[0] += 1
            return already_run_sequence[idx]

        with patch("trading_bot.cli._now_et", return_value=pre_open_et):
            with patch("trading_bot.cli.run_off_hours_prep", side_effect=fake_prep):
                with patch("trading_bot.cli._off_hours_prep_already_run", side_effect=fake_already_run):
                    with patch("trading_bot.cli._mark_off_hours_prep_run"):
                        trading_bot.cli.run_off_hours_watch(args)

        # Prep should only be called once (second cycle sees it already run)
        assert len(prep_calls) == 1, (
            f"Idempotency guard: prep must run exactly once per <date>:<phase>; "
            f"called {len(prep_calls)} time(s)"
        )
