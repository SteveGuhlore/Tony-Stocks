"""Tests for catalyst_enrichment — pure classification core.

TDD: these tests are written before the implementation and define the contract.
"""
from __future__ import annotations

from datetime import date

import pytest

from trading_bot.analytics.catalyst_enrichment import CatalystTags, build_catalyst_tags


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY = date(2026, 6, 6)

_REC_A = {"strongBuy": 5, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0}
# net_A = 5*2 + 10 - 1 - 0*2 = 10 + 10 - 1 = 19

_REC_B = {"strongBuy": 2, "buy": 5, "hold": 3, "sell": 4, "strongSell": 1}
# net_B = 2*2 + 5 - 4 - 1*2 = 4 + 5 - 4 - 2 = 3


# ---------------------------------------------------------------------------
# earnings_blackout
# ---------------------------------------------------------------------------


class TestEarningsBlackout:
    def test_within_blackout_window(self):
        """3 days out with blackout_days=5 → blackout True."""
        earnings = date(2026, 6, 9)  # 3 days after _TODAY
        tags = build_catalyst_tags(
            "AAPL",
            earnings_date=earnings,
            today=_TODAY,
            blackout_days=5,
        )
        assert tags.earnings_blackout is True

    def test_at_boundary_exactly_blackout_days(self):
        """Exactly blackout_days out → still blackout True (inclusive)."""
        earnings = date(2026, 6, 11)  # 5 days after _TODAY
        tags = build_catalyst_tags(
            "AAPL",
            earnings_date=earnings,
            today=_TODAY,
            blackout_days=5,
        )
        assert tags.earnings_blackout is True

    def test_beyond_blackout_window(self):
        """10 days out → blackout False."""
        earnings = date(2026, 6, 16)  # 10 days after _TODAY
        tags = build_catalyst_tags(
            "AAPL",
            earnings_date=earnings,
            today=_TODAY,
            blackout_days=5,
        )
        assert tags.earnings_blackout is False

    def test_none_earnings_date(self):
        """No earnings date → blackout False."""
        tags = build_catalyst_tags("AAPL", today=_TODAY)
        assert tags.earnings_blackout is False

    def test_past_earnings_date_not_blackout(self):
        """Past earnings date (negative delta) → blackout False."""
        earnings = date(2026, 6, 4)  # 2 days before _TODAY
        tags = build_catalyst_tags(
            "AAPL",
            earnings_date=earnings,
            today=_TODAY,
            blackout_days=5,
        )
        assert tags.earnings_blackout is False

    def test_earnings_today_is_blackout(self):
        """Same day as today → delta=0, still within window → True."""
        tags = build_catalyst_tags(
            "AAPL",
            earnings_date=_TODAY,
            today=_TODAY,
            blackout_days=5,
        )
        assert tags.earnings_blackout is True

    def test_earnings_date_as_iso_string(self):
        """earnings_date may be passed as ISO string and stored correctly."""
        tags = build_catalyst_tags(
            "AAPL",
            earnings_date="2026-06-09",
            today=_TODAY,
            blackout_days=5,
        )
        assert tags.earnings_blackout is True
        assert tags.upcoming_earnings_date == "2026-06-09"

    def test_upcoming_earnings_date_stored_as_iso_string(self):
        """date object is stored as ISO string on the tag."""
        earnings = date(2026, 6, 9)
        tags = build_catalyst_tags(
            "AAPL",
            earnings_date=earnings,
            today=_TODAY,
        )
        assert tags.upcoming_earnings_date == "2026-06-09"

    def test_no_earnings_date_upcoming_is_none(self):
        """When no earnings date provided, upcoming_earnings_date is None."""
        tags = build_catalyst_tags("AAPL", today=_TODAY)
        assert tags.upcoming_earnings_date is None

    def test_blackout_days_zero_only_today(self):
        """blackout_days=0 → only earnings today triggers blackout."""
        today_tags = build_catalyst_tags(
            "AAPL", earnings_date=_TODAY, today=_TODAY, blackout_days=0
        )
        tomorrow_tags = build_catalyst_tags(
            "AAPL", earnings_date=date(2026, 6, 7), today=_TODAY, blackout_days=0
        )
        assert today_tags.earnings_blackout is True
        assert tomorrow_tags.earnings_blackout is False

    def test_malformed_iso_string_degrades_safely(self):
        """A junk earnings_date string → no blackout, upcoming date None."""
        tags = build_catalyst_tags(
            "AAPL", earnings_date="not-a-date", today=_TODAY, blackout_days=5
        )
        assert tags.earnings_blackout is False
        assert tags.upcoming_earnings_date is None


# ---------------------------------------------------------------------------
# analyst_rec_trend
# ---------------------------------------------------------------------------


class TestAnalystRecTrend:
    def test_net_now_greater_than_prev_is_up(self):
        """net_now > net_prev → trend 'up'."""
        # net_A=19 > net_B=3
        tags = build_catalyst_tags(
            "AAPL",
            today=_TODAY,
            recommendation_now=_REC_A,
            recommendation_prev=_REC_B,
        )
        assert tags.analyst_rec_trend == "up"

    def test_net_now_less_than_prev_is_down(self):
        """net_now < net_prev → trend 'down'."""
        # net_B=3 < net_A=19
        tags = build_catalyst_tags(
            "AAPL",
            today=_TODAY,
            recommendation_now=_REC_B,
            recommendation_prev=_REC_A,
        )
        assert tags.analyst_rec_trend == "down"

    def test_net_now_equal_to_prev_is_flat(self):
        """Same dict → nets equal → trend 'flat'."""
        tags = build_catalyst_tags(
            "AAPL",
            today=_TODAY,
            recommendation_now=_REC_A,
            recommendation_prev=_REC_A,
        )
        assert tags.analyst_rec_trend == "flat"

    def test_missing_recommendation_now_is_flat(self):
        """Missing rec_now → 'flat'."""
        tags = build_catalyst_tags(
            "AAPL",
            today=_TODAY,
            recommendation_prev=_REC_A,
        )
        assert tags.analyst_rec_trend == "flat"

    def test_missing_recommendation_prev_is_flat(self):
        """Missing rec_prev → 'flat'."""
        tags = build_catalyst_tags(
            "AAPL",
            today=_TODAY,
            recommendation_now=_REC_A,
        )
        assert tags.analyst_rec_trend == "flat"

    def test_both_missing_is_flat(self):
        """Both missing → 'flat'."""
        tags = build_catalyst_tags("AAPL", today=_TODAY)
        assert tags.analyst_rec_trend == "flat"

    def test_net_calculation_strong_buys_and_sells(self):
        """Verify net formula: strongBuy*2 + buy - sell - strongSell*2."""
        # net = 1*2 + 0 - 0 - 1*2 = 0 → flat vs any equal net
        rec_zero = {"strongBuy": 1, "buy": 0, "hold": 0, "sell": 0, "strongSell": 1}
        # net_zero = 0
        rec_pos = {"strongBuy": 1, "buy": 1, "hold": 0, "sell": 0, "strongSell": 0}
        # net_pos = 2 + 1 = 3
        tags = build_catalyst_tags(
            "AAPL",
            today=_TODAY,
            recommendation_now=rec_pos,
            recommendation_prev=rec_zero,
        )
        assert tags.analyst_rec_trend == "up"

    def test_empty_dicts_treated_as_flat(self):
        """Empty dicts → no data → flat."""
        tags = build_catalyst_tags(
            "AAPL",
            today=_TODAY,
            recommendation_now={},
            recommendation_prev={},
        )
        assert tags.analyst_rec_trend == "flat"

    def test_empty_dict_vs_populated_is_flat(self):
        """An empty dict means 'no data', not an all-zero neutral reading,
        so it degrades to flat even against a populated previous snapshot."""
        tags = build_catalyst_tags(
            "AAPL",
            today=_TODAY,
            recommendation_now={},
            recommendation_prev=_REC_A,
        )
        assert tags.analyst_rec_trend == "flat"

    def test_malformed_rec_dict_degrades_to_flat(self):
        """Non-numeric counts → safe-default to flat (no crash)."""
        tags = build_catalyst_tags(
            "AAPL",
            today=_TODAY,
            recommendation_now={"strongBuy": "garbage", "buy": None},
            recommendation_prev=_REC_A,
        )
        assert tags.analyst_rec_trend == "flat"


# ---------------------------------------------------------------------------
# to_dict — key contract
# ---------------------------------------------------------------------------


class TestToDict:
    EXPECTED_KEYS = {
        "symbol",
        "upcoming_earnings_date",
        "earnings_blackout",
        "analyst_rec_trend",
        "news_sentiment",
        "revenue_growth",
    }

    def test_to_dict_keys_match_contract(self):
        tags = build_catalyst_tags("TSLA", today=_TODAY)
        assert set(tags.to_dict().keys()) == self.EXPECTED_KEYS

    def test_to_dict_keys_with_all_fields(self):
        tags = build_catalyst_tags(
            "TSLA",
            earnings_date=date(2026, 6, 9),
            today=_TODAY,
            blackout_days=5,
            recommendation_now=_REC_A,
            recommendation_prev=_REC_B,
            news_sentiment=0.42,
            revenue_growth=0.15,
        )
        d = tags.to_dict()
        assert set(d.keys()) == self.EXPECTED_KEYS

    def test_to_dict_values_correct(self):
        tags = build_catalyst_tags(
            "TSLA",
            earnings_date=date(2026, 6, 9),
            today=_TODAY,
            blackout_days=5,
            recommendation_now=_REC_A,
            recommendation_prev=_REC_B,
            news_sentiment=0.42,
            revenue_growth=0.15,
        )
        d = tags.to_dict()
        assert d["symbol"] == "TSLA"
        assert d["upcoming_earnings_date"] == "2026-06-09"
        assert d["earnings_blackout"] is True
        assert d["analyst_rec_trend"] == "up"
        assert d["news_sentiment"] == pytest.approx(0.42)
        assert d["revenue_growth"] == pytest.approx(0.15)

    def test_to_dict_none_passthrough_fields(self):
        """news_sentiment and revenue_growth default to None and appear in dict."""
        tags = build_catalyst_tags("TSLA", today=_TODAY)
        d = tags.to_dict()
        assert d["news_sentiment"] is None
        assert d["revenue_growth"] is None


# ---------------------------------------------------------------------------
# Pass-through optional floats
# ---------------------------------------------------------------------------


class TestPassthroughFloats:
    def test_news_sentiment_stored(self):
        tags = build_catalyst_tags("AAPL", today=_TODAY, news_sentiment=-0.3)
        assert tags.news_sentiment == pytest.approx(-0.3)

    def test_revenue_growth_stored(self):
        tags = build_catalyst_tags("AAPL", today=_TODAY, revenue_growth=0.25)
        assert tags.revenue_growth == pytest.approx(0.25)

    def test_both_none_by_default(self):
        tags = build_catalyst_tags("AAPL", today=_TODAY)
        assert tags.news_sentiment is None
        assert tags.revenue_growth is None


# ---------------------------------------------------------------------------
# symbol stored correctly
# ---------------------------------------------------------------------------


class TestSymbol:
    def test_symbol_stored_verbatim(self):
        tags = build_catalyst_tags("NVDA", today=_TODAY)
        assert tags.symbol == "NVDA"

    def test_frozen_dataclass(self):
        """CatalystTags is frozen — mutation should raise."""
        tags = build_catalyst_tags("AAPL", today=_TODAY)
        with pytest.raises((AttributeError, TypeError)):
            tags.symbol = "TSLA"  # type: ignore[misc]
