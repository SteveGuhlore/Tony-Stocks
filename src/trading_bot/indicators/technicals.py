from __future__ import annotations

import pandas as pd


def simple_moving_average(series: pd.Series, window: int) -> pd.Series:
    """Calculate a simple moving average."""
    if window <= 0:
        raise ValueError("window must be greater than 0")
    return series.rolling(window=window, min_periods=window).mean()


def exponential_moving_average(series: pd.Series, window: int) -> pd.Series:
    """Calculate an exponential moving average."""
    if window <= 0:
        raise ValueError("window must be greater than 0")
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def crossover_signal(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """Return 1 on bullish crossover, -1 on bearish crossover, otherwise 0."""
    above_now = fast > slow
    above_prev = fast.shift(1) > slow.shift(1)
    signal = pd.Series(0, index=fast.index, dtype="int64")
    signal[(above_now == True) & (above_prev == False)] = 1
    signal[(above_now == False) & (above_prev == True)] = -1
    return signal


def relative_strength_index(series: pd.Series, window: int = 14) -> pd.Series:
    """Calculate RSI using rolling average gains and losses."""
    if window <= 0:
        raise ValueError("window must be greater than 0")
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=window, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).rolling(window=window, min_periods=window).mean()
    rs = gain / loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50)


def average_true_range(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Calculate average true range from OHLCV data."""
    if window <= 0:
        raise ValueError("window must be greater than 0")
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=window, min_periods=window).mean()


def rolling_volatility(series: pd.Series, window: int = 20) -> pd.Series:
    """Calculate rolling standard deviation of daily returns."""
    if window <= 0:
        raise ValueError("window must be greater than 0")
    return series.pct_change().rolling(window=window, min_periods=window).std()


def percent_return(series: pd.Series, periods: int) -> pd.Series:
    """Calculate percent return over N periods."""
    if periods <= 0:
        raise ValueError("periods must be greater than 0")
    return series.pct_change(periods=periods)


def relative_volume(volume: pd.Series, window: int = 20) -> pd.Series:
    """Calculate volume divided by recent average volume."""
    if window <= 0:
        raise ValueError("window must be greater than 0")
    avg_volume = volume.rolling(window=window, min_periods=window).mean()
    return volume / avg_volume.replace(0, pd.NA)


def dollar_volume(close: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
    """Calculate rolling average dollar volume."""
    if window <= 0:
        raise ValueError("window must be greater than 0")
    return (close * volume).rolling(window=window, min_periods=window).mean()


def rolling_high(series: pd.Series, window: int) -> pd.Series:
    """Calculate rolling high."""
    if window <= 0:
        raise ValueError("window must be greater than 0")
    return series.rolling(window=window, min_periods=window).max()


def rolling_low(series: pd.Series, window: int) -> pd.Series:
    """Calculate rolling low."""
    if window <= 0:
        raise ValueError("window must be greater than 0")
    return series.rolling(window=window, min_periods=window).min()

