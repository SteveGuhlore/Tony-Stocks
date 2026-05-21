"""V15.8 research-only active tracking: frozen original plan + live price refresh.

Does not create paper trades, broker orders, or live execution.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from trading_bot.snapshots.entry_triggers import ENTRY_STATUS_MISSING_REAL_DATA, ENTRY_STATUS_TRIGGERED
from trading_bot.snapshots.followup import (
    OUTCOME_ENTRY_NOT_TRIGGERED,
    OUTCOME_EXPIRED_NO_TRIGGER,
    OUTCOME_FAILED_SETUP,
    OUTCOME_PARTIAL_MOVE,
    OUTCOME_STOP_BEFORE_TARGET,
    OUTCOME_STOP_HIT,
    OUTCOME_TARGET_BEFORE_STOP,
    OUTCOME_TARGET_HIT,
)
from trading_bot.utils.time_utils import utc_now_iso

TRACKING_STATUS_ACTIVE = "active"
TRACKING_STATUS_TARGET_HIT = "target_hit"
TRACKING_STATUS_STOP_HIT = "stop_hit"
TRACKING_STATUS_PARTIAL_MOVE = "partial_move"
TRACKING_STATUS_EXPIRED = "expired"
TRACKING_STATUS_INVALIDATED = "invalidated"
TRACKING_STATUS_MISSING_REAL_DATA = "missing_real_data"
TRACKING_STATUS_CLOSED = "closed"

TRACKING_FIELD_NAMES = (
    "original_entry_price",
    "original_target_price",
    "original_stop_price",
    "original_plan_captured_at",
    "tracking_status",
    "tracking_started_at",
    "current_price",
    "current_price_at",
    "research_unrealized_pl_pct",
    "current_target_price",
    "current_stop_price",
    "reassessment_label",
    "reassessment_note",
    "last_reassessed_at",
    "invalidation_reason",
    "time_active_minutes",
    "pick_phase",
)

REASSESSMENT_STILL_VALID = "still_valid"
REASSESSMENT_WEAKENING = "weakening"
REASSESSMENT_INVALIDATED = "invalidated"
REASSESSMENT_NEEDS_REVIEW = "needs_review"

_TERMINAL_OUTCOMES = {
    OUTCOME_TARGET_HIT,
    OUTCOME_STOP_HIT,
    OUTCOME_TARGET_BEFORE_STOP,
    OUTCOME_STOP_BEFORE_TARGET,
    OUTCOME_FAILED_SETUP,
    OUTCOME_EXPIRED_NO_TRIGGER,
    OUTCOME_ENTRY_NOT_TRIGGERED,
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and value.strip().lower() in ("", "nan", "none", "null"):
        return True
    return False


def _to_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def snapshot_pick_phase(snapshot: dict[str, Any]) -> str:
    """Classify pick phase for storage (mirrors dashboard derive_pick_phase)."""
    outcome = str(snapshot.get("outcome_label") or "unreviewed").strip().lower()
    entry_status = str(snapshot.get("entry_status") or "").strip().lower()
    entry_triggered = int(snapshot.get("entry_triggered") or 0)

    if outcome in _TERMINAL_OUTCOMES:
        return "closed"
    if entry_status in ("expired", "missing_real_data", "not_triggered") and entry_triggered == 0:
        return "closed"
    if entry_status == ENTRY_STATUS_TRIGGERED or entry_triggered == 1:
        if outcome in ("unreviewed", "still_open", OUTCOME_PARTIAL_MOVE, ""):
            return "tracking"
        return "closed"
    if entry_status == "pending":
        return "waiting_alert"
    return "pick"


def map_tracking_status_from_outcome(
    outcome_label: str | None,
    entry_status: str | None,
    *,
    has_original_plan: bool,
) -> str:
    """Map snapshot outcome/entry fields to deterministic tracking_status."""
    entry = str(entry_status or "").strip().lower()
    outcome = str(outcome_label or "unreviewed").strip().lower()

    if entry == ENTRY_STATUS_MISSING_REAL_DATA:
        return TRACKING_STATUS_MISSING_REAL_DATA

    if outcome in (OUTCOME_TARGET_HIT, OUTCOME_TARGET_BEFORE_STOP):
        return TRACKING_STATUS_TARGET_HIT
    if outcome in (OUTCOME_STOP_HIT, OUTCOME_STOP_BEFORE_TARGET, OUTCOME_FAILED_SETUP):
        return TRACKING_STATUS_STOP_HIT
    if outcome == OUTCOME_PARTIAL_MOVE:
        return TRACKING_STATUS_PARTIAL_MOVE
    if outcome in (OUTCOME_EXPIRED_NO_TRIGGER, OUTCOME_ENTRY_NOT_TRIGGERED):
        return TRACKING_STATUS_EXPIRED
    if outcome in _TERMINAL_OUTCOMES:
        return TRACKING_STATUS_CLOSED

    if has_original_plan and entry == ENTRY_STATUS_TRIGGERED:
        return TRACKING_STATUS_ACTIVE

    return TRACKING_STATUS_CLOSED


def _is_triggered(snapshot: dict[str, Any]) -> bool:
    entry_status = str(snapshot.get("entry_status") or "").strip().lower()
    return entry_status == ENTRY_STATUS_TRIGGERED or int(snapshot.get("entry_triggered") or 0) == 1


def build_original_plan_freeze_updates(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Freeze original plan when entry triggers; never overwrite original_* once set."""
    if not _is_triggered(snapshot):
        return {}

    if not _is_missing(snapshot.get("original_entry_price")):
        return {}

    actual_entry = _to_float(snapshot.get("actual_entry_price"))
    if actual_entry is None or actual_entry <= 0:
        return {}

    target = _to_float(snapshot.get("target"))
    stop = _to_float(snapshot.get("stop"))
    captured_at = (
        str(snapshot.get("actual_entry_time") or "").strip()
        or str(snapshot.get("entry_triggered_at") or "").strip()
        or utc_now_iso()
    )

    updates: dict[str, Any] = {
        "original_entry_price": round(actual_entry, 6),
        "original_plan_captured_at": captured_at,
        "tracking_status": TRACKING_STATUS_ACTIVE,
        "tracking_started_at": captured_at,
        "pick_phase": "tracking",
    }
    if target is not None:
        updates["original_target_price"] = round(target, 6)
        updates["current_target_price"] = round(target, 6)
    if stop is not None:
        updates["original_stop_price"] = round(stop, 6)
        updates["current_stop_price"] = round(stop, 6)

    return updates


def _latest_real_close(
    intraday_bars: pd.DataFrame | None,
    *,
    after: pd.Timestamp | None = None,
) -> tuple[float | None, str | None]:
    """Latest 5Min close from real bars (optionally after a reference time)."""
    if intraday_bars is None or intraday_bars.empty or "close" not in intraday_bars.columns:
        return None, None
    data = intraday_bars.copy()
    data.index = pd.to_datetime(data.index)
    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_convert(None)
    if after is not None:
        ref = after.tz_convert(None) if after.tzinfo is not None else after
        data = data[data.index >= ref]
    if data.empty:
        return None, None
    last_idx = data.index[-1]
    close = _to_float(data.iloc[-1]["close"])
    if close is None:
        return None, None
    return round(close, 6), pd.Timestamp(last_idx).isoformat()


def compute_time_active_minutes(
    tracking_started_at: str | None,
    *,
    now: datetime | None = None,
) -> int | None:
    """Minutes from tracking_started_at to now (safe for bad timestamps)."""
    if not tracking_started_at:
        return None
    try:
        started = datetime.fromisoformat(str(tracking_started_at).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        ref = now if now is not None else datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        minutes = int((ref - started).total_seconds() / 60)
        return max(0, minutes)
    except Exception:
        return None


def compute_research_unrealized_pl_pct(
    original_entry_price: float | None,
    current_price: float | None,
) -> float | None:
    if original_entry_price is None or current_price is None:
        return None
    if original_entry_price <= 0:
        return None
    pct = (current_price - original_entry_price) / original_entry_price * 100.0
    return round(pct, 4)


def derive_reassessment_state(
    snapshot: dict[str, Any],
    *,
    current_price: float | None = None,
    intraday_bars: pd.DataFrame | None = None,
) -> tuple[str, str]:
    """Deterministically label the current research validity of an active tracked setup."""
    working = dict(snapshot)
    outcome = str(working.get("outcome_label") or "").strip().lower()
    tracking_status = str(working.get("tracking_status") or "").strip().lower()
    entry_status = str(working.get("entry_status") or "").strip().lower()
    entry = _to_float(working.get("original_entry_price"))
    target = _to_float(working.get("current_target_price") or working.get("original_target_price") or working.get("target"))
    stop = _to_float(working.get("current_stop_price") or working.get("original_stop_price") or working.get("stop"))
    live_price = current_price
    if live_price is None:
        live_price = _to_float(working.get("current_price"))
    if live_price is None:
        live_price = _to_float(working.get("intraday_close"))
    if live_price is None:
        live_price = _to_float(working.get("close"))

    stored_pl = _to_float(working.get("research_unrealized_pl_pct"))
    pl_pct = stored_pl
    if pl_pct is None and entry is not None and live_price is not None:
        pl_pct = compute_research_unrealized_pl_pct(entry, live_price)

    if entry_status == ENTRY_STATUS_MISSING_REAL_DATA or tracking_status == TRACKING_STATUS_MISSING_REAL_DATA:
        return (
            REASSESSMENT_NEEDS_REVIEW,
            "Needs review: missing real intraday context for reassessment.",
        )
    if entry is None or target is None or stop is None:
        return (
            REASSESSMENT_NEEDS_REVIEW,
            "Needs review: active entry, target, or stop is missing.",
        )
    if outcome in (OUTCOME_STOP_HIT, OUTCOME_STOP_BEFORE_TARGET, OUTCOME_FAILED_SETUP) or tracking_status in (
        TRACKING_STATUS_STOP_HIT,
        TRACKING_STATUS_INVALIDATED,
    ):
        return (
            REASSESSMENT_INVALIDATED,
            "Invalidated: stop/failure outcome was recorded for this research setup.",
        )
    if live_price is not None and stop is not None and live_price <= stop:
        return (
            REASSESSMENT_INVALIDATED,
            "Invalidated: current price is at or below the tracked stop level.",
        )
    if live_price is None:
        return (
            REASSESSMENT_NEEDS_REVIEW,
            "Needs review: no current or closing price is available yet.",
        )

    downside = entry - stop
    recent_intraday_slip = False
    if intraday_bars is not None and not intraday_bars.empty and "close" in intraday_bars.columns and len(intraday_bars) >= 2:
        try:
            first_close = _to_float(intraday_bars.iloc[0]["close"])
            last_close = _to_float(intraday_bars.iloc[-1]["close"])
            recent_intraday_slip = (
                first_close is not None
                and last_close is not None
                and last_close < first_close
            )
        except Exception:
            recent_intraday_slip = False

    if (
        (pl_pct is not None and pl_pct < 0)
        or (downside > 0 and live_price <= entry - downside * 0.5)
        or recent_intraday_slip
    ):
        if pl_pct is not None and pl_pct < 0:
            return (
                REASSESSMENT_WEAKENING,
                "Weakening: price is below the active research entry.",
            )
        if downside > 0 and live_price <= entry - downside * 0.5:
            return (
                REASSESSMENT_WEAKENING,
                "Weakening: price has given back at least half the planned downside buffer to stop.",
            )
        return (
            REASSESSMENT_WEAKENING,
            "Weakening: recent intraday context shows a pullback from earlier bars.",
        )

    return (
        REASSESSMENT_STILL_VALID,
        "Still valid: price remains above the tracked stop and the setup is intact.",
    )


def build_active_tracking_refresh_updates(
    snapshot: dict[str, Any],
    intraday_bars: pd.DataFrame | None,
    *,
    real_data_only: bool,
    provider_name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Refresh live research tracking fields for triggered snapshots."""
    working = dict(snapshot)
    has_plan = not _is_missing(working.get("original_entry_price"))
    if not has_plan and not _is_triggered(working):
        return {"pick_phase": snapshot_pick_phase(working)}

    if _is_triggered(working) and not has_plan:
        working.update(build_original_plan_freeze_updates(working))
        has_plan = not _is_missing(working.get("original_entry_price"))

    if not has_plan:
        return {"pick_phase": snapshot_pick_phase(working)}

    checked_at = utc_now_iso()
    updates: dict[str, Any] = {
        "last_reassessed_at": checked_at,
        "pick_phase": snapshot_pick_phase(working),
    }

    entry_status = str(working.get("entry_status") or "").strip().lower()
    outcome = working.get("outcome_label")
    updates["tracking_status"] = map_tracking_status_from_outcome(
        outcome,
        entry_status,
        has_original_plan=True,
    )

    started_at = working.get("tracking_started_at") or working.get("original_plan_captured_at")
    minutes = compute_time_active_minutes(started_at, now=now)
    if minutes is not None:
        updates["time_active_minutes"] = minutes

    can_use_real_bars = provider_name == "alpaca_iex"
    if real_data_only and provider_name != "alpaca_iex":
        can_use_real_bars = False
    if entry_status == ENTRY_STATUS_MISSING_REAL_DATA:
        updates["tracking_status"] = TRACKING_STATUS_MISSING_REAL_DATA
        label, reason = derive_reassessment_state(working, current_price=None, intraday_bars=None)
        updates["reassessment_label"] = label
        updates["reassessment_note"] = reason
        return updates

    if not can_use_real_bars or intraday_bars is None or intraday_bars.empty:
        label, reason = derive_reassessment_state(working, current_price=None, intraday_bars=None)
        updates["reassessment_label"] = label
        updates["reassessment_note"] = reason
        return updates

    ref_time = None
    raw_ref = working.get("tracking_started_at") or working.get("actual_entry_time")
    if raw_ref:
        try:
            ref_time = pd.Timestamp(raw_ref)
        except Exception:
            ref_time = None

    current_price, current_at = _latest_real_close(intraday_bars, after=ref_time)
    if current_price is None:
        return updates

    original_entry = _to_float(working.get("original_entry_price"))
    updates["current_price"] = current_price
    updates["current_price_at"] = current_at or checked_at
    pl_pct = compute_research_unrealized_pl_pct(original_entry, current_price)
    if pl_pct is not None:
        updates["research_unrealized_pl_pct"] = pl_pct
    reassessment_input = dict(working)
    reassessment_input.update(updates)
    label, reason = derive_reassessment_state(
        reassessment_input,
        current_price=current_price,
        intraday_bars=intraday_bars,
    )
    updates["reassessment_label"] = label
    updates["reassessment_note"] = reason
    if label == REASSESSMENT_INVALIDATED:
        updates["invalidation_reason"] = reason

    return updates


def compute_terminal_outcome_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compute terminal exit price and final research P/L for closed/terminal positions.

    Active positions and insufficient_future_data rows return is_terminal_outcome=False.
    For stop_hit and target_hit the exit price comes from the tracked stop/target level.
    For other closed states the exit price falls back to current_price with a note.
    """
    tracking_status = str(snapshot.get("tracking_status") or "").strip().lower()
    outcome_label = str(snapshot.get("outcome_label") or "").strip().lower()

    _ACTIVE_STATUSES = {TRACKING_STATUS_ACTIVE, ""}
    _INSUFFICIENT = {"insufficient_future_data"}

    if tracking_status in _ACTIVE_STATUSES or outcome_label in _INSUFFICIENT:
        return {
            "is_terminal_outcome": False,
            "terminal_exit_price": None,
            "terminal_exit_reason": None,
            "terminal_research_pl_pct": None,
            "terminal_exit_price_note": None,
        }

    is_stop = tracking_status == TRACKING_STATUS_STOP_HIT or outcome_label in {
        OUTCOME_STOP_HIT,
        OUTCOME_STOP_BEFORE_TARGET,
        OUTCOME_FAILED_SETUP,
    }
    is_target = tracking_status == TRACKING_STATUS_TARGET_HIT or outcome_label in {
        OUTCOME_TARGET_HIT,
        OUTCOME_TARGET_BEFORE_STOP,
    }

    exit_price: float | None = None
    exit_reason: str | None = None
    inferred_note: str | None = None

    if is_stop:
        exit_price = _to_float(
            snapshot.get("current_stop_price")
            or snapshot.get("original_stop_price")
            or snapshot.get("stop")
        )
        exit_reason = "stop_hit"
    elif is_target:
        exit_price = _to_float(
            snapshot.get("current_target_price")
            or snapshot.get("original_target_price")
            or snapshot.get("target")
        )
        exit_reason = "target_hit"
    else:
        exit_price = _to_float(
            snapshot.get("current_price")
            or snapshot.get("intraday_close")
            or snapshot.get("close")
        )
        exit_reason = tracking_status or outcome_label or "closed"
        if exit_price is not None:
            inferred_note = "Final exit price is inferred from available closing price data."
        else:
            inferred_note = "No exit price available; final P/L cannot be computed."

    entry_price = _to_float(
        snapshot.get("original_entry_price") or snapshot.get("actual_entry_price")
    )
    pl_pct: float | None = None
    if exit_price is not None and entry_price is not None and entry_price > 0:
        pl_pct = round((exit_price - entry_price) / entry_price * 100.0, 4)

    return {
        "is_terminal_outcome": True,
        "terminal_exit_price": exit_price,
        "terminal_exit_reason": exit_reason,
        "terminal_research_pl_pct": pl_pct,
        "terminal_exit_price_note": inferred_note,
    }


def summarize_tracked_setup_refresh(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate refresh stats for Tony tracked_setup_updated event."""
    summary = {
        "total_active": 0,
        "updated_current_price_count": 0,
        "missing_current_price_count": 0,
        "positive_research_pl_count": 0,
        "negative_research_pl_count": 0,
        "target_hit_count": 0,
        "stop_hit_count": 0,
        "still_valid_count": 0,
        "weakening_count": 0,
        "invalidated_count": 0,
        "needs_review_count": 0,
    }
    for row in rows:
        status = str(row.get("tracking_status") or "")
        reassessment = str(row.get("reassessment_label") or "")
        if status == TRACKING_STATUS_ACTIVE:
            summary["total_active"] += 1
        if status == TRACKING_STATUS_TARGET_HIT:
            summary["target_hit_count"] += 1
        if status == TRACKING_STATUS_STOP_HIT:
            summary["stop_hit_count"] += 1
        if reassessment == REASSESSMENT_STILL_VALID:
            summary["still_valid_count"] += 1
        elif reassessment == REASSESSMENT_WEAKENING:
            summary["weakening_count"] += 1
        elif reassessment == REASSESSMENT_INVALIDATED:
            summary["invalidated_count"] += 1
        elif reassessment == REASSESSMENT_NEEDS_REVIEW:
            summary["needs_review_count"] += 1
        if row.get("current_price") not in (None, ""):
            summary["updated_current_price_count"] += 1
            pl = _to_float(row.get("research_unrealized_pl_pct"))
            if pl is not None:
                if pl > 0:
                    summary["positive_research_pl_count"] += 1
                elif pl < 0:
                    summary["negative_research_pl_count"] += 1
        elif status == TRACKING_STATUS_ACTIVE:
            summary["missing_current_price_count"] += 1
    return summary
