"""Tests for the pure Research Funnel staging logic (data/research_funnel.py)."""
from __future__ import annotations

from datetime import date

from trading_bot.data.research_funnel import (
    FunnelStageConfig,
    SymbolSignals,
    build_funnel,
)

TODAY = date(2026, 6, 4)


def _sig(symbol, **kw):
    return SymbolSignals(symbol=symbol, **kw)


class TestCheapScreen:
    def test_price_out_of_band_dropped(self):
        cfg = FunnelStageConfig(min_price=5, max_price=500)
        signals = {
            "LOW": _sig("LOW", price=2.0, dollar_volume=9e6),
            "HIGH": _sig("HIGH", price=900.0, dollar_volume=9e6),
            "OK": _sig("OK", price=50.0, dollar_volume=9e6),
        }
        res = build_funnel(["LOW", "HIGH", "OK"], signals, cfg, TODAY)
        assert res.shortlist == ["OK"]
        assert "price_out_of_band" in res.dropped["LOW"]
        assert "price_out_of_band" in res.dropped["HIGH"]

    def test_dollar_volume_floor(self):
        cfg = FunnelStageConfig(min_dollar_volume=5_000_000)
        signals = {"THIN": _sig("THIN", price=20, dollar_volume=1_000_000),
                   "LIQUID": _sig("LIQUID", price=20, dollar_volume=20_000_000)}
        res = build_funnel(["THIN", "LIQUID"], signals, cfg, TODAY)
        assert res.shortlist == ["LIQUID"]
        assert "dollar_volume_below_floor" in res.dropped["THIN"]

    def test_missing_data_never_drops(self):
        # A symbol with no signals at all must survive the screen (advisory-by-default).
        cfg = FunnelStageConfig()
        res = build_funnel(["UNKNOWN"], {}, cfg, TODAY)
        assert res.shortlist == ["UNKNOWN"]
        assert "UNKNOWN" not in res.dropped

    def test_relative_strength_filter_off_by_default(self):
        cfg = FunnelStageConfig()  # min_relative_strength is None
        signals = {"WEAK": _sig("WEAK", price=20, dollar_volume=9e6, relative_strength=-0.5)}
        res = build_funnel(["WEAK"], signals, cfg, TODAY)
        assert res.shortlist == ["WEAK"]

    def test_relative_strength_filter_when_set(self):
        cfg = FunnelStageConfig(min_relative_strength=0.0)
        signals = {
            "WEAK": _sig("WEAK", price=20, dollar_volume=9e6, relative_strength=-0.2),
            "STRONG": _sig("STRONG", price=20, dollar_volume=9e6, relative_strength=0.3),
        }
        res = build_funnel(["WEAK", "STRONG"], signals, cfg, TODAY)
        assert res.shortlist == ["STRONG"]
        assert "weak_relative_strength" in res.dropped["WEAK"]

    def test_earnings_blackout(self):
        cfg = FunnelStageConfig(earnings_blackout_days=5)
        signals = {
            "SOON": _sig("SOON", price=20, dollar_volume=9e6, earnings_date=date(2026, 6, 7)),
            "FAR": _sig("FAR", price=20, dollar_volume=9e6, earnings_date=date(2026, 7, 1)),
            "PAST": _sig("PAST", price=20, dollar_volume=9e6, earnings_date=date(2026, 6, 1)),
        }
        res = build_funnel(["SOON", "FAR", "PAST"], signals, cfg, TODAY)
        assert set(res.shortlist) == {"FAR", "PAST"}
        assert "earnings_blackout" in res.dropped["SOON"]


class TestCatalystStage:
    def test_sentiment_annotate_mode_does_not_drop(self):
        cfg = FunnelStageConfig(sentiment_mode="annotate", min_news_sentiment=0.0)
        signals = {"BEAR": _sig("BEAR", price=20, dollar_volume=9e6, news_sentiment=-0.9)}
        res = build_funnel(["BEAR"], signals, cfg, TODAY)
        assert res.shortlist == ["BEAR"]  # annotate, not filter

    def test_sentiment_filter_mode_drops_bearish(self):
        cfg = FunnelStageConfig(sentiment_mode="filter", min_news_sentiment=-0.3)
        signals = {
            "BEAR": _sig("BEAR", price=20, dollar_volume=9e6, news_sentiment=-0.9),
            "BULL": _sig("BULL", price=20, dollar_volume=9e6, news_sentiment=0.5),
        }
        res = build_funnel(["BEAR", "BULL"], signals, cfg, TODAY)
        assert res.shortlist == ["BULL"]
        assert "bearish_news" in res.dropped["BEAR"]

    def test_revenue_growth_gate_when_set(self):
        cfg = FunnelStageConfig(min_revenue_growth=-0.5)
        signals = {
            "JUNK": _sig("JUNK", price=20, dollar_volume=9e6, revenue_growth=-0.8),
            "GROW": _sig("GROW", price=20, dollar_volume=9e6, revenue_growth=0.2),
        }
        res = build_funnel(["JUNK", "GROW"], signals, cfg, TODAY)
        assert res.shortlist == ["GROW"]
        assert "negative_growth" in res.dropped["JUNK"]


class TestRankingAndShortlist:
    def test_ranked_by_composite_score_desc(self):
        cfg = FunnelStageConfig(weight_relative_strength=1.0, weight_sentiment=0.5, weight_recommendation=0.5)
        signals = {
            "A": _sig("A", price=20, dollar_volume=9e6, relative_strength=0.1, news_sentiment=0.2, recommendation_score=0.0),
            "B": _sig("B", price=20, dollar_volume=9e6, relative_strength=0.4, news_sentiment=0.0, recommendation_score=0.0),
            "C": _sig("C", price=20, dollar_volume=9e6, relative_strength=0.0, news_sentiment=0.0, recommendation_score=0.0),
        }
        res = build_funnel(["A", "B", "C"], signals, cfg, TODAY)
        assert res.shortlist == ["B", "A", "C"]  # 0.4 > 0.2 > 0.0

    def test_shortlist_size_cap(self):
        cfg = FunnelStageConfig(shortlist_size=2)
        signals = {s: _sig(s, price=20, dollar_volume=9e6, relative_strength=v)
                   for s, v in [("A", 0.3), ("B", 0.2), ("C", 0.1)]}
        res = build_funnel(["A", "B", "C"], signals, cfg, TODAY)
        assert res.shortlist == ["A", "B"]
        assert res.after_catalyst == 3  # all passed; cap only limits shortlist

    def test_deterministic_tiebreak_by_ticker(self):
        cfg = FunnelStageConfig()
        signals = {s: _sig(s, price=20, dollar_volume=9e6, relative_strength=0.1) for s in ("ZZZ", "AAA", "MMM")}
        res = build_funnel(["ZZZ", "AAA", "MMM"], signals, cfg, TODAY)
        assert res.shortlist == ["AAA", "MMM", "ZZZ"]


class TestAlwaysInclude:
    def test_always_include_bypasses_drops_and_cap(self):
        cfg = FunnelStageConfig(shortlist_size=1, min_dollar_volume=5_000_000)
        signals = {
            "SPY": _sig("SPY", price=600.0, dollar_volume=1.0),  # would fail price AND volume
            "HOT": _sig("HOT", price=20, dollar_volume=9e6, relative_strength=0.9),
        }
        res = build_funnel(["SPY", "HOT"], signals, cfg, TODAY, always_include={"SPY"})
        assert "HOT" in res.shortlist
        assert "SPY" in res.shortlist  # survived despite failing screen + exceeding cap
        assert "SPY" not in res.dropped


class TestResultShape:
    def test_stage_counts_and_dedup(self):
        cfg = FunnelStageConfig(min_dollar_volume=5_000_000)
        signals = {
            "A": _sig("A", price=20, dollar_volume=9e6),
            "B": _sig("B", price=20, dollar_volume=1.0),  # dropped
        }
        res = build_funnel(["A", "a", "B"], signals, cfg, TODAY)  # 'a' dup of 'A'
        assert res.universe_count == 2  # deduped
        assert res.after_screen == 1
        assert res.after_catalyst == 1
        d = res.to_dict()
        assert d["stage_counts"] == {"universe": 2, "screened": 1, "catalyst_passed": 1, "shortlist": 1}

    def test_from_dict_ignores_unknown_keys(self):
        cfg = FunnelStageConfig.from_dict({"min_price": 10, "bogus": 99, "shortlist_size": 5})
        assert cfg.min_price == 10
        assert cfg.shortlist_size == 5


class TestConfigIntegration:
    def test_default_config_funnel_parses(self):
        # The funnel was enabled live 2026-06-04 (deliberate). Whatever its on/off
        # state, the config must parse into a sane FunnelStageConfig.
        from trading_bot.settings import load_scanner_settings

        settings = load_scanner_settings("config/default_config.yaml")
        cfg = settings.research_funnel or {}
        assert isinstance(cfg.get("enabled"), bool)
        stage = FunnelStageConfig.from_dict(cfg)
        assert stage.shortlist_size >= 1
        assert stage.min_price > 0
        assert stage.sentiment_mode in ("annotate", "filter")
