from __future__ import annotations

import abc
import hashlib
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trading_bot.data.cache import MarketDataCache
from trading_bot.settings import configured_api_keys
from trading_bot.utils.validation import normalize_ohlcv


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
        if timeframe != "daily":
            raise ValueError("DemoGeneratedProvider only supports daily timeframe.")
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


class CachedMarketDataProvider(MarketDataProvider):
    """Provider wrapper that stores OHLCV results in local CSV cache."""

    def __init__(self, provider: MarketDataProvider, cache: MarketDataCache) -> None:
        self.provider = provider
        self.cache = cache
        self.name = provider.name

    def fetch_ohlcv(self, symbol: str, lookback_days: int, timeframe: str = "daily") -> pd.DataFrame:
        cached = self.cache.load(symbol, lookback_days)
        if cached is not None:
            return cached
        data = self.provider.fetch_ohlcv(symbol, lookback_days, timeframe)
        self.cache.save(symbol, lookback_days, data)
        return data


def build_market_data_provider(
    provider_name: str,
    cache_dir: str | Path,
    profiles_by_symbol: dict[str, str] | None = None,
) -> MarketDataProvider:
    """Build the configured provider with caching."""
    if provider_name == "demo_generated":
        provider: MarketDataProvider = DemoGeneratedProvider(profiles_by_symbol=profiles_by_symbol)
        if profiles_by_symbol:
            cache_dir = Path(cache_dir) / "profiled_demo_v1"
    elif provider_name == "demo_csv":
        provider = CsvMarketDataProvider()
    else:
        provider = HttpMarketDataProvider(provider_name)
    return CachedMarketDataProvider(provider, MarketDataCache(cache_dir))
