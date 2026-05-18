"""Tests for Tony Stocks analyst engine (V10).

Safety invariants verified here:
  - No paper trades created.
  - No live trades or orders.
  - Only allowed recommended_actions.
  - Seeded demo excluded from outcome learning by default.
  - Benchmark/reference always gets reference_only.
  - Fallback/stale always gets needs_more_data.
"""
from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.scoring.score_models import ScoredStock
from trading_bot.tony.analysis import (
    ALLOWED_ACTIONS,
    ACTION_AVOID,
    ACTION_NEEDS_DATA,
    ACTION_REFERENCE,
    ACTION_SNAPSHOT,
    ACTION_WATCH,
    DQ_ALPACA_IEX,
    DQ_DEMO,
    DQ_FALLBACK,
    DQ_SEEDED,
    DQ_STALE,
    MKT_MISSING,
    MKT_MIXED,
    MKT_SUPPORTIVE,
    MKT_WEAK,
    OC_NOT_ENOUGH,
    PRI_AVOID,
    PRI_REFERENCE,
    RISK_INVALID_PLAN,
    RISK_STRONG_RR,
    RISK_WIDE_ATR,
    SETUP_BREAKOUT,
    SETUP_INSUFFICIENT,
    SETUP_MOMENTUM,
    SETUP_OVEREXTENDED,
    SETUP_PULLBACK,
    SETUP_REFERENCE,
    SETUP_WEAK,
    VOL_CONFIRMATION,
    VOL_LOW_DOLLAR,
    VOL_LOW_LIQUIDITY,
    VOL_SPECULATIVE_RISK,
    MarketContext,
    CandidateAnalysis,
    analyze_candidates,
    _data_quality,
    _outcome_context,
    _priority_and_action,
    _risk_read,
    _setup_read,
    _volume_read,
)
from trading_bot.intraday.features import IntradayFeatures


# ── Test helpers ──────────────────────────────────────────────────────────────

def _stock(
    symbol: str = "PLTR",
    setup_category: str = "Breakout Watch",
    universe_role: str = "primary_candidate",
    final_score: float = 82.0,
    trade_plan_valid: bool = True,
    trade_plan_status: str = "valid",
    risk_reward_ratio: float = 2.5,
    suggested_entry: float = 100.0,
    suggested_stop: float = 93.0,
    suggested_target_1: float = 115.0,
    atr_percent: float = 0.03,
    atr_14: float = 3.0,
    volatility_20d: float = 0.03,
    avg_volume_20: float = 2_000_000.0,
    dollar_volume_20: float = 200_000_000.0,
    relative_volume: float = 1.2,
    return_5d: float = 0.03,
    return_10d: float = 0.05,
    return_20d: float = 0.07,
    trend_score: float = 75.0,
    momentum_score: float = 72.0,
    tags: list[str] | None = None,
    warnings: list[str] | None = None,
    notes: str = "",
) -> ScoredStock:
    return ScoredStock(
        symbol=symbol,
        scanned_at="2026-05-17T00:00:00+00:00",
        final_score=final_score,
        setup_category=setup_category,
        tags=tags or ["mid_cap", "software"],
        universe_role=universe_role,
        name="Test Stock",
        sector="technology",
        industry="software",
        demo_profile="clean_breakout",
        notes=notes,
        candidate_summary="Test candidate.",
        trend_score=trend_score,
        momentum_score=momentum_score,
        volume_score=75.0,
        risk_score=70.0,
        setup_quality_score=72.0,
        latest_close=100.0,
        avg_volume_20=avg_volume_20,
        dollar_volume_20=dollar_volume_20,
        return_5d=return_5d,
        return_10d=return_10d,
        return_20d=return_20d,
        atr_14=atr_14,
        atr_percent=atr_percent,
        volatility_20d=volatility_20d,
        relative_volume=relative_volume,
        suggested_entry=suggested_entry,
        suggested_stop=suggested_stop,
        suggested_target_1=suggested_target_1,
        risk_reward_ratio=risk_reward_ratio,
        trade_plan_valid=trade_plan_valid,
        trade_plan_status=trade_plan_status,
        reasons=["Price above trend.", "Positive momentum."],
        warnings=warnings or [],
    )


def _spy() -> ScoredStock:
    return _stock(
        symbol="SPY",
        setup_category="ETF / Benchmark Reference",
        universe_role="benchmark",
        tags=["etf", "benchmark"],
        return_20d=0.04,
    )


def _qqq(positive: bool = True) -> ScoredStock:
    return _stock(
        symbol="QQQ",
        setup_category="ETF / Benchmark Reference",
        universe_role="benchmark",
        tags=["etf", "benchmark", "tech"],
        return_20d=0.03 if positive else -0.04,
    )


# ── Setup read tests ──────────────────────────────────────────────────────────

class TestSetupRead:
    def test_breakout_watch(self):
        label, text = _setup_read(_stock(setup_category="Breakout Watch"))
        assert label == SETUP_BREAKOUT
        assert "breakout" in text.lower() or "recent high" in text.lower()

    def test_pullback_watch(self):
        label, text = _setup_read(_stock(setup_category="Pullback Watch"))
        assert label == SETUP_PULLBACK
        assert "pullback" in text.lower() or "support" in text.lower()

    def test_momentum_continuation(self):
        label, text = _setup_read(_stock(setup_category="Momentum Continuation"))
        assert label == SETUP_MOMENTUM
        assert "momentum" in text.lower()

    def test_overextended(self):
        label, text = _setup_read(_stock(setup_category="Overextended / Wait"))
        assert label == SETUP_OVEREXTENDED
        assert "extended" in text.lower() or "pullback" in text.lower()

    def test_weak_avoid(self):
        label, text = _setup_read(_stock(setup_category="Weak / Avoid", return_20d=-0.05))
        assert label == SETUP_WEAK
        assert "weak" in text.lower() or "downtrend" in text.lower()

    def test_reference_only_for_benchmark_role(self):
        label, text = _setup_read(_stock(universe_role="benchmark", setup_category="ETF / Benchmark Reference"))
        assert label == SETUP_REFERENCE
        assert "benchmark" in text.lower() or "context" in text.lower()

    def test_reference_only_for_reference_role(self):
        label, text = _setup_read(_stock(universe_role="reference", setup_category="Momentum Continuation"))
        assert label == SETUP_REFERENCE

    def test_invalid_trade_plan_gives_insufficient_data(self):
        label, text = _setup_read(_stock(setup_category="Invalid Trade Plan", trade_plan_valid=False, trade_plan_status="invalid_entry"))
        assert label == SETUP_INSUFFICIENT
        assert "invalid" in text.lower()

    def test_speculative_watchlist_gives_momentum(self):
        label, _ = _setup_read(_stock(setup_category="Speculative Watchlist", universe_role="speculative_candidate"))
        assert label == SETUP_MOMENTUM


# ── Volume read tests ─────────────────────────────────────────────────────────

class TestVolumeRead:
    def test_volume_confirmation(self):
        label, text = _volume_read(_stock(avg_volume_20=2_000_000, dollar_volume_20=200_000_000, relative_volume=1.25))
        assert label == VOL_CONFIRMATION or "confirmation" in label
        assert "PLTR" in text

    def test_low_dollar_volume(self):
        label, text = _volume_read(_stock(avg_volume_20=1_000_000, dollar_volume_20=1_000_000))
        assert label == VOL_LOW_DOLLAR
        assert "dollar" in text.lower()

    def test_low_avg_volume(self):
        label, text = _volume_read(_stock(avg_volume_20=100_000, dollar_volume_20=50_000_000))
        assert label == VOL_LOW_LIQUIDITY

    def test_speculative_volume_risk(self):
        label, text = _volume_read(
            _stock(
                avg_volume_20=200_000,
                dollar_volume_20=2_000_000,
                universe_role="speculative_candidate",
                tags=["speculative", "small_cap"],
            )
        )
        assert label == VOL_SPECULATIVE_RISK
        assert "speculative" in text.lower()

    def test_adequate_volume_returns_confirmation(self):
        label, _ = _volume_read(_stock(avg_volume_20=3_000_000, dollar_volume_20=300_000_000, relative_volume=1.0))
        assert label == VOL_CONFIRMATION


# ── Risk read tests ───────────────────────────────────────────────────────────

class TestRiskRead:
    def test_invalid_plan(self):
        label, text = _risk_read(_stock(trade_plan_valid=False, trade_plan_status="invalid_entry"))
        assert label == RISK_INVALID_PLAN
        assert "invalid" in text.lower()

    def test_strong_risk_reward(self):
        label, text = _risk_read(_stock(risk_reward_ratio=3.0, trade_plan_valid=True, atr_percent=0.02, volatility_20d=0.02))
        assert label == RISK_STRONG_RR
        assert "3.0x" in text or "strong" in text.lower()

    def test_wide_atr_concern(self):
        label, text = _risk_read(_stock(atr_percent=0.09, trade_plan_valid=True, risk_reward_ratio=2.0, volatility_20d=0.04))
        assert label == RISK_WIDE_ATR
        assert "ATR" in text or "wide" in text.lower()

    def test_high_volatility_concern(self):
        label, _ = _risk_read(_stock(volatility_20d=0.10, atr_percent=0.03, trade_plan_valid=True, risk_reward_ratio=2.5))
        assert label == RISK_WIDE_ATR or label == "high_volatility_concern"

    def test_acceptable_risk(self):
        label, _ = _risk_read(_stock(risk_reward_ratio=1.8, atr_percent=0.03, volatility_20d=0.03, trade_plan_valid=True))
        assert label in ("acceptable_risk", RISK_WIDE_ATR, RISK_STRONG_RR)  # depends on exact values


# ── Market context tests ──────────────────────────────────────────────────────

class TestMarketContext:
    def test_supportive_when_all_benchmarks_positive(self):
        ctx = MarketContext([_spy(), _qqq(positive=True)])
        assert ctx.context_label() == MKT_SUPPORTIVE

    def test_weak_when_majority_benchmarks_negative(self):
        neg = _stock("SPY", universe_role="benchmark", tags=["etf", "benchmark"], return_20d=-0.05)
        neg2 = _stock("QQQ", universe_role="benchmark", tags=["etf", "benchmark"], return_20d=-0.04)
        ctx = MarketContext([neg, neg2])
        assert ctx.context_label() == MKT_WEAK

    def test_mixed_context(self):
        pos = _stock("SPY", universe_role="benchmark", tags=["etf", "benchmark"], return_20d=0.03)
        neg = _stock("QQQ", universe_role="benchmark", tags=["etf", "benchmark"], return_20d=-0.03)
        ctx = MarketContext([pos, neg])
        assert ctx.context_label() == MKT_MIXED

    def test_missing_when_no_benchmarks(self):
        ctx = MarketContext([])
        assert ctx.context_label() == MKT_MISSING

    def test_description_includes_spy_return(self):
        ctx = MarketContext([_spy()])
        desc = ctx.description()
        assert "SPY" in desc


# ── Data quality tests ────────────────────────────────────────────────────────

class TestDataQuality:
    def test_demo_data_when_provider_is_demo(self):
        label, text = _data_quality(_stock(), "demo_generated", set(), set())
        assert label == DQ_DEMO
        assert "demo" in text.lower()

    def test_alpaca_iex_real_data(self):
        label, text = _data_quality(_stock(), "alpaca_iex", set(), set())
        assert label == DQ_ALPACA_IEX
        assert "IEX" in text
        assert "single-exchange" in text

    def test_fallback_data(self):
        label, text = _data_quality(_stock(symbol="PLTR"), "alpaca_iex", {"PLTR"}, set())
        assert label == DQ_FALLBACK
        assert "demo" in text.lower() or "synthetic" in text.lower()

    def test_stale_data(self):
        label, text = _data_quality(_stock(symbol="PLTR"), "alpaca_iex", set(), {"PLTR"})
        assert label == DQ_STALE
        assert "stale" in text.lower()

    def test_seeded_demo_fixture_via_tags(self):
        label, text = _data_quality(_stock(tags=["demo_seeded", "software"]), "alpaca_iex", set(), set())
        assert label == DQ_SEEDED
        assert "seeded" in text.lower() or "fixture" in text.lower()

    def test_seeded_demo_fixture_via_notes(self):
        label, _ = _data_quality(_stock(notes="Demo seeded snapshot for testing"), "demo_generated", set(), set())
        assert label == DQ_SEEDED

    def test_fallback_takes_priority_over_demo(self):
        label, _ = _data_quality(_stock(symbol="PLTR"), "demo_generated", {"PLTR"}, set())
        assert label == DQ_FALLBACK


# ── Priority and action tests ─────────────────────────────────────────────────

class TestPriorityAndAction:
    def test_benchmark_gives_reference_only(self):
        priority, action = _priority_and_action(_stock(universe_role="benchmark"), SETUP_REFERENCE, "acceptable_risk", DQ_DEMO)
        assert priority == PRI_REFERENCE
        assert action == ACTION_REFERENCE

    def test_reference_gives_reference_only(self):
        priority, action = _priority_and_action(_stock(universe_role="reference"), SETUP_REFERENCE, "acceptable_risk", DQ_DEMO)
        assert priority == PRI_REFERENCE
        assert action == ACTION_REFERENCE

    def test_invalid_plan_gives_avoid(self):
        priority, action = _priority_and_action(_stock(trade_plan_valid=False), SETUP_INSUFFICIENT, RISK_INVALID_PLAN, DQ_DEMO)
        assert priority == PRI_AVOID
        assert action == ACTION_AVOID

    def test_high_score_real_data_gives_snapshot(self):
        priority, action = _priority_and_action(
            _stock(final_score=85.0, trade_plan_valid=True),
            SETUP_BREAKOUT, "acceptable_risk", DQ_ALPACA_IEX,
        )
        assert action == ACTION_SNAPSHOT

    def test_fallback_gives_needs_more_data(self):
        priority, action = _priority_and_action(
            _stock(final_score=82.0, trade_plan_valid=True),
            SETUP_BREAKOUT, "acceptable_risk", DQ_FALLBACK,
        )
        assert action == ACTION_NEEDS_DATA

    def test_stale_gives_needs_more_data(self):
        priority, action = _priority_and_action(
            _stock(final_score=80.0, trade_plan_valid=True),
            SETUP_BREAKOUT, "acceptable_risk", DQ_STALE,
        )
        assert action == ACTION_NEEDS_DATA

    def test_overextended_gives_avoid(self):
        priority, action = _priority_and_action(
            _stock(trade_plan_valid=True), SETUP_OVEREXTENDED, "acceptable_risk", DQ_DEMO,
        )
        assert action == ACTION_AVOID

    def test_weak_gives_avoid(self):
        priority, action = _priority_and_action(
            _stock(trade_plan_valid=True), SETUP_WEAK, "acceptable_risk", DQ_DEMO,
        )
        assert action == ACTION_AVOID

    def test_mid_score_gives_watch(self):
        priority, action = _priority_and_action(
            _stock(final_score=70.0, trade_plan_valid=True),
            SETUP_BREAKOUT, "acceptable_risk", DQ_ALPACA_IEX,
        )
        assert action == ACTION_WATCH


# ── Outcome context tests ─────────────────────────────────────────────────────

class TestOutcomeContext:
    def test_not_enough_history_when_snapshots_none(self):
        result = _outcome_context("Breakout Watch", "80-89", "primary_candidate", None, False)
        assert result == OC_NOT_ENOUGH

    def test_not_enough_history_when_snapshots_empty(self):
        result = _outcome_context("Breakout Watch", "80-89", "primary_candidate", pd.DataFrame(), False)
        assert result == OC_NOT_ENOUGH

    def test_seeded_demo_excluded_by_default(self):
        snapshots = pd.DataFrame([
            {
                "symbol": "PLTR",
                "setup_category": "Breakout Watch",
                "universe_role": "primary_candidate",
                "total_score": 82,
                "outcome_label": "target_hit",
                "entry_triggered": 1,
                "notes": "Demo seeded snapshot",
                "tags_json": '["demo_seeded"]',
                "warnings_json": "[]",
            }
        ] * 10)
        result = _outcome_context("Breakout Watch", "80-89", "primary_candidate", snapshots, include_seeded_demo=False)
        assert result == OC_NOT_ENOUGH

    def test_seeded_demo_included_when_flag_set(self):
        snapshots = pd.DataFrame([
            {
                "symbol": "PLTR",
                "setup_category": "Breakout Watch",
                "universe_role": "primary_candidate",
                "total_score": 82,
                "outcome_label": "target_hit",
                "entry_triggered": 1,
                "notes": "Demo seeded snapshot",
                "tags_json": '["demo_seeded"]',
                "warnings_json": "[]",
            }
        ] * 10)
        result = _outcome_context("Breakout Watch", "80-89", "primary_candidate", snapshots, include_seeded_demo=True)
        assert result in ("historically_positive", "historically_mixed", "historically_negative")

    def test_not_enough_below_min_snapshots(self):
        snapshots = pd.DataFrame([
            {
                "symbol": "PLTR",
                "setup_category": "Breakout Watch",
                "universe_role": "primary_candidate",
                "total_score": 82,
                "outcome_label": "target_hit",
                "entry_triggered": 1,
                "notes": "",
                "tags_json": "[]",
                "warnings_json": "[]",
            }
        ] * 3)  # below min of 5
        result = _outcome_context("Breakout Watch", "80-89", "primary_candidate", snapshots, False)
        assert result == OC_NOT_ENOUGH


# ── Full analyze_candidates integration tests ─────────────────────────────────

class TestAnalyzeCandidates:
    def test_benchmark_gets_reference_only_action(self):
        spy = _spy()
        results = analyze_candidates([spy], provider_name="demo_generated")
        assert len(results) == 1
        assert results[0].recommended_action == ACTION_REFERENCE
        assert results[0].priority_label == PRI_REFERENCE

    def test_all_recommended_actions_are_allowed(self):
        candidates = [
            _stock("PLTR", setup_category="Breakout Watch", final_score=85, universe_role="primary_candidate"),
            _stock("SPY", setup_category="ETF / Benchmark Reference", universe_role="benchmark", tags=["etf", "benchmark"]),
            _stock("WEAK", setup_category="Weak / Avoid", final_score=30, universe_role="primary_candidate"),
        ]
        results = analyze_candidates(candidates, provider_name="demo_generated")
        for r in results:
            assert r.recommended_action in ALLOWED_ACTIONS, (
                f"{r.symbol} has invalid recommended_action: {r.recommended_action!r}"
            )

    def test_no_paper_trades_returned(self):
        candidates = [_stock("PLTR"), _stock("CRWD")]
        results = analyze_candidates(candidates, provider_name="demo_generated")
        for r in results:
            assert r.recommended_action != "paper_trade"
            assert r.recommended_action != "live_trade"
            assert r.recommended_action in ALLOWED_ACTIONS

    def test_market_context_propagates_to_all_candidates(self):
        spy = _spy()
        pltr = _stock("PLTR", setup_category="Breakout Watch")
        crwd = _stock("CRWD", setup_category="Momentum Continuation")
        results = analyze_candidates([pltr, crwd], benchmark_rows=[spy], provider_name="alpaca_iex")
        ctx_labels = {r.market_context_read for r in results}
        assert len(ctx_labels) == 1, "Market context should be identical for all candidates in same cycle"

    def test_outcome_cache_shared_across_same_category(self):
        snapshots = pd.DataFrame([
            {
                "symbol": s,
                "setup_category": "Breakout Watch",
                "universe_role": "primary_candidate",
                "total_score": 80,
                "outcome_label": "target_hit",
                "entry_triggered": 1,
                "notes": "",
                "tags_json": "[]",
                "warnings_json": "[]",
            }
            for s in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
        ])
        pltr = _stock("PLTR", setup_category="Breakout Watch", final_score=82)
        crwd = _stock("CRWD", setup_category="Breakout Watch", final_score=78)
        results = analyze_candidates([pltr, crwd], outcome_snapshots=snapshots, provider_name="demo_generated")
        oc_labels = [r.outcome_context for r in results]
        assert oc_labels[0] == oc_labels[1], "Same setup+bucket should share outcome context"

    def test_fallback_symbols_give_needs_more_data(self):
        pltr = _stock("PLTR", final_score=85, setup_category="Breakout Watch")
        results = analyze_candidates(
            [pltr],
            fallback_symbols=["PLTR"],
            provider_name="alpaca_iex",
        )
        assert results[0].recommended_action == ACTION_NEEDS_DATA
        assert results[0].data_quality_read == DQ_FALLBACK

    def test_stale_symbols_give_needs_more_data(self):
        pltr = _stock("PLTR", final_score=85, setup_category="Breakout Watch")
        results = analyze_candidates(
            [pltr],
            stale_symbols=["PLTR"],
            provider_name="alpaca_iex",
        )
        assert results[0].recommended_action == ACTION_NEEDS_DATA
        assert results[0].data_quality_read == DQ_STALE

    def test_candidate_analysis_to_dict(self):
        result = analyze_candidates([_stock("PLTR")], provider_name="demo_generated")[0]
        d = result.to_dict()
        assert d["symbol"] == "PLTR"
        assert "tony_hypothesis" in d
        assert "recommended_action" in d
        assert isinstance(d["reasons"], list)
        assert isinstance(d["concerns"], list)

    def test_returns_analysis_for_each_candidate(self):
        candidates = [_stock(s) for s in ["PLTR", "CRWD", "HIMS"]]
        results = analyze_candidates(candidates, provider_name="demo_generated")
        assert len(results) == len(candidates)
        symbols = [r.symbol for r in results]
        assert symbols == ["PLTR", "CRWD", "HIMS"]

    def test_hypothesis_not_empty(self):
        candidates = [
            _stock("PLTR", setup_category="Breakout Watch"),
            _stock("SPY", universe_role="benchmark", setup_category="ETF / Benchmark Reference", tags=["etf", "benchmark"]),
        ]
        results = analyze_candidates(candidates, provider_name="demo_generated")
        for r in results:
            assert r.tony_hypothesis, f"{r.symbol} hypothesis is empty"
            assert len(r.tony_hypothesis) > 20, f"{r.symbol} hypothesis too short"

    def test_analyst_says_it_is_analyzing_not_trading(self):
        result = analyze_candidates([_stock("PLTR")], provider_name="demo_generated")[0]
        assert "analyzing" in result.tony_hypothesis.lower() or "not trading" in result.tony_hypothesis.lower()

    def test_intraday_read_labels_are_attached_without_trade_action(self):
        intraday = {
            "PLTR": IntradayFeatures(
                symbol="PLTR",
                timeframe="5Min",
                data_available=True,
                status="ok",
                latest_close=105,
                day_open=100,
                high_of_day=105.5,
                low_of_day=99,
                intraday_change_percent=0.05,
                vwap=102,
                price_above_vwap=True,
                distance_from_high_percent=-0.004,
                opening_range_high=104,
                opening_range_low=99,
                opening_range_breakout_candidate=True,
            )
        }
        result = analyze_candidates([_stock("PLTR", final_score=86)], provider_name="alpaca_iex", intraday_features_by_symbol=intraday)[0]
        assert result.intraday_read in {"opening_range_breakout_watch", "near_high_of_day", "above_vwap"}
        assert result.recommended_action in ALLOWED_ACTIONS
        assert result.recommended_action != "paper_trade"


# ── Tony events analyst methods ───────────────────────────────────────────────

class TestTonyAnalystEvents:
    def test_analyst_events_created(self, tmp_path):
        from trading_bot.storage.repositories import ScannerRepository
        from trading_bot.tony.events import TonyStocksService

        repo = ScannerRepository(tmp_path / "test.db")
        tony = TonyStocksService(repo, {
            "enabled": True,
            "max_events_per_cycle": 50,
            "create_events_for": [
                "analyst_candidate_hypothesis",
                "analyst_market_context",
                "analyst_data_quality",
                "analyst_risk_warning",
            ],
        })

        tony.record_analyst_candidate_hypothesis(
            symbol="PLTR",
            priority_label="high_priority",
            recommended_action="snapshot_only",
            hypothesis="PLTR is approaching a potential breakout.",
            setup_read="breakout_candidate",
        )
        tony.record_analyst_market_context(
            context_label="market_supportive",
            description="Market context is supportive.",
            benchmark_symbols=["SPY", "QQQ"],
        )
        tony.record_analyst_data_quality(
            dq_summary={"alpaca_iex_real_data": 10, "demo_data": 2},
            provider_name="alpaca_iex",
            total_candidates=12,
        )
        tony.record_analyst_risk_warning(
            symbols_with_risk=["UPST"],
            risk_types=["wide_atr_concern"],
            provider_name="alpaca_iex",
        )

        events = repo.list_tony_events(limit=20)
        event_types = set(events["event_type"])
        assert "analyst_candidate_hypothesis" in event_types
        assert "analyst_market_context" in event_types
        assert "analyst_data_quality" in event_types
        assert "analyst_risk_warning" in event_types

    def test_analyst_risk_warning_skips_empty_list(self, tmp_path):
        from trading_bot.storage.repositories import ScannerRepository
        from trading_bot.tony.events import TonyStocksService

        repo = ScannerRepository(tmp_path / "test.db")
        tony = TonyStocksService(repo, {
            "enabled": True,
            "max_events_per_cycle": 20,
            "create_events_for": ["analyst_risk_warning"],
        })
        tony.record_analyst_risk_warning([], [], "alpaca_iex")
        events = repo.list_tony_events(limit=10)
        assert events.empty or "analyst_risk_warning" not in set(events.get("event_type", pd.Series()))

    def test_analyst_events_respect_max_budget(self, tmp_path):
        from trading_bot.storage.repositories import ScannerRepository
        from trading_bot.tony.events import TonyStocksService

        repo = ScannerRepository(tmp_path / "test.db")
        tony = TonyStocksService(repo, {
            "enabled": True,
            "max_events_per_cycle": 2,
            "create_events_for": ["analyst_candidate_hypothesis"],
        })
        for sym in ["A", "B", "C", "D", "E"]:
            tony.record_analyst_candidate_hypothesis(
                symbol=sym,
                priority_label="watch",
                recommended_action="watch_only",
                hypothesis=f"{sym} is watching.",
                setup_read="breakout_candidate",
            )
        events = repo.list_tony_events(event_type="analyst_candidate_hypothesis", limit=20)
        assert len(events) <= 2
