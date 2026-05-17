from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestMetrics:
    starting_cash: float
    ending_equity: float
    total_return_fraction: float
    max_drawdown_fraction: float
    trade_count: int
    win_rate_fraction: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "starting_cash": self.starting_cash,
            "ending_equity": self.ending_equity,
            "total_return_fraction": self.total_return_fraction,
            "max_drawdown_fraction": self.max_drawdown_fraction,
            "trade_count": self.trade_count,
            "win_rate_fraction": self.win_rate_fraction,
        }


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    if equity_curve.empty:
        return 0.0
    running_peak = equity_curve.cummax()
    drawdown = (running_peak - equity_curve) / running_peak
    return float(drawdown.max())
