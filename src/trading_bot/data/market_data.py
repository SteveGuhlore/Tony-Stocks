from __future__ import annotations

import abc
import hashlib
import logging
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from trading_bot.data.cache import MarketDataCache
from trading_bot.settings import configured_api_keys
from trading_bot.utils.validation import normalize_ohlcv


LOGGER = logging.getLogger(__name__)


class MarketDataProvider(abc.ABC):
    """Abstract OHLCV provider interface."""

    name = "base"

    @abc.abstractmethod
    def fetch_ohlcv(self, symbol: str, lookback_days: int, timeframe: str = "daily") -> pd.DataFrame:
        """Fetch recent OHLCV bars for a symbol."""


class DemoGeneratedProvider(MarketDataProvider):
    """Deterministic development provider that needs no API keys."""

    name = "demo_generated"

    def __init__(self, profiles_by_symbol: dict[str, str] | None = None) -> None:
        self.profiles_by_symbol = {symbol.upper(): profile for symbol, profile in (profiles_by_symbol or {}).items()}

    def fetch_ohlcv(self, symbol: str, lookback_days: int, timeframe: str = "daily") -> pd.DataFrame:
        if _normalize_timeframe(timeframe) != "1Day":
            return self._fetch_intraday(symbol, lookback_days, timeframe)
        seed = int(hashlib.sha256(symbol.upper().encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        periods = max(lookback_days, 80)
        dates = pd.bdate_range(end=pd.Timestamp(datetime.now(UTC).date()), periods=periods)
        base = 25 + (seed % 250)
        profile = self.profiles_by_symbol.get(symbol.upper(), "")
        returns = self._profile_returns(profile, periods, rng, seed)
        close = np.maximum(base * np.cumprod(1 + returns), 2.0)
        open_ = close * (1 + rng.normal(0, 0.003, size=periods))
        high = np.maximum(open_, close) * (1 + rng.uniform(0.002, 0.018, size=periods))
        low = np.minimum(open_, close) * (1 - rng.uniform(0.002, 0.018, size=periods))
        volume = self._profile_volume(profile, periods, rng, seed)
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=dates,
        )

    def _fetch_intraday(self, symbol: str, lookback_days: int, timeframe: str) -> pd.DataFrame:
        """Return deterministic synthetic intraday bars for tests and demo fallback."""
        seed = int(hashlib.sha256(f"{symbol.upper()}:{timeframe}".encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        minutes = _timeframe_minutes(timeframe)
        bars_per_day = max(1, 390 // minutes)
        periods = max(lookback_days, 1) * bars_per_day
        dates = pd.bdate_range(end=pd.Timestamp(datetime.now(UTC).date()), periods=max(lookback_days, 1))
        timestamps: list[pd.Timestamp] = []
        for day in dates:
            session_start = pd.Timestamp(day.date()).replace(hour=9, minute=30, tzinfo=UTC)
            for idx in range(bars_per_day):
                timestamps.append(session_start + pd.Timedelta(minutes=idx * minutes))
        timestamps = timestamps[-periods:]
        base = 25 + (seed % 250)
        returns = rng.normal(0.00015, 0.0025, size=len(timestamps))
        close = np.maximum(base * np.cumprod(1 + returns), 2.0)
        open_ = close * (1 + rng.normal(0, 0.0015, size=len(timestamps)))
        high = np.maximum(open_, close) * (1 + rng.uniform(0.0005, 0.004, size=len(timestamps)))
        low = np.minimum(open_, close) * (1 - rng.uniform(0.0005, 0.004, size=len(timestamps)))
        volume = np.maximum(10_000, rng.normal(80_000 + (seed % 250_000), 12_000, size=len(timestamps))).astype(int)
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

    def _profile_returns(self, profile: str, periods: int, rng: np.random.Generator, seed: int) -> np.ndarray:
        """Create deterministic return paths with recognizable setup shapes."""
        drift = ((seed % 9) - 2) / 1000
        volatility = 0.012 + ((seed % 7) / 1000)
        returns = rng.normal(drift, volatility, size=periods)
        if profile == "benchmark_index":
            returns = rng.normal(0.00035, 0.006, size=periods)
        elif profile == "steady_mega_cap_trend":
            returns = rng.normal(0.0007, 0.008, size=periods)
        elif profile == "clean_breakout":
            returns = rng.normal(0.0002, 0.011, size=periods)
            returns[-25:-6] = rng.normal(0.0001, 0.004, size=19)
            returns[-6:] = np.array([0.006, 0.008, 0.011, 0.014, 0.009, 0.012])
        elif profile == "pullback_in_uptrend":
            returns = rng.normal(0.0012, 0.01, size=periods)
            returns[-8:] = np.array([-0.006, -0.004, -0.003, 0.001, -0.002, 0.002, 0.003, 0.004])
        elif profile == "momentum_continuation":
            returns = rng.normal(0.0015, 0.014, size=periods)
            returns[-12:] += 0.004
        elif profile == "overextended_runner":
            returns = rng.normal(0.0012, 0.016, size=periods)
            returns[-10:] = np.array([0.012, 0.018, 0.022, 0.017, 0.025, 0.019, 0.014, 0.021, 0.016, 0.018])
        elif profile == "low_volume_chop":
            returns = rng.normal(0.0001, 0.009, size=periods)
            returns[-20:] = rng.normal(0.0, 0.004, size=20)
        elif profile == "high_volatility_whipsaw":
            returns = rng.normal(0.0005, 0.045, size=periods)
        elif profile == "failed_breakout":
            returns = rng.normal(0.0004, 0.018, size=periods)
            returns[-12:-5] = np.array([0.011, 0.016, 0.019, 0.013, 0.017, 0.015, 0.01])
            returns[-5:] = np.array([-0.018, -0.022, -0.014, -0.01, -0.006])
        elif profile == "weak_downtrend":
            returns = rng.normal(-0.0015, 0.014, size=periods)
            returns[-20:] -= 0.002
        elif profile == "base_building":
            returns = rng.normal(0.0006, 0.009, size=periods)
            returns[-25:] = rng.normal(0.0001, 0.004, size=25)
        elif profile == "gap_risk_placeholder":
            returns = rng.normal(0.0008, 0.025, size=periods)
            returns[-15] = 0.12
            returns[-8] = -0.09
        return returns

    def _profile_volume(self, profile: str, periods: int, rng: np.random.Generator, seed: int) -> np.ndarray:
        """Create deterministic volume behavior that matches the setup profile."""
        volume_base = 600_000 + (seed % 8_000_000)
        if profile == "low_volume_chop":
            volume_base = 120_000 + (seed % 250_000)
        elif profile in {"clean_breakout", "momentum_continuation", "overextended_runner"}:
            volume_base *= 1.15
        elif profile == "benchmark_index":
            volume_base *= 1.6
        volume_wave = 1 + 0.15 * np.sin(np.linspace(0, math.pi * 4, periods))
        volume = volume_base * volume_wave * rng.normal(1, 0.08, size=periods)
        if profile == "clean_breakout":
            volume[-6:] *= np.array([1.15, 1.25, 1.45, 1.7, 1.55, 1.8])
        elif profile == "momentum_continuation":
            volume[-10:] *= 1.25
        elif profile == "failed_breakout":
            volume[-12:-5] *= 1.4
            volume[-5:] *= 0.8
        elif profile == "high_volatility_whipsaw":
            volume *= rng.uniform(0.7, 1.8, size=periods)
        return np.maximum(volume, 50_000).astype(int)


class CsvMarketDataProvider(MarketDataProvider):
    """Provider that reads one CSV per symbol from a folder."""

    name = "demo_csv"

    def __init__(self, data_dir: str | Path = "data/demo") -> None:
        self.data_dir = Path(data_dir)

    def fetch_ohlcv(self, symbol: str, lookback_days: int, timeframe: str = "daily") -> pd.DataFrame:
        path = self.data_dir / f"{symbol.upper()}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Demo CSV not found for {symbol}: {path}")
        return normalize_ohlcv(pd.read_csv(path)).tail(lookback_days)


class HttpMarketDataProvider(MarketDataProvider):
    """Placeholder adapter for real HTTP providers.

    TODO: Wire provider-specific endpoints for Polygon, Alpaca, Finnhub,
    Financial Modeling Prep, Twelve Data, or another approved provider.
    """

    name = "http_placeholder"

    def __init__(self, provider_name: str) -> None:
        self.name = provider_name
        self.available_keys = configured_api_keys()

    def fetch_ohlcv(self, symbol: str, lookback_days: int, timeframe: str = "daily") -> pd.DataFrame:
        raise NotImplementedError(
            f"{self.name} provider is not wired yet. Use demo_generated for V1 development."
        )


class RateLimiter:
    """Sliding-window rate limiter for Alpaca API HTTP requests.

    Tracks real request timestamps. Sleeps when the configured safe
    limit (max_per_minute reduced by buffer_percent) would be exceeded.
    Does not track symbols — only HTTP request calls.
    """

    def __init__(
        self,
        max_per_minute: int,
        buffer_percent: int = 15,
        sleep_seconds: float = 0.25,
    ) -> None:
        self.max_per_minute = max(1, int(max_per_minute * (1 - buffer_percent / 100)))
        self.sleep_seconds = sleep_seconds
        self._request_times: deque[float] = deque()
        self.total_requests: int = 0
        self.total_waits: int = 0

    def acquire(self) -> None:
        """Block until a request slot is available."""
        now = time.monotonic()
        while self._request_times and now - self._request_times[0] > 60.0:
            self._request_times.popleft()
        if len(self._request_times) >= self.max_per_minute:
            oldest = self._request_times[0]
            wait = max(0.0, 60.0 - (now - oldest) + 0.05)
            if wait > 0:
                self.total_waits += 1
                LOGGER.info(
                    "Rate limiter: waiting %.1fs (%d/%d requests in window)",
                    wait, len(self._request_times), self.max_per_minute,
                )
                time.sleep(wait)
                now = time.monotonic()
                while self._request_times and now - self._request_times[0] > 60.0:
                    self._request_times.popleft()
        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)
        self._request_times.append(time.monotonic())
        self.total_requests += 1

    def reset(self) -> None:
        self._request_times.clear()
        self.total_requests = 0
        self.total_waits = 0


class AlpacaIEXProvider(MarketDataProvider):
    """Alpaca IEX market data provider for US equities (historical daily bars).

    Uses Alpaca's free-tier IEX feed. IEX is a single-exchange feed and may
    differ from consolidated SIP data. Do not use for production execution data.

    Keys are read from environment variables ALPACA_API_KEY and ALPACA_SECRET_KEY.
    No trading or order endpoints are called — market data only.
    """

    name = "alpaca_iex"
    BASE_URL = "https://data.alpaca.markets/v2/stocks"
    BATCH_URL = "https://data.alpaca.markets/v2/stocks/bars"

    _TIMEFRAME_MAP = {
        "daily": "1Day",
        "1day": "1Day",
        "1Day": "1Day",
        "5Min": "5Min",
        "5min": "5Min",
        "1Min": "1Min",
        "1min": "1Min",
        "15Min": "15Min",
        "15min": "15Min",
        "1Hour": "1Hour",
        "1hour": "1Hour",
    }

    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        feed: str = "iex",
        timeframe: str = "1Day",
        adjustment: str = "raw",
        timeout: int = 15,
        fail_safe_to_demo: bool = True,
        stale_data_minutes: int = 20,
        batch_requests_enabled: bool = True,
        max_symbols_per_batch: int = 175,
        stop_on_rate_limit: bool = False,
        fallback_on_rate_limit: bool = True,
        rate_limiter: "RateLimiter | None" = None,
        profiles_by_symbol: dict[str, str] | None = None,
        _skip_key_check: bool = False,
    ) -> None:
        if not _skip_key_check and (not api_key or not secret_key):
            raise EnvironmentError(
                "Missing ALPACA_API_KEY or ALPACA_SECRET_KEY. "
                "Add them to .env or switch provider to demo_generated."
            )
        self.api_key = api_key
        self.secret_key = secret_key
        self.feed = feed
        self.alpaca_timeframe = timeframe
        self.adjustment = adjustment
        self.timeout = timeout
        self.fail_safe_to_demo = fail_safe_to_demo
        self.stale_data_minutes = stale_data_minutes
        self.batch_requests_enabled = batch_requests_enabled
        self.max_symbols_per_batch = max_symbols_per_batch
        self.stop_on_rate_limit = stop_on_rate_limit
        self.fallback_on_rate_limit = fallback_on_rate_limit
        self._rate_limiter = rate_limiter
        self._demo = DemoGeneratedProvider(profiles_by_symbol=profiles_by_symbol)
        self.fallback_symbols: list[str] = []
        self.missing_symbols: list[str] = []
        self.stale_symbols: list[str] = []
        self._requests_this_cycle: int = 0
        self._batch_requests_this_cycle: int = 0
        self._rate_limit_warnings_this_cycle: int = 0

    def reset_cycle_state(self) -> None:
        """Reset per-scan tracking. Call before each scan cycle."""
        self.fallback_symbols = []
        self.missing_symbols = []
        self.stale_symbols = []
        self._requests_this_cycle = 0
        self._batch_requests_this_cycle = 0
        self._rate_limit_warnings_this_cycle = 0
        if self._rate_limiter:
            self._rate_limiter.reset()

    def get_cycle_stats(self) -> dict[str, Any]:
        """Return per-cycle API usage stats. Safe to include in Tony events and logs."""
        return {
            "api_requests_used": self._requests_this_cycle,
            "batch_requests_used": self._batch_requests_this_cycle,
            "rate_limit_warnings": self._rate_limit_warnings_this_cycle,
            "fallback_count": len(self.fallback_symbols),
            "missing_count": len(self.missing_symbols),
            "stale_count": len(self.stale_symbols),
            "batch_mode": self.batch_requests_enabled,
        }

    def fetch_ohlcv(self, symbol: str, lookback_days: int, timeframe: str = "daily") -> pd.DataFrame:
        try:
            return self._fetch_bars(symbol, lookback_days, timeframe)
        except Exception as exc:
            if self.fail_safe_to_demo:
                LOGGER.warning("Alpaca IEX fallback to demo for %s: %s", symbol, exc)
                self.fallback_symbols.append(symbol)
                return self._demo.fetch_ohlcv(symbol, lookback_days, timeframe)
            self.missing_symbols.append(symbol.upper())
            raise

    def fetch_ohlcv_batch(
        self,
        symbols: list[str],
        lookback_days: int,
        timeframe: str = "daily",
    ) -> dict[str, pd.DataFrame]:
        """Fetch OHLCV bars for multiple symbols in batched API requests.

        Uses Alpaca's multi-symbol /v2/stocks/bars endpoint. Falls back to
        per-symbol fetching if the batch request fails and fail_safe_to_demo is True.
        Returns a dict mapping each symbol to its OHLCV DataFrame.
        """
        if not symbols:
            return {}
        try:
            return self._fetch_bars_batch(symbols, lookback_days, timeframe)
        except Exception as exc:
            if self.fail_safe_to_demo:
                LOGGER.warning(
                    "Alpaca IEX batch fetch failed (%s). Falling back to per-symbol demo.", exc
                )
                result: dict[str, pd.DataFrame] = {}
                for symbol in symbols:
                    self.fallback_symbols.append(symbol)
                    result[symbol] = self._demo.fetch_ohlcv(symbol, lookback_days, timeframe)
                return result
            self.missing_symbols.extend(s.upper() for s in symbols)
            raise

    def _fetch_bars(self, symbol: str, lookback_days: int, timeframe: str) -> pd.DataFrame:
        alpaca_tf = _normalize_timeframe(timeframe, self.alpaca_timeframe)
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=lookback_days + 30)
        headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }
        params: dict[str, Any] = {
            "timeframe": alpaca_tf,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "feed": self.feed,
            "adjustment": self.adjustment,
            "limit": _alpaca_limit_for_timeframe(lookback_days, alpaca_tf),
        }
        all_bars: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            if page_token:
                params["page_token"] = page_token
            if self._rate_limiter:
                self._rate_limiter.acquire()
            resp = requests.get(
                f"{self.BASE_URL}/{symbol.upper()}/bars",
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
            self._requests_this_cycle += 1
            if resp.status_code == 429:
                self._rate_limit_warnings_this_cycle += 1
                LOGGER.warning("Alpaca IEX rate limit (429) for %s. Sleeping 61s.", symbol)
                time.sleep(61)
                continue
            if not resp.ok:
                raise OSError(f"Alpaca IEX HTTP {resp.status_code} for {symbol}: {resp.text[:200]}")
            body = resp.json()
            all_bars.extend(body.get("bars") or [])
            page_token = body.get("next_page_token")
            if not page_token:
                break
        if not all_bars:
            LOGGER.warning("Alpaca IEX returned no bars for %s", symbol)
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        return self._normalize_raw_bars(all_bars, lookback_days, symbol, alpaca_tf)

    def _fetch_bars_batch(
        self,
        symbols: list[str],
        lookback_days: int,
        timeframe: str,
    ) -> dict[str, pd.DataFrame]:
        """Call the multi-symbol Alpaca bars endpoint.

        The BATCH_URL accepts a 'symbols' query param (comma-separated).
        Response: {"bars": {"PLTR": [...], "AAPL": [...]}, "next_page_token": ...}
        """
        alpaca_tf = _normalize_timeframe(timeframe, self.alpaca_timeframe)
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=lookback_days + 30)
        headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }
        upper_symbols = [s.upper() for s in symbols]
        params: dict[str, Any] = {
            "symbols": ",".join(upper_symbols),
            "timeframe": alpaca_tf,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "feed": self.feed,
            "adjustment": self.adjustment,
            "limit": 10000,
        }
        bars_by_symbol: dict[str, list[dict[str, Any]]] = {s: [] for s in upper_symbols}
        page_token: str | None = None
        while True:
            if page_token:
                params["page_token"] = page_token
            if self._rate_limiter:
                self._rate_limiter.acquire()
            resp = requests.get(
                self.BATCH_URL,
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
            self._requests_this_cycle += 1
            self._batch_requests_this_cycle += 1
            if resp.status_code == 429:
                self._rate_limit_warnings_this_cycle += 1
                LOGGER.warning("Alpaca IEX batch rate limit (429). Sleeping 61s.")
                time.sleep(61)
                continue
            if not resp.ok:
                raise OSError(f"Alpaca IEX batch HTTP {resp.status_code}: {resp.text[:200]}")
            body = resp.json()
            raw = body.get("bars") or {}
            for sym, bars in raw.items():
                key = sym.upper()
                if key in bars_by_symbol:
                    bars_by_symbol[key].extend(bars or [])
            page_token = body.get("next_page_token")
            if not page_token:
                break

        result: dict[str, pd.DataFrame] = {}
        for symbol in upper_symbols:
            bars = bars_by_symbol.get(symbol, [])
            if not bars:
                LOGGER.warning("Alpaca IEX batch: no bars for %s", symbol)
                if self.fail_safe_to_demo:
                    self.fallback_symbols.append(symbol)
                    result[symbol] = self._demo.fetch_ohlcv(symbol, lookback_days, timeframe)
                else:
                    self.missing_symbols.append(symbol)
                    result[symbol] = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            else:
                result[symbol] = self._normalize_raw_bars(bars, lookback_days, symbol, alpaca_tf)
        return result

    def _normalize_raw_bars(
        self,
        bars: list[dict[str, Any]],
        lookback_days: int,
        symbol: str,
        alpaca_tf: str,
    ) -> pd.DataFrame:
        """Convert a raw Alpaca bars list to a normalized OHLCV DataFrame."""
        if not bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(bars)
        df["timestamp"] = pd.to_datetime(df["t"], utc=True)
        df = df.set_index("timestamp").sort_index()
        df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df = df[["open", "high", "low", "close", "volume"]].dropna(subset=["close"]).tail(
            _rows_to_keep_for_timeframe(lookback_days, alpaca_tf)
        )
        if alpaca_tf != "1Day" and not df.empty:
            latest_ts = df.index[-1].to_pydatetime()
            age_minutes = (datetime.now(UTC) - latest_ts).total_seconds() / 60
            if age_minutes > self.stale_data_minutes:
                LOGGER.warning(
                    "Alpaca IEX stale data for %s: latest bar is %.0f minutes old", symbol, age_minutes
                )
                self.stale_symbols.append(symbol)
        return df


class CachedMarketDataProvider(MarketDataProvider):
    """Provider wrapper that stores OHLCV results in local CSV cache."""

    def __init__(self, provider: MarketDataProvider, cache: MarketDataCache) -> None:
        self.provider = provider
        self.cache = cache
        self.name = provider.name

    def fetch_ohlcv(self, symbol: str, lookback_days: int, timeframe: str = "daily") -> pd.DataFrame:
        cached = self.cache.load(symbol, lookback_days, timeframe)
        if cached is not None:
            return cached
        data = self.provider.fetch_ohlcv(symbol, lookback_days, timeframe)
        self.cache.save(symbol, lookback_days, data, timeframe)
        return data


def build_market_data_provider(
    provider_name: str,
    cache_dir: str | Path,
    profiles_by_symbol: dict[str, str] | None = None,
    market_data_config: dict[str, Any] | None = None,
) -> MarketDataProvider:
    """Build the configured provider with optional caching.

    For demo providers, caching is applied. For Alpaca IEX, caching is skipped
    so watch mode always fetches the latest real bars.
    """
    if provider_name == "alpaca_iex":
        return _build_alpaca_provider(market_data_config or {}, profiles_by_symbol)
    if provider_name == "demo_generated":
        provider: MarketDataProvider = DemoGeneratedProvider(profiles_by_symbol=profiles_by_symbol)
        if profiles_by_symbol:
            cache_dir = Path(cache_dir) / "profiled_demo_v1"
    elif provider_name == "demo_csv":
        provider = CsvMarketDataProvider()
    else:
        provider = HttpMarketDataProvider(provider_name)
    return CachedMarketDataProvider(provider, MarketDataCache(cache_dir))


def _build_alpaca_provider(
    market_data_config: dict[str, Any],
    profiles_by_symbol: dict[str, str] | None = None,
) -> AlpacaIEXProvider:
    """Construct an AlpacaIEXProvider from config and environment variables."""
    alpaca_cfg = market_data_config.get("alpaca") or {}
    real_only = bool(market_data_config.get("real_data_only", False))
    api_key = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    feed = os.getenv("ALPACA_DATA_FEED") or str(alpaca_cfg.get("feed", "iex"))
    max_rpm = int(alpaca_cfg.get("max_requests_per_minute", 175))
    buffer_pct = int(alpaca_cfg.get("request_buffer_percent", 15))
    sleep_secs = float(alpaca_cfg.get("request_sleep_seconds", 0.25))
    batch_enabled = bool(alpaca_cfg.get("batch_requests_enabled", True))
    rate_limiter = RateLimiter(max_rpm, buffer_pct, sleep_secs) if batch_enabled or max_rpm < 200 else None
    return AlpacaIEXProvider(
        api_key=api_key,
        secret_key=secret_key,
        feed=feed,
        timeframe=str(alpaca_cfg.get("timeframe", "1Day")),
        adjustment=str(alpaca_cfg.get("adjustment", "raw")),
        timeout=int(alpaca_cfg.get("request_timeout_seconds", 15)),
        fail_safe_to_demo=False if real_only else bool(alpaca_cfg.get("fail_safe_to_demo", True)),
        stale_data_minutes=int(alpaca_cfg.get("stale_data_minutes", 20)),
        batch_requests_enabled=batch_enabled,
        max_symbols_per_batch=int(alpaca_cfg.get("max_symbols_per_batch", 175)),
        stop_on_rate_limit=bool(alpaca_cfg.get("stop_on_rate_limit", False)),
        fallback_on_rate_limit=False if real_only else bool(alpaca_cfg.get("fallback_on_rate_limit", True)),
        rate_limiter=rate_limiter,
        profiles_by_symbol=profiles_by_symbol,
    )


def _normalize_timeframe(timeframe: str, fallback: str = "1Day") -> str:
    mapping = AlpacaIEXProvider._TIMEFRAME_MAP
    return mapping.get(str(timeframe), mapping.get(str(timeframe).lower(), mapping.get(str(fallback), "1Day")))


def _timeframe_minutes(timeframe: str) -> int:
    normalized = _normalize_timeframe(timeframe)
    if normalized.endswith("Min"):
        return max(1, int(normalized.replace("Min", "")))
    if normalized.endswith("Hour"):
        return max(1, int(normalized.replace("Hour", "")) * 60)
    return 390


def _rows_to_keep_for_timeframe(lookback_days: int, alpaca_tf: str) -> int:
    if alpaca_tf == "1Day":
        return lookback_days
    return max(1, lookback_days) * max(1, 390 // _timeframe_minutes(alpaca_tf))


def _alpaca_limit_for_timeframe(lookback_days: int, alpaca_tf: str) -> int:
    if alpaca_tf == "1Day":
        return min(lookback_days + 60, 1000)
    return min(max(_rows_to_keep_for_timeframe(lookback_days + 2, alpaca_tf), 100), 10000)


@dataclass
class ProviderHealth:
    """Summary of a provider health check.

    Keys are never stored — only a boolean indicating presence.
    This object is safe to log and pass to Tony events.
    """

    configured_provider: str
    effective_provider: str
    fallback_provider: str
    keys_present: bool
    feed: str
    timeframe: str
    using_fallback: bool = False
    symbols_requested: int = 0
    symbols_with_data: int = 0
    symbols_fallback: int = 0
    symbols_stale: int = 0
    latest_bar_time: str | None = None
    provider_errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.symbols_with_data > 0 and not self.using_fallback

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured_provider": self.configured_provider,
            "effective_provider": self.effective_provider,
            "fallback_provider": self.fallback_provider,
            "keys_present": self.keys_present,
            "feed": self.feed,
            "timeframe": self.timeframe,
            "using_fallback": self.using_fallback,
            "symbols_requested": self.symbols_requested,
            "symbols_with_data": self.symbols_with_data,
            "symbols_fallback": self.symbols_fallback,
            "symbols_stale": self.symbols_stale,
            "latest_bar_time": self.latest_bar_time,
            "provider_errors": self.provider_errors,
            "passed": self.passed,
        }


def check_provider_health(
    effective_provider: str,
    configured_provider: str,
    market_data_config: dict[str, Any] | None,
    test_symbols: list[str] | None = None,
    lookback_days: int = 5,
    profiles_by_symbol: dict[str, str] | None = None,
) -> ProviderHealth:
    """Run a quick provider health check against a small set of symbols.

    No keys or secret values are stored in the returned object — only a
    boolean indicating whether the required keys are present.
    """
    market_data = market_data_config or {}
    alpaca_cfg = market_data.get("alpaca") or {}
    fallback_provider = str(market_data.get("fallback_provider", "demo_generated"))

    if effective_provider == "alpaca_iex":
        feed = str(alpaca_cfg.get("feed", "iex"))
        timeframe = str(alpaca_cfg.get("timeframe", "1Day"))
        keys_present = bool(os.getenv("ALPACA_API_KEY")) and bool(os.getenv("ALPACA_SECRET_KEY"))
    else:
        feed = "n/a"
        timeframe = "daily"
        keys_present = False

    health = ProviderHealth(
        configured_provider=configured_provider,
        effective_provider=effective_provider,
        fallback_provider=fallback_provider,
        keys_present=keys_present,
        feed=feed,
        timeframe=timeframe,
    )

    symbols = test_symbols or ["PLTR", "AAPL", "SPY"]
    health.symbols_requested = len(symbols)

    try:
        provider = build_market_data_provider(
            effective_provider,
            Path("."),
            profiles_by_symbol=profiles_by_symbol,
            market_data_config=market_data_config,
        )
    except EnvironmentError as exc:
        health.provider_errors.append(str(exc))
        health.using_fallback = True
        return health

    bar_times: list[str] = []
    for symbol in symbols:
        try:
            data = provider.fetch_ohlcv(symbol, lookback_days, "daily")
            if not data.empty:
                health.symbols_with_data += 1
                bar_times.append(str(data.index[-1]))
        except Exception as exc:
            health.provider_errors.append(f"{symbol}: {exc}")

    if isinstance(provider, AlpacaIEXProvider):
        health.symbols_fallback = len(provider.fallback_symbols)
        health.symbols_stale = len(provider.stale_symbols)
        if health.symbols_fallback >= health.symbols_requested and health.symbols_requested > 0:
            health.using_fallback = True

    if bar_times:
        health.latest_bar_time = max(bar_times)

    return health
