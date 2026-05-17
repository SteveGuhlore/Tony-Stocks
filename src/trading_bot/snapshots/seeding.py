from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading_bot.data.market_data import MarketDataProvider
from trading_bot.data.universe import UniverseSymbol
from trading_bot.snapshots.followup import (
    OUTCOME_ENTRY_NOT_TRIGGERED,
    OUTCOME_FAILED_SETUP,
    OUTCOME_INSUFFICIENT_FUTURE_DATA,
    OUTCOME_PARTIAL_MOVE,
    OUTCOME_STOP_HIT,
    OUTCOME_TARGET_HIT,
    calculate_snapshot_followup,
)


DEMO_SEED_OUTCOMES = (
    OUTCOME_TARGET_HIT,
    OUTCOME_STOP_HIT,
    OUTCOME_PARTIAL_MOVE,
    OUTCOME_FAILED_SETUP,
    OUTCOME_ENTRY_NOT_TRIGGERED,
    OUTCOME_INSUFFICIENT_FUTURE_DATA,
)


@dataclass(frozen=True)
class DemoSeedPlan:
    symbol: str
    expected_outcome: str
    index_offset: int


def build_demo_seed_snapshots(
    provider: MarketDataProvider,
    metadata_by_symbol: dict[str, UniverseSymbol],
    scan_run_id: int,
    count: int = 12,
    days_back_start: int = 25,
    note_prefix: str = "Demo seeded snapshot",
    lookback_days: int = 120,
    timeframe: str = "daily",
) -> list[dict[str, Any]]:
    """Build historical demo snapshots whose outcomes are calculated from future demo bars."""
    plans = _seed_plans(metadata_by_symbol, count=count, days_back_start=days_back_start)
    snapshots: list[dict[str, Any]] = []
    for plan in plans:
        metadata = metadata_by_symbol.get(plan.symbol, UniverseSymbol(symbol=plan.symbol))
        data = provider.fetch_ohlcv(plan.symbol, lookback_days, timeframe)
        snapshot = _snapshot_for_outcome(
            data=data,
            plan=plan,
            metadata=metadata,
            scan_run_id=scan_run_id,
            note_prefix=note_prefix,
        )
        if snapshot:
            snapshots.append(snapshot)
    return snapshots


def _seed_plans(metadata_by_symbol: dict[str, UniverseSymbol], count: int, days_back_start: int) -> list[DemoSeedPlan]:
    preferred = [
        "PLTR",
        "UPST",
        "SOFI",
        "U",
        "ROKU",
        "HIMS",
        "ELF",
        "BILL",
        "AI",
        "HOOD",
        "GTLB",
        "NET",
    ]
    symbols = [symbol for symbol in preferred if symbol in metadata_by_symbol]
    symbols.extend(symbol for symbol in metadata_by_symbol if symbol not in symbols)
    outcomes = list(DEMO_SEED_OUTCOMES)
    plans: list[DemoSeedPlan] = []
    for index, symbol in enumerate(symbols[:count]):
        outcome = outcomes[index % len(outcomes)]
        offset = max(1, days_back_start - (index % 5))
        if outcome == OUTCOME_ENTRY_NOT_TRIGGERED:
            offset = 8
        elif outcome == OUTCOME_INSUFFICIENT_FUTURE_DATA:
            offset = 0
        plans.append(DemoSeedPlan(symbol=symbol, expected_outcome=outcome, index_offset=offset))
    return plans


def _snapshot_for_outcome(
    data: pd.DataFrame,
    plan: DemoSeedPlan,
    metadata: UniverseSymbol,
    scan_run_id: int,
    note_prefix: str,
) -> dict[str, Any] | None:
    if data.empty:
        return None
    index_position = len(data) - 1 - plan.index_offset
    if index_position < 0:
        return None
    row = data.iloc[index_position]
    future = data.iloc[index_position + 1 :]
    close = float(row["close"])
    if plan.expected_outcome == OUTCOME_INSUFFICIENT_FUTURE_DATA:
        entry = close
        stop = max(close * 0.94, 0.01)
        target = close * 1.08
    elif future.empty:
        return None
    else:
        entry, stop, target = _levels_for_expected_outcome(close, future, plan.expected_outcome)
    if not (entry > 0 and stop > 0 and target > entry and stop < entry):
        return None

    candidate = {
        "id": 0,
        "symbol": plan.symbol,
        "snapshot_time": pd.Timestamp(data.index[index_position]).isoformat(),
        "close": close,
        "entry": entry,
        "stop": stop,
        "target": target,
    }
    calculated = calculate_snapshot_followup(candidate, data)
    if calculated.outcome_label != plan.expected_outcome:
        return None

    risk = entry - stop
    reward = target - entry
    tags = sorted(set(metadata.tags + ("demo_seeded", "outcome_fixture")))
    return {
        "scan_run_id": scan_run_id,
        "symbol": plan.symbol,
        "snapshot_time": candidate["snapshot_time"],
        "universe_role": metadata.universe_role or "primary_candidate",
        "tags": tags,
        "setup_category": "Demo Outcome Fixture",
        "total_score": 70.0,
        "close": round(close, 4),
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "risk_reward": round(reward / risk, 2),
        "trade_plan_valid": 1,
        "trade_plan_status": "valid",
        "dollar_volume": round(float(row["close"] * row["volume"]), 2),
        "relative_volume": 1.0,
        "atr_percent": 0.02,
        "reasons": ["Demo seeded snapshot for outcome tracker testing."],
        "warnings": ["Seeded demo snapshot; not evidence of real market edge."],
        "candidate_summary": "Demo seeded snapshot for dashboard/outcome tracker testing only.",
        "status": "open/watch",
        "notes": f"{note_prefix} - expected {plan.expected_outcome}. Testing only; not evidence of real market edge.",
    }


def _levels_for_expected_outcome(close: float, future: pd.DataFrame, expected_outcome: str) -> tuple[float, float, float]:
    future_high = float(future["high"].max())
    future_low = float(future["low"].min())
    if expected_outcome == OUTCOME_TARGET_HIT:
        first = future.iloc[0]
        entry = min(close, float(first["high"]) * 0.995)
        target = entry + max(float(first["high"]) - entry, entry * 0.01) * 0.6
        stop = min(float(future["low"].min()) * 0.95, entry * 0.94)
        return entry, max(stop, 0.01), target
    if expected_outcome == OUTCOME_STOP_HIT:
        first = future.iloc[0]
        entry = min(close, float(first["high"]) * 0.995)
        stop = float(first["low"]) * 1.002
        if stop >= entry:
            stop = entry * 0.99
        target = max(future_high * 1.08, entry * 1.08)
        return entry, max(stop, 0.01), target
    if expected_outcome == OUTCOME_PARTIAL_MOVE:
        entry = min(close, future_high * 0.98)
        stop = max(future_low * 0.90, 0.01)
        target = future_high * 1.10
        return entry, stop, target
    if expected_outcome == OUTCOME_FAILED_SETUP:
        entry = future_high * 0.9995
        stop = max(future_low * 0.90, 0.01)
        target = future_high * 1.10
        return entry, stop, target
    if expected_outcome == OUTCOME_ENTRY_NOT_TRIGGERED:
        entry = future_high * 1.05
        stop = max(close * 0.90, 0.01)
        target = entry * 1.08
        return entry, stop, target
    raise ValueError(f"Unsupported demo seed outcome: {expected_outcome}")
