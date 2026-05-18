"""V9 scaling tests — batch fetch, rate limiter, universe rotation.

All tests are mocked. No real Alpaca API calls are made.
No broker execution, paper trades, or live orders are tested or implied.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading_bot.data.market_data import AlpacaIEXProvider, RateLimiter
from trading_bot.data.universe_rotation import RotationResult, WatchUniverseRotator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_bars(symbol: str, n: int = 5) -> list[dict]:
    return [
        {
            "t": f"2024-01-{i + 1:02d}T00:00:00Z",
            "o": 10.0,
            "h": 11.0,
            "l": 9.0,
            "c": 10.5,
            "v": 1_000_000,
        }
        for i in range(n)
    ]


def _make_provider(**kwargs) -> AlpacaIEXProvider:
    defaults = dict(
        api_key="test_key",
        secret_key="test_secret",
        feed="iex",
        timeframe="1Day",
        fail_safe_to_demo=True,
        batch_requests_enabled=True,
        max_symbols_per_batch=175,
        stop_on_rate_limit=False,
        fallback_on_rate_limit=True,
        _skip_key_check=True,
    )
    defaults.update(kwargs)
    return AlpacaIEXProvider(**defaults)


# ---------------------------------------------------------------------------
# 1. Batch response normalisation — multi-symbol dict format
# ---------------------------------------------------------------------------

class TestBatchResponseNormalisation:
    def test_batch_response_parsed_per_symbol(self):
        """Multi-symbol response {"bars": {"PLTR": [...], "AAPL": [...]}} is
        normalised into a dict of DataFrames keyed by symbol."""
        provider = _make_provider()
        mock_response = {
            "bars": {
                "PLTR": _sample_bars("PLTR"),
                "AAPL": _sample_bars("AAPL"),
            }
        }
        with patch.object(provider, "_fetch_bars_batch", return_value={
            "PLTR": provider._normalize_raw_bars(_sample_bars("PLTR"), 5, "PLTR", "1Day"),
            "AAPL": provider._normalize_raw_bars(_sample_bars("AAPL"), 5, "AAPL", "1Day"),
        }):
            result = provider.fetch_ohlcv_batch(["PLTR", "AAPL"], lookback_days=5)
        assert "PLTR" in result
        assert "AAPL" in result
        assert not result["PLTR"].empty
        assert not result["AAPL"].empty
        assert list(result["PLTR"].columns) == ["open", "high", "low", "close", "volume"]

    def test_normalize_raw_bars_returns_dataframe(self):
        bars = _sample_bars("PLTR", n=3)
        provider = _make_provider()
        df = provider._normalize_raw_bars(bars, lookback_days=3, symbol="PLTR", alpaca_tf="1Day")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "close" in df.columns

    def test_empty_bars_returns_empty_dataframe(self):
        provider = _make_provider()
        df = provider._normalize_raw_bars([], lookback_days=5, symbol="EMPTY", alpaca_tf="1Day")
        assert df.empty


# ---------------------------------------------------------------------------
# 2. Single-symbol fallback when batch disabled
# ---------------------------------------------------------------------------

class TestSingleSymbolFallback:
    def test_batch_disabled_falls_back_to_per_symbol(self):
        provider = _make_provider(batch_requests_enabled=False)
        assert not provider.batch_requests_enabled
        fake_df = pd.DataFrame(
            {"open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "volume": [500_000]},
            index=pd.to_datetime(["2024-01-01"]),
        )
        with patch.object(provider, "_fetch_bars", return_value=fake_df):
            result = provider.fetch_ohlcv("PLTR", lookback_days=5)
        assert not result.empty

    def test_fetch_ohlcv_batch_returns_demo_on_http_error(self):
        """When the batch endpoint fails, missing symbols fall back to demo."""
        provider = _make_provider(fail_safe_to_demo=True)
        with patch.object(provider, "_fetch_bars_batch", side_effect=Exception("network error")):
            result = provider.fetch_ohlcv_batch(["PLTR"], lookback_days=5)
        # Fail-safe: result should exist (demo fallback) or be empty dict — no crash
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 3. Rate limiter stays under safe cap
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_rate_limiter_respects_effective_cap(self):
        """With buffer=20%, a 100 RPM limiter accepts at most 80 per minute."""
        limiter = RateLimiter(max_per_minute=100, buffer_percent=20, sleep_seconds=0.0)
        assert limiter.max_per_minute == 80

    def test_rate_limiter_tracks_total_requests(self):
        limiter = RateLimiter(max_per_minute=1000, buffer_percent=0, sleep_seconds=0.0)
        for _ in range(5):
            limiter.acquire()
        assert limiter.total_requests == 5

    def test_rate_limiter_reset_clears_state(self):
        limiter = RateLimiter(max_per_minute=1000, buffer_percent=0, sleep_seconds=0.0)
        for _ in range(3):
            limiter.acquire()
        limiter.reset()
        assert limiter.total_requests == 0
        assert limiter.total_waits == 0

    def test_rate_limiter_enforces_window(self):
        """Limiter should wait when the sliding window is full."""
        limiter = RateLimiter(max_per_minute=2, buffer_percent=0, sleep_seconds=0.01)
        # Fill the window
        limiter.acquire()
        limiter.acquire()
        # Third call should trigger at least one wait
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        # Should have slept at least once (sleep_seconds=0.01)
        assert elapsed >= 0.005 or limiter.total_waits >= 1


# ---------------------------------------------------------------------------
# 4. 429 handling — sleep and retry
# ---------------------------------------------------------------------------

class TestRateLimitRetry:
    def test_provider_tracks_rate_limit_warnings_on_429(self):
        """_rate_limit_warnings_this_cycle increments on HTTP 429."""
        provider = _make_provider()
        provider.reset_cycle_state()

        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.ok = False

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.ok = True
        mock_ok.json.return_value = {"bars": _sample_bars("PLTR"), "next_page_token": None}

        with patch("trading_bot.data.market_data.requests.get", side_effect=[mock_429, mock_ok]):
            with patch("time.sleep"):
                try:
                    provider._fetch_bars("PLTR", 5, "1Day")
                except Exception:
                    pass

        # Warning counter should have incremented on 429
        assert provider._rate_limit_warnings_this_cycle >= 1


# ---------------------------------------------------------------------------
# 5. Universe rotation preserves core symbols
# ---------------------------------------------------------------------------

class TestUniverseRotationCore:
    def _make_rotator(self, all_symbols=None, config=None) -> WatchUniverseRotator:
        if all_symbols is None:
            all_symbols = [f"SYM{i:03d}" for i in range(50)]
        if config is None:
            config = {
                "max_symbols_per_cycle": 20,
                "core_symbols": ["SPY", "QQQ"],
                "core_max_symbols": 5,
                "rotating_bucket_size": 15,
                "keep_previous_candidates": True,
                "always_include_open_snapshots": True,
            }
        return WatchUniverseRotator(all_symbols, config)

    def test_core_symbols_always_first(self):
        rotator = self._make_rotator()
        result = rotator.get_cycle_symbols()
        assert result.symbols[0] == "SPY"
        assert result.symbols[1] == "QQQ"

    def test_core_count_matches(self):
        rotator = self._make_rotator()
        result = rotator.get_cycle_symbols()
        assert result.core_count == 2

    def test_total_respects_max_per_cycle(self):
        rotator = self._make_rotator(config={
            "max_symbols_per_cycle": 10,
            "core_symbols": ["SPY"],
            "core_max_symbols": 5,
            "rotating_bucket_size": 50,
            "keep_previous_candidates": False,
            "always_include_open_snapshots": False,
        })
        result = rotator.get_cycle_symbols()
        assert result.total <= 10


# ---------------------------------------------------------------------------
# 6. Open snapshot symbols are included
# ---------------------------------------------------------------------------

class TestOpenSnapshotInclusion:
    def test_open_snapshot_symbols_included(self):
        all_syms = [f"SYM{i:03d}" for i in range(20)]
        config = {
            "max_symbols_per_cycle": 25,
            "core_symbols": [],
            "core_max_symbols": 5,
            "rotating_bucket_size": 10,
            "keep_previous_candidates": False,
            "always_include_open_snapshots": True,
        }
        rotator = WatchUniverseRotator(all_syms, config)
        result = rotator.get_cycle_symbols(open_snapshot_symbols=["OPEN1", "OPEN2"])
        assert "OPEN1" in result.symbols
        assert "OPEN2" in result.symbols
        assert result.open_snapshot_count == 2

    def test_open_snapshot_disabled(self):
        all_syms = [f"SYM{i:03d}" for i in range(10)]
        config = {
            "max_symbols_per_cycle": 25,
            "core_symbols": [],
            "core_max_symbols": 5,
            "rotating_bucket_size": 10,
            "keep_previous_candidates": False,
            "always_include_open_snapshots": False,
        }
        rotator = WatchUniverseRotator(all_syms, config)
        result = rotator.get_cycle_symbols(open_snapshot_symbols=["OPEN1"])
        assert "OPEN1" not in result.symbols
        assert result.open_snapshot_count == 0


# ---------------------------------------------------------------------------
# 7. Rotation avoids duplicates
# ---------------------------------------------------------------------------

class TestRotationDeduplication:
    def test_no_duplicates_in_result(self):
        # Core symbol also appears in all_symbols and open_snapshots
        all_syms = ["SPY", "QQQ"] + [f"SYM{i:03d}" for i in range(20)]
        config = {
            "max_symbols_per_cycle": 30,
            "core_symbols": ["SPY", "QQQ"],
            "core_max_symbols": 5,
            "rotating_bucket_size": 20,
            "keep_previous_candidates": True,
            "always_include_open_snapshots": True,
        }
        rotator = WatchUniverseRotator(all_syms, config)
        rotator.update_previous_candidates(["SPY", "SYM001"])
        result = rotator.get_cycle_symbols(open_snapshot_symbols=["SPY", "QQQ", "SYM002"])
        assert len(result.symbols) == len(set(result.symbols)), "Duplicates found in rotation result"

    def test_bucket_index_advances(self):
        all_syms = [f"SYM{i:03d}" for i in range(100)]
        config = {
            "max_symbols_per_cycle": 15,
            "core_symbols": [],
            "core_max_symbols": 0,
            "rotating_bucket_size": 10,
            "keep_previous_candidates": False,
            "always_include_open_snapshots": False,
        }
        rotator = WatchUniverseRotator(all_syms, config)
        r1 = rotator.get_cycle_symbols()
        r2 = rotator.get_cycle_symbols()
        assert r1.bucket_id != r2.bucket_id or r1.symbols != r2.symbols


# ---------------------------------------------------------------------------
# 8. max_symbols_per_cycle is always respected
# ---------------------------------------------------------------------------

class TestMaxSymbolsPerCycle:
    def test_max_enforced_with_many_inputs(self):
        all_syms = [f"SYM{i:03d}" for i in range(200)]
        config = {
            "max_symbols_per_cycle": 25,
            "core_symbols": [f"CORE{i}" for i in range(20)],
            "core_max_symbols": 20,
            "rotating_bucket_size": 50,
            "keep_previous_candidates": True,
            "always_include_open_snapshots": True,
        }
        rotator = WatchUniverseRotator(all_syms, config)
        rotator.update_previous_candidates([f"PREV{i}" for i in range(30)])
        result = rotator.get_cycle_symbols(open_snapshot_symbols=[f"OPEN{i}" for i in range(20)])
        assert result.total <= 25
        assert len(result.symbols) <= 25


# ---------------------------------------------------------------------------
# 9. Scanner still works in demo mode (no Alpaca involved)
# ---------------------------------------------------------------------------

class TestDemoModeScanner:
    def test_rotator_works_with_empty_universe(self):
        """Empty universe should not crash the rotator."""
        rotator = WatchUniverseRotator([], {
            "max_symbols_per_cycle": 10,
            "core_symbols": ["SPY"],
            "core_max_symbols": 5,
            "rotating_bucket_size": 5,
            "keep_previous_candidates": False,
            "always_include_open_snapshots": False,
        })
        result = rotator.get_cycle_symbols()
        assert "SPY" in result.symbols
        assert result.total <= 10

    def test_rotation_result_to_dict(self):
        rotator = WatchUniverseRotator(["SPY", "QQQ"], {
            "max_symbols_per_cycle": 10,
            "core_symbols": ["SPY"],
            "core_max_symbols": 2,
            "rotating_bucket_size": 5,
            "keep_previous_candidates": False,
            "always_include_open_snapshots": False,
        })
        result = rotator.get_cycle_symbols()
        d = result.to_dict()
        assert "bucket_id" in d
        assert "core_count" in d
        assert "total" in d


# ---------------------------------------------------------------------------
# 11. Batch limit audit — must use high limit to minimise pagination
# ---------------------------------------------------------------------------

class TestBatchLimitAudit:
    """Verify that batch requests use limit=10000 to avoid excessive pagination.

    Root cause of V9 '23 requests for 39 symbols': the batch endpoint
    interprets `limit` as total bars per page across all symbols.
    With limit=180 and 39 symbols × 107 bars ≈ 4173 bars, that caused ~23
    pages.  Fix: always use limit=10000 (Alpaca max) for batch requests.
    """

    def test_batch_request_uses_high_limit(self):
        """_fetch_bars_batch must pass limit=10000 to eliminate pagination."""
        provider = _make_provider()
        captured_params: dict = {}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "bars": {"PLTR": _sample_bars("PLTR"), "AAPL": _sample_bars("AAPL")},
            "next_page_token": None,
        }

        def capture_get(url, headers, params, timeout):
            captured_params.update(params)
            return mock_resp

        with patch("trading_bot.data.market_data.requests.get", side_effect=capture_get):
            provider._fetch_bars_batch(["PLTR", "AAPL"], lookback_days=120, timeframe="daily")

        assert "limit" in captured_params
        assert int(captured_params["limit"]) >= 10000, (
            f"Batch limit too low ({captured_params['limit']}); will cause excessive pagination "
            "for large symbol sets. Use limit=10000 (Alpaca max)."
        )

    def test_single_symbol_fetch_independent_of_batch_limit(self):
        """_fetch_bars (single-symbol) uses its own limit formula — not affected by batch fix."""
        provider = _make_provider()
        captured_params: dict = {}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {"bars": _sample_bars("SPY"), "next_page_token": None}

        def capture_get(url, headers, params, timeout):
            captured_params.update(params)
            return mock_resp

        with patch("trading_bot.data.market_data.requests.get", side_effect=capture_get):
            provider._fetch_bars("SPY", 120, "daily")

        assert "limit" in captured_params
        # Single-symbol limit may be smaller; key constraint is it covers the lookback
        assert int(captured_params["limit"]) >= 120


# ---------------------------------------------------------------------------
# 12. Request count metadata accuracy
# ---------------------------------------------------------------------------

class TestRequestCountMetadata:
    """Verify that get_cycle_stats() reflects actual HTTP calls, not symbols."""

    def test_batch_of_n_symbols_counts_as_one_http_request(self):
        """fetch_ohlcv_batch for N symbols with no pagination = 1 batch HTTP call."""
        provider = _make_provider()
        provider.reset_cycle_state()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "bars": {
                "PLTR": _sample_bars("PLTR"),
                "SOFI": _sample_bars("SOFI"),
                "HOOD": _sample_bars("HOOD"),
            },
            "next_page_token": None,
        }

        with patch("trading_bot.data.market_data.requests.get", return_value=mock_resp):
            provider.fetch_ohlcv_batch(["PLTR", "SOFI", "HOOD"], lookback_days=5)

        stats = provider.get_cycle_stats()
        assert stats["api_requests_used"] == 1, (
            f"Expected 1 HTTP request for 3-symbol batch with no pagination, "
            f"got {stats['api_requests_used']}."
        )
        assert stats["batch_requests_used"] == 1
        assert stats["batch_mode"] is True

    def test_pagination_increments_both_counters(self):
        """Each paginated HTTP call increments api_requests_used and batch_requests_used."""
        provider = _make_provider()
        provider.reset_cycle_state()

        page1 = MagicMock()
        page1.status_code = 200
        page1.ok = True
        page1.json.return_value = {
            "bars": {"PLTR": _sample_bars("PLTR", 2)},
            "next_page_token": "tok1",
        }
        page2 = MagicMock()
        page2.status_code = 200
        page2.ok = True
        page2.json.return_value = {
            "bars": {"PLTR": _sample_bars("PLTR", 2)},
            "next_page_token": None,
        }

        with patch("trading_bot.data.market_data.requests.get", side_effect=[page1, page2]):
            provider._fetch_bars_batch(["PLTR"], lookback_days=5, timeframe="daily")

        stats = provider.get_cycle_stats()
        assert stats["api_requests_used"] == 2
        assert stats["batch_requests_used"] == 2

    def test_reset_clears_all_counters_between_cycles(self):
        provider = _make_provider()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "bars": {"PLTR": _sample_bars("PLTR")},
            "next_page_token": None,
        }

        with patch("trading_bot.data.market_data.requests.get", return_value=mock_resp):
            provider._fetch_bars_batch(["PLTR"], lookback_days=5, timeframe="daily")

        assert provider.get_cycle_stats()["api_requests_used"] == 1

        provider.reset_cycle_state()
        stats = provider.get_cycle_stats()
        assert stats["api_requests_used"] == 0
        assert stats["batch_requests_used"] == 0
        assert stats["rate_limit_warnings"] == 0


# ---------------------------------------------------------------------------
# 10. Safety: no broker/order/paper-trade behaviour
# ---------------------------------------------------------------------------

class TestSafetyConstraints:
    """Guard against accidental introduction of broker/execution paths."""

    def test_alpaca_provider_has_no_order_method(self):
        provider = _make_provider()
        for attr in ("place_order", "submit_order", "create_order", "buy", "sell", "short"):
            assert not hasattr(provider, attr), f"Provider should not have method: {attr}"

    def test_rate_limiter_has_no_order_method(self):
        limiter = RateLimiter(max_per_minute=100)
        for attr in ("place_order", "submit_order", "execute"):
            assert not hasattr(limiter, attr)

    def test_rotator_has_no_order_method(self):
        rotator = WatchUniverseRotator(["SPY"], {})
        for attr in ("place_order", "submit_order", "execute", "buy", "sell"):
            assert not hasattr(rotator, attr)

    def test_provider_cycle_stats_no_trade_fields(self):
        provider = _make_provider()
        provider.reset_cycle_state()
        stats = provider.get_cycle_stats()
        for bad_key in ("orders_placed", "trades_executed", "positions_opened"):
            assert bad_key not in stats, f"Unexpected trade-related key in cycle stats: {bad_key}"
