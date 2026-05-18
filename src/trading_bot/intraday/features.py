from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class IntradayFeatures:
    """Deterministic intraday read derived from OHLCV bars.

    These fields are research signals only. They do not create entries,
    paper trades, broker orders, or live trades.
    """

    symbol: str
    timeframe: str
    data_available: bool
    status: str
    latest_close: float | None = None
    day_open: float | None = None
    high_of_day: float | None = None
    low_of_day: float | None = None
    intraday_change_percent: float | None = None
    range_percent: float | None = None
    volume_so_far: float | None = None
    average_intraday_volume: float | None = None
    intraday_relative_volume: float | None = None
    trend_since_open: str = "intraday_data_missing"
    distance_from_high_percent: float | None = None
    distance_from_low_percent: float | None = None
    vwap: float | None = None
    price_above_vwap: bool | None = None
    distance_from_vwap_percent: float | None = None
    vwap_reclaim_candidate: bool = False
    vwap_loss_warning: bool = False
    opening_range_high: float | None = None
    opening_range_low: float | None = None
    above_opening_range: bool | None = None
    below_opening_range: bool | None = None
    opening_range_breakout_candidate: bool = False
    opening_range_breakdown_warning: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable dictionary."""
        return asdict(self)


def calculate_intraday_features(
    symbol: str,
    bars: pd.DataFrame | None,
    timeframe: str = "5Min",
    opening_range_minutes: int = 30,
) -> IntradayFeatures:
    """Calculate compact intraday features from one session of OHLCV bars."""
    if bars is None or bars.empty:
        return IntradayFeatures(symbol=symbol, timeframe=timeframe, data_available=False, status="intraday_data_missing")

    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(set(bars.columns)):
        return IntradayFeatures(symbol=symbol, timeframe=timeframe, data_available=False, status="intraday_data_missing")

    data = bars.copy().dropna(subset=["open", "high", "low", "close"])
    if data.empty:
        return IntradayFeatures(symbol=symbol, timeframe=timeframe, data_available=False, status="intraday_data_missing")

    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index, utc=True, errors="coerce")
        data = data[~data.index.isna()]
    if data.empty:
        return IntradayFeatures(symbol=symbol, timeframe=timeframe, data_available=False, status="intraday_data_missing")

    data = data.sort_index()
    latest_session = data.index[-1].date()
    session = data[data.index.date == latest_session].copy()
    if session.empty:
        session = data.tail(1).copy()

    latest_close = _safe_float(session["close"].iloc[-1])
    day_open = _safe_float(session["open"].iloc[0])
    high_of_day = _safe_float(session["high"].max())
    low_of_day = _safe_float(session["low"].min())
    volume_so_far = _safe_float(session["volume"].sum())
    avg_intraday_volume = _average_session_volume(data)
    intraday_relative_volume = (
        round(volume_so_far / avg_intraday_volume, 6)
        if avg_intraday_volume and avg_intraday_volume > 0
        else None
    )

    change_pct = _pct(latest_close, day_open)
    range_pct = ((high_of_day - low_of_day) / day_open) if day_open and day_open > 0 else None
    distance_high = ((latest_close / high_of_day) - 1) if high_of_day and high_of_day > 0 else None
    distance_low = ((latest_close / low_of_day) - 1) if low_of_day and low_of_day > 0 else None
    trend = "intraday_trend_up" if change_pct is not None and change_pct > 0 else "intraday_trend_down" if change_pct is not None and change_pct < 0 else "intraday_trend_flat"

    vwap = _session_vwap(session)
    price_above_vwap = latest_close > vwap if vwap else None
    distance_vwap = _pct(latest_close, vwap) if vwap else None
    vwap_reclaim = bool(vwap and latest_close > vwap and float(session["low"].tail(min(3, len(session))).min()) <= vwap)
    vwap_loss = bool(vwap and latest_close < vwap and float(session["high"].tail(min(3, len(session))).max()) >= vwap)

    or_high, or_low = _opening_range(session, timeframe, opening_range_minutes)
    above_or = latest_close > or_high if or_high else None
    below_or = latest_close < or_low if or_low else None
    or_breakout = bool(or_high and latest_close > or_high and high_of_day >= latest_close)
    or_breakdown = bool(or_low and latest_close < or_low and low_of_day <= latest_close)

    status = "ok"
    if vwap is None:
        status = "intraday_vwap_unavailable"
    if or_high is None or or_low is None:
        status = "intraday_opening_range_unavailable"

    return IntradayFeatures(
        symbol=symbol.upper(),
        timeframe=timeframe,
        data_available=True,
        status=status,
        latest_close=round(latest_close, 6),
        day_open=round(day_open, 6),
        high_of_day=round(high_of_day, 6),
        low_of_day=round(low_of_day, 6),
        intraday_change_percent=round(change_pct, 6) if change_pct is not None else None,
        range_percent=round(range_pct, 6) if range_pct is not None else None,
        volume_so_far=round(volume_so_far, 2),
        average_intraday_volume=round(avg_intraday_volume, 2) if avg_intraday_volume is not None else None,
        intraday_relative_volume=intraday_relative_volume,
        trend_since_open=trend,
        distance_from_high_percent=round(distance_high, 6) if distance_high is not None else None,
        distance_from_low_percent=round(distance_low, 6) if distance_low is not None else None,
        vwap=round(vwap, 6) if vwap is not None else None,
        price_above_vwap=price_above_vwap,
        distance_from_vwap_percent=round(distance_vwap, 6) if distance_vwap is not None else None,
        vwap_reclaim_candidate=vwap_reclaim,
        vwap_loss_warning=vwap_loss,
        opening_range_high=round(or_high, 6) if or_high is not None else None,
        opening_range_low=round(or_low, 6) if or_low is not None else None,
        above_opening_range=above_or,
        below_opening_range=below_or,
        opening_range_breakout_candidate=or_breakout,
        opening_range_breakdown_warning=or_breakdown,
    )


def _safe_float(value: Any) -> float:
    return float(value or 0.0)


def _pct(value: float, basis: float) -> float | None:
    if not basis:
        return None
    return value / basis - 1


def _session_vwap(session: pd.DataFrame) -> float | None:
    volume = pd.to_numeric(session["volume"], errors="coerce").fillna(0)
    if float(volume.sum()) <= 0:
        return None
    typical = (session["high"].astype(float) + session["low"].astype(float) + session["close"].astype(float)) / 3
    return float((typical * volume).sum() / volume.sum())


def _average_session_volume(data: pd.DataFrame) -> float | None:
    if data.empty:
        return None
    volumes = data.copy()
    volumes["_session"] = volumes.index.date
    grouped = volumes.groupby("_session")["volume"].sum()
    historical = grouped.iloc[:-1] if len(grouped) > 1 else grouped
    if historical.empty:
        return None
    value = float(pd.to_numeric(historical, errors="coerce").dropna().mean())
    return value if value > 0 else None


def _opening_range(
    session: pd.DataFrame,
    timeframe: str,
    opening_range_minutes: int,
) -> tuple[float | None, float | None]:
    if session.empty:
        return None, None
    minutes_per_bar = _timeframe_minutes(timeframe)
    bars_needed = max(1, opening_range_minutes // minutes_per_bar)
    if len(session) < bars_needed:
        return None, None
    opening = session.head(bars_needed)
    return float(opening["high"].max()), float(opening["low"].min())


def _timeframe_minutes(timeframe: str) -> int:
    value = str(timeframe).lower()
    if value.endswith("min"):
        return max(1, int(value.replace("min", "")))
    if value.endswith("hour"):
        return max(1, int(value.replace("hour", "")) * 60)
    return 5
