import pandas as pd

from trading_bot.backtester import Backtester
from trading_bot.risk import RiskManager
from trading_bot.strategies import MovingAverageCrossoverStrategy


def sample_data():
    dates = pd.date_range("2024-01-01", periods=80)
    close = list(range(100, 180))
    return pd.DataFrame(
        {
            "open": close,
            "high": [x + 1 for x in close],
            "low": [x - 1 for x in close],
            "close": close,
            "volume": [1000] * len(close),
        },
        index=dates,
    )


def test_backtester_runs():
    strategy = MovingAverageCrossoverStrategy(fast_window=3, slow_window=5)
    risk = RiskManager()
    result = Backtester(strategy=strategy, risk_manager=risk).run(sample_data())
    assert result.metrics.starting_cash == 10_000
    assert result.metrics.ending_equity > 0
    assert len(result.equity_curve) == 80
