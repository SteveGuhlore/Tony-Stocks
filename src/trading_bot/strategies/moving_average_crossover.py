from __future__ import annotations

import pandas as pd

from trading_bot.indicators import crossover_signal, simple_moving_average
from trading_bot.strategies.base import Strategy


class MovingAverageCrossoverStrategy(Strategy):
    name = "moving_average_crossover"

    def __init__(self, fast_window: int = 20, slow_window: int = 50) -> None:
        if fast_window <= 0 or slow_window <= 0:
            raise ValueError("Moving average windows must be positive.")
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window.")
        self.fast_window = fast_window
        self.slow_window = slow_window

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if "close" not in data.columns:
            raise ValueError("Data must include a 'close' column.")
        close = data["close"]
        fast = simple_moving_average(close, self.fast_window)
        slow = simple_moving_average(close, self.slow_window)
        return crossover_signal(fast, slow)
