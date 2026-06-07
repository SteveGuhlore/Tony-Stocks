"""Tests for the off-hours window guard (Task 1 — pure time classifier).

All datetimes are passed explicitly as ET-aware datetime objects, matching the
project convention in _is_within_regular_market_hours (cli.py ~line 2981).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from trading_bot.analytics.off_hours_window import (
    Phase,
    current_phase,
    is_off_hours,
    next_market_open,
)

ET = ZoneInfo("America/New_York")


def _et(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Construct a timezone-aware datetime in America/New_York."""
    return datetime(year, month, day, hour, minute, tzinfo=ET)


# ── Phase enum sanity ──────────────────────────────────────────────────────────

class TestPhaseEnum:
    def test_all_phases_present(self) -> None:
        assert {p.value for p in Phase} == {
            "market_hours", "pre_open", "post_close", "overnight", "weekend"
        }

    def test_phase_is_str_subclass(self) -> None:
        assert isinstance(Phase.MARKET_HOURS, str)


# ── is_off_hours ───────────────────────────────────────────────────────────────

class TestIsOffHours:
    def test_weekday_market_hours_not_off_hours(self) -> None:
        # Mon 2026-06-01 10:00 ET — inside 09:30–16:00
        now = _et(2026, 6, 1, 10, 0)
        assert is_off_hours(now) is False

    def test_weekday_at_market_open_not_off_hours(self) -> None:
        # Exactly 09:30 → MARKET_HOURS, not off hours
        now = _et(2026, 6, 2, 9, 30)
        assert is_off_hours(now) is False

    def test_weekday_post_close_is_off_hours(self) -> None:
        # Mon 16:45 ET
        now = _et(2026, 6, 1, 16, 45)
        assert is_off_hours(now) is True

    def test_weekday_at_close_boundary_is_off_hours(self) -> None:
        # Exactly 16:00 → POST_CLOSE
        now = _et(2026, 6, 1, 16, 0)
        assert is_off_hours(now) is True

    def test_weekday_overnight_is_off_hours(self) -> None:
        now = _et(2026, 6, 2, 3, 0)
        assert is_off_hours(now) is True

    def test_weekday_pre_open_is_off_hours(self) -> None:
        now = _et(2026, 6, 2, 8, 30)
        assert is_off_hours(now) is True

    def test_saturday_is_off_hours(self) -> None:
        # 2026-06-06 is a Saturday
        now = _et(2026, 6, 6, 12, 0)
        assert is_off_hours(now) is True

    def test_sunday_is_off_hours(self) -> None:
        # 2026-06-07 is a Sunday
        now = _et(2026, 6, 7, 12, 0)
        assert is_off_hours(now) is True


# ── current_phase ──────────────────────────────────────────────────────────────

class TestCurrentPhase:
    def test_weekday_market_hours_phase(self) -> None:
        now = _et(2026, 6, 1, 10, 0)
        assert current_phase(now) == Phase.MARKET_HOURS

    def test_weekday_market_open_boundary_is_market_hours(self) -> None:
        now = _et(2026, 6, 2, 9, 30)
        assert current_phase(now) == Phase.MARKET_HOURS

    def test_weekday_post_close_phase(self) -> None:
        now = _et(2026, 6, 1, 16, 45)
        assert current_phase(now) == Phase.POST_CLOSE

    def test_weekday_close_boundary_is_post_close(self) -> None:
        now = _et(2026, 6, 1, 16, 0)
        assert current_phase(now) == Phase.POST_CLOSE

    def test_weekday_overnight_phase(self) -> None:
        # 03:00 is before 06:00 → OVERNIGHT
        now = _et(2026, 6, 2, 3, 0)
        assert current_phase(now) == Phase.OVERNIGHT

    def test_weekday_midnight_is_overnight(self) -> None:
        now = _et(2026, 6, 2, 0, 0)
        assert current_phase(now) == Phase.OVERNIGHT

    def test_weekday_pre_open_phase(self) -> None:
        # 08:30 is 06:00–09:30 → PRE_OPEN
        now = _et(2026, 6, 2, 8, 30)
        assert current_phase(now) == Phase.PRE_OPEN

    def test_weekday_pre_open_boundary_at_6am(self) -> None:
        # Exactly 06:00 → PRE_OPEN
        now = _et(2026, 6, 2, 6, 0)
        assert current_phase(now) == Phase.PRE_OPEN

    def test_saturday_phase(self) -> None:
        now = _et(2026, 6, 6, 12, 0)
        assert current_phase(now) == Phase.WEEKEND

    def test_sunday_phase(self) -> None:
        now = _et(2026, 6, 7, 12, 0)
        assert current_phase(now) == Phase.WEEKEND

    def test_saturday_overnight_hour_still_weekend(self) -> None:
        # Even at 02:00 on Saturday it's WEEKEND, not OVERNIGHT
        now = _et(2026, 6, 6, 2, 0)
        assert current_phase(now) == Phase.WEEKEND


# ── next_market_open ───────────────────────────────────────────────────────────

class TestNextMarketOpen:
    def test_friday_evening_gives_monday_open(self) -> None:
        # 2026-06-05 (Fri) 18:00 → next open Mon 2026-06-08 09:30
        now = _et(2026, 6, 5, 18, 0)
        expected = _et(2026, 6, 8, 9, 30)
        assert next_market_open(now) == expected

    def test_tuesday_early_morning_gives_same_day_open(self) -> None:
        # Tue 2026-06-02 08:00 → Tue 2026-06-02 09:30
        now = _et(2026, 6, 2, 8, 0)
        expected = _et(2026, 6, 2, 9, 30)
        assert next_market_open(now) == expected

    def test_saturday_gives_monday_open(self) -> None:
        # Sat 2026-06-06 12:00 → Mon 2026-06-08 09:30
        now = _et(2026, 6, 6, 12, 0)
        expected = _et(2026, 6, 8, 9, 30)
        assert next_market_open(now) == expected

    def test_sunday_gives_monday_open(self) -> None:
        # Sun 2026-06-07 12:00 → Mon 2026-06-08 09:30 (different month context)
        now = _et(2026, 6, 7, 12, 0)
        expected = _et(2026, 6, 8, 9, 30)
        assert next_market_open(now) == expected

    def test_during_market_hours_gives_next_day_open(self) -> None:
        # Mon 10:00 ET is INSIDE market hours — next_market_open must be STRICTLY AFTER now
        # so it returns Tue 09:30
        now = _et(2026, 6, 1, 10, 0)
        expected = _et(2026, 6, 2, 9, 30)
        assert next_market_open(now) == expected

    def test_exactly_at_open_boundary_gives_next_day(self) -> None:
        # Exactly 09:30 on a weekday → strictly after, so next day
        now = _et(2026, 6, 1, 9, 30)
        expected = _et(2026, 6, 2, 9, 30)
        assert next_market_open(now) == expected

    def test_result_is_et_aware(self) -> None:
        now = _et(2026, 6, 2, 8, 0)
        result = next_market_open(now)
        assert result.tzinfo is not None
        # Should be 09:30 ET
        assert result.hour == 9
        assert result.minute == 30
