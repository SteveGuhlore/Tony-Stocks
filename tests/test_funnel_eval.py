"""Tests for the funnel evaluation harness (roadmap item 3).

Pure, deterministic: synthetic picks with known outcomes -> known per-stage deltas.
Research only — the harness measures whether each funnel stage *separates* winners
from losers in the stored history; it makes no profitability claim.
"""
from __future__ import annotations

from trading_bot.analytics.funnel_eval import (
    EvaluatedPick,
    build_evaluated_picks,
    evaluate_funnel_stages,
)
from trading_bot.data.research_funnel import FunnelStageConfig


def _pick(symbol, win, *, r=None, price=None, dv=None, rs=None, reco=None, days_to_earnings=None):
    return EvaluatedPick(
        symbol=symbol, win=win, r_multiple=r, price=price, dollar_volume=dv,
        relative_strength=rs, recommendation_score=reco, days_to_earnings=days_to_earnings,
    )


def _stage(report, name):
    return next(s for s in report.stages if s.stage == name)


class TestDollarVolumeStage:
    def test_screen_that_drops_losers_reads_as_helps(self):
        # High dollar-volume names all win; low ones all lose. The dollar-volume
        # floor (5M) should drop the losers -> stage "helps".
        cfg = FunnelStageConfig(min_dollar_volume=5_000_000)
        picks = [
            _pick("WIN1", True, dv=20_000_000), _pick("WIN2", True, dv=10_000_000),
            _pick("WIN3", True, dv=8_000_000), _pick("WIN4", True, dv=9_000_000),
            _pick("WIN5", True, dv=12_000_000),
            _pick("LOSE1", False, dv=1_000_000), _pick("LOSE2", False, dv=500_000),
            _pick("LOSE3", False, dv=2_000_000), _pick("LOSE4", False, dv=900_000),
            _pick("LOSE5", False, dv=1_500_000),
        ]
        report = evaluate_funnel_stages(picks, cfg, min_sample=5)
        st = _stage(report, "dollar_volume_screen")
        assert st.kept_n == 5 and st.dropped_n == 5
        assert st.kept_win_rate == 1.0
        assert st.dropped_win_rate == 0.0
        assert st.win_rate_delta == 1.0
        assert st.verdict == "helps"

    def test_screen_that_drops_winners_reads_as_hurts(self):
        cfg = FunnelStageConfig(min_dollar_volume=5_000_000)
        picks = [
            _pick("WIN1", True, dv=1_000_000), _pick("WIN2", True, dv=900_000),
            _pick("WIN3", True, dv=2_000_000), _pick("WIN4", True, dv=800_000),
            _pick("WIN5", True, dv=1_200_000),
            _pick("LOSE1", False, dv=20_000_000), _pick("LOSE2", False, dv=10_000_000),
            _pick("LOSE3", False, dv=8_000_000), _pick("LOSE4", False, dv=9_000_000),
            _pick("LOSE5", False, dv=12_000_000),
        ]
        report = evaluate_funnel_stages(picks, cfg, min_sample=5)
        st = _stage(report, "dollar_volume_screen")
        assert st.win_rate_delta == -1.0
        assert st.verdict == "hurts"


class TestEarningsBlackoutStage:
    def test_blackout_drops_names_reporting_soon(self):
        cfg = FunnelStageConfig(earnings_blackout_days=5)
        picks = [
            _pick("KEEP1", True, days_to_earnings=30), _pick("KEEP2", True, days_to_earnings=20),
            _pick("KEEP3", True, days_to_earnings=None), _pick("KEEP4", True, days_to_earnings=10),
            _pick("KEEP5", True, days_to_earnings=40),
            _pick("DROP1", False, days_to_earnings=2), _pick("DROP2", False, days_to_earnings=0),
            _pick("DROP3", False, days_to_earnings=4), _pick("DROP4", False, days_to_earnings=1),
            _pick("DROP5", False, days_to_earnings=5),
        ]
        report = evaluate_funnel_stages(picks, cfg, min_sample=5)
        st = _stage(report, "earnings_blackout")
        # KEEP3 has no earnings date -> not droppable -> still kept (advisory).
        assert st.dropped_n == 5
        assert st.kept_n == 5
        assert st.verdict == "helps"

    def test_blackout_off_when_days_zero_is_not_evaluated(self):
        cfg = FunnelStageConfig(earnings_blackout_days=0)
        picks = [_pick(f"S{i}", i % 2 == 0, days_to_earnings=1) for i in range(10)]
        report = evaluate_funnel_stages(picks, cfg, min_sample=1)
        st = _stage(report, "earnings_blackout")
        assert st.verdict == "not_configured"


class TestRecommendationStage:
    def test_positive_recommendation_separates_winners(self):
        cfg = FunnelStageConfig()
        picks = [
            _pick("WIN1", True, reco=0.8), _pick("WIN2", True, reco=0.5),
            _pick("WIN3", True, reco=0.2), _pick("WIN4", True, reco=0.6),
            _pick("WIN5", True, reco=0.9),
            _pick("LOSE1", False, reco=-0.5), _pick("LOSE2", False, reco=-0.2),
            _pick("LOSE3", False, reco=-0.8), _pick("LOSE4", False, reco=-0.1),
            _pick("LOSE5", False, reco=-0.3),
        ]
        report = evaluate_funnel_stages(picks, cfg, min_sample=5)
        st = _stage(report, "recommendation_rank")
        assert st.kept_win_rate == 1.0
        assert st.dropped_win_rate == 0.0
        assert st.verdict == "helps"


class TestInsufficientData:
    def test_absent_signal_excluded_and_marked_insufficient(self):
        cfg = FunnelStageConfig(min_dollar_volume=5_000_000)
        # No dollar_volume on any pick -> nothing classifiable -> insufficient.
        picks = [_pick(f"S{i}", i % 2 == 0) for i in range(10)]
        report = evaluate_funnel_stages(picks, cfg, min_sample=5)
        st = _stage(report, "dollar_volume_screen")
        assert st.kept_n == 0 and st.dropped_n == 0
        assert st.verdict == "insufficient_data"

    def test_too_few_samples_is_insufficient(self):
        cfg = FunnelStageConfig(min_dollar_volume=5_000_000)
        picks = [_pick("A", True, dv=10_000_000), _pick("B", False, dv=1_000_000)]
        report = evaluate_funnel_stages(picks, cfg, min_sample=5)
        st = _stage(report, "dollar_volume_screen")
        assert st.verdict == "insufficient_data"


class TestAvgR:
    def test_avg_r_computed_over_present_values(self):
        cfg = FunnelStageConfig(min_dollar_volume=5_000_000)
        picks = [
            _pick("A", True, r=2.0, dv=10_000_000), _pick("B", True, r=1.0, dv=10_000_000),
            _pick("C", False, r=-1.0, dv=1_000_000), _pick("D", False, r=-1.0, dv=1_000_000),
        ]
        report = evaluate_funnel_stages(picks, cfg, min_sample=2)
        st = _stage(report, "dollar_volume_screen")
        assert st.kept_avg_r == 1.5
        assert st.dropped_avg_r == -1.0
        assert st.avg_r_delta == 2.5


class TestBuildEvaluatedPicks:
    def test_target_hit_is_win_stop_hit_is_loss(self):
        outcomes = [
            {"symbol": "aaa", "result": "target_hit", "return_pct": 8.0},
            {"symbol": "BBB", "result": "stop_hit", "return_pct": -3.0},
        ]
        picks = build_evaluated_picks(outcomes)
        by = {p.symbol: p for p in picks}
        assert by["AAA"].win is True and by["AAA"].r_multiple == 8.0
        assert by["BBB"].win is False and by["BBB"].r_multiple == -3.0

    def test_closed_uses_return_sign(self):
        outcomes = [
            {"symbol": "AAA", "result": "closed", "return_pct": 2.0},
            {"symbol": "BBB", "result": "closed", "return_pct": -1.0},
        ]
        by = {p.symbol: p for p in build_evaluated_picks(outcomes)}
        assert by["AAA"].win is True
        assert by["BBB"].win is False

    def test_unresolved_without_return_is_skipped(self):
        outcomes = [{"symbol": "AAA", "result": "closed"}]  # no return_pct
        assert build_evaluated_picks(outcomes) == []

    def test_signals_joined_by_symbol(self):
        outcomes = [{"symbol": "AAA", "result": "target_hit", "return_pct": 5.0}]
        signals = {"AAA": {"price": 42.0, "dollar_volume": 9e6, "days_to_earnings": 3}}
        pick = build_evaluated_picks(outcomes, signals)[0]
        assert pick.price == 42.0
        assert pick.dollar_volume == 9e6
        assert pick.days_to_earnings == 3
        assert pick.recommendation_score is None  # absent -> None

    def test_blank_symbol_skipped(self):
        assert build_evaluated_picks([{"symbol": "", "result": "target_hit"}]) == []


class TestReportShape:
    def test_report_to_dict_has_all_stages_and_disclaimer(self):
        cfg = FunnelStageConfig()
        report = evaluate_funnel_stages([_pick("A", True, dv=1e7)], cfg)
        d = report.to_dict()
        assert d["research_only"] is True
        assert d["total_picks"] == 1
        stage_names = {s["stage"] for s in d["stages"]}
        assert {"price_screen", "dollar_volume_screen", "earnings_blackout",
                "recommendation_rank"} <= stage_names
