from __future__ import annotations

import pandas as pd

from trading_bot.intraday import calculate_intraday_features


def _bars(closes: list[float], volumes: list[int] | None = None) -> pd.DataFrame:
    index = pd.date_range("2026-05-18 13:30:00+00:00", periods=len(closes), freq="5min")
    vols = volumes or [1000] * len(closes)
    return pd.DataFrame(
        {
            "open": closes,
            "high": [value + 0.5 for value in closes],
            "low": [value - 0.5 for value in closes],
            "close": closes,
            "volume": vols,
        },
        index=index,
    )


def test_intraday_config_style_5min_features_include_vwap_and_range():
    features = calculate_intraday_features("PLTR", _bars([100, 101, 102, 103, 104, 105]), timeframe="5Min")
    assert features.data_available
    assert features.latest_close == 105
    assert features.day_open == 100
    assert features.vwap is not None
    assert features.price_above_vwap is True
    assert features.trend_since_open == "intraday_trend_up"
    assert features.intraday_change_percent and features.intraday_change_percent > 0


def test_opening_range_requires_first_30_minutes_for_5min_bars():
    insufficient = calculate_intraday_features("SOFI", _bars([10, 10.1, 10.2]), timeframe="5Min")
    assert insufficient.opening_range_high is None
    assert insufficient.status == "intraday_opening_range_unavailable"

    enough = calculate_intraday_features("SOFI", _bars([10, 10.1, 10.2, 10.3, 10.4, 11]), timeframe="5Min")
    assert enough.opening_range_high is not None
    assert enough.opening_range_low is not None


def test_vwap_returns_insufficient_when_volume_missing():
    features = calculate_intraday_features("HOOD", _bars([20, 20.2, 20.3, 20.5, 20.6, 20.7], [0, 0, 0, 0, 0, 0]), timeframe="5Min")
    assert features.data_available
    assert features.vwap is None
    assert features.status == "intraday_vwap_unavailable"


def test_intraday_missing_data_returns_clean_status():
    features = calculate_intraday_features("PLTR", pd.DataFrame(), timeframe="5Min")
    assert not features.data_available
    assert features.status == "intraday_data_missing"
