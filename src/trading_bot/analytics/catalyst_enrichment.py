"""Catalyst enrichment — pure classification core (off-hours research engine).

Computes lightweight catalyst tags for a single symbol from optional inputs:
  - upcoming earnings date / blackout window
  - Finnhub-style analyst recommendation snapshots (trend direction)
  - pass-through sentiment / growth floats

Pure + deterministic — no I/O, no network. Safe defaults everywhere; any missing
or malformed input degrades gracefully to neutral values.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


def _parse_date(value: date | str | None) -> date | None:
    """Return a ``date`` object or None; accepts ``date`` or ISO 'YYYY-MM-DD' string."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _rec_net(rec: dict[str, Any] | None) -> int | None:
    """Compute Finnhub recommendation net score.

    net = strongBuy*2 + buy - sell - strongSell*2

    Returns None when there is no usable snapshot — a missing (``None``) or
    empty dict both mean "no data" and degrade the trend to ``"flat"`` rather
    than being treated as an all-zero "neutral" reading.
    """
    if not rec:  # None or empty dict → no data
        return None
    try:
        strong_buy = int(rec.get("strongBuy", 0) or 0)
        buy = int(rec.get("buy", 0) or 0)
        sell = int(rec.get("sell", 0) or 0)
        strong_sell = int(rec.get("strongSell", 0) or 0)
    except (TypeError, ValueError):
        return None
    return strong_buy * 2 + buy - sell - strong_sell * 2


def _trend(net_now: int | None, net_prev: int | None) -> str:
    """Return 'up', 'down', or 'flat' from two net scores."""
    if net_now is None or net_prev is None:
        return "flat"
    diff = net_now - net_prev
    if diff > 0:
        return "up"
    if diff < 0:
        return "down"
    return "flat"


@dataclass(frozen=True)
class CatalystTags:
    """Immutable catalyst tag bundle for a single symbol."""

    symbol: str
    upcoming_earnings_date: str | None = None
    earnings_blackout: bool = False
    analyst_rec_trend: str = "flat"  # "up" | "down" | "flat"
    news_sentiment: float | None = None
    revenue_growth: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "upcoming_earnings_date": self.upcoming_earnings_date,
            "earnings_blackout": self.earnings_blackout,
            "analyst_rec_trend": self.analyst_rec_trend,
            "news_sentiment": self.news_sentiment,
            "revenue_growth": self.revenue_growth,
        }


def build_catalyst_tags(
    symbol: str,
    *,
    earnings_date: date | str | None = None,
    today: date,
    blackout_days: int = 5,
    recommendation_now: dict[str, Any] | None = None,
    recommendation_prev: dict[str, Any] | None = None,
    news_sentiment: float | None = None,
    revenue_growth: float | None = None,
) -> CatalystTags:
    """Build a :class:`CatalystTags` for *symbol* from optional catalyst inputs.

    Parameters
    ----------
    symbol:
        Ticker symbol (stored verbatim).
    earnings_date:
        Optional upcoming earnings date — ``date`` object or ISO 'YYYY-MM-DD' string.
    today:
        Reference date for blackout calculation (required keyword-only).
    blackout_days:
        Inclusive window: ``0 <= (earnings_date - today).days <= blackout_days``
        → ``earnings_blackout=True``.
    recommendation_now / recommendation_prev:
        Finnhub-style dicts ``{strongBuy, buy, hold, sell, strongSell}``.
        If either is missing the trend defaults to ``"flat"``.
    news_sentiment:
        Pass-through float (no computation).
    revenue_growth:
        Pass-through float (no computation).
    """
    # --- earnings date / blackout ---
    parsed_date = _parse_date(earnings_date)
    if parsed_date is not None:
        upcoming_earnings_date_str: str | None = parsed_date.isoformat()
        delta = (parsed_date - today).days
        blackout = 0 <= delta <= blackout_days
    else:
        upcoming_earnings_date_str = None
        blackout = False

    # --- analyst recommendation trend ---
    net_now = _rec_net(recommendation_now)
    net_prev = _rec_net(recommendation_prev)
    rec_trend = _trend(net_now, net_prev)

    return CatalystTags(
        symbol=symbol,
        upcoming_earnings_date=upcoming_earnings_date_str,
        earnings_blackout=blackout,
        analyst_rec_trend=rec_trend,
        news_sentiment=news_sentiment,
        revenue_growth=revenue_growth,
    )
