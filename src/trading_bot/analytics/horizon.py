"""Mechanical time-to-target horizon estimates.

RESEARCH SIMULATION ONLY — heuristics, not predictions.
No order, risk, or sizing logic lives here.
"""

from __future__ import annotations

import math


def bot_horizon_days(
    last: float,
    target: float | None,
    atr: float | None,
    realized_vol: float | None = None,
    *,
    max_days: int = 60,
) -> list[int] | None:
    """Mechanical time-to-target estimate as an inclusive [min, max] trading-day range.

    Returns None when there is no usable target (target is None) or atr is non-positive.
    RESEARCH SIMULATION ONLY — a heuristic, not a prediction.

    Parameters
    ----------
    last:
        Most recent price (close or live).
    target:
        Price target set by the scanner (entry + ATR * multiplier).
    atr:
        ATR(14) in dollar terms.
    realized_vol:
        Population stdev of simple daily returns (dimensionless fraction, e.g. 0.02 for 2%).
        Pass ``None`` or omit to skip volatility adjustment.
    max_days:
        Upper clamp for the result range.
    """
    if target is None or atr is None or atr <= 0:
        return None

    dist = target - last
    if dist <= 0:
        return [1, 1]

    center = dist / atr  # ATRs of distance == trading days @ ~1 ATR/day

    atr_pct = (atr / last) if last > 0 else 0.0
    if realized_vol and atr_pct > 0:
        vol_adj = realized_vol / atr_pct
    else:
        vol_adj = 1.0

    w = max(0.20, min(0.80, 0.30 * vol_adj))

    lo = max(1, round(center * (1 - w)))
    hi = round(center * (1 + w))

    lo = max(1, min(lo, max_days))
    hi = max(1, min(hi, max_days))
    if hi < lo:
        hi = lo

    return [int(lo), int(hi)]


def horizon_basis(last: float, target: float | None, atr: float | None) -> str:
    """Human-readable description of the ATR distance to target.

    Returns an empty string when the calculation is not possible.
    Example: "~3.0×ATR to target at current RVOL"
    """
    if target is None or atr is None or atr <= 0 or last <= 0:
        return ""
    dist = target - last
    if dist <= 0:
        return ""
    multiples = dist / atr
    return f"~{multiples:.1f}×ATR to target at current RVOL"


def realized_vol_from_closes(closes: list[float]) -> float | None:
    """Population stdev of simple daily returns of the last ~14 closes.

    Returns None if fewer than 3 closes are provided.
    """
    if len(closes) < 3:
        return None
    # Use up to the last 14 closes
    sample = closes[-14:]
    returns = [
        (sample[i] - sample[i - 1]) / sample[i - 1]
        for i in range(1, len(sample))
        if sample[i - 1] != 0
    ]
    if len(returns) < 2:
        return None
    # population stdev
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)
