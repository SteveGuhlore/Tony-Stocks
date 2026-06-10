"""V34B — true-coverage + throughput tests.

Part A: _fetch_bars_batch chunks wire requests at max_symbols_per_batch and
        accumulates per-symbol output identically to a single-request fetch.
Part B: WatchUniverseRotator discovery uses strided sampling — each cycle is
        an evenly-spread cross-section of the ranked list (no contiguous
        score-band/sector clumps) while still covering every symbol once per
        epoch.

All tests are mocked. No real Alpaca API calls are made.
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

from trading_bot.data.market_data import AlpacaIEXProvider
from trading_bot.data.universe_rotation import WatchUniverseRotator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_bars(n: int = 5) -> list[dict]:
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
        fail_safe_to_demo=False,
        batch_requests_enabled=True,
        max_symbols_per_batch=175,
        stop_on_rate_limit=False,
        fallback_on_rate_limit=True,
        _skip_key_check=True,
    )
    defaults.update(kwargs)
    return AlpacaIEXProvider(**defaults)


def _batch_response_for(params_symbols: str) -> MagicMock:
    """Build a mock response returning sample bars for each requested symbol."""
    resp = MagicMock()
    resp.ok = True
    resp.status_code = 200
    resp.json.return_value = {
        "bars": {sym: _sample_bars() for sym in params_symbols.split(",")},
        "next_page_token": None,
    }
    return resp


def _request_recorder(requested_chunks: list[list[str]]):
    def _fake_get(url, headers=None, params=None, timeout=None):
        symbols = params["symbols"]
        requested_chunks.append(symbols.split(","))
        return _batch_response_for(symbols)

    return _fake_get


# ---------------------------------------------------------------------------
# Part A — batch chunking
# ---------------------------------------------------------------------------

class TestBatchChunking:
    def test_at_or_below_chunk_size_is_one_request(self):
        provider = _make_provider(max_symbols_per_batch=175)
        chunks: list[list[str]] = []
        symbols = [f"SYM{i:03d}" for i in range(175)]
        with patch("trading_bot.data.market_data.requests.get",
                   side_effect=_request_recorder(chunks)):
            result = provider.fetch_ohlcv_batch(symbols, lookback_days=30)
        assert len(chunks) == 1
        assert chunks[0] == symbols
        assert set(result) == set(symbols)

    def test_above_chunk_size_splits_requests(self):
        provider = _make_provider(max_symbols_per_batch=175)
        chunks: list[list[str]] = []
        symbols = [f"SYM{i:03d}" for i in range(350)]
        with patch("trading_bot.data.market_data.requests.get",
                   side_effect=_request_recorder(chunks)):
            result = provider.fetch_ohlcv_batch(symbols, lookback_days=30)
        assert len(chunks) == 2
        assert [len(c) for c in chunks] == [175, 175]
        # No symbol is dropped, duplicated, or reordered across chunks.
        assert [s for c in chunks for s in c] == symbols
        assert set(result) == set(symbols)
        assert all(not df.empty for df in result.values())

    def test_uneven_tail_chunk(self):
        provider = _make_provider(max_symbols_per_batch=100)
        chunks: list[list[str]] = []
        symbols = [f"SYM{i:03d}" for i in range(250)]
        with patch("trading_bot.data.market_data.requests.get",
                   side_effect=_request_recorder(chunks)):
            result = provider.fetch_ohlcv_batch(symbols, lookback_days=30)
        assert [len(c) for c in chunks] == [100, 100, 50]
        assert set(result) == set(symbols)

    def test_request_counters_track_chunks(self):
        provider = _make_provider(max_symbols_per_batch=100)
        symbols = [f"SYM{i:03d}" for i in range(250)]
        with patch("trading_bot.data.market_data.requests.get",
                   side_effect=_request_recorder([])):
            provider.fetch_ohlcv_batch(symbols, lookback_days=30)
        assert provider._requests_this_cycle == 3
        assert provider._batch_requests_this_cycle == 3

    def test_pagination_stays_within_chunk(self):
        """A next_page_token in chunk 1 must re-request chunk 1's symbols,
        never leak into chunk 2's params."""
        provider = _make_provider(max_symbols_per_batch=2)
        symbols = ["AAA", "BBB", "CCC"]
        seen_params: list[dict] = []

        def _fake_get(url, headers=None, params=None, timeout=None):
            seen_params.append(dict(params))
            resp = MagicMock()
            resp.ok = True
            resp.status_code = 200
            syms = params["symbols"].split(",")
            first_page_of_first_chunk = (
                params["symbols"] == "AAA,BBB" and "page_token" not in params
            )
            resp.json.return_value = {
                "bars": {s: _sample_bars(2) for s in syms},
                "next_page_token": "tok1" if first_page_of_first_chunk else None,
            }
            return resp

        with patch("trading_bot.data.market_data.requests.get", side_effect=_fake_get):
            result = provider.fetch_ohlcv_batch(symbols, lookback_days=30)

        assert [p["symbols"] for p in seen_params] == ["AAA,BBB", "AAA,BBB", "CCC"]
        assert seen_params[1].get("page_token") == "tok1"
        assert "page_token" not in seen_params[2]
        # Paged bars accumulate: AAA got 2 bars per page across 2 pages.
        assert len(result["AAA"]) == 4
        assert len(result["CCC"]) == 2


# ---------------------------------------------------------------------------
# Part B — strided discovery rotation
# ---------------------------------------------------------------------------

def _discovery_only_config(max_per_cycle: int, bucket: int) -> dict:
    return {
        "max_symbols_per_cycle": max_per_cycle,
        "core_symbols": [],
        "core_max_symbols": 0,
        "rotating_bucket_size": bucket,
        "keep_previous_candidates": False,
        "always_include_open_snapshots": False,
    }


class TestStridedCoverage:
    def test_full_coverage_within_one_epoch(self):
        """Every symbol is scanned at least once within ceil(N/bucket) cycles."""
        n, bucket = 1000, 350
        all_syms = [f"SYM{i:04d}" for i in range(n)]
        rotator = WatchUniverseRotator(all_syms, _discovery_only_config(bucket, bucket))
        epoch = math.ceil(n / bucket)
        scanned: set[str] = set()
        for _ in range(epoch):
            scanned.update(rotator.get_cycle_symbols().symbols)
        assert scanned == set(all_syms)

    def test_coverage_with_non_divisible_sizes(self):
        for n, bucket in [(10, 4), (37, 5), (101, 33), (7, 7), (200, 199)]:
            all_syms = [f"S{i:04d}" for i in range(n)]
            rotator = WatchUniverseRotator(all_syms, _discovery_only_config(bucket, bucket))
            scanned: set[str] = set()
            for _ in range(math.ceil(n / bucket)):
                scanned.update(rotator.get_cycle_symbols().symbols)
            assert scanned == set(all_syms), f"gap at n={n}, bucket={bucket}"

    def test_cycle_is_spread_not_contiguous(self):
        """Each cycle's picks span the whole ranked list (the anti-clustering
        property): consecutive picked ranks are ~step apart, never a
        contiguous block, and both the head and the tail of the ranking are
        represented every cycle."""
        n, bucket = 1000, 350
        all_syms = [f"SYM{i:04d}" for i in range(n)]
        rank = {s: i for i, s in enumerate(all_syms)}
        rotator = WatchUniverseRotator(all_syms, _discovery_only_config(bucket, bucket))
        result = rotator.get_cycle_symbols()
        ranks = sorted(rank[s] for s in result.symbols)
        assert len(ranks) == bucket
        # Spread: picks reach into the final stride of the list, not just the top.
        assert ranks[0] < math.ceil(n / bucket)
        assert ranks[-1] >= n - math.ceil(n / bucket)
        # No long contiguous run (a contiguous slice would have 350 adjacent ranks).
        longest_run = run = 1
        for a, b in zip(ranks, ranks[1:]):
            run = run + 1 if b == a + 1 else 1
            longest_run = max(longest_run, run)
        assert longest_run <= 2

    def test_no_duplicates_within_cycle(self):
        n, bucket = 100, 37
        all_syms = [f"S{i:03d}" for i in range(n)]
        rotator = WatchUniverseRotator(all_syms, _discovery_only_config(bucket, bucket))
        result = rotator.get_cycle_symbols()
        assert len(result.symbols) == len(set(result.symbols)) == bucket

    def test_bucket_id_advances_per_cycle(self):
        all_syms = [f"S{i:03d}" for i in range(50)]
        rotator = WatchUniverseRotator(all_syms, _discovery_only_config(10, 10))
        r1 = rotator.get_cycle_symbols()
        r2 = rotator.get_cycle_symbols()
        assert r2.bucket_id == r1.bucket_id + 1

    def test_precedence_layers_untouched(self):
        """Core, open-snapshot, and carryover symbols still come first and are
        excluded from the discovery comb (no duplicates)."""
        all_syms = [f"S{i:03d}" for i in range(100)]
        config = {
            "max_symbols_per_cycle": 30,
            "core_symbols": ["SPY", "QQQ"],
            "core_max_symbols": 5,
            "rotating_bucket_size": 50,
            "keep_previous_candidates": True,
            "always_include_open_snapshots": True,
        }
        rotator = WatchUniverseRotator(all_syms, config)
        rotator.update_previous_candidates(["S010", "S020"])
        result = rotator.get_cycle_symbols(open_snapshot_symbols=["S005"])
        assert result.symbols[:2] == ["SPY", "QQQ"]
        assert result.symbols[2] == "S005"
        assert result.symbols[3:5] == ["S010", "S020"]
        assert len(result.symbols) == len(set(result.symbols))
        assert result.total <= 30

    def test_bucket_larger_than_universe_scans_everything(self):
        all_syms = [f"S{i:02d}" for i in range(8)]
        rotator = WatchUniverseRotator(all_syms, _discovery_only_config(20, 20))
        result = rotator.get_cycle_symbols()
        assert set(result.symbols) == set(all_syms)

    def test_empty_universe_does_not_crash(self):
        rotator = WatchUniverseRotator([], _discovery_only_config(10, 10))
        result = rotator.get_cycle_symbols()
        assert result.symbols == []
        assert result.discovery_count == 0
