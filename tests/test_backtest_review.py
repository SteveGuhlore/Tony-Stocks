from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.analytics import BacktestReview
from trading_bot.analytics.backtest_review import BacktestReview as BacktestReviewDirect
from trading_bot.scoring.score_models import ScoredStock
from trading_bot.storage.database import connect
from trading_bot.storage.repositories import ScannerRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def stock(symbol="TEST", score=80, category="Breakout Watch", role="primary_candidate"):
    return ScoredStock(
        symbol=symbol,
        scanned_at="2026-05-17T00:00:00+00:00",
        final_score=score,
        setup_category=category,
        tags=["mid_cap"],
        universe_role=role,
        name=symbol,
        sector="technology",
        industry="software",
        demo_profile="",
        notes="",
        candidate_summary="Test.",
        trend_score=80,
        momentum_score=80,
        volume_score=80,
        risk_score=80,
        setup_quality_score=80,
        latest_close=100.0,
        avg_volume_20=1_000_000,
        dollar_volume_20=100_000_000,
        return_5d=0.01,
        return_10d=0.02,
        return_20d=0.05,
        atr_14=2.0,
        atr_percent=0.02,
        volatility_20d=0.02,
        relative_volume=1.3,
        suggested_entry=100.0,
        suggested_stop=95.0,
        suggested_target_1=110.0,
        risk_reward_ratio=2.0,
        trade_plan_valid=True,
        trade_plan_status="valid",
        reasons=["test"],
        warnings=[],
    )


def _snap_config(result):
    return {
        "enabled": True,
        "min_score": 0,
        "include_roles": [result.universe_role],
        "include_categories": [result.setup_category],
        "dedupe_minutes": 0,
    }


def _tony(provider="alpaca_iex", data_source="real_alpaca"):
    return {
        "data_quality_read": "daily_real_alpaca",
        "data_source": data_source,
        "data_source_provider": provider,
        "used_demo_data": False,
        "used_fallback_data": False,
        "real_data_only_run": True,
    }


def create_snapshot(repo, result, outcome, *, provider="alpaca_iex", data_source="real_alpaca"):
    run_id = repo.create_scan_run(1, provider, {"provider": provider})
    ids = repo.create_candidate_snapshots(
        run_id, [result], _snap_config(result), tony_analyses={result.symbol: _tony(provider, data_source)}
    )
    repo.update_candidate_snapshot_followup(
        ids[0],
        entry_triggered=1,
        last_checked_at="2026-05-18T00:00:00+00:00",
        outcome_label=outcome,
        result_eod=0.01,
        result_3d=0.015,
        result_5d=0.02,
    )
    return ids[0]


@pytest.fixture()
def repo(tmp_path):
    db_path = tmp_path / "test.db"
    conn = connect(str(db_path))
    conn.close()
    return ScannerRepository(str(db_path))


# ---------------------------------------------------------------------------
# Export test
# ---------------------------------------------------------------------------

def test_backtest_review_exported_from_analytics_package():
    assert BacktestReview is BacktestReviewDirect


# ---------------------------------------------------------------------------
# Empty snapshots
# ---------------------------------------------------------------------------

def test_empty_snapshots_returns_safe_summary():
    review = BacktestReview(pd.DataFrame(), real_only=True)
    result = review.summary()
    assert result["snapshots_reviewed"] == 0
    assert result["conclusive_outcomes"] == 0
    assert result["win_rate"] is None
    assert result["avg_simulated_pl_per_trade"] is None
    assert result["max_drawdown"] is None
    assert result["equity_curve"] == []
    assert result["by_setup_category"] == []
    assert result["by_score_bucket"] == []
    assert result["by_universe_role"] == []


def test_win_rate_none_when_no_conclusive_data():
    review = BacktestReview(pd.DataFrame(), real_only=True)
    assert review.win_rate() is None


def test_avg_pl_none_when_no_conclusive_data():
    review = BacktestReview(pd.DataFrame(), real_only=True)
    assert review.avg_simulated_pl() is None


def test_max_drawdown_zero_when_no_data():
    review = BacktestReview(pd.DataFrame(), real_only=True)
    assert review.max_drawdown() == 0.0


# ---------------------------------------------------------------------------
# Win rate calculation
# ---------------------------------------------------------------------------

def test_win_rate_all_targets(repo):
    for sym in ("A", "B", "C"):
        create_snapshot(repo, stock(symbol=sym), "target_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    assert review.win_rate() == 1.0


def test_win_rate_all_stops(repo):
    for sym in ("A", "B"):
        create_snapshot(repo, stock(symbol=sym), "stop_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    assert review.win_rate() == 0.0


def test_win_rate_mixed(repo):
    create_snapshot(repo, stock(symbol="WIN1"), "target_hit")
    create_snapshot(repo, stock(symbol="WIN2"), "target_hit")
    create_snapshot(repo, stock(symbol="LOSE"), "stop_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    assert abs(review.win_rate() - 2 / 3) < 0.001


def test_win_rate_ignores_non_conclusive_outcomes(repo):
    create_snapshot(repo, stock(symbol="T"), "target_hit")
    create_snapshot(repo, stock(symbol="I"), "insufficient_future_data")
    create_snapshot(repo, stock(symbol="O"), "still_open")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    # Only the target_hit counts
    assert review.win_rate() == 1.0


# ---------------------------------------------------------------------------
# Simulated P/L
# ---------------------------------------------------------------------------

def test_avg_pl_positive_for_target_hits(repo):
    # entry=100, target=110, stop=95 → P/L = +10%
    create_snapshot(repo, stock(symbol="A"), "target_hit")
    create_snapshot(repo, stock(symbol="B"), "target_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    avg = review.avg_simulated_pl()
    assert avg is not None
    assert avg > 0


def test_avg_pl_negative_for_stop_hits(repo):
    # entry=100, stop=95 → P/L = -5%
    create_snapshot(repo, stock(symbol="A"), "stop_hit")
    create_snapshot(repo, stock(symbol="B"), "stop_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    avg = review.avg_simulated_pl()
    assert avg is not None
    assert avg < 0


def test_avg_pl_mixed_outcomes(repo):
    create_snapshot(repo, stock(symbol="W"), "target_hit")   # +10%
    create_snapshot(repo, stock(symbol="L"), "stop_hit")      # -5%
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    avg = review.avg_simulated_pl()
    assert avg is not None
    assert abs(avg - 0.025) < 0.001  # (0.10 + (-0.05)) / 2 = 0.025


# ---------------------------------------------------------------------------
# Equity curve
# ---------------------------------------------------------------------------

def test_equity_curve_empty_when_no_conclusive(repo):
    create_snapshot(repo, stock(symbol="X"), "insufficient_future_data")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    assert review.equity_curve() == []


def test_equity_curve_grows_on_wins(repo):
    create_snapshot(repo, stock(symbol="A"), "target_hit")
    create_snapshot(repo, stock(symbol="B"), "target_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    curve = review.equity_curve()
    assert len(curve) == 2
    assert curve[0] > 1.0
    assert curve[1] > curve[0]


def test_equity_curve_shrinks_on_losses(repo):
    create_snapshot(repo, stock(symbol="A"), "stop_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    curve = review.equity_curve()
    assert len(curve) == 1
    assert curve[0] < 1.0


# ---------------------------------------------------------------------------
# Max drawdown
# ---------------------------------------------------------------------------

def test_max_drawdown_zero_with_only_wins(repo):
    for sym in ("A", "B", "C"):
        create_snapshot(repo, stock(symbol=sym), "target_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    assert review.max_drawdown() == 0.0


def test_max_drawdown_positive_when_losses_follow_wins(repo):
    create_snapshot(repo, stock(symbol="W"), "target_hit")
    create_snapshot(repo, stock(symbol="L"), "stop_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    assert review.max_drawdown() > 0


# ---------------------------------------------------------------------------
# Grouping tables
# ---------------------------------------------------------------------------

def test_by_setup_category_returns_dataframe(repo):
    create_snapshot(repo, stock(symbol="A", category="Breakout Watch"), "target_hit")
    create_snapshot(repo, stock(symbol="B", category="Pullback Watch"), "stop_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    df = review.by_setup_category()
    assert isinstance(df, pd.DataFrame)
    assert "setup_category" in df.columns
    assert len(df) >= 1


def test_by_score_bucket_returns_dataframe(repo):
    create_snapshot(repo, stock(symbol="A", score=85), "target_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    df = review.by_score_bucket()
    assert isinstance(df, pd.DataFrame)
    assert "score_bucket" in df.columns


def test_by_universe_role_returns_dataframe(repo):
    create_snapshot(repo, stock(symbol="A", role="primary_candidate"), "target_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    df = review.by_universe_role()
    assert isinstance(df, pd.DataFrame)
    assert "universe_role" in df.columns


# ---------------------------------------------------------------------------
# Real-data-only enforcement
# ---------------------------------------------------------------------------

def test_demo_data_excluded_with_real_only(repo):
    create_snapshot(repo, stock(symbol="REAL"), "target_hit", provider="alpaca_iex", data_source="real_alpaca")
    create_snapshot(repo, stock(symbol="DEMO"), "target_hit", provider="demo_generated", data_source="demo_generated")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    prepared = review.prepared()
    symbols = list(prepared["symbol"].unique()) if not prepared.empty else []
    assert "DEMO" not in symbols


# ---------------------------------------------------------------------------
# Summary dict
# ---------------------------------------------------------------------------

def test_summary_contains_disclaimer(repo):
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    result = review.summary()
    assert "research" in result["research_disclaimer"].lower()
    assert "no trades" in result["research_disclaimer"].lower()


def test_summary_serialisable(repo):
    import json
    create_snapshot(repo, stock(symbol="A"), "target_hit")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    result = review.summary()
    # Should not raise
    json.dumps(result, default=str)


def test_summary_counts_match_prepared(repo):
    create_snapshot(repo, stock(symbol="A"), "target_hit")
    create_snapshot(repo, stock(symbol="B"), "insufficient_future_data")
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    review = BacktestReview(snaps, real_only=True)
    result = review.summary()
    assert result["snapshots_reviewed"] == 2
    assert result["conclusive_outcomes"] == 1
