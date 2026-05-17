import pandas as pd

from trading_bot.data.market_data import DemoGeneratedProvider
from trading_bot.data.universe import UniverseSymbol
from trading_bot.scoring import ScoreEngine
from trading_bot.scoring.score_engine import ScoringConfig, ScoreThresholds, ScoreWeights, validate_long_trade_plan


def test_score_engine_returns_transparent_score():
    provider = DemoGeneratedProvider()
    data = provider.fetch_ohlcv("AAPL", 120)
    engine = ScoreEngine(ScoringConfig(weights=ScoreWeights(), thresholds=ScoreThresholds()))
    result = engine.score("AAPL", data)
    assert result.symbol == "AAPL"
    assert 0 <= result.final_score <= 100
    assert result.latest_close > 0
    assert result.setup_category
    assert result.universe_role == "primary_candidate"
    assert result.relative_volume > 0
    assert result.atr_percent > 0
    assert result.trade_plan_valid
    assert result.suggested_stop < result.suggested_entry < result.suggested_target_1
    assert result.risk_reward_ratio > 0
    assert isinstance(result.reasons, list)
    assert isinstance(result.warnings, list)


def test_score_engine_rejects_short_history():
    data = pd.DataFrame(
        {"open": [1] * 10, "high": [2] * 10, "low": [1] * 10, "close": [1] * 10, "volume": [1000] * 10},
        index=pd.date_range("2024-01-01", periods=10),
    )
    engine = ScoreEngine(ScoringConfig(weights=ScoreWeights(), thresholds=ScoreThresholds()))
    try:
        engine.score("BAD", data)
    except ValueError as exc:
        assert "at least 60 rows" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_etf_gets_reference_warning_and_category():
    provider = DemoGeneratedProvider()
    data = provider.fetch_ohlcv("SPY", 120)
    engine = ScoreEngine(ScoringConfig(weights=ScoreWeights(), thresholds=ScoreThresholds()))
    metadata = UniverseSymbol(symbol="SPY", universe_role="benchmark", demo_profile="benchmark_index")
    result = engine.score("SPY", data, tags=["etf", "benchmark"], metadata=metadata)
    assert result.setup_category == "ETF / Benchmark Reference"
    assert result.universe_role == "benchmark"
    assert any("ETF/reference symbol" in warning for warning in result.warnings)
    assert "Context/reference symbol" in result.candidate_summary


def test_overextended_symbol_gets_wait_warning():
    dates = pd.date_range("2024-01-01", periods=90)
    close = [100 + index * 0.15 for index in range(89)] + [145]
    data = pd.DataFrame(
        {
            "open": close,
            "high": [value * 1.02 for value in close],
            "low": [value * 0.98 for value in close],
            "close": close,
            "volume": [1_500_000] * len(close),
        },
        index=dates,
    )
    engine = ScoreEngine(ScoringConfig(weights=ScoreWeights(), thresholds=ScoreThresholds()))
    result = engine.score("TEST", data)
    assert result.setup_category == "Overextended / Wait"
    assert any("Extended above short-term moving average" in warning for warning in result.warnings)


def test_swing_reasons_include_risk_reward_and_momentum_context():
    provider = DemoGeneratedProvider()
    data = provider.fetch_ohlcv("AMD", 120)
    engine = ScoreEngine(ScoringConfig(weights=ScoreWeights(), thresholds=ScoreThresholds()))
    result = engine.score("AMD", data, tags=["tech", "watchlist"])
    joined_reasons = " ".join(result.reasons)
    assert "Risk/reward above configured minimum." in result.reasons
    assert "Demo data only; do not use for real trade decisions." in result.warnings
    assert "momentum" in joined_reasons.lower() or "trend" in joined_reasons.lower()


def test_primary_candidate_gets_opportunity_role_context():
    provider = DemoGeneratedProvider({"PLTR": "clean_breakout"})
    data = provider.fetch_ohlcv("PLTR", 120)
    engine = ScoreEngine(ScoringConfig(weights=ScoreWeights(), thresholds=ScoreThresholds()))
    metadata = UniverseSymbol(
        symbol="PLTR",
        name="Palantir",
        tags=("mid_cap", "software", "breakout_candidate"),
        universe_role="primary_candidate",
        demo_profile="clean_breakout",
    )
    result = engine.score("PLTR", data, tags=metadata.tags, metadata=metadata)
    assert result.universe_role == "primary_candidate"
    assert "mid_cap" in result.tags
    assert result.setup_category in {"Breakout Watch", "Momentum Continuation", "Pullback Watch"}
    assert "Primary candidate" in result.candidate_summary


def test_speculative_candidate_gets_warning_without_exclusion():
    provider = DemoGeneratedProvider({"SOFI": "momentum_continuation"})
    data = provider.fetch_ohlcv("SOFI", 120)
    engine = ScoreEngine(ScoringConfig(weights=ScoreWeights(), thresholds=ScoreThresholds()))
    metadata = UniverseSymbol(symbol="SOFI", tags=("speculative",), universe_role="speculative_candidate")
    result = engine.score("SOFI", data, tags=metadata.tags, metadata=metadata)
    assert result.universe_role == "speculative_candidate"
    assert any("Speculative candidate" in warning for warning in result.warnings)
    assert result.setup_category in {"Speculative Watchlist", "Overextended / Wait", "Weak / Avoid", "Momentum Continuation"}


def test_trade_plan_validation_repairs_target_below_entry():
    plan = validate_long_trade_plan(entry=100, stop=95, target=99, atr=2, minimum_risk_reward=1.5)
    assert plan.valid
    assert plan.stop < plan.entry < plan.target
    assert plan.risk_reward > 0
    assert any("target is not above entry" in warning for warning in plan.warnings)
    assert plan.status == "valid_after_fallback"


def test_trade_plan_validation_repairs_stop_equal_or_above_entry():
    equal_stop = validate_long_trade_plan(entry=100, stop=100, target=110, atr=2)
    above_stop = validate_long_trade_plan(entry=100, stop=101, target=110, atr=2)
    for plan in (equal_stop, above_stop):
        assert plan.valid
        assert plan.stop < plan.entry < plan.target
        assert plan.risk_reward > 0
        assert any("stop is not below entry" in warning for warning in plan.warnings)


def test_trade_plan_validation_repairs_target_equal_entry_without_dividing_by_zero():
    plan = validate_long_trade_plan(entry=100, stop=100, target=100, atr=0, minimum_risk_reward=1.5)
    assert plan.valid
    assert plan.stop < plan.entry < plan.target
    assert plan.risk_reward > 0
    assert any("stop is not below entry" in warning for warning in plan.warnings)
    assert any("target is not above entry" in warning for warning in plan.warnings)


def test_trade_plan_validation_rejects_zero_entry_with_warning():
    plan = validate_long_trade_plan(entry=0, stop=0, target=0, atr=0)
    assert not plan.valid
    assert plan.risk_reward == 0
    assert any("entry must be greater than zero" in warning for warning in plan.warnings)
