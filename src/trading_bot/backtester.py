from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading_bot.metrics import BacktestMetrics, calculate_max_drawdown
from trading_bot.risk import RiskManager
from trading_bot.strategies.base import Strategy


@dataclass(frozen=True)
class Trade:
    timestamp: pd.Timestamp
    side: str
    price: float
    quantity: int
    cash_after: float
    position_after: int


@dataclass(frozen=True)
class BacktestResult:
    strategy_name: str
    trades: list[Trade]
    equity_curve: pd.Series
    metrics: BacktestMetrics

    def print_summary(self) -> None:
        print(f"Strategy: {self.strategy_name}")
        print(f"Starting cash: ${self.metrics.starting_cash:,.2f}")
        print(f"Ending equity: ${self.metrics.ending_equity:,.2f}")
        print(f"Total return: {self.metrics.total_return_fraction * 100:.2f}%")
        print(f"Max drawdown: {self.metrics.max_drawdown_fraction * 100:.2f}%")
        print(f"Trade count: {self.metrics.trade_count}")
        if self.metrics.win_rate_fraction is not None:
            print(f"Win rate: {self.metrics.win_rate_fraction * 100:.2f}%")
        else:
            print("Win rate: n/a")


class Backtester:
    def __init__(
        self,
        strategy: Strategy,
        risk_manager: RiskManager,
        starting_cash: float = 10_000.0,
        fee_per_trade: float = 0.0,
        slippage_fraction: float = 0.0005,
    ) -> None:
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.starting_cash = starting_cash
        self.fee_per_trade = fee_per_trade
        self.slippage_fraction = slippage_fraction

    def run(self, data: pd.DataFrame) -> BacktestResult:
        if data.empty:
            raise ValueError("Cannot backtest empty data.")
        if "close" not in data.columns:
            raise ValueError("Backtest data must include a 'close' column.")

        signals = self.strategy.generate_signals(data)
        cash = float(self.starting_cash)
        position = 0
        trades: list[Trade] = []
        equity_values: list[float] = []
        equity_index: list[pd.Timestamp] = []
        peak_equity = float(self.starting_cash)

        for timestamp, row in data.iterrows():
            price = float(row["close"])
            signal = int(signals.loc[timestamp]) if timestamp in signals.index else 0
            equity = cash + position * price
            peak_equity = max(peak_equity, equity)

            if self.risk_manager.drawdown_breached(peak_equity, equity):
                signal = 0

            if signal == 1 and position == 0:
                decision = self.risk_manager.approve_order("buy", equity=equity, price=price, current_position=position)
                if decision.allowed:
                    fill_price = price * (1 + self.slippage_fraction)
                    cost = decision.quantity * fill_price + self.fee_per_trade
                    if cost <= cash:
                        cash -= cost
                        position += decision.quantity
                        trades.append(Trade(timestamp, "buy", fill_price, decision.quantity, cash, position))
            elif signal == -1 and position > 0:
                fill_price = price * (1 - self.slippage_fraction)
                proceeds = position * fill_price - self.fee_per_trade
                cash += proceeds
                trades.append(Trade(timestamp, "sell", fill_price, position, cash, 0))
                position = 0

            ending_equity = cash + position * price
            equity_index.append(pd.Timestamp(timestamp))
            equity_values.append(ending_equity)

        equity_curve = pd.Series(equity_values, index=pd.DatetimeIndex(equity_index), name="equity")
        ending_equity = float(equity_curve.iloc[-1])
        metrics = BacktestMetrics(
            starting_cash=self.starting_cash,
            ending_equity=ending_equity,
            total_return_fraction=(ending_equity - self.starting_cash) / self.starting_cash,
            max_drawdown_fraction=calculate_max_drawdown(equity_curve),
            trade_count=len(trades),
            win_rate_fraction=None,
        )
        return BacktestResult(self.strategy.name, trades, equity_curve, metrics)
