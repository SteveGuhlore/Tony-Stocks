"""Off-hours window guard — pure time classifier.

Classifies a given America/New_York datetime into a market Phase and provides
a helper to compute the next market open. Zero I/O, zero network.

Edge-window conventions (per spec):
- 09:30 exactly → MARKET_HOURS  (market open)
- 16:00 exactly → POST_CLOSE    (market closed)
- 06:00 exactly → PRE_OPEN      (pre-open begins)
- next_market_open is strictly after *now_et*

Pattern follows _is_within_regular_market_hours in cli.py (ZoneInfo, weekday).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import Enum

__all__ = ["Phase", "is_off_hours", "current_phase", "next_market_open"]

_MARKET_OPEN = time(9, 30)
_MARKET_CLOSE = time(16, 0)
_PRE_OPEN_START = time(6, 0)

# weekday() values: Mon=0 … Fri=4, Sat=5, Sun=6
_WEEKEND = frozenset({5, 6})


class Phase(str, Enum):
    """Market session phases."""

    MARKET_HOURS = "market_hours"
    PRE_OPEN = "pre_open"
    POST_CLOSE = "post_close"
    OVERNIGHT = "overnight"
    WEEKEND = "weekend"


def is_off_hours(now_et: datetime) -> bool:
    """Return False only on weekdays strictly inside [09:30, 16:00).

    Exactly 09:30 → not off hours (market open).
    Exactly 16:00 → off hours (market closed).
    """
    if now_et.weekday() in _WEEKEND:
        return True
    t = now_et.time()
    return not (_MARKET_OPEN <= t < _MARKET_CLOSE)


def current_phase(now_et: datetime) -> Phase:
    """Classify *now_et* into one of the five Phase values.

    Windows (weekdays):
      MARKET_HOURS : 09:30 ≤ t < 16:00
      POST_CLOSE   : 16:00 ≤ t < 24:00
      OVERNIGHT    : 00:00 ≤ t < 06:00
      PRE_OPEN     : 06:00 ≤ t < 09:30
    WEEKEND: all of Saturday and Sunday regardless of time.
    """
    if now_et.weekday() in _WEEKEND:
        return Phase.WEEKEND

    t = now_et.time()

    if _MARKET_OPEN <= t < _MARKET_CLOSE:
        return Phase.MARKET_HOURS
    if t < _PRE_OPEN_START:
        return Phase.OVERNIGHT
    if t < _MARKET_OPEN:
        return Phase.PRE_OPEN
    # t >= _MARKET_CLOSE
    return Phase.POST_CLOSE


def next_market_open(now_et: datetime) -> datetime:
    """Return the next weekday 09:30 ET strictly after *now_et*.

    If *now_et* is a weekday before 09:30, the next open is today at 09:30
    only if that time is strictly in the future relative to *now_et*.
    Exactly at 09:30 counts as "not strictly after", so the next open is the
    following trading day.
    """
    candidate = now_et.replace(hour=9, minute=30, second=0, microsecond=0)

    # Advance by one day if candidate is not strictly after now_et. The time
    # component stays pinned at 09:30, so adding whole days preserves it.
    if candidate <= now_et:
        candidate += timedelta(days=1)

    # Skip weekends
    while candidate.weekday() in _WEEKEND:
        candidate += timedelta(days=1)

    return candidate
