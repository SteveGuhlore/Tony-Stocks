from __future__ import annotations
from fastapi import APIRouter, Depends
from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import AnalyticsResponse, BacktestSummaryResponse
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.analytics.backtest_review import BacktestReview
from trading_bot.analytics.outcomes import OutcomeAnalytics

router = APIRouter(tags=["analytics"])

@router.get("/analytics/backtest", response_model=AnalyticsResponse)
def get_analytics(repo: ScannerRepository = Depends(get_repo)):
    df = repo.list_snapshots_for_analytics()
    s = BacktestReview(snapshots=df, real_only=True).summary()
    analytics = OutcomeAnalytics(df, include_seeded_demo=False)
    counts_df = analytics.outcome_counts()
    return AnalyticsResponse(
        backtest=BacktestSummaryResponse(
            research_disclaimer=s["research_disclaimer"],
            snapshots_reviewed=s["snapshots_reviewed"],
            conclusive_outcomes=s["conclusive_outcomes"],
            win_rate=s["win_rate"],
            avg_simulated_pl_per_trade=s["avg_simulated_pl_per_trade"],
            max_drawdown=s["max_drawdown"],
            equity_curve=s["equity_curve"],
            by_setup_category=s["by_setup_category"],
            by_score_bucket=s["by_score_bucket"],
            by_universe_role=s["by_universe_role"],
        ),
        outcome_counts=counts_df.to_dict("records") if not counts_df.empty else [])
