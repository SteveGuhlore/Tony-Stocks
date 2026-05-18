from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from trading_bot.intraday.features import IntradayFeatures, calculate_intraday_features
from trading_bot.utils.time_utils import utc_now_iso

ENTRY_STATUS_PENDING = "pending"
ENTRY_STATUS_TRIGGERED = "triggered"
ENTRY_STATUS_NOT_TRIGGERED = "not_triggered"
ENTRY_STATUS_EXPIRED = "expired"
ENTRY_STATUS_MISSING_REAL_DATA = "missing_real_data"
ENTRY_STATUS_NO_INTRADAY_TRIGGER = "no_intraday_trigger"

TRIGGER_SOURCE_ALPACA_5MIN = "alpaca_5min"
TRIGGER_TIMEFRAME_5MIN = "5Min"

RULE_BREAKOUT = "breakout_above_recent_high"
RULE_MOMENTUM = "momentum_break_5min_high_above_vwap"
RULE_PULLBACK = "pullback_reclaim_vwap_or_prior_high"
RULE_FALLBACK_MISSING = "missing_intraday_context"
RULE_FALLBACK_NO_TRIGGER = "no_intraday_trigger_rule"


@dataclass(frozen=True)
class PlannedEntryPlan:
    """Research-only planned intraday entry trigger (not a buy recommendation)."""

    snapshot_price: float
    snapshot_bar_time: str | None
    planned_entry_price: float | None
    planned_entry_rule: str
    planned_entry_buffer_pct: float
    entry_status: str
    entry_trigger_source: str | None
    entry_trigger_timeframe: str | None
    entry_trigger_notes: str

    def to_snapshot_fields(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EntryTriggerSimulationResult:
    """Result of simulating whether future 5Min bars hit the planned trigger."""

    entry_status: str
    actual_entry_price: float | None
    actual_entry_time: str | None
    entry_triggered: bool
    entry_triggered_at: str | None
    entry_trigger_source: str | None
    entry_trigger_timeframe: str | None
    entry_trigger_notes: str
    last_checked_at: str

    def to_update_fields(self) -> dict[str, Any]:
        return {
            "entry_status": self.entry_status,
            "actual_entry_price": self.actual_entry_price,
            "actual_entry_time": self.actual_entry_time,
            "entry_triggered": int(self.entry_triggered),
            "entry_triggered_at": self.entry_triggered_at,
            "entry_trigger_price": self.actual_entry_price,
            "entry_trigger_source": self.entry_trigger_source,
            "entry_trigger_timeframe": self.entry_trigger_timeframe,
            "entry_trigger_notes": self.entry_trigger_notes,
            "last_checked_at": self.last_checked_at,
        }


def compute_planned_entry_at_snapshot(
    snapshot: dict[str, Any],
    intraday_features: IntradayFeatures | None,
    intraday_bars: pd.DataFrame | None,
    *,
    default_buffer_pct: float = 0.001,
    real_data_only: bool = False,
    data_source: str | None = None,
) -> PlannedEntryPlan:
    """Compute research-only planned entry trigger fields at snapshot creation."""
    setup = str(snapshot.get("setup_category") or "")
    close = float(snapshot.get("close") or snapshot.get("latest_close") or 0)
    intraday_close = snapshot.get("intraday_close")
    snapshot_price = float(intraday_close if intraday_close not in (None, "") else close)
    snapshot_bar_time = _latest_bar_time(intraday_bars)

    if real_data_only and _is_missing_real_data(data_source, snapshot):
        return PlannedEntryPlan(
            snapshot_price=round(snapshot_price, 6),
            snapshot_bar_time=snapshot_bar_time,
            planned_entry_price=None,
            planned_entry_rule=RULE_FALLBACK_MISSING,
            planned_entry_buffer_pct=default_buffer_pct,
            entry_status=ENTRY_STATUS_MISSING_REAL_DATA,
            entry_trigger_source=None,
            entry_trigger_timeframe=None,
            entry_trigger_notes="Real intraday data required; no demo trigger.",
        )

    if intraday_features is None or not intraday_features.data_available:
        return PlannedEntryPlan(
            snapshot_price=round(snapshot_price, 6),
            snapshot_bar_time=snapshot_bar_time,
            planned_entry_price=None,
            planned_entry_rule=RULE_FALLBACK_NO_TRIGGER,
            planned_entry_buffer_pct=default_buffer_pct,
            entry_status=ENTRY_STATUS_NO_INTRADAY_TRIGGER,
            entry_trigger_source=None,
            entry_trigger_timeframe=None,
            entry_trigger_notes="No real intraday bars available for trigger planning.",
        )

    rule, base_level, notes = _planned_level_for_setup(setup, snapshot_price, intraday_features, intraday_bars)
    if base_level is None:
        return PlannedEntryPlan(
            snapshot_price=round(snapshot_price, 6),
            snapshot_bar_time=snapshot_bar_time,
            planned_entry_price=None,
            planned_entry_rule=rule,
            planned_entry_buffer_pct=default_buffer_pct,
            entry_status=ENTRY_STATUS_NO_INTRADAY_TRIGGER,
            entry_trigger_source=TRIGGER_SOURCE_ALPACA_5MIN,
            entry_trigger_timeframe=TRIGGER_TIMEFRAME_5MIN,
            entry_trigger_notes=notes,
        )

    buffer = max(0.0, float(default_buffer_pct))
    planned = round(base_level * (1 + buffer), 6)
    if planned <= snapshot_price:
        planned = round(snapshot_price * (1 + buffer), 6)

    return PlannedEntryPlan(
        snapshot_price=round(snapshot_price, 6),
        snapshot_bar_time=snapshot_bar_time,
        planned_entry_price=planned,
        planned_entry_rule=rule,
        planned_entry_buffer_pct=buffer,
        entry_status=ENTRY_STATUS_PENDING,
        entry_trigger_source=TRIGGER_SOURCE_ALPACA_5MIN,
        entry_trigger_timeframe=TRIGGER_TIMEFRAME_5MIN,
        entry_trigger_notes=notes,
    )


def simulate_entry_trigger(
    snapshot: dict[str, Any],
    intraday_bars: pd.DataFrame | None,
    *,
    expire_after_trading_days: int = 1,
    use_planned_price_as_fill: bool = True,
    now: pd.Timestamp | None = None,
) -> EntryTriggerSimulationResult:
    """Simulate whether future 5Min bars hit the planned research trigger.

    Uses only bars strictly after snapshot_time / snapshot_bar_time.
    Does not treat end-of-day close as entry.
    """
    checked_at = utc_now_iso()
    status = str(snapshot.get("entry_status") or ENTRY_STATUS_PENDING)
    planned = snapshot.get("planned_entry_price")
    planned_float = float(planned) if planned not in (None, "") else None

    if status in (ENTRY_STATUS_MISSING_REAL_DATA, ENTRY_STATUS_NO_INTRADAY_TRIGGER):
        return EntryTriggerSimulationResult(
            entry_status=status,
            actual_entry_price=None,
            actual_entry_time=None,
            entry_triggered=False,
            entry_triggered_at=None,
            entry_trigger_source=snapshot.get("entry_trigger_source"),
            entry_trigger_timeframe=snapshot.get("entry_trigger_timeframe"),
            entry_trigger_notes=str(snapshot.get("entry_trigger_notes") or ""),
            last_checked_at=checked_at,
        )

    if planned_float is None or planned_float <= 0:
        return EntryTriggerSimulationResult(
            entry_status=ENTRY_STATUS_NO_INTRADAY_TRIGGER,
            actual_entry_price=None,
            actual_entry_time=None,
            entry_triggered=False,
            entry_triggered_at=None,
            entry_trigger_source=snapshot.get("entry_trigger_source"),
            entry_trigger_timeframe=snapshot.get("entry_trigger_timeframe"),
            entry_trigger_notes="No planned entry trigger price.",
            last_checked_at=checked_at,
        )

    if intraday_bars is None or intraday_bars.empty:
        return EntryTriggerSimulationResult(
            entry_status=ENTRY_STATUS_PENDING if status == ENTRY_STATUS_PENDING else status,
            actual_entry_price=snapshot.get("actual_entry_price"),
            actual_entry_time=snapshot.get("actual_entry_time"),
            entry_triggered=bool(snapshot.get("entry_triggered")),
            entry_triggered_at=snapshot.get("entry_triggered_at") or snapshot.get("actual_entry_time"),
            entry_trigger_source=snapshot.get("entry_trigger_source") or TRIGGER_SOURCE_ALPACA_5MIN,
            entry_trigger_timeframe=snapshot.get("entry_trigger_timeframe") or TRIGGER_TIMEFRAME_5MIN,
            entry_trigger_notes="Awaiting real 5Min bars for trigger simulation.",
            last_checked_at=checked_at,
        )

    after = _bars_after_snapshot(snapshot, intraday_bars)
    if after.empty:
        return EntryTriggerSimulationResult(
            entry_status=ENTRY_STATUS_PENDING,
            actual_entry_price=None,
            actual_entry_time=None,
            entry_triggered=False,
            entry_triggered_at=None,
            entry_trigger_source=TRIGGER_SOURCE_ALPACA_5MIN,
            entry_trigger_timeframe=TRIGGER_TIMEFRAME_5MIN,
            entry_trigger_notes="No post-snapshot 5Min bars yet.",
            last_checked_at=checked_at,
        )

    trigger_rows = after[after["high"].astype(float) >= planned_float]
    if not trigger_rows.empty:
        first_idx = trigger_rows.index[0]
        fill = planned_float if use_planned_price_as_fill else float(trigger_rows.iloc[0]["high"])
        triggered_at = _index_to_iso(first_idx)
        return EntryTriggerSimulationResult(
            entry_status=ENTRY_STATUS_TRIGGERED,
            actual_entry_price=round(fill, 6),
            actual_entry_time=triggered_at,
            entry_triggered=True,
            entry_triggered_at=triggered_at,
            entry_trigger_source=TRIGGER_SOURCE_ALPACA_5MIN,
            entry_trigger_timeframe=TRIGGER_TIMEFRAME_5MIN,
            entry_trigger_notes=f"Trigger hit on first bar at {triggered_at}.",
            last_checked_at=checked_at,
        )

    # Not triggered yet — classify pending vs expired vs not_triggered
    now_ts = now or pd.Timestamp.utcnow()
    if now_ts.tzinfo is not None:
        now_ts = now_ts.tz_convert(None)
    snapshot_ts = _snapshot_reference_time(snapshot)
    same_day = snapshot_ts.date() == now_ts.date() if snapshot_ts is not None else False
    trading_days = len({idx.date() for idx in after.index})

    if same_day:
        new_status = ENTRY_STATUS_PENDING
        notes = "Same-day trigger still pending."
    elif trading_days >= expire_after_trading_days:
        new_status = ENTRY_STATUS_EXPIRED
        notes = f"No trigger within {expire_after_trading_days} session day(s) after snapshot."
    else:
        new_status = ENTRY_STATUS_NOT_TRIGGERED
        notes = "Post-snapshot bars reviewed; trigger not hit yet."

    return EntryTriggerSimulationResult(
        entry_status=new_status,
        actual_entry_price=None,
        actual_entry_time=None,
        entry_triggered=False,
        entry_triggered_at=None,
        entry_trigger_source=TRIGGER_SOURCE_ALPACA_5MIN,
        entry_trigger_timeframe=TRIGGER_TIMEFRAME_5MIN,
        entry_trigger_notes=notes,
        last_checked_at=checked_at,
    )


def _planned_level_for_setup(
    setup: str,
    snapshot_price: float,
    features: IntradayFeatures,
    bars: pd.DataFrame | None,
) -> tuple[str, float | None, str]:
    recent_high = _recent_intraday_high(bars, lookback_bars=12, features=features)
    recent_5min_high = recent_high
    vwap = features.vwap
    above_vwap = features.price_above_vwap

    if setup == "Breakout Watch":
        base = max(snapshot_price, recent_high or snapshot_price)
        return (
            RULE_BREAKOUT,
            base,
            "Research trigger: max(snapshot, recent intraday high) plus buffer.",
        )

    if setup == "Momentum Continuation":
        if recent_5min_high is None:
            return RULE_MOMENTUM, None, "Momentum trigger needs recent 5Min high."
        if vwap is not None and above_vwap is False:
            return RULE_MOMENTUM, None, "Momentum trigger requires price above VWAP when VWAP available."
        return (
            RULE_MOMENTUM,
            recent_5min_high,
            "Research trigger: break above recent 5Min high while above VWAP.",
        )

    if setup == "Pullback Watch":
        if vwap is not None:
            return (
                RULE_PULLBACK,
                max(vwap, recent_5min_high or vwap),
                "Research trigger: reclaim VWAP or break prior 5Min high.",
            )
        if recent_5min_high is not None:
            return RULE_PULLBACK, recent_5min_high, "Research trigger: break prior 5Min high (VWAP unavailable)."
        return RULE_PULLBACK, None, "Pullback trigger needs VWAP or recent 5Min high."

    return RULE_FALLBACK_NO_TRIGGER, None, f"No intraday trigger rule for setup '{setup}'."


def _bars_after_snapshot(snapshot: dict[str, Any], bars: pd.DataFrame) -> pd.DataFrame:
    ref = _snapshot_reference_time(snapshot)
    if ref is None:
        return pd.DataFrame()
    data = bars.copy()
    data.index = pd.to_datetime(data.index)
    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_convert(None)
    ref_naive = ref.tz_convert(None) if ref.tzinfo is not None else ref
    return data[data.index > ref_naive].sort_index()


def _snapshot_reference_time(snapshot: dict[str, Any]) -> pd.Timestamp | None:
    raw = snapshot.get("snapshot_bar_time") or snapshot.get("snapshot_time")
    if not raw:
        return None
    ts = pd.Timestamp(raw)
    return ts


def _latest_bar_time(bars: pd.DataFrame | None) -> str | None:
    if bars is None or bars.empty:
        return None
    data = bars.copy()
    data.index = pd.to_datetime(data.index)
    return _index_to_iso(data.index[-1])


def _recent_intraday_high(
    bars: pd.DataFrame | None,
    lookback_bars: int = 12,
    features: IntradayFeatures | None = None,
) -> float | None:
    if bars is None or bars.empty:
        if features and features.high_of_day:
            return float(features.high_of_day)
        return None
    data = bars.copy().sort_index()
    tail = data.tail(lookback_bars)
    if tail.empty or "high" not in tail.columns:
        return None
    value = float(tail["high"].max())
    return value if value > 0 else None


def _index_to_iso(value: Any) -> str:
    return pd.Timestamp(value).isoformat()


def _is_missing_real_data(data_source: str | None, snapshot: dict[str, Any]) -> bool:
    ds = data_source or snapshot.get("data_source")
    if ds == "missing_real_data":
        return True
    reason = snapshot.get("missing_real_data_reason")
    return bool(reason)


def build_intraday_features_from_bars(
    symbol: str,
    bars: pd.DataFrame | None,
    timeframe: str = "5Min",
) -> IntradayFeatures:
    return calculate_intraday_features(symbol, bars, timeframe=timeframe)
