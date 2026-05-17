from __future__ import annotations

import pandas as pd


REQUIRED_OHLCV_COLUMNS = {"open", "high", "low", "close", "volume"}


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV data to lower-case columns and a DatetimeIndex."""
    if df.empty:
        raise ValueError("OHLCV data is empty.")
    result = df.copy()
    result.columns = [str(col).lower().strip() for col in result.columns]
    if "date" in result.columns:
        result["date"] = pd.to_datetime(result["date"])
        result = result.set_index("date")
    elif not isinstance(result.index, pd.DatetimeIndex):
        result.index = pd.to_datetime(result.index)
    missing = REQUIRED_OHLCV_COLUMNS - set(result.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {', '.join(sorted(missing))}")
    result = result.sort_index()
    return result[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])

