"""Tests for research provider adapters + gather_funnel_signals.

All HTTP is faked via an injected get_json — no network calls, deterministic.
"""
from __future__ import annotations

from datetime import date

from trading_bot.data.research_providers import (
    FinnhubProvider,
    FmpProvider,
    TwelveDataProvider,
    gather_funnel_signals,
)


def fake_get(responses: dict):
    """Return a get_json that maps a substring of the URL to a canned response."""
    def _get(url, params, timeout=12):
        for needle, payload in responses.items():
            if needle in url:
                return payload
        return None
    return _get


class TestFmp:
    def test_inert_without_key(self):
        p = FmpProvider("", fake_get({"stock-screener": [{"symbol": "AAA"}]}))
        assert p.available is False
        assert p.screen() == []
        assert p.earnings_calendar(date(2026, 6, 4), date(2026, 6, 10)) == {}

    def test_screen_returns_uppercased_symbols(self):
        p = FmpProvider("k", fake_get({"stock-screener": [{"symbol": "aaa"}, {"symbol": "BBB"}, {"x": 1}]}))
        assert p.screen() == ["AAA", "BBB"]

    def test_earnings_calendar_keeps_earliest_per_symbol(self):
        p = FmpProvider("k", fake_get({"earning_calendar": [
            {"symbol": "NVDA", "date": "2026-06-09"},
            {"symbol": "NVDA", "date": "2026-06-20"},
            {"symbol": "AMD", "date": "2026-06-11"},
        ]}))
        cal = p.earnings_calendar(date(2026, 6, 4), date(2026, 6, 30))
        assert cal == {"NVDA": date(2026, 6, 9), "AMD": date(2026, 6, 11)}

    def test_revenue_growth_parsed(self):
        p = FmpProvider("k", fake_get({"income-statement-growth": [{"growthRevenue": 0.23}]}))
        assert p.revenue_growth("AAA") == 0.23

    def test_http_failure_degrades_to_empty(self):
        p = FmpProvider("k", fake_get({}))  # returns None for everything
        assert p.screen() == []
        assert p.revenue_growth("AAA") is None


class TestFinnhub:
    def test_news_sentiment_normalized(self):
        p = FinnhubProvider("k", fake_get({"news-sentiment": {"companyNewsScore": 0.75}}))
        # 0.75 -> (0.75-0.5)*2 = 0.5
        assert abs(p.news_sentiment("AAA") - 0.5) < 1e-9

    def test_news_sentiment_bullish_percent_fallback(self):
        p = FinnhubProvider("k", fake_get({"news-sentiment": {"sentiment": {"bullishPercent": 1.0}}}))
        assert p.news_sentiment("AAA") == 1.0

    def test_recommendation_score(self):
        p = FinnhubProvider("k", fake_get({"recommendation": [
            {"strongBuy": 10, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0, "period": "2026-06-01"},
        ]}))
        assert p.recommendation("AAA") == 1.0  # all strong buy

    def test_recommendation_balanced_is_neutralish(self):
        p = FinnhubProvider("k", fake_get({"recommendation": [
            {"strongBuy": 0, "buy": 5, "hold": 0, "sell": 5, "strongSell": 0, "period": "2026-06-01"},
        ]}))
        assert p.recommendation("AAA") == 0.0  # buy*.5 - sell*.5 = 0

    def test_inert_without_key(self):
        p = FinnhubProvider("", fake_get({"news-sentiment": {"companyNewsScore": 0.9}}))
        assert p.news_sentiment("AAA") is None


class TestTwelve:
    def test_quote(self):
        p = TwelveDataProvider("k", fake_get({"quote": {"close": "12.34", "volume": "1000000"}}))
        assert p.quote("AAA") == {"price": 12.34, "volume": 1_000_000.0}

    def test_quote_error_status(self):
        p = TwelveDataProvider("k", fake_get({"quote": {"status": "error", "message": "bad"}}))
        assert p.quote("AAA") is None


class TestGatherFunnelSignals:
    def test_merges_base_metrics_and_enrichment(self):
        getj = fake_get({
            "earning_calendar": [{"symbol": "NVDA", "date": "2026-06-09"}],
            "news-sentiment": {"companyNewsScore": 1.0},
            "recommendation": [{"strongBuy": 1, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}],
        })
        fmp = FmpProvider("k", getj)
        finnhub = FinnhubProvider("k", getj)
        base = {"NVDA": {"price": 120.0, "dollar_volume": 5e9, "relative_strength": 0.2}}
        signals = gather_funnel_signals(
            ["NVDA"], today=date(2026, 6, 4), base_metrics=base,
            fmp=fmp, finnhub=finnhub, earnings_blackout_days=10,
        )
        s = signals["NVDA"]
        assert s.price == 120.0
        assert s.dollar_volume == 5e9
        assert s.relative_strength == 0.2
        assert s.earnings_date == date(2026, 6, 9)
        assert s.news_sentiment == 1.0
        assert s.recommendation_score == 1.0

    def test_enrich_limit_caps_per_symbol_calls(self):
        getj = fake_get({"news-sentiment": {"companyNewsScore": 1.0},
                         "recommendation": [{"strongBuy": 1, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}]})
        finnhub = FinnhubProvider("k", getj)
        signals = gather_funnel_signals(
            ["A", "B", "C"], today=date(2026, 6, 4),
            base_metrics={s: {"price": 10.0} for s in ("A", "B", "C")},
            finnhub=finnhub, enrich_limit=1,
        )
        enriched = [s for s in signals.values() if s.news_sentiment is not None]
        assert len(enriched) == 1  # only first symbol enriched
        # all still carry base price
        assert all(s.price == 10.0 for s in signals.values())

    def test_works_with_no_providers(self):
        signals = gather_funnel_signals(
            ["A"], today=date(2026, 6, 4), base_metrics={"A": {"price": 10.0, "dollar_volume": 1e6}}
        )
        assert signals["A"].price == 10.0
        assert signals["A"].news_sentiment is None
        assert signals["A"].earnings_date is None
