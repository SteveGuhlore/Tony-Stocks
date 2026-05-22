"""Tests for the lightweight pre-screener funnel (data/pre_screener.py).

Covers:
- Symbols below min_price are excluded
- Symbols above max_price are excluded
- Symbols below min_avg_volume are excluded
- Symbols with no recent cache data pass through (no hard-fail)
- When filtered pool < min_symbols_after_filter, fall back to full list
- enabled: false (via load_pre_screener_config) returns defaults
- build_recent_symbol_metrics: picks newest row per symbol, respects cutoff
- Repository.get_recent_scan_result_metrics: integration with real in-memory SQLite
- Pre-screener does not mutate the original symbol list
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_bot.data.pre_screener import (
    PreScreenResult,
    build_recent_symbol_metrics,
    load_pre_screener_config,
    pre_screen_universe,
)
from trading_bot.storage.database import initialize_database
from trading_bot.storage.repositories import ScannerRepository


# ── helpers ───────────────────────────────────────────────────────────────────

def _ts(delta_days: float = 0.0) -> str:
    """Return a UTC ISO timestamp offset by delta_days from now."""
    t = datetime.now(timezone.utc) - timedelta(days=delta_days)
    return t.isoformat()


def _make_metrics(**kwargs: float) -> dict[str, float]:
    """Shorthand: pass latest_close and avg_volume_20 as keyword args."""
    return dict(kwargs)


def _make_scan_result_row(
    symbol: str,
    latest_close: float | None,
    avg_volume_20: float | None,
    age_days: float = 0.0,
) -> dict:
    return {
        "symbol": symbol,
        "latest_close": latest_close,
        "avg_volume_20": avg_volume_20,
        "created_at": _ts(age_days),
    }


# ── TestPreScreenUniverse ─────────────────────────────────────────────────────

class TestPreScreenUniverse:
    """Unit tests for pre_screen_universe()."""

    _SYMBOLS = ["AAPL", "MSFT", "NVDA", "TSLA", "LOW_VOL"]
    _MIN_PRICE = 5.0
    _MAX_PRICE = 500.0
    _MIN_AVG_VOL = 300_000.0

    def _base_metrics(self) -> dict[str, dict]:
        return {
            "AAPL": _make_metrics(latest_close=190.0, avg_volume_20=55_000_000),
            "MSFT": _make_metrics(latest_close=410.0, avg_volume_20=20_000_000),
            "NVDA": _make_metrics(latest_close=880.0, avg_volume_20=40_000_000),
            "TSLA": _make_metrics(latest_close=170.0, avg_volume_20=90_000_000),
            "LOW_VOL": _make_metrics(latest_close=50.0, avg_volume_20=10_000),
        }

    def test_passes_symbols_within_bounds(self):
        metrics = {
            "AAPL": _make_metrics(latest_close=190.0, avg_volume_20=55_000_000),
        }
        result = pre_screen_universe(
            ["AAPL"],
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        assert "AAPL" in result.symbols
        assert result.screened_out_count == 0
        assert not result.fallback_used

    def test_excludes_symbol_below_min_price(self):
        # Use a large enough universe so fallback threshold isn't triggered.
        # 10 bad-price symbols: screened_out=10, filtered=0, fallback triggers at < 1.
        symbols = [f"PENNY{i}" for i in range(10)]
        metrics = {s: _make_metrics(latest_close=2.50, avg_volume_20=5_000_000) for s in symbols}
        result = pre_screen_universe(
            symbols,
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=0,  # disable fallback for this unit test
        )
        for s in symbols:
            assert s not in result.symbols
        assert result.screened_out_count == 10
        assert result.reasons["price_below_min"] == 10

    def test_excludes_symbol_above_max_price(self):
        symbols = [f"BIGPRICE{i}" for i in range(5)]
        metrics = {s: _make_metrics(latest_close=600.0, avg_volume_20=5_000_000) for s in symbols}
        result = pre_screen_universe(
            symbols,
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=0,
        )
        for s in symbols:
            assert s not in result.symbols
        assert result.screened_out_count == 5
        assert result.reasons["price_above_max"] == 5

    def test_excludes_symbol_below_min_avg_volume(self):
        symbols = [f"LOVOL{i}" for i in range(5)]
        metrics = {s: _make_metrics(latest_close=50.0, avg_volume_20=10_000) for s in symbols}
        result = pre_screen_universe(
            symbols,
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=0,
        )
        for s in symbols:
            assert s not in result.symbols
        assert result.screened_out_count == 5
        assert result.reasons["avg_volume_below_minimum"] == 5

    def test_symbol_at_exactly_min_price_passes(self):
        metrics = {"EXACT": _make_metrics(latest_close=5.0, avg_volume_20=5_000_000)}
        result = pre_screen_universe(
            ["EXACT"],
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        assert "EXACT" in result.symbols

    def test_symbol_at_exactly_max_price_passes(self):
        metrics = {"EXACT": _make_metrics(latest_close=500.0, avg_volume_20=5_000_000)}
        result = pre_screen_universe(
            ["EXACT"],
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        assert "EXACT" in result.symbols

    def test_no_cache_data_passes_through(self):
        """Symbols with no cached data must pass through — no hard-fail."""
        result = pre_screen_universe(
            ["NEWCO"],
            recent_metrics={},
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        assert "NEWCO" in result.symbols
        assert result.no_cache_data_count == 1
        assert result.screened_out_count == 0

    def test_partial_cache_data_close_only_passes_volume_check_skipped(self):
        """If only latest_close is known but avg_volume is missing, volume check is skipped."""
        metrics = {"HALFDATA": {"latest_close": 100.0}}  # no avg_volume_20
        result = pre_screen_universe(
            ["HALFDATA"],
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        # price is OK, volume unknown → passes
        assert "HALFDATA" in result.symbols

    def test_partial_cache_data_volume_only_passes_price_check_skipped(self):
        """If only avg_volume is known but close is missing, price check is skipped."""
        metrics = {"HALFDATA": {"avg_volume_20": 5_000_000}}  # no latest_close
        result = pre_screen_universe(
            ["HALFDATA"],
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        # volume is OK, close unknown → passes
        assert "HALFDATA" in result.symbols

    def test_fallback_when_filtered_pool_too_small(self):
        """When fewer than min_symbols_after_filter pass, return the full list."""
        symbols = [f"SYM{i}" for i in range(10)]
        # All have bad prices
        metrics = {s: _make_metrics(latest_close=1.0, avg_volume_20=5_000_000) for s in symbols}
        result = pre_screen_universe(
            symbols,
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=5,  # 0 pass < 5 → fallback
        )
        assert result.fallback_used
        assert len(result.symbols) == len(symbols)
        assert result.filtered_count == 0

    def test_no_fallback_when_enough_pass(self):
        symbols = [f"SYM{i}" for i in range(10)]
        metrics = {s: _make_metrics(latest_close=100.0, avg_volume_20=5_000_000) for s in symbols}
        result = pre_screen_universe(
            symbols,
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=5,
        )
        assert not result.fallback_used
        assert len(result.symbols) == 10

    def test_does_not_mutate_input_list(self):
        original = ["AAPL", "MSFT", "LOWVOL"]
        metrics = {
            "AAPL": _make_metrics(latest_close=190.0, avg_volume_20=55_000_000),
            "MSFT": _make_metrics(latest_close=410.0, avg_volume_20=20_000_000),
            "LOWVOL": _make_metrics(latest_close=50.0, avg_volume_20=1_000),
        }
        original_copy = list(original)
        pre_screen_universe(
            original,
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
        )
        assert original == original_copy  # not mutated

    def test_result_counts_are_consistent(self):
        symbols = ["PASS", "FAIL_PRICE", "FAIL_VOL", "NO_DATA"]
        metrics = {
            "PASS": _make_metrics(latest_close=100.0, avg_volume_20=1_000_000),
            "FAIL_PRICE": _make_metrics(latest_close=1.0, avg_volume_20=1_000_000),
            "FAIL_VOL": _make_metrics(latest_close=100.0, avg_volume_20=100),
            # NO_DATA absent
        }
        result = pre_screen_universe(
            symbols,
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        assert result.original_count == 4
        # PASS and NO_DATA pass
        assert result.filtered_count == 2
        assert result.screened_out_count == 2
        assert result.no_cache_data_count == 1
        assert not result.fallback_used

    def test_to_dict_has_expected_keys(self):
        result = pre_screen_universe(
            ["SYM"],
            recent_metrics={"SYM": _make_metrics(latest_close=100.0, avg_volume_20=1_000_000)},
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
        )
        d = result.to_dict()
        assert "original_count" in d
        assert "filtered_count" in d
        assert "screened_out_count" in d
        assert "no_cache_data_count" in d
        assert "fallback_used" in d
        assert "reasons" in d


# ── TestBuildRecentSymbolMetrics ──────────────────────────────────────────────

class TestBuildRecentSymbolMetrics:
    """Unit tests for build_recent_symbol_metrics()."""

    def test_returns_empty_for_no_rows(self):
        result = build_recent_symbol_metrics([])
        assert result == {}

    def test_picks_most_recent_row_per_symbol(self):
        rows = [
            _make_scan_result_row("AAPL", 180.0, 50_000_000, age_days=5.0),
            _make_scan_result_row("AAPL", 195.0, 52_000_000, age_days=1.0),  # newer
        ]
        result = build_recent_symbol_metrics(rows, max_cache_age_days=7)
        assert "AAPL" in result
        assert result["AAPL"]["latest_close"] == 195.0

    def test_ignores_rows_older_than_cutoff(self):
        rows = [
            _make_scan_result_row("OLD", 100.0, 1_000_000, age_days=10.0),  # 10 days old
        ]
        result = build_recent_symbol_metrics(rows, max_cache_age_days=7)
        assert "OLD" not in result

    def test_includes_rows_within_cutoff(self):
        rows = [
            _make_scan_result_row("NEW", 200.0, 5_000_000, age_days=3.0),
        ]
        result = build_recent_symbol_metrics(rows, max_cache_age_days=7)
        assert "NEW" in result
        assert result["NEW"]["latest_close"] == 200.0

    def test_handles_missing_close_field(self):
        rows = [{"symbol": "MSFT", "latest_close": None, "avg_volume_20": 20_000_000, "created_at": _ts(0)}]
        result = build_recent_symbol_metrics(rows)
        assert "MSFT" in result
        # latest_close should not be included when None
        assert "latest_close" not in result["MSFT"]

    def test_handles_missing_volume_field(self):
        rows = [{"symbol": "TSLA", "latest_close": 170.0, "avg_volume_20": None, "created_at": _ts(0)}]
        result = build_recent_symbol_metrics(rows)
        assert "TSLA" in result
        assert result["TSLA"]["latest_close"] == 170.0
        assert "avg_volume_20" not in result["TSLA"]

    def test_skips_rows_without_symbol(self):
        rows = [{"symbol": "", "latest_close": 100.0, "avg_volume_20": 1_000_000, "created_at": _ts(0)}]
        result = build_recent_symbol_metrics(rows)
        assert result == {}

    def test_skips_rows_without_created_at(self):
        rows = [{"symbol": "NADA", "latest_close": 100.0, "avg_volume_20": 1_000_000, "created_at": None}]
        result = build_recent_symbol_metrics(rows)
        assert "NADA" not in result

    def test_normalizes_symbol_to_uppercase(self):
        rows = [{"symbol": "aapl", "latest_close": 190.0, "avg_volume_20": 55_000_000, "created_at": _ts(0)}]
        result = build_recent_symbol_metrics(rows)
        assert "AAPL" in result
        assert "aapl" not in result

    def test_multiple_symbols_all_returned(self):
        rows = [
            _make_scan_result_row("AAPL", 190.0, 55_000_000, 1.0),
            _make_scan_result_row("MSFT", 410.0, 20_000_000, 2.0),
            _make_scan_result_row("NVDA", 880.0, 40_000_000, 0.5),
        ]
        result = build_recent_symbol_metrics(rows, max_cache_age_days=7)
        assert set(result.keys()) == {"AAPL", "MSFT", "NVDA"}


# ── TestLoadPreScreenerConfig ─────────────────────────────────────────────────

class TestLoadPreScreenerConfig:
    def test_defaults_when_none(self):
        cfg = load_pre_screener_config(None)
        assert cfg["enabled"] is True
        assert cfg["min_symbols_after_filter"] == 50
        assert cfg["use_snapshot_cache"] is True
        assert cfg["max_cache_age_days"] == 7

    def test_defaults_when_empty_dict(self):
        cfg = load_pre_screener_config({})
        assert cfg["enabled"] is True

    def test_override_enabled_false(self):
        cfg = load_pre_screener_config({"enabled": False})
        assert cfg["enabled"] is False

    def test_override_min_symbols(self):
        cfg = load_pre_screener_config({"min_symbols_after_filter": 100})
        assert cfg["min_symbols_after_filter"] == 100

    def test_override_max_cache_age_days(self):
        cfg = load_pre_screener_config({"max_cache_age_days": 14})
        assert cfg["max_cache_age_days"] == 14

    def test_partial_overrides_keep_defaults(self):
        cfg = load_pre_screener_config({"enabled": False})
        assert cfg["min_symbols_after_filter"] == 50
        assert cfg["use_snapshot_cache"] is True


# ── TestRepositoryGetRecentScanResultMetrics ──────────────────────────────────

class TestRepositoryGetRecentScanResultMetrics:
    """Integration tests using real in-memory SQLite."""

    @pytest.fixture()
    def repo(self, tmp_path: Path) -> ScannerRepository:
        db = tmp_path / "test_prescreener.db"
        return ScannerRepository(db)

    def _insert_scan_result(
        self,
        repo: ScannerRepository,
        symbol: str,
        latest_close: float,
        avg_volume_20: float,
        age_days: float = 0.0,
    ) -> None:
        from trading_bot.storage.database import connect
        from datetime import datetime, timedelta, timezone

        created_at = (
            datetime.now(timezone.utc) - timedelta(days=age_days)
        ).isoformat()

        with connect(repo.database_path) as conn:
            # Insert a scan_run first
            cursor = conn.execute(
                "INSERT INTO scan_runs (created_at, universe_count, provider, config_snapshot_json) "
                "VALUES (?, ?, ?, ?)",
                (created_at, 10, "test_provider", "{}"),
            )
            scan_run_id = cursor.lastrowid
            # Insert a scan_result row with the metrics we need
            conn.execute(
                """
                INSERT INTO scan_results (
                    scan_run_id, symbol, final_score, setup_category, tags_json, universe_role,
                    name, sector, industry, demo_profile, notes, candidate_summary,
                    trend_score, momentum_score, volume_score, risk_score, setup_quality_score,
                    latest_close, avg_volume_20, dollar_volume_20, return_5d, return_10d,
                    return_20d, atr_14, atr_percent, volatility_20d, relative_volume,
                    suggested_entry, suggested_stop, suggested_target_1, risk_reward_ratio,
                    trade_plan_valid, trade_plan_status, reasons_json, warnings_json, created_at
                )
                VALUES (
                    ?, ?, 75.0, 'Breakout Watch', '[]', 'primary_candidate',
                    '', '', '', '', '', '',
                    60.0, 55.0, 70.0, 65.0, 60.0,
                    ?, ?, 0.0, 0.01, 0.02,
                    0.03, 2.5, 0.015, 0.02, 1.1,
                    ?, 0.0, 0.0, 2.0,
                    1, 'valid', '[]', '[]', ?
                )
                """,
                (scan_run_id, symbol, latest_close, avg_volume_20, latest_close, created_at),
            )

    def test_returns_empty_list_when_no_rows(self, repo: ScannerRepository):
        rows = repo.get_recent_scan_result_metrics(max_age_days=7)
        assert rows == []

    def test_returns_row_within_window(self, repo: ScannerRepository):
        self._insert_scan_result(repo, "AAPL", 190.0, 55_000_000, age_days=1.0)
        rows = repo.get_recent_scan_result_metrics(max_age_days=7)
        assert len(rows) >= 1
        symbols = {r["symbol"] for r in rows}
        assert "AAPL" in symbols

    def test_excludes_row_outside_window(self, repo: ScannerRepository):
        self._insert_scan_result(repo, "OLD", 100.0, 5_000_000, age_days=10.0)
        rows = repo.get_recent_scan_result_metrics(max_age_days=7)
        symbols = {r["symbol"] for r in rows}
        assert "OLD" not in symbols

    def test_returns_correct_fields(self, repo: ScannerRepository):
        self._insert_scan_result(repo, "MSFT", 410.0, 20_000_000, age_days=0.0)
        rows = repo.get_recent_scan_result_metrics(max_age_days=7)
        msft_rows = [r for r in rows if r["symbol"] == "MSFT"]
        assert msft_rows, "MSFT row not found"
        row = msft_rows[0]
        assert "symbol" in row
        assert "latest_close" in row
        assert "avg_volume_20" in row
        assert "created_at" in row
        assert abs(float(row["latest_close"]) - 410.0) < 0.01
        assert abs(float(row["avg_volume_20"]) - 20_000_000) < 1.0

    def test_multiple_symbols_returned(self, repo: ScannerRepository):
        for sym, close, vol in [("A", 100.0, 5_000_000), ("B", 200.0, 10_000_000)]:
            self._insert_scan_result(repo, sym, close, vol, age_days=0.0)
        rows = repo.get_recent_scan_result_metrics(max_age_days=7)
        symbols = {r["symbol"] for r in rows}
        assert "A" in symbols
        assert "B" in symbols


# ── TestPreScreenerEndToEnd ────────────────────────────────────────────────────

class TestPreScreenerEndToEnd:
    """Combines repo + build_recent_symbol_metrics + pre_screen_universe."""

    @pytest.fixture()
    def repo(self, tmp_path: Path) -> ScannerRepository:
        db = tmp_path / "e2e_pre.db"
        return ScannerRepository(db)

    def _insert(self, repo, symbol, close, vol, age_days=0.0):
        from trading_bot.storage.database import connect
        from datetime import datetime, timedelta, timezone
        created_at = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
        with connect(repo.database_path) as conn:
            cursor = conn.execute(
                "INSERT INTO scan_runs (created_at, universe_count, provider, config_snapshot_json) VALUES (?, ?, ?, ?)",
                (created_at, 5, "test", "{}"),
            )
            sid = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO scan_results (
                    scan_run_id, symbol, final_score, setup_category, tags_json, universe_role,
                    name, sector, industry, demo_profile, notes, candidate_summary,
                    trend_score, momentum_score, volume_score, risk_score, setup_quality_score,
                    latest_close, avg_volume_20, dollar_volume_20, return_5d, return_10d,
                    return_20d, atr_14, atr_percent, volatility_20d, relative_volume,
                    suggested_entry, suggested_stop, suggested_target_1, risk_reward_ratio,
                    trade_plan_valid, trade_plan_status, reasons_json, warnings_json, created_at
                ) VALUES (
                    ?, ?, 75.0, 'Breakout Watch', '[]', 'primary_candidate',
                    '', '', '', '', '', '',
                    60.0, 55.0, 70.0, 65.0, 60.0,
                    ?, ?, 0.0, 0.01, 0.02, 0.03, 2.5, 0.015, 0.02, 1.1,
                    ?, 0.0, 0.0, 2.0, 1, 'valid', '[]', '[]', ?
                )
                """,
                (sid, symbol, close, vol, close, created_at),
            )

    def test_full_pipeline_filters_bad_symbols(self, repo: ScannerRepository):
        self._insert(repo, "GOOD", 100.0, 5_000_000, 0.0)
        self._insert(repo, "CHEAPO", 1.0, 5_000_000, 0.0)
        self._insert(repo, "ILLIQUID", 100.0, 1_000, 0.0)

        raw_rows = repo.get_recent_scan_result_metrics(max_age_days=7)
        metrics = build_recent_symbol_metrics(raw_rows, max_cache_age_days=7)
        result = pre_screen_universe(
            ["GOOD", "CHEAPO", "ILLIQUID"],
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        assert "GOOD" in result.symbols
        assert "CHEAPO" not in result.symbols
        assert "ILLIQUID" not in result.symbols
        assert result.screened_out_count == 2

    def test_no_data_symbols_pass_through_pipeline(self, repo: ScannerRepository):
        # Insert nothing — repo is empty
        raw_rows = repo.get_recent_scan_result_metrics(max_age_days=7)
        metrics = build_recent_symbol_metrics(raw_rows, max_cache_age_days=7)
        result = pre_screen_universe(
            ["NEWCO", "STARTUP"],
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        # Both pass through because no cached data
        assert "NEWCO" in result.symbols
        assert "STARTUP" in result.symbols
        assert result.no_cache_data_count == 2

    def test_stale_data_excluded_from_metrics(self, repo: ScannerRepository):
        self._insert(repo, "STALE", 100.0, 5_000_000, age_days=10.0)
        raw_rows = repo.get_recent_scan_result_metrics(max_age_days=7)
        metrics = build_recent_symbol_metrics(raw_rows, max_cache_age_days=7)
        # STALE is too old → not in metrics → treated as no-data → passes through
        result = pre_screen_universe(
            ["STALE"],
            recent_metrics=metrics,
            min_price=5.0,
            max_price=500.0,
            min_avg_volume=300_000.0,
            min_symbols_after_filter=1,
        )
        assert "STALE" in result.symbols
        assert result.no_cache_data_count == 1
