"""Tests for research provider adapters + gather_funnel_signals.

All HTTP is faked via an injected get_json — no network calls, deterministic.
"""
from __future__ import annotations

from datetime import date

from trading_bot.data.research_providers import (
    FinnhubProvider,
    FmpProvider,
    RecommendationCache,
    TwelveDataProvider,
    gather_funnel_signals,
    warm_recommendation_cache,
)


def fake_get(responses: dict):
    """Return a get_json that maps a substring of the URL to a canned response."""
    def _get(url, params, timeout=12):
        for needle, payload in responses.items():
            if needle in url:
                return payload
        return None
    return _get


def counting_get(responses: dict):
    """Like fake_get but records every URL hit on the returned callable's ``.calls``."""
    calls: list[str] = []

    def _get(url, params, timeout=12):
        calls.append(url)
        for needle, payload in responses.items():
            if needle in url:
                return payload
        return None

    _get.calls = calls  # type: ignore[attr-defined]
    return _get


class TestFmp:
    def test_inert_without_key(self):
        p = FmpProvider("", fake_get({"company-screener": [{"symbol": "AAA"}]}))
        assert p.available is False
        assert p.screen() == []
        assert p.earnings_calendar(date(2026, 6, 4), date(2026, 6, 10)) == {}

    def test_screen_returns_uppercased_symbols(self):
        p = FmpProvider("k", fake_get({"company-screener": [{"symbol": "aaa"}, {"symbol": "BBB"}, {"x": 1}]}))
        assert p.screen() == ["AAA", "BBB"]

    def test_earnings_calendar_keeps_earliest_per_symbol(self):
        p = FmpProvider("k", fake_get({"earnings-calendar": [
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
            "earnings-calendar": [{"symbol": "NVDA", "date": "2026-06-09"}],
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


class TestRecommendationCache:
    def test_put_then_get_fresh_same_day_is_hit(self, tmp_path):
        cache = RecommendationCache(tmp_path / "reco.json")
        cache.put("AAA", 0.8, date(2026, 6, 4))
        assert cache.get_fresh("AAA", date(2026, 6, 4)) == (True, 0.8)

    def test_missing_symbol_is_miss(self, tmp_path):
        cache = RecommendationCache(tmp_path / "reco.json")
        assert cache.get_fresh("ZZZ", date(2026, 6, 4)) == (False, None)

    def test_stale_entry_is_miss(self, tmp_path):
        cache = RecommendationCache(tmp_path / "reco.json")
        cache.put("AAA", 0.8, date(2026, 6, 3))
        # next day -> stale (ttl 1 day) -> miss, so it gets refetched
        assert cache.get_fresh("AAA", date(2026, 6, 4)) == (False, None)

    def test_cached_none_score_is_still_a_fresh_hit(self, tmp_path):
        # A symbol Finnhub has no coverage for caches as None for the day so we
        # don't re-hammer it every cycle.
        cache = RecommendationCache(tmp_path / "reco.json")
        cache.put("AAA", None, date(2026, 6, 4))
        assert cache.get_fresh("AAA", date(2026, 6, 4)) == (True, None)

    def test_round_trips_through_save_and_load(self, tmp_path):
        path = tmp_path / "reco.json"
        cache = RecommendationCache(path)
        cache.put("AAA", 0.5, date(2026, 6, 4))
        cache.put("BBB", -0.25, date(2026, 6, 4))
        cache.save()

        reloaded = RecommendationCache(path)
        reloaded.load()
        assert reloaded.get_fresh("AAA", date(2026, 6, 4)) == (True, 0.5)
        assert reloaded.get_fresh("BBB", date(2026, 6, 4)) == (True, -0.25)

    def test_load_missing_file_is_empty_not_error(self, tmp_path):
        cache = RecommendationCache(tmp_path / "nope.json")
        cache.load()  # must not raise
        assert cache.get_fresh("AAA", date(2026, 6, 4)) == (False, None)

    def test_load_corrupt_file_degrades_to_empty(self, tmp_path):
        path = tmp_path / "reco.json"
        path.write_text("{not valid json", encoding="utf-8")
        cache = RecommendationCache(path)
        cache.load()  # must not raise
        assert cache.get_fresh("AAA", date(2026, 6, 4)) == (False, None)


class TestGatherFunnelSignalsCache:
    RECO = {"recommendation": [{"strongBuy": 1, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}]}

    def test_cache_hit_skips_fetch_and_does_not_spend_budget(self, tmp_path):
        getj = counting_get(self.RECO)
        finnhub = FinnhubProvider("k", getj)
        cache = RecommendationCache(tmp_path / "reco.json")
        cache.put("A", 0.42, date(2026, 6, 4))  # pre-warm A

        signals = gather_funnel_signals(
            ["A", "B"], today=date(2026, 6, 4),
            base_metrics={s: {"price": 10.0} for s in ("A", "B")},
            finnhub=finnhub, reco_cache=cache, enrich_per_run=1,
        )
        # A served from cache (no HTTP for A); only B fetched -> 1 recommendation call
        assert signals["A"].recommendation_score == 0.42
        assert signals["B"].recommendation_score == 1.0
        assert sum("recommendation" in u for u in getj.calls) == 1

    def test_per_run_budget_limits_fetches_rest_left_for_next_cycle(self, tmp_path):
        getj = counting_get(self.RECO)
        finnhub = FinnhubProvider("k", getj)
        cache = RecommendationCache(tmp_path / "reco.json")

        signals = gather_funnel_signals(
            ["A", "B", "C"], today=date(2026, 6, 4),
            base_metrics={s: {"price": 10.0} for s in ("A", "B", "C")},
            finnhub=finnhub, reco_cache=cache, enrich_per_run=2,
        )
        scored = [s for s in signals.values() if s.recommendation_score is not None]
        assert len(scored) == 2  # budget of 2 fetched; C left for a later cycle
        assert sum("recommendation" in u for u in getj.calls) == 2

    def test_two_cycles_warm_the_whole_universe(self, tmp_path):
        path = tmp_path / "reco.json"
        symbols = ["A", "B", "C", "D"]
        base = {s: {"price": 10.0} for s in symbols}

        # cycle 1: budget 2 -> A,B fetched; cache persisted
        getj1 = counting_get(self.RECO)
        c1 = RecommendationCache(path); c1.load()
        gather_funnel_signals(symbols, today=date(2026, 6, 4), base_metrics=base,
                              finnhub=FinnhubProvider("k", getj1), reco_cache=c1, enrich_per_run=2)
        assert sum("recommendation" in u for u in getj1.calls) == 2

        # cycle 2 (same day): A,B are cache hits -> only C,D fetched
        getj2 = counting_get(self.RECO)
        c2 = RecommendationCache(path); c2.load()
        signals2 = gather_funnel_signals(symbols, today=date(2026, 6, 4), base_metrics=base,
                                         finnhub=FinnhubProvider("k", getj2), reco_cache=c2, enrich_per_run=2)
        assert sum("recommendation" in u for u in getj2.calls) == 2
        # whole universe now scored
        assert all(s.recommendation_score is not None for s in signals2.values())

    def test_no_cache_preserves_legacy_enrich_limit_behavior(self, tmp_path):
        getj = counting_get(self.RECO)
        finnhub = FinnhubProvider("k", getj)
        signals = gather_funnel_signals(
            ["A", "B", "C"], today=date(2026, 6, 4),
            base_metrics={s: {"price": 10.0} for s in ("A", "B", "C")},
            finnhub=finnhub, enrich_limit=1,
        )
        scored = [s for s in signals.values() if s.recommendation_score is not None]
        assert len(scored) == 1


class TestWarmRecommendationCache:
    RECO = {"recommendation": [{"strongBuy": 1, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}]}

    def test_warms_up_to_budget_and_persists(self, tmp_path):
        path = tmp_path / "reco.json"
        getj = counting_get(self.RECO)
        cache = RecommendationCache(path)
        fetched = warm_recommendation_cache(
            ["A", "B", "C", "D"], finnhub=FinnhubProvider("k", getj),
            cache=cache, today=date(2026, 6, 4), budget=2,
        )
        assert fetched == 2
        assert sum("recommendation" in u for u in getj.calls) == 2
        # persisted to disk
        reloaded = RecommendationCache(path); reloaded.load()
        warmed = [s for s in ("A", "B", "C", "D") if reloaded.is_fresh(s, date(2026, 6, 4))]
        assert len(warmed) == 2

    def test_skips_fresh_entries(self, tmp_path):
        getj = counting_get(self.RECO)
        cache = RecommendationCache(tmp_path / "reco.json")
        cache.put("A", 0.9, date(2026, 6, 4))  # already fresh
        fetched = warm_recommendation_cache(
            ["A", "B"], finnhub=FinnhubProvider("k", getj),
            cache=cache, today=date(2026, 6, 4), budget=5,
        )
        assert fetched == 1  # only B fetched; A skipped
        assert sum("recommendation" in u for u in getj.calls) == 1

    def test_inert_without_finnhub_key(self, tmp_path):
        cache = RecommendationCache(tmp_path / "reco.json")
        fetched = warm_recommendation_cache(
            ["A", "B"], finnhub=FinnhubProvider("", fake_get(self.RECO)),
            cache=cache, today=date(2026, 6, 4), budget=5,
        )
        assert fetched == 0

    def test_none_finnhub_is_safe(self, tmp_path):
        cache = RecommendationCache(tmp_path / "reco.json")
        assert warm_recommendation_cache(
            ["A"], finnhub=None, cache=cache, today=date(2026, 6, 4), budget=5,
        ) == 0
