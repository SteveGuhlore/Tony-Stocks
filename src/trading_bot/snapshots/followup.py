from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from trading_bot.utils.time_utils import utc_now_iso


OUTCOME_TARGET_HIT = "target_hit"
OUTCOME_STOP_HIT = "stop_hit"
OUTCOME_ENTRY_NOT_TRIGGERED = "entry_not_triggered"
OUTCOME_TARGET_BEFORE_STOP = "target_before_stop"
OUTCOME_STOP_BEFORE_TARGET = "stop_before_target"
OUTCOME_PARTIAL_MOVE = "partial_move"
OUTCOME_FAILED_SETUP = "failed_setup"
OUTCOME_STILL_OPEN = "still_open"
OUTCOME_INSUFFICIENT_FUTURE_DATA = "insufficient_future_data"
OUTCOME_EXPIRED_NO_TRIGGER = "expired_no_trigger"

TERMINAL_OUTCOMES = {
    OUTCOME_TARGET_HIT,
    OUTCOME_STOP_HIT,
    OUTCOME_TARGET_BEFORE_STOP,
    OUTCOME_STOP_BEFORE_TARGET,
    OUTCOME_FAILED_SETUP,
    OUTCOME_EXPIRED_NO_TRIGGER,
}


@dataclass(frozen=True)
class SnapshotFollowupResult:
    """Calculated follow-up fields for one candidate snapshot."""

    highest_price_seen: float | None
    lowest_price_seen: float | None
    last_checked_at: str
    result_1h: float | None
    result_eod: float | None
    result_3d: float | None
    result_5d: float | None
    result_10d: float | None
    result_20d: float | None
    entry_triggered: bool
    entry_triggered_at: str | None
    outcome_label: str
    status: str | None = None

    def to_update_fields(self) -> dict[str, Any]:
        """Return fields accepted by the snapshot repository update method."""
        payload = asdict(self)
        payload["entry_triggered"] = int(self.entry_triggered)
        if payload.get("status") is None:
            payload.pop("status")
        return payload


def calculate_snapshot_followup(
    snapshot: dict[str, Any],
    ohlcv: pd.DataFrame,
    same_bar_target_stop_policy: str = "conservative_stop_first",
    expire_after_trading_days: int = 20,
) -> SnapshotFollowupResult:
    """Compare a candidate snapshot's long trade plan with future OHLCV bars."""
    outcome_start = _outcome_reference_time(snapshot)
    future = _future_bars(snapshot, ohlcv, after=outcome_start)
    if future.empty:
        return SnapshotFollowupResult(
            highest_price_seen=None,
            lowest_price_seen=None,
            last_checked_at=utc_now_iso(),
            result_1h=None,
            result_eod=None,
            result_3d=None,
            result_5d=None,
            result_10d=None,
            result_20d=None,
            entry_triggered=_legacy_entry_triggered(snapshot),
            entry_triggered_at=snapshot.get("entry_triggered_at") or snapshot.get("actual_entry_time"),
            outcome_label=OUTCOME_INSUFFICIENT_FUTURE_DATA,
        )

    close = float(snapshot.get("close") or 0)
    entry = _effective_entry_price(snapshot)
    stop = float(snapshot.get("stop") or 0)
    target = float(snapshot.get("target") or 0)
    highest = float(future["high"].max())
    lowest = float(future["low"].min())
    intraday_triggered = _intraday_trigger_active(snapshot)
    if intraday_triggered:
        entry_triggered = True
        entry_triggered_at = snapshot.get("actual_entry_time") or snapshot.get("entry_triggered_at")
        entry_at = pd.Timestamp(entry_triggered_at) if entry_triggered_at else None
        if entry_at is not None and entry_at.tzinfo is not None:
            entry_at = entry_at.tz_convert(None)
        if entry_at is not None and entry_at in future.index:
            pass
        elif entry_at is not None:
            after_entry = future[future.index > entry_at]
            entry_at = after_entry.index[0] if not after_entry.empty else future.index[0]
        else:
            entry_at = future.index[0]
    else:
        entry_rows = future[future["high"] >= entry] if entry > 0 else future.iloc[0:0]
        entry_triggered = not entry_rows.empty
        entry_triggered_at = _index_to_iso(entry_rows.index[0]) if entry_triggered else None
        entry_at = entry_rows.index[0] if entry_triggered else None
    outcome = _outcome_label(
        future=future,
        entry_triggered=entry_triggered,
        entry_at=entry_at,
        entry=entry,
        stop=stop,
        target=target,
        highest=highest,
        same_bar_target_stop_policy=same_bar_target_stop_policy,
        expire_after_trading_days=expire_after_trading_days,
        intraday_trigger_pending=_intraday_trigger_pending(snapshot),
    )
    status = "expired" if outcome == OUTCOME_EXPIRED_NO_TRIGGER else None
    return SnapshotFollowupResult(
        highest_price_seen=round(highest, 4),
        lowest_price_seen=round(lowest, 4),
        last_checked_at=utc_now_iso(),
        result_1h=None,
        result_eod=_return_at_bar(close, future, 1),
        result_3d=_return_at_bar(close, future, 3),
        result_5d=_return_at_bar(close, future, 5),
        result_10d=_return_at_bar(close, future, 10),
        result_20d=_return_at_bar(close, future, 20),
        entry_triggered=entry_triggered,
        entry_triggered_at=entry_triggered_at,
        outcome_label=outcome,
        status=status,
    )


def _future_bars(
    snapshot: dict[str, Any],
    ohlcv: pd.DataFrame,
    after: pd.Timestamp | None = None,
) -> pd.DataFrame:
    if ohlcv.empty:
        return ohlcv
    snapshot_time = after or pd.Timestamp(snapshot["snapshot_time"])
    if snapshot_time.tzinfo is not None:
        snapshot_time = snapshot_time.tz_convert(None)
    data = ohlcv.copy()
    data.index = pd.to_datetime(data.index)
    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_convert(None)
    return data[data.index > snapshot_time].sort_index()


def _outcome_reference_time(snapshot: dict[str, Any]) -> pd.Timestamp | None:
    """Use actual intraday entry time for outcomes when V15 trigger simulation fired."""
    if _intraday_trigger_active(snapshot):
        raw = snapshot.get("actual_entry_time") or snapshot.get("entry_triggered_at")
        if raw:
            ts = pd.Timestamp(raw)
            return ts.tz_convert(None) if ts.tzinfo is not None else ts
    return None


def _effective_entry_price(snapshot: dict[str, Any]) -> float:
    if _intraday_trigger_active(snapshot):
        actual = snapshot.get("actual_entry_price")
        if actual not in (None, ""):
            return float(actual)
        planned = snapshot.get("planned_entry_price")
        if planned not in (None, ""):
            return float(planned)
    return float(snapshot.get("entry") or 0)


def _intraday_trigger_active(snapshot: dict[str, Any]) -> bool:
    status = str(snapshot.get("entry_status") or "")
    if status == "triggered":
        return True
    return bool(snapshot.get("entry_triggered")) and snapshot.get("actual_entry_time") not in (None, "")


def _intraday_trigger_pending(snapshot: dict[str, Any]) -> bool:
    status = str(snapshot.get("entry_status") or "")
    return status in ("pending", "missing_real_data", "no_intraday_trigger")


def _legacy_entry_triggered(snapshot: dict[str, Any]) -> bool:
    if _intraday_trigger_active(snapshot):
        return True
    return bool(snapshot.get("entry_triggered"))


def _outcome_label(
    future: pd.DataFrame,
    entry_triggered: bool,
    entry_at: Any | None,
    entry: float,
    stop: float,
    target: float,
    highest: float,
    same_bar_target_stop_policy: str,
    expire_after_trading_days: int,
    intraday_trigger_pending: bool = False,
) -> str:
    if not entry_triggered:
        if intraday_trigger_pending:
            return OUTCOME_ENTRY_NOT_TRIGGERED
        if len(future) >= expire_after_trading_days:
            return OUTCOME_EXPIRED_NO_TRIGGER
        return OUTCOME_ENTRY_NOT_TRIGGERED

    after_entry = future.loc[entry_at:]
    for _, row in after_entry.iterrows():
        target_hit = target > 0 and float(row["high"]) >= target
        stop_hit = stop > 0 and float(row["low"]) <= stop
        if target_hit and stop_hit:
            if same_bar_target_stop_policy == "optimistic_target_first":
                return OUTCOME_TARGET_BEFORE_STOP
            return OUTCOME_STOP_BEFORE_TARGET
        if target_hit:
            return OUTCOME_TARGET_HIT
        if stop_hit:
            return OUTCOME_STOP_HIT

    if highest > entry * 1.001:
        return OUTCOME_PARTIAL_MOVE
    if len(future) >= expire_after_trading_days:
        return OUTCOME_FAILED_SETUP
    return OUTCOME_STILL_OPEN


def _return_at_bar(start_close: float, future: pd.DataFrame, bar_number: int) -> float | None:
    if start_close <= 0 or len(future) < bar_number:
        return None
    close = float(future["close"].iloc[bar_number - 1])
    return round(close / start_close - 1, 6)


def _index_to_iso(value: Any) -> str:
    timestamp = pd.Timestamp(value)
    return timestamp.isoformat()
