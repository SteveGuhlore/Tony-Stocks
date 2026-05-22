from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading_bot.analytics.outcomes import (
    OutcomeAnalytics,
    STOP_OUTCOMES,
    TARGET_OUTCOMES,
)
from trading_bot.metrics import calculate_max_drawdown

RESEARCH_DISCLAIMER = (
    "Research only. Simulated from stored scanner outcomes. "
    "Not evidence of real market edge. No trades placed."
)


@dataclass(frozen=True)
class BacktestReview:
    """Research-only backtest review of candidate snapshot outcomes.

    Replays stored scanner signals (entry, stop, target, outcome_label) in
    chronological order to produce simulated equity metrics. No new OHLCV data
    is fetched and no trades are placed. Results are preliminary until enough
    conclusive outcomes exist.
    """

    snapshots: pd.DataFrame
    real_only: bool = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _analytics(self) -> OutcomeAnalytics:
        return OutcomeAnalytics(
            self.snapshots,
            include_seeded_demo=False,
            real_only=self.real_only,
        )

    def prepared(self) -> pd.DataFrame:
        """Normalized snapshots with real-data-only filtering applied."""
        return self._analytics().prepared()

    def _conclusive_from(self, prepared: pd.DataFrame) -> pd.DataFrame:
        """Filter an already-prepared DataFrame to conclusive trades only."""
        if prepared.empty:
            return prepared
        mask = prepared["outcome_label"].isin(TARGET_OUTCOMES | STOP_OUTCOMES)
        data = prepared[mask].copy()
        for col in ("entry", "stop", "target"):
            if col in data.columns:
                data = data[data[col].notna() & (data[col].astype(float) > 0)]
        if "snapshot_time" in data.columns:
            data = data.sort_values("snapshot_time")
        return data

    def conclusive_trades(self) -> pd.DataFrame:
        """Snapshots with a target_hit or stop_hit outcome and valid prices."""
        return self._conclusive_from(self.prepared())

    def _pl_from_conclusive(self, conclusive: pd.DataFrame) -> list[float]:
        """Vectorised simulated P/L fraction for each conclusive trade."""
        if conclusive.empty:
            return []
        entry = conclusive["entry"].astype(float) if "entry" in conclusive.columns else pd.Series(dtype=float, index=conclusive.index)
        stop = conclusive["stop"].astype(float) if "stop" in conclusive.columns else pd.Series(dtype=float, index=conclusive.index)
        target = conclusive["target"].astype(float) if "target" in conclusive.columns else pd.Series(dtype=float, index=conclusive.index)
        outcome = conclusive["outcome_label"].astype(str)

        is_win = outcome.isin(TARGET_OUTCOMES) & (target > entry) & (entry > 0)
        is_loss = outcome.isin(STOP_OUTCOMES) & (stop > 0) & (stop < entry) & (entry > 0)

        pl = pd.Series(index=conclusive.index, dtype=float)
        pl[is_win] = (target[is_win] - entry[is_win]) / entry[is_win]
        pl[is_loss] = (stop[is_loss] - entry[is_loss]) / entry[is_loss]

        return pl[is_win | is_loss].tolist()

    def _pl_per_trade(self) -> list[float]:
        """Simulated P/L fraction for each conclusive trade, chronologically."""
        return self._pl_from_conclusive(self.conclusive_trades())

    def _equity_series_from_pl(self, pl: list[float]) -> pd.Series:
        if not pl:
            return pd.Series(dtype=float)
        equity = [1.0]
        for r in pl:
            equity.append(equity[-1] * (1.0 + r))
        return pd.Series(equity[1:], dtype=float)

    def _equity_series(self) -> pd.Series:
        """Compound equity curve starting at 1.0, one value per trade."""
        return self._equity_series_from_pl(self._pl_per_trade())

    # ------------------------------------------------------------------
    # Public metrics
    # ------------------------------------------------------------------

    def win_rate(self) -> float | None:
        """Fraction of conclusive trades that hit their target (0.0–1.0)."""
        trades = self.conclusive_trades()
        if trades.empty:
            return None
        wins = int(trades["outcome_label"].isin(TARGET_OUTCOMES).sum())
        losses = int(trades["outcome_label"].isin(STOP_OUTCOMES).sum())
        total = wins + losses
        return wins / total if total > 0 else None

    def avg_simulated_pl(self) -> float | None:
        """Average simulated P/L fraction per conclusive trade."""
        pl = self._pl_per_trade()
        return float(sum(pl) / len(pl)) if pl else None

    def max_drawdown(self) -> float:
        """Max peak-to-trough drawdown of the simulated equity curve (0.0–1.0)."""
        return calculate_max_drawdown(self._equity_series())

    def equity_curve(self) -> list[float]:
        """Compound equity curve as a list of values, starting trade after 1.0."""
        curve = self._equity_series()
        return [round(float(v), 6) for v in curve] if not curve.empty else []

    def by_setup_category(self) -> pd.DataFrame:
        return self._analytics().grouped_by("setup_category")

    def by_score_bucket(self) -> pd.DataFrame:
        return self._analytics().grouped_by("score_bucket")

    def by_universe_role(self) -> pd.DataFrame:
        return self._analytics().grouped_by("universe_role")

    # ------------------------------------------------------------------
    # Serialisable summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a serialisable summary for JSON report output.

        Uses a single OutcomeAnalytics instance and a single prepared() call
        to avoid redundant recomputation across metrics and grouped tables.
        """
        analytics = self._analytics()
        prepared = analytics.prepared()
        conclusive = self._conclusive_from(prepared)

        pl = self._pl_from_conclusive(conclusive)

        if not conclusive.empty:
            wins = int(conclusive["outcome_label"].isin(TARGET_OUTCOMES).sum())
            losses = int(conclusive["outcome_label"].isin(STOP_OUTCOMES).sum())
            total = wins + losses
            wr: float | None = wins / total if total > 0 else None
        else:
            wr = None

        avg_pl: float | None = float(sum(pl) / len(pl)) if pl else None
        equity = self._equity_series_from_pl(pl)
        md = calculate_max_drawdown(equity)
        curve = [round(float(v), 6) for v in equity] if not equity.empty else []

        by_setup = analytics.grouped_by("setup_category")
        by_bucket = analytics.grouped_by("score_bucket")
        by_role = analytics.grouped_by("universe_role")

        return {
            "research_disclaimer": RESEARCH_DISCLAIMER,
            "snapshots_reviewed": len(prepared),
            "conclusive_outcomes": len(conclusive),
            "win_rate": round(wr, 4) if wr is not None else None,
            "avg_simulated_pl_per_trade": round(avg_pl, 4) if avg_pl is not None else None,
            "max_drawdown": round(md, 4) if md > 0 else None,
            "equity_curve": curve,
            "by_setup_category": by_setup.to_dict("records") if not by_setup.empty else [],
            "by_score_bucket": by_bucket.to_dict("records") if not by_bucket.empty else [],
            "by_universe_role": by_role.to_dict("records") if not by_role.empty else [],
        }
