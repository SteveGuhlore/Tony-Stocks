"""Tests for trading_bot.analytics.horizon.

Covers the full contract:
  (a) inverse-ATR scaling
  (b) None target → None
  (c) atr<=0 → None; dist<=0 → [1,1]
  (d) higher realized_vol widens the band
  (e) clamp to [1, max_days] and hi>=lo
  (f) realized_vol_from_closes edge cases
"""

from __future__ import annotations

import pytest

from trading_bot.analytics.horizon import (
    bot_horizon_days,
    horizon_basis,
    realized_vol_from_closes,
)


# ── (a) inverse-ATR scaling ──────────────────────────────────────────────────


def test_larger_atr_gives_smaller_or_equal_range():
    """Larger ATR → fewer days to cover same price distance."""
    last = 100.0
    target = 110.0  # $10 distance

    result_small = bot_horizon_days(last, target, atr=1.0)  # 10 ATRs away
    result_large = bot_horizon_days(last, target, atr=5.0)  # 2 ATRs away

    assert result_small is not None
    assert result_large is not None
    # Larger ATR → both lo and hi must be <= those of the smaller ATR
    assert result_large[0] <= result_small[0]
    assert result_large[1] <= result_small[1]


def test_center_is_dist_over_atr():
    """Without vol adjustment center == dist/atr, band is ±30%.

    center = (60-50)/2 = 5; w = 0.30 (vol_adj=1, default)
    lo = max(1, round(5 * 0.70)) = round(3.5) = 4  (banker's rounding)
    hi = round(5 * 1.30) = round(6.5) = 6           (banker's rounding)
    """
    last = 50.0
    target = 60.0
    atr = 2.0
    result = bot_horizon_days(last, target, atr)
    assert result == [4, 6]


# ── (b) None target → None ───────────────────────────────────────────────────


def test_none_target_returns_none():
    assert bot_horizon_days(100.0, None, 2.0) is None


# ── (c) atr edge cases ───────────────────────────────────────────────────────


def test_zero_atr_returns_none():
    assert bot_horizon_days(100.0, 110.0, 0.0) is None


def test_negative_atr_returns_none():
    assert bot_horizon_days(100.0, 110.0, -1.0) is None


def test_none_atr_returns_none():
    assert bot_horizon_days(100.0, 110.0, None) is None


def test_dist_zero_returns_one_one():
    """target == last → already at target."""
    assert bot_horizon_days(100.0, 100.0, 2.0) == [1, 1]


def test_dist_negative_returns_one_one():
    """target < last → already through target."""
    assert bot_horizon_days(105.0, 100.0, 2.0) == [1, 1]


# ── (d) higher realized_vol widens the band ──────────────────────────────────


def test_higher_realized_vol_widens_band():
    last = 100.0
    target = 120.0
    atr = 2.0
    low_vol = 0.005  # very low → vol_adj < 1 → w shrunk toward 0.20
    high_vol = 0.10  # high → vol_adj > 1 → w pushed toward 0.80

    result_low = bot_horizon_days(last, target, atr, realized_vol=low_vol)
    result_high = bot_horizon_days(last, target, atr, realized_vol=high_vol)

    assert result_low is not None
    assert result_high is not None
    band_low = result_low[1] - result_low[0]
    band_high = result_high[1] - result_high[0]
    assert band_high >= band_low


def test_no_realized_vol_uses_default_band():
    """Omitting realized_vol should equal realized_vol=None."""
    last = 100.0
    target = 115.0
    atr = 1.5
    r1 = bot_horizon_days(last, target, atr)
    r2 = bot_horizon_days(last, target, atr, realized_vol=None)
    assert r1 == r2


# ── (e) clamping and hi>=lo invariant ────────────────────────────────────────


def test_results_clamp_to_max_days():
    """Very small ATR relative to distance should clamp at max_days."""
    result = bot_horizon_days(100.0, 200.0, atr=0.01, max_days=30)
    assert result is not None
    assert result[1] <= 30
    assert result[0] >= 1


def test_hi_always_ge_lo():
    """hi must never be less than lo regardless of inputs."""
    for atr in [0.5, 1.0, 2.0, 5.0]:
        for target in [101.0, 110.0, 150.0]:
            r = bot_horizon_days(100.0, target, atr)
            if r is not None:
                assert r[1] >= r[0], f"hi < lo for atr={atr}, target={target}: {r}"


def test_clamp_lo_min_is_1():
    """lo must always be at least 1."""
    result = bot_horizon_days(100.0, 100.5, atr=2.0)
    assert result is not None
    assert result[0] >= 1


def test_custom_max_days_respected():
    result = bot_horizon_days(10.0, 500.0, atr=0.1, max_days=10)
    assert result == [10, 10]


# ── (f) realized_vol_from_closes ─────────────────────────────────────────────


def test_realized_vol_none_for_fewer_than_3():
    assert realized_vol_from_closes([]) is None
    assert realized_vol_from_closes([100.0]) is None
    assert realized_vol_from_closes([100.0, 101.0]) is None


def test_realized_vol_positive_for_valid_input():
    closes = [100.0, 101.0, 102.0, 101.5, 103.0]
    vol = realized_vol_from_closes(closes)
    assert vol is not None
    assert vol > 0.0


def test_realized_vol_exactly_3_closes():
    closes = [100.0, 101.0, 100.0]
    vol = realized_vol_from_closes(closes)
    assert vol is not None
    assert vol > 0.0


def test_realized_vol_uses_at_most_14():
    """15 closes should give same result as last-14 only."""
    closes_15 = [float(100 + i) for i in range(15)]
    closes_14 = closes_15[1:]  # last 14 of the 15
    # Both should give the same vol since _14 slice matches
    vol_15 = realized_vol_from_closes(closes_15)
    vol_14 = realized_vol_from_closes(closes_14)
    assert vol_15 == vol_14


def test_realized_vol_constant_prices():
    """Flat prices → returns are 0 → stdev is 0."""
    closes = [100.0] * 10
    vol = realized_vol_from_closes(closes)
    # All returns = 0; population stdev = 0.0
    assert vol is not None
    assert vol == pytest.approx(0.0, abs=1e-10)


# ── horizon_basis ─────────────────────────────────────────────────────────────


def test_horizon_basis_format():
    basis = horizon_basis(100.0, 106.0, 2.0)  # dist=6, atr=2 → 3.0×ATR
    assert basis == "~3.0×ATR to target at current RVOL"


def test_horizon_basis_none_target():
    assert horizon_basis(100.0, None, 2.0) == ""


def test_horizon_basis_zero_atr():
    assert horizon_basis(100.0, 110.0, 0.0) == ""


def test_horizon_basis_dist_zero():
    assert horizon_basis(100.0, 100.0, 2.0) == ""
