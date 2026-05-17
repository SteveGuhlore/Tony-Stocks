import pandas as pd

from trading_bot.snapshots import (
    OUTCOME_ENTRY_NOT_TRIGGERED,
    OUTCOME_INSUFFICIENT_FUTURE_DATA,
    OUTCOME_PARTIAL_MOVE,
    OUTCOME_STOP_HIT,
    OUTCOME_STOP_BEFORE_TARGET,
    OUTCOME_TARGET_HIT,
    OUTCOME_TARGET_BEFORE_STOP,
    calculate_snapshot_followup,
)


def snapshot(**overrides):
    base = {
        "id": 1,
        "symbol": "TEST",
        "snapshot_time": "2026-01-01T00:00:00+00:00",
        "close": 100.0,
        "entry": 101.0,
        "stop": 95.0,
        "target": 110.0,
    }
    base.update(overrides)
    return base


def bars(highs, lows, closes):
    dates = pd.bdate_range("2026-01-02", periods=len(closes))
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1_000_000] * len(closes),
        },
        index=dates,
    )


def test_followup_target_hit():
    result = calculate_snapshot_followup(
        snapshot(),
        bars(highs=[102, 111], lows=[99, 100], closes=[102, 110]),
    )
    assert result.entry_triggered
    assert result.outcome_label == OUTCOME_TARGET_HIT
    assert result.highest_price_seen == 111
    assert result.lowest_price_seen == 99


def test_followup_stop_hit():
    result = calculate_snapshot_followup(
        snapshot(),
        bars(highs=[102, 104], lows=[99, 94], closes=[101, 95]),
    )
    assert result.entry_triggered
    assert result.outcome_label == OUTCOME_STOP_HIT


def test_followup_same_bar_policy_is_conservative_by_default():
    result = calculate_snapshot_followup(
        snapshot(),
        bars(highs=[111], lows=[94], closes=[100]),
    )
    assert result.entry_triggered
    assert result.outcome_label == OUTCOME_STOP_BEFORE_TARGET


def test_followup_same_bar_can_be_optimistic_if_configured():
    result = calculate_snapshot_followup(
        snapshot(),
        bars(highs=[111], lows=[94], closes=[100]),
        same_bar_target_stop_policy="optimistic_target_first",
    )
    assert result.entry_triggered
    assert result.outcome_label == OUTCOME_TARGET_BEFORE_STOP


def test_followup_entry_not_triggered():
    result = calculate_snapshot_followup(
        snapshot(),
        bars(highs=[100, 100.5], lows=[98, 97], closes=[99, 98]),
    )
    assert not result.entry_triggered
    assert result.outcome_label == OUTCOME_ENTRY_NOT_TRIGGERED


def test_followup_insufficient_future_data_when_no_later_bars():
    result = calculate_snapshot_followup(snapshot(), pd.DataFrame())
    assert result.outcome_label == OUTCOME_INSUFFICIENT_FUTURE_DATA
    assert result.result_eod is None
    assert result.highest_price_seen is None


def test_followup_horizon_returns_and_missing_horizons():
    result = calculate_snapshot_followup(
        snapshot(target=200),
        bars(
            highs=[102, 103, 104, 105, 106],
            lows=[99, 99, 99, 99, 99],
            closes=[101, 102, 103, 104, 105],
        ),
    )
    assert result.outcome_label == OUTCOME_PARTIAL_MOVE
    assert result.result_eod == 0.01
    assert result.result_3d == 0.03
    assert result.result_5d == 0.05
    assert result.result_10d is None
    assert result.result_20d is None
    assert result.result_1h is None
