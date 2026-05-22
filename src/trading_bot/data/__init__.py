from __future__ import annotations

from pathlib import Path

import pandas as pd

from trading_bot.data.market_data import DemoGeneratedProvider, MarketDataProvider
from trading_bot.utils.validation import normalize_ohlcv


def load_csv(path: str | Path) -> pd.DataFrame:
    """Compatibility loader for existing backtest code."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    return normalize_ohlcv(pd.read_csv(csv_path))


def load_yfinance(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Compatibility loader for existing backtest code."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is not installed. Run: pip install -r requirements.txt") from exc
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}' and period '{period}'.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return normalize_ohlcv(df)


def load_yfinance_range(ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Fetch OHLCV bars for a specific date range via yfinance."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is not installed. Run: pip install -r requirements.txt") from exc
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}' (start={start}, end={end}).")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return normalize_ohlcv(df)


__all__ = ["DemoGeneratedProvider", "MarketDataProvider", "load_csv", "load_yfinance", "load_yfinance_range", "normalize_ohlcv"]

