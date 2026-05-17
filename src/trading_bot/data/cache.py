from __future__ import annotations

from pathlib import Path

import pandas as pd

from trading_bot.utils.validation import normalize_ohlcv


class MarketDataCache:
    """Small CSV cache to reduce repeated provider calls."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, symbol: str, lookback_days: int) -> Path:
        safe_symbol = symbol.upper().replace("/", "_")
        return self.cache_dir / f"{safe_symbol}_{lookback_days}d.csv"

    def load(self, symbol: str, lookback_days: int) -> pd.DataFrame | None:
        path = self.path_for(symbol, lookback_days)
        if not path.exists():
            return None
        return normalize_ohlcv(pd.read_csv(path))

    def save(self, symbol: str, lookback_days: int, data: pd.DataFrame) -> None:
        path = self.path_for(symbol, lookback_days)
        data.reset_index(names="date").to_csv(path, index=False)

