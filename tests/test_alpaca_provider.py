"""Tests for AlpacaIEXProvider and V8.5 provider features — all HTTP calls are mocked; no real API requests."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading_bot.data.market_data import AlpacaIEXProvider, ProviderHealth, build_market_data_provider, check_provider_health
from trading_bot.settings import ScannerSettings, resolve_effective_provider


SAMPLE_BARS = [
    {"t": "2024-01-02T05:00:00Z", "o": 10.0, "h": 11.0, "l": 9.5, "c": 10.5, "v": 100_000},
    {"t": "2024-01-03T05:00:00Z", "o": 10.5, "h": 12.0, "l": 10.0, "c": 11.0, "v": 120_000},
    {"t": "2024-01-04T05:00:00Z", "o": 11.0, "h": 13.0, "l": 10.5, "c": 12.0, "v": 90_000},
]


def _mock_ok_response(bars, next_token=None):
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = {"bars": bars, "next_page_token": next_token}
    return mock


def _mock_error_response(status_code=500, text="Internal Server Error"):
    mock = MagicMock()
    mock.ok = False
    mock.status_code = status_code
    mock.text = text
    return mock


def _make_provider(**kwargs):
    return AlpacaIEXProvider(api_key="test_key", secret_key="test_secret", _skip_key_check=True, **kwargs)


# --- Key validation ---

def test_alpaca_missing_api_key_raises():
    with pytest.raises(EnvironmentError, match="ALPACA_API_KEY"):
        AlpacaIEXProvider(api_key="", secret_key="some_secret")


def test_alpaca_missing_secret_key_raises():
    with pytest.raises(EnvironmentError, match="ALPACA_API_KEY"):
        AlpacaIEXProvider(api_key="some_key", secret_key="")


def test_alpaca_skip_key_check_allows_empty_keys():
    provider = AlpacaIEXProvider(api_key="", secret_key="", _skip_key_check=True)
    assert provider.api_key == ""


# --- Bar normalization ---

def test_alpaca_normalizes_bars_to_ohlcv_schema():
    provider = _make_provider()
    with patch("requests.get", return_value=_mock_ok_response(SAMPLE_BARS)):
        data = provider.fetch_ohlcv("AAPL", 30)
    assert list(data.columns) == ["open", "high", "low", "close", "volume"]
    assert len(data) == 3
    assert data["close"].iloc[-1] == 12.0
    assert isinstance(data.index, pd.DatetimeIndex)


def test_alpaca_returns_correct_bar_count():
    provider = _make_provider()
    with patch("requests.get", return_value=_mock_ok_response(SAMPLE_BARS)):
        data = provider.fetch_ohlcv("PLTR", 3)
    assert len(data) == 3


# --- Empty response ---

def test_alpaca_empty_response_returns_empty_dataframe():
    provider = _make_provider()
    with patch("requests.get", return_value=_mock_ok_response([])):
        data = provider.fetch_ohlcv("AAPL", 30)
    assert data.empty
    assert set(data.columns) == {"open", "high", "low", "close", "volume"}


def test_alpaca_none_bars_field_returns_empty_dataframe():
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = {"bars": None, "next_page_token": None}
    provider = _make_provider()
    with patch("requests.get", return_value=mock):
        data = provider.fetch_ohlcv("AAPL", 30)
    assert data.empty


# --- HTTP error ---

def test_alpaca_http_error_raises_os_error_without_fallback():
    provider = _make_provider(fail_safe_to_demo=False)
    with patch("requests.get", return_value=_mock_error_response(403, "Forbidden")):
        with pytest.raises(OSError, match="HTTP 403"):
            provider.fetch_ohlcv("AAPL", 30)


def test_alpaca_http_error_falls_back_to_demo_when_configured():
    provider = _make_provider(fail_safe_to_demo=True)
    with patch("requests.get", return_value=_mock_error_response(500)):
        data = provider.fetch_ohlcv("AAPL", 120)
    # Demo provider returns data, not empty
    assert not data.empty
    assert "AAPL" in provider.fallback_symbols


# --- Demo fallback ---

def test_alpaca_fallback_tracked_in_fallback_symbols():
    provider = _make_provider(fail_safe_to_demo=True)
    with patch("requests.get", side_effect=OSError("timeout")):
        provider.fetch_ohlcv("TSLA", 30)
    assert "TSLA" in provider.fallback_symbols


def test_alpaca_reset_cycle_state_clears_tracking():
    provider = _make_provider(fail_safe_to_demo=True)
    with patch("requests.get", side_effect=OSError("timeout")):
        provider.fetch_ohlcv("TSLA", 30)
    assert "TSLA" in provider.fallback_symbols
    provider.reset_cycle_state()
    assert provider.fallback_symbols == []
    assert provider.stale_symbols == []


# --- build_market_data_provider ---

def test_build_market_data_provider_demo_returns_cached_demo():
    provider = build_market_data_provider("demo_generated", Path("."), profiles_by_symbol={})
    # CachedMarketDataProvider wraps demo
    assert provider.name == "demo_generated"


def test_build_market_data_provider_alpaca_iex_returns_alpaca_provider():
    market_data_cfg = {
        "alpaca": {
            "feed": "iex",
            "timeframe": "1Day",
            "adjustment": "raw",
            "request_timeout_seconds": 10,
            "fail_safe_to_demo": True,
            "stale_data_minutes": 20,
        }
    }
    env_patch = {"ALPACA_API_KEY": "key123", "ALPACA_SECRET_KEY": "secret456"}
    with patch.dict(os.environ, env_patch):
        provider = build_market_data_provider("alpaca_iex", Path("."), market_data_config=market_data_cfg)
    assert isinstance(provider, AlpacaIEXProvider)
    assert provider.feed == "iex"
    assert provider.api_key == "key123"


def test_build_alpaca_missing_keys_raises_environment_error():
    market_data_cfg = {"alpaca": {"feed": "iex"}}
    env_without_keys = {k: "" for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")}
    with patch.dict(os.environ, env_without_keys, clear=False):
        os.environ.pop("ALPACA_API_KEY", None)
        os.environ.pop("ALPACA_SECRET_KEY", None)
        with pytest.raises(EnvironmentError, match="ALPACA_API_KEY"):
            build_market_data_provider("alpaca_iex", Path("."), market_data_config=market_data_cfg)


# --- Existing scanner still works with demo provider ---

def test_scanner_still_works_with_demo_provider(tmp_path: Path):
    """Regression: scanner with demo_generated must still pass after V8 changes."""
    from argparse import Namespace
    from trading_bot.cli import run_scan

    universe_path = tmp_path / "universe.yaml"
    config_path = tmp_path / "config.yaml"
    universe_path.write_text(
        """
symbols:
  - symbol: PLTR
    tags: [mid_cap, software]
    universe_role: primary_candidate
    demo_profile: clean_breakout
csv_path:
filters:
  max_universe_size: 5
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {(tmp_path / "test.db").as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {(tmp_path / "cache").as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 5
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
""",
        encoding="utf-8",
    )
    summary = run_scan(Namespace(config=str(config_path), symbols="", save_snapshots=False))
    assert summary["provider"] == "demo_generated"
    assert summary["symbols_scored"] >= 1


# --- Watch mode does not trade (regression) ---

def test_watch_mode_does_not_create_paper_trades(tmp_path: Path):
    from argparse import Namespace
    from trading_bot.cli import run_watch
    from trading_bot.storage.repositories import ScannerRepository

    universe_path = tmp_path / "universe.yaml"
    stop_file = tmp_path / "STOP"
    config_path = tmp_path / "config.yaml"
    universe_path.write_text(
        """
symbols:
  - symbol: PLTR
    tags: [mid_cap]
    universe_role: primary_candidate
    demo_profile: clean_breakout
csv_path:
filters:
  max_universe_size: 2
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {(tmp_path / "watch.db").as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {(tmp_path / "cache").as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 2
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
scheduled_watch:
  enabled: true
  interval_minutes: 0
  run_snapshot_update_after_scan: false
  market_hours_only: false
  stop_file: {stop_file.as_posix()}
""",
        encoding="utf-8",
    )
    summary = run_watch(Namespace(config=str(config_path), max_cycles=1, once=False))
    repo = ScannerRepository(tmp_path / "watch.db")
    assert summary["cycles_completed"] == 1
    assert repo.paper_trades().empty


# ==========================================================================
# V8.5 — Provider Precedence Tests
# ==========================================================================

def _make_settings(**overrides) -> ScannerSettings:
    defaults = dict(
        provider="demo_generated",
        database_path=Path("data/trading_bot.db"),
        outputs_dir=Path("outputs"),
        cache_dir=Path("data/cache"),
        log_dir=Path("logs"),
        lookback_days=120,
        timeframe="daily",
        max_symbols=100,
        min_price=5.0,
        max_price=500.0,
        min_avg_volume=300_000,
        min_dollar_volume=2_000_000,
        score_threshold_watchlist=70.0,
        score_threshold_high_quality=80.0,
        live_trading_enabled=False,
        scoring_config_path=Path("config/scoring_config.yaml"),
        universe_config_path=Path("config/universe_config.yaml"),
    )
    defaults.update(overrides)
    return ScannerSettings(**defaults)


def test_resolve_effective_provider_real_enabled_uses_market_data_provider():
    settings = _make_settings(
        provider="demo_generated",
        market_data={
            "provider": "alpaca_iex",
            "real_provider_enabled": True,
            "fallback_provider": "demo_generated",
        },
    )
    assert resolve_effective_provider(settings) == "alpaca_iex"


def test_resolve_effective_provider_real_disabled_uses_legacy_provider():
    settings = _make_settings(
        provider="demo_generated",
        market_data={
            "provider": "alpaca_iex",
            "real_provider_enabled": False,
        },
    )
    assert resolve_effective_provider(settings) == "demo_generated"


def test_resolve_effective_provider_no_market_data_block_uses_legacy():
    settings = _make_settings(provider="demo_generated", market_data=None)
    assert resolve_effective_provider(settings) == "demo_generated"


def test_resolve_effective_provider_market_data_no_provider_field_uses_legacy():
    settings = _make_settings(
        provider="demo_generated",
        market_data={"real_provider_enabled": True},
    )
    assert resolve_effective_provider(settings) == "demo_generated"


# ==========================================================================
# V8.5 — ProviderHealth: keys_present is bool, never the key value
# ==========================================================================

def test_provider_health_keys_present_is_bool_not_string():
    health = ProviderHealth(
        configured_provider="demo_generated",
        effective_provider="alpaca_iex",
        fallback_provider="demo_generated",
        keys_present=True,
        feed="iex",
        timeframe="1Day",
    )
    assert isinstance(health.keys_present, bool)
    assert health.keys_present is True


def test_provider_health_keys_present_false_when_no_env_keys():
    env_without_keys = {"ALPACA_API_KEY": "", "ALPACA_SECRET_KEY": ""}
    with patch.dict(os.environ, env_without_keys, clear=False):
        os.environ.pop("ALPACA_API_KEY", None)
        os.environ.pop("ALPACA_SECRET_KEY", None)
        health = check_provider_health(
            effective_provider="alpaca_iex",
            configured_provider="alpaca_iex",
            market_data_config={"alpaca": {"feed": "iex"}},
            test_symbols=["PLTR"],
        )
    assert isinstance(health.keys_present, bool)
    assert health.keys_present is False


def test_provider_health_demo_provider_passes_without_keys():
    with patch("requests.get", return_value=_mock_ok_response(SAMPLE_BARS)):
        health = check_provider_health(
            effective_provider="demo_generated",
            configured_provider="demo_generated",
            market_data_config=None,
            test_symbols=["PLTR"],
            lookback_days=3,
        )
    assert health.symbols_requested == 1
    assert health.symbols_with_data == 1
    assert health.keys_present is False
    assert health.passed is True


# ==========================================================================
# V8.5 — All-symbol fallback detection and Tony event
# ==========================================================================

def test_all_symbol_fallback_fires_tony_event(tmp_path: Path):
    """When all scanned symbols fall back to demo, Tony records all_symbol_fallback (critical)."""
    from argparse import Namespace
    from trading_bot.cli import run_scan
    from trading_bot.storage.repositories import ScannerRepository

    universe_path = tmp_path / "universe.yaml"
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "test.db"

    universe_path.write_text(
        """
symbols:
  - symbol: PLTR
    tags: [mid_cap]
    universe_role: primary_candidate
    demo_profile: clean_breakout
csv_path:
filters:
  max_universe_size: 2
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {db_path.as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {(tmp_path / "cache").as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 2
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
market_data:
  provider: alpaca_iex
  fallback_provider: demo_generated
  real_provider_enabled: true
  alpaca:
    enabled: true
    feed: iex
    timeframe: 1Day
    max_symbols_per_scan: 30
    fail_safe_to_demo: true
    stale_data_minutes: 20
tony_stocks:
  enabled: true
  create_events_for:
    - scan_started
    - scan_completed
    - all_symbol_fallback
    - real_provider_active
    - data_provider_fallback
""",
        encoding="utf-8",
    )

    env_patch = {"ALPACA_API_KEY": "fakekey", "ALPACA_SECRET_KEY": "fakesecret"}
    # All Alpaca calls return HTTP 500 → fail_safe_to_demo causes all to fall back
    with patch.dict(os.environ, env_patch):
        with patch("requests.get", return_value=_mock_error_response(500)):
            summary = run_scan(Namespace(config=str(config_path), symbols="", save_snapshots=False))

    repo = ScannerRepository(db_path)
    events = repo.list_tony_events(limit=50)
    event_types = set(events["event_type"].tolist()) if not events.empty else set()
    # All symbols fell back, so all_symbol_fallback should fire (not real_provider_active)
    assert "all_symbol_fallback" in event_types, f"Expected all_symbol_fallback in {event_types}"
    assert "real_provider_active" not in event_types, f"real_provider_active should not fire when all fell back"


# ==========================================================================
# V8.5 — check_provider_health with mocked Alpaca
# ==========================================================================

def test_check_provider_health_alpaca_returns_health_object():
    market_data_cfg = {
        "fallback_provider": "demo_generated",
        "alpaca": {"feed": "iex", "timeframe": "1Day", "fail_safe_to_demo": False},
    }
    env_patch = {"ALPACA_API_KEY": "key123", "ALPACA_SECRET_KEY": "secret456"}
    with patch.dict(os.environ, env_patch):
        with patch("requests.get", return_value=_mock_ok_response(SAMPLE_BARS)):
            health = check_provider_health(
                effective_provider="alpaca_iex",
                configured_provider="alpaca_iex",
                market_data_config=market_data_cfg,
                test_symbols=["PLTR"],
                lookback_days=3,
            )
    assert health.effective_provider == "alpaca_iex"
    assert health.configured_provider == "alpaca_iex"
    assert health.keys_present is True
    assert health.symbols_requested == 1
    assert health.symbols_with_data == 1
    assert health.passed is True
    assert "key123" not in str(health.to_dict())
    assert "secret456" not in str(health.to_dict())


def test_check_provider_health_no_keys_sets_using_fallback():
    market_data_cfg = {
        "alpaca": {"feed": "iex", "fail_safe_to_demo": True},
    }
    env_without_keys = {"ALPACA_API_KEY": "", "ALPACA_SECRET_KEY": ""}
    with patch.dict(os.environ, env_without_keys, clear=False):
        os.environ.pop("ALPACA_API_KEY", None)
        os.environ.pop("ALPACA_SECRET_KEY", None)
        health = check_provider_health(
            effective_provider="alpaca_iex",
            configured_provider="alpaca_iex",
            market_data_config=market_data_cfg,
            test_symbols=["PLTR"],
        )
    assert health.keys_present is False
    assert health.using_fallback is True
    assert len(health.provider_errors) > 0
