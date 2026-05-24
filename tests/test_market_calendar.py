"""Tests for NYSE market calendar helper."""
from __future__ import annotations
from datetime import datetime, timezone


def test_market_open_tuesday_midday():
    from trading_bot.api.market_calendar import is_market_open, market_status
    # 2024-01-16 (Tuesday) 14:35 UTC = 9:35 AM ET — open
    ts = datetime(2024, 1, 16, 14, 35, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is True
    s = market_status(ts)
    assert s["open"] is True
    assert s["next_close"] is not None
    assert s["timezone"] == "America/New_York"


def test_market_closed_before_open():
    from trading_bot.api.market_calendar import is_market_open, market_status
    # 2024-01-16 (Tuesday) 13:00 UTC = 8:00 AM ET — before open
    ts = datetime(2024, 1, 16, 13, 0, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is False
    s = market_status(ts)
    assert s["open"] is False
    assert s["next_open"] is not None


def test_market_closed_after_close():
    from trading_bot.api.market_calendar import is_market_open
    # 2024-01-16 (Tuesday) 21:30 UTC = 4:30 PM ET — after close at 21:00 UTC
    ts = datetime(2024, 1, 16, 21, 30, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is False


def test_market_closed_saturday():
    from trading_bot.api.market_calendar import is_market_open, market_status
    # 2024-01-13 (Saturday) 15:00 UTC
    ts = datetime(2024, 1, 13, 15, 0, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is False
    s = market_status(ts)
    assert s["open"] is False
    assert s["next_open"] is not None


def test_next_open_precedes_next_close_when_closed():
    from trading_bot.api.market_calendar import market_status
    # Saturday — next_open is Monday open, next_close is Monday close
    ts = datetime(2024, 1, 13, 15, 0, tzinfo=timezone.utc)
    s = market_status(ts)
    assert s["next_open"] < s["next_close"]


def test_market_closed_holiday():
    from trading_bot.api.market_calendar import is_market_open
    # 2024-01-15 (MLK Day) 15:00 UTC — NYSE closed
    ts = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is False
