import pandas as pd

from trading_bot.indicators import (
    average_true_range,
    crossover_signal,
    percent_return,
    relative_strength_index,
    simple_moving_average,
)


def test_simple_moving_average():
    series = pd.Series([1, 2, 3, 4, 5])
    result = simple_moving_average(series, 3)
    assert pd.isna(result.iloc[0])
    assert result.iloc[-1] == 4


def test_crossover_signal_bullish():
    fast = pd.Series([1, 1, 3], index=pd.date_range("2024-01-01", periods=3))
    slow = pd.Series([2, 2, 2], index=fast.index)
    signal = crossover_signal(fast, slow)
    assert signal.iloc[-1] == 1


def test_rsi_handles_flat_series():
    series = pd.Series([10] * 20)
    result = relative_strength_index(series, 14)
    assert result.iloc[-1] == 50


def test_atr_and_return():
    data = pd.DataFrame(
        {
            "high": [11, 12, 13, 14, 15],
            "low": [9, 10, 11, 12, 13],
            "close": [10, 11, 12, 13, 14],
        }
    )
    atr = average_true_range(data, 3)
    returns = percent_return(data["close"], 2)
    assert atr.iloc[-1] > 0
    assert round(returns.iloc[-1], 4) == round(14 / 12 - 1, 4)

