"""Pure, Streamlit-free helper functions for the Trading Bot dashboard.

Extracted here so they can be unit-tested without importing Streamlit.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

_MARKET_OPEN_ET = dt_time(9, 30)
_MARKET_CLOSE_ET = dt_time(16, 0)
_US_EASTERN = ZoneInfo("America/New_York")


def event_age_label(ts_str: str | None) -> str:
    """Return a human-readable age string for a UTC ISO timestamp."""
    if not ts_str:
        return "unknown"
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - ts
        minutes = int(diff.total_seconds() / 60)
        if minutes < 1:
            return "just now"
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return str(ts_str)[:16]


def is_fallback_provider(provider_name: str) -> bool:
    """Return True if the provider is a demo/fallback source, not real market data."""
    return provider_name in ("demo_generated", "fallback", "demo")


def filter_events_by_type(events: pd.DataFrame, event_type: str) -> pd.DataFrame:
    """Return rows from events matching the given event_type."""
    if events.empty or "event_type" not in events.columns:
        return pd.DataFrame()
    return events[events["event_type"] == event_type]


def latest_event_of_type(events: pd.DataFrame, event_type: str) -> dict | None:
    """Return the most recent event row of the given type as a dict, or None."""
    filtered = filter_events_by_type(events, event_type)
    if filtered.empty:
        return None
    return dict(filtered.iloc[0])


def is_current_cycle_event(ts_str: str | None, max_minutes: int = 30) -> bool:
    """Return True if the event timestamp is within the last max_minutes."""
    if not ts_str:
        return False
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - ts).total_seconds() / 60
        return elapsed <= max_minutes
    except Exception:
        return False


def count_hypothesis_by_priority(analyst_events: pd.DataFrame) -> dict[str, int]:
    """Count analyst hypothesis events grouped by priority_label from payload."""
    counts: dict[str, int] = {}
    if analyst_events.empty:
        return counts
    for _, ev in analyst_events.iterrows():
        try:
            label = json.loads(ev.get("payload_json") or "{}").get("priority_label", "unknown")
            counts[label] = counts.get(label, 0) + 1
        except Exception:
            pass
    return counts


def is_seeded_demo_snapshot(notes: str | None, tags_json: str | None) -> bool:
    """Return True if the snapshot is a seeded demo fixture that should be excluded from analytics."""
    if notes and ("Demo seeded snapshot" in notes or "Seeded demo snapshot" in notes):
        return True
    if tags_json:
        try:
            tags = json.loads(tags_json)
            if "demo_seeded" in tags or "outcome_fixture" in tags:
                return True
        except Exception:
            pass
    return False


def is_within_us_eastern_market_hours(now_et: datetime) -> bool:
    """Return True if now_et falls within the regular US equity session (9:30–16:00 ET).

    No holiday calendar is applied. Use for simple market-hours guard only.
    """
    t = now_et.time()
    return _MARKET_OPEN_ET <= t <= _MARKET_CLOSE_ET


def is_heartbeat_stale(
    last_heartbeat_at: str | None,
    stale_minutes: int = 10,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True if the watch run heartbeat is older than stale_minutes.

    Pass now= to inject a fixed reference time in tests.
    Returns False (not stale) if last_heartbeat_at is None — the run hasn't started yet.
    """
    if not last_heartbeat_at:
        return False
    try:
        ts = datetime.fromisoformat(str(last_heartbeat_at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ref = now if now is not None else datetime.now(timezone.utc)
        return (ref - ts).total_seconds() / 60 > stale_minutes
    except Exception:
        return False


def watch_status_label(
    watch_run: dict[str, Any] | None,
    stale_minutes: int = 10,
    *,
    now: datetime | None = None,
) -> str:
    """Return a display label for the watch run status.

    Labels: no_run | running | stale | stopped | error | unknown
    A running run with a stale heartbeat is reported as 'stale'.
    """
    if not watch_run:
        return "no_run"
    status = str(watch_run.get("status", "unknown"))
    if status == "running" and is_heartbeat_stale(
        watch_run.get("last_heartbeat_at"), stale_minutes, now=now
    ):
        return "stale"
    return status


_TONY_STATUS_BEGINNER = {
    "running": "Running",
    "stopped": "Stopped",
    "error": "Error",
    "stale": "Needs attention",
    "no_run": "Not started",
    "unknown": "Unknown",
}

_MARKET_CONTEXT_PLAIN = {
    "market_supportive": ("Supportive", "Benchmarks look steady. Tony may find more setups worth watching."),
    "market_weak": ("Weak", "Benchmarks look soft. Tony is being more selective today."),
    "market_mixed": ("Mixed", "Benchmarks are mixed. Tony is watching carefully."),
    "benchmark_data_missing": ("Unknown", "Benchmark data is missing. Market read is limited."),
}

_ENTRY_TRIGGER_PLAIN = {
    "pending": "Waiting for alert",
    "triggered": "Alert triggered — tracking",
    "not_triggered": "Alert not hit yet",
    "expired": "Alert expired",
    "missing_real_data": "Missing live data",
    "no_intraday_trigger": "No planned alert yet",
    None: "Not tracked yet",
    "": "Not tracked yet",
}

_DATA_QUALITY_PLAIN = {
    "daily_real_alpaca": "Good daily data",
    "intraday_real_alpaca": "Good live 5-minute data",
    "intraday_missing": "Missing live 5-minute data",
    "intraday_fallback_demo": "Demo data (not used in active runs)",
    "demo_data": "Demo data (blocked)",
    "missing_real_data": "Missing real data",
    "fallback_data": "Missing real data",
    "stale_intraday": "Live data is stale",
}


def tony_status_beginner_label(
    watch_status: str,
    *,
    waiting_for_market: bool = False,
) -> str:
    """Map internal watch status to a beginner-friendly label."""
    if waiting_for_market:
        return "Waiting"
    return _TONY_STATUS_BEGINNER.get(watch_status, "Unknown")


def is_waiting_for_market_open(events: pd.DataFrame, max_minutes: int = 120) -> bool:
    """Return True if Tony recently reported waiting for market open."""
    row = latest_event_of_type(events, "watch_waiting_for_market_open")
    if not row:
        return False
    return is_current_cycle_event(row.get("created_at"), max_minutes=max_minutes)


def missing_symbols_from_events(events: pd.DataFrame) -> list[str]:
    """Return symbols repeatedly missing real data from Tony event payloads."""
    if events.empty or "payload_json" not in events.columns:
        return []
    counts: dict[str, int] = {}
    for raw in events["payload_json"].tolist():
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            continue
        symbols = (
            payload.get("missing_real_data_symbols")
            or payload.get("fallback_symbols")
            or payload.get("intraday_missing_symbols")
            or payload.get("intraday_fallback_symbols")
            or []
        )
        if isinstance(symbols, str):
            symbols = [symbols]
        for symbol in symbols:
            key = str(symbol).upper().strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    if counts and max(counts.values()) > 1:
        counts = {symbol: count for symbol, count in counts.items() if count > 1}
    return [symbol for symbol, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def summarize_symbol_list(symbols: list[str], *, max_show: int = 8) -> str:
    """Format a symbol list for beginner-facing captions."""
    if not symbols:
        return "none"
    shown = symbols[:max_show]
    suffix = f" (+{len(symbols) - max_show} more)" if len(symbols) > max_show else ""
    return ", ".join(shown) + suffix


def market_context_plain_english(context_label: str | None, message: str | None = None) -> tuple[str, str]:
    """Return (headline, one_liner) for Today's Market Read."""
    label = str(context_label or "benchmark_data_missing")
    headline, default_line = _MARKET_CONTEXT_PLAIN.get(label, ("Unknown", "Market context is not available yet."))
    one_liner = (message or default_line).strip()
    if len(one_liner) > 160:
        one_liner = one_liner[:157] + "..."
    return headline, one_liner


def format_entry_trigger_status_label(entry_status: str | None) -> str:
    """Beginner label for V15 entry trigger status."""
    key = str(entry_status or "").strip().lower() or None
    return _ENTRY_TRIGGER_PLAIN.get(key, _ENTRY_TRIGGER_PLAIN[None])


def format_data_quality_plain(data_quality_read: str | None) -> str:
    """Plain-English data quality label."""
    key = str(data_quality_read or "").strip().lower()
    return _DATA_QUALITY_PLAIN.get(key, "Data quality unknown")


def format_risk_level_plain(risk_read: str | None) -> str:
    """Plain-English risk level from Tony risk_read."""
    key = str(risk_read or "").strip().lower()
    mapping = {
        "acceptable_risk": "Normal",
        "wide_atr_concern": "Higher volatility",
        "high_volatility_concern": "High volatility",
        "avoid_invalid_plan": "Invalid plan — review manually",
        "low_risk": "Low",
    }
    return mapping.get(key, key.replace("_", " ").title() if key else "Unknown")


def format_setup_type_plain(setup_read: str | None, setup_category: str | None = None) -> str:
    """Plain-English setup type."""
    if setup_category:
        return str(setup_category)
    key = str(setup_read or "").strip().lower()
    mapping = {
        "breakout_candidate": "Breakout Watch",
        "pullback_candidate": "Pullback Watch",
        "momentum_candidate": "Momentum Continuation",
        "base_building": "Base Building",
    }
    return mapping.get(key, key.replace("_", " ").title() if key else "Uncategorized")


def count_interesting_and_risky_stocks(analyst_events: pd.DataFrame) -> tuple[int, int]:
    """Count interesting (high_priority/watch) vs risky (avoid/wide risk) hypothesis events."""
    interesting = 0
    risky = 0
    if analyst_events.empty:
        return interesting, risky
    for _, ev in analyst_events.iterrows():
        try:
            payload = json.loads(ev.get("payload_json") or "{}")
        except json.JSONDecodeError:
            continue
        priority = str(payload.get("priority_label", ""))
        risk = str(payload.get("risk_read", ""))
        if priority in ("high_priority", "watch"):
            interesting += 1
        if priority == "avoid" or risk in ("wide_atr_concern", "high_volatility_concern", "avoid_invalid_plan"):
            risky += 1
    return interesting, risky


def build_top_watch_rows(
    analyst_events: pd.DataFrame,
    snapshot_lookup: dict[str, dict[str, Any]] | None = None,
    *,
    limit: int = 10,
) -> list[dict[str, str]]:
    """Build beginner-friendly top-watch rows for Command Center."""
    rows: list[dict[str, str]] = []
    if analyst_events.empty:
        return rows
    lookup = snapshot_lookup or {}
    for _, ev in analyst_events.head(limit).iterrows():
        try:
            payload = json.loads(ev.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        symbol = str(ev.get("symbol") or payload.get("symbol") or "?").upper()
        snap = lookup.get(symbol, {})
        hypothesis = str(ev.get("message") or payload.get("tony_hypothesis") or "Tony flagged this symbol for review.")
        if len(hypothesis) > 120:
            hypothesis = hypothesis[:117] + "..."
        rows.append(
            {
                "Symbol": symbol,
                "Why Tony is watching": hypothesis,
                "Setup type": format_setup_type_plain(payload.get("setup_read"), snap.get("setup_category")),
                "Risk level": format_risk_level_plain(payload.get("risk_read")),
                "Planned entry alert": format_entry_trigger_status_label(snap.get("entry_status")),
                "Data quality": format_data_quality_plain(payload.get("data_quality_read")),
            }
        )
    return rows


def trigger_tracker_summary(
    *,
    planned_today: int,
    triggered_today: int,
    pending: int,
    expired_not_triggered: int,
    missing_real_data: int,
) -> dict[str, int]:
    """Return labeled counts for the Entry Trigger Tracker section."""
    return {
        "planned_entry_alerts_today": planned_today,
        "triggered_entries": triggered_today,
        "pending_alerts": pending,
        "expired_or_not_triggered": expired_not_triggered,
        "missing_real_data_alerts": missing_real_data,
    }


def eod_outcome_summary_today(snapshots_today: pd.DataFrame) -> dict[str, int]:
    """Summarize today's watchlist record outcomes for Command Center."""
    labels = {
        "target_hit": 0,
        "partial_move": 0,
        "entry_not_triggered": 0,
        "insufficient_future_data": 0,
        "stop_hit": 0,
        "still_open": 0,
        "other": 0,
    }
    if snapshots_today.empty or "outcome_label" not in snapshots_today.columns:
        return labels
    for raw in snapshots_today["outcome_label"].fillna("unreviewed"):
        key = str(raw)
        if key in labels:
            labels[key] += 1
        elif key == "unreviewed":
            labels["still_open"] += 1
        else:
            labels["other"] += 1
    return labels


def collect_health_issues(
    *,
    watch_status: str,
    real_data_only: bool,
    provider: str,
    demo_blocked: bool,
    rate_limit_count: int,
    all_fallback: bool,
    stale_symbols: list[str] | None = None,
    missing_tracked_symbols: list[str] | None = None,
) -> list[str]:
    """Return plain-English issues for 'Is anything broken?'"""
    issues: list[str] = []
    if watch_status == "error":
        issues.append("Tony stopped with an error.")
    if watch_status == "stale":
        issues.append("Tony's heartbeat is late — the watch process may be stuck.")
    if is_fallback_provider(provider):
        issues.append("Tony is not using real market data right now.")
    elif not real_data_only:
        issues.append("Real-data-only mode is off in config.")
    if all_fallback:
        issues.append("All symbols were missing real data in the last scan.")
    if rate_limit_count > 0:
        issues.append(f"Rate-limit warnings recorded ({rate_limit_count}).")
    if stale_symbols:
        syms = summarize_symbol_list(stale_symbols)
        issues.append(
            f"{len(stale_symbols)} prior tracked position(s) need review — no closure record found: {syms}."
        )
    if missing_tracked_symbols:
        syms = summarize_symbol_list(missing_tracked_symbols)
        issues.append(
            f"{len(missing_tracked_symbols)} tracked position(s) expected from prior active list "
            f"but no stored tracked-position row was found: {syms}."
        )
    return issues


def find_unreconciled_tracked_symbols(
    snapshots: pd.DataFrame,
    *,
    active_symbols: set[str],
    stale_symbols: set[str],
) -> list[str]:
    """Return symbols that ever had entry_triggered=1 but have no active/stale record
    and no terminal outcome — these are missing from the tracked-position ledger."""
    if snapshots.empty or "symbol" not in snapshots.columns:
        return []
    if "entry_triggered" not in snapshots.columns:
        return []
    triggered_mask = snapshots["entry_triggered"].fillna(0).astype(int).eq(1)
    triggered = snapshots[triggered_mask]
    if triggered.empty:
        return []
    triggered_syms = set(triggered["symbol"].astype(str).str.upper())
    already_shown = active_symbols | stale_symbols
    candidates = triggered_syms - already_shown
    if not candidates:
        return []
    _terminal = {
        "target_hit", "stop_hit", "target_before_stop", "stop_before_target",
        "failed_setup", "expired_no_trigger", "entry_not_triggered",
    }
    _terminal_statuses = {"target_hit", "stop_hit", "invalidated", "closed", "expired", "partial_move"}
    result: list[str] = []
    for sym in sorted(candidates):
        sym_rows = triggered[triggered["symbol"].astype(str).str.upper().eq(sym)]
        outcomes = sym_rows["outcome_label"].fillna("").astype(str).str.lower() if "outcome_label" in sym_rows.columns else pd.Series(dtype=str)
        statuses = sym_rows["tracking_status"].fillna("").astype(str).str.lower() if "tracking_status" in sym_rows.columns else pd.Series(dtype=str)
        if outcomes.isin(_terminal).any() or statuses.isin(_terminal_statuses).any():
            continue
        result.append(sym)
    return result


def human_review_items(
    *,
    interesting_count: int,
    risky_count: int,
    pending_triggers: int,
    missing_symbols: list[str],
    quarantined_symbols: list[str],
    health_issues: list[str],
) -> list[str]:
    """Suggested human review bullets."""
    items: list[str] = []
    if interesting_count:
        items.append(f"Review {interesting_count} interesting stock(s) in Tony's Top Watches.")
    if risky_count:
        items.append(f"Check {risky_count} higher-risk name(s) before trusting the list.")
    if pending_triggers:
        items.append(f"{pending_triggers} planned entry alert(s) are still waiting — see watchlist records.")
    if missing_symbols:
        items.append(f"Missing real data for: {summarize_symbol_list(missing_symbols)}.")
    if quarantined_symbols:
        items.append(f"Quarantined symbols (skipped on purpose): {summarize_symbol_list(quarantined_symbols)}.")
    if health_issues:
        items.extend(health_issues)
    if not items:
        items.append("No urgent items. Skim Tony's Top Watches when you have time.")
    return items


def snapshots_today_dataframe(repo: object) -> pd.DataFrame:
    """Return non-seeded watchlist records created today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        snaps = repo.list_candidate_snapshots(date=today, limit=500)  # type: ignore[attr-defined]
        if snaps.empty:
            return snaps
        notes_col = snaps["notes"].fillna("") if "notes" in snaps.columns else pd.Series([""] * len(snaps))
        tags_col = snaps["tags_json"].fillna("[]") if "tags_json" in snaps.columns else pd.Series(["[]"] * len(snaps))
        seeded = pd.Series([
            is_seeded_demo_snapshot(n, t) for n, t in zip(notes_col, tags_col)
        ])
        return snaps[~seeded].copy()
    except Exception:
        return pd.DataFrame()


def snapshot_symbol_lookup(snapshots: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Map symbol -> latest snapshot row fields for top-watch cards."""
    if snapshots.empty or "symbol" not in snapshots.columns:
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for _, row in snapshots.iterrows():
        symbol = str(row.get("symbol", "")).upper()
        if symbol:
            lookup[symbol] = dict(row)
    return lookup


def snapshots_today_count(repo: object) -> int:
    """Count real (non-seeded-demo) snapshots created today (UTC)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        snaps = repo.list_candidate_snapshots(date=today, limit=500)  # type: ignore[attr-defined]
        if snaps.empty:
            return 0
        notes_col = snaps["notes"].fillna("") if "notes" in snaps.columns else pd.Series([""] * len(snaps))
        tags_col = snaps["tags_json"].fillna("[]") if "tags_json" in snaps.columns else pd.Series(["[]"] * len(snaps))
        seeded = pd.Series([
            is_seeded_demo_snapshot(n, t) for n, t in zip(notes_col, tags_col)
        ])
        return int((~seeded).sum())
    except Exception:
        return 0


# ── V15.7 Trading-app dashboard helpers ───────────────────────────────────────

TERMINAL_OUTCOMES = {
    "target_hit",
    "stop_hit",
    "target_before_stop",
    "stop_before_target",
    "failed_setup",
    "expired_no_trigger",
    "entry_not_triggered",
}

# V26: named lifecycle states for unified Watchlist
WATCHLIST_LIFECYCLE_STATES = (
    "watching",                    # phase=pick, no planned entry trigger
    "waiting_for_trigger",         # phase=waiting_alert, pending entry
    "active",                      # triggered and tracking (still_valid / needs_review)
    "weakening",                   # triggered and tracking, reassessment=weakening
    "stale_tracking_needs_review", # triggered, lost real data, no closure record (V26C)
    "invalidated",                 # tracking_status=invalidated → surfaces in Results
    "closed",                      # terminal outcome → surfaces in Results
    "expired",                     # entry expired / not triggered → surfaces in Results
)

# Lifecycle sort priority for Tony Watchlist: lower = shown first
_LIFECYCLE_SORT_PRIORITY: dict[str, int] = {
    "active": 0,
    "weakening": 1,
    "stale_tracking_needs_review": 2,
    "waiting_for_trigger": 3,
    "watching": 4,
}

_TRACKING_OUTCOMES = {
    "unreviewed",
    "still_open",
    "partial_move",
    "insufficient_future_data",
}

_TONY_RATING_PLAIN = {
    "high_priority": "High attention",
    "watch": "On watch",
    "low_priority": "Low priority",
    "avoid": "Avoid",
    "reference_only": "Reference only",
}

_PICK_STATUS_PLAIN = {
    "pick": "Tony Pick",
    "waiting_alert": "Waiting for entry alert",
    "tracking": "Active tracking",
    "closed": "Closed",
}

_TRACKING_STATUS_PLAIN = {
    "active": "Still active",
    "target_hit": "Target reached",
    "stop_hit": "Stop reached",
    "partial_move": "Partial move toward target",
    "expired": "Alert expired",
    "invalidated": "Setup invalidated",
    "missing_real_data": "Missing live data",
    "closed": "Closed",
}


def format_tracking_status_plain(tracking_status: str | None, outcome_label: str | None = None) -> str:
    """Plain-English label for V15.8 tracking_status."""
    key = str(tracking_status or "").strip().lower()
    if key in _TRACKING_STATUS_PLAIN:
        return _TRACKING_STATUS_PLAIN[key]
    if key:
        return key.replace("_", " ").title()
    return format_outcome_plain(outcome_label)


def format_time_active_minutes_label(
    minutes: Any,
    *,
    fallback_started_at: str | None = None,
    now: datetime | None = None,
) -> str:
    """Human-readable active duration from stored minutes or start time."""
    if not is_missing_scalar(minutes):
        try:
            total = int(minutes)
        except (TypeError, ValueError):
            total = None
        if total is not None and total >= 0:
            if total < 60:
                return f"{total}m active"
            hours = total // 60
            if hours < 24:
                return f"{hours}h active"
            return f"{hours // 24}d active"
    return format_time_active(fallback_started_at, now=now)


_OUTCOME_PLAIN = {
    "target_hit": "Target reached",
    "stop_hit": "Stop reached",
    "target_before_stop": "Target reached (before stop)",
    "stop_before_target": "Stop reached (before target)",
    "partial_move": "Partial move toward target",
    "failed_setup": "Setup failed",
    "still_open": "Still active",
    "unreviewed": "Still active",
    "entry_not_triggered": "Entry alert never hit",
    "expired_no_trigger": "Alert expired",
    "insufficient_future_data": "Not enough data yet",
}


def filter_research_snapshots(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Exclude seeded demo fixtures from product-facing views."""
    if snapshots.empty:
        return snapshots
    notes_col = (
        snapshots["notes"].fillna("")
        if "notes" in snapshots.columns
        else pd.Series([""] * len(snapshots), index=snapshots.index)
    )
    tags_col = (
        snapshots["tags_json"].fillna("[]")
        if "tags_json" in snapshots.columns
        else pd.Series(["[]"] * len(snapshots), index=snapshots.index)
    )
    seeded = pd.Series([
        is_seeded_demo_snapshot(n, t) for n, t in zip(notes_col, tags_col)
    ], index=snapshots.index)
    filtered = snapshots[~seeded].copy()
    if "used_demo_data" in filtered.columns:
        filtered = filtered[filtered["used_demo_data"].fillna(0).astype(int).eq(0)]
    return filtered


def _as_utc_timestamp(value: Any) -> pd.Timestamp:
    """Best-effort UTC timestamp for sorting/grouping, NaT when unavailable."""
    if is_missing_scalar(value):
        return pd.NaT
    return pd.to_datetime(value, utc=True, errors="coerce")


def _product_sort_series(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    """Return the first usable timestamp from candidate columns."""
    if frame.empty:
        return pd.Series(dtype="datetime64[ns, UTC]")
    result = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    for column in columns:
        if column not in frame.columns:
            continue
        parsed = pd.to_datetime(frame[column], utc=True, errors="coerce")
        result = result.fillna(parsed)
    return result


_BAD_DQ_VALUES = frozenset({"missing_real_data", "fallback_data", "intraday_fallback_demo", "demo_data"})


def _product_rows_only(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Hide demo, fallback, missing-real-data, and legacy rows from main product views."""
    if snapshots.empty:
        return snapshots.copy()
    filtered = filter_research_snapshots(snapshots)
    if filtered.empty:
        return filtered
    product = filtered.copy()
    if "used_fallback_data" in product.columns:
        product = product[product["used_fallback_data"].fillna(0).astype(int).eq(0)]
    if "used_demo_data" in product.columns:
        product = product[product["used_demo_data"].fillna(0).astype(int).eq(0)]
    if "data_source" in product.columns:
        excluded = {"demo_generated", "missing_real_data", "legacy_unknown", "unknown_legacy"}
        product = product[~product["data_source"].fillna("").astype(str).str.lower().isin(excluded)]
    if "missing_real_data_reason" in product.columns:
        product = product[
            product["missing_real_data_reason"].isna()
            | product["missing_real_data_reason"].astype(str).str.strip().eq("")
        ]
    if "tony_data_quality_read" in product.columns:
        product = product[
            ~product["tony_data_quality_read"].fillna("").astype(str).str.lower().isin(_BAD_DQ_VALUES)
        ]
    if "snapshot_provider" in product.columns:
        bad_provider = product["snapshot_provider"].fillna("").astype(str).str.lower()
        product = product[~bad_provider.str.contains("demo|fallback", regex=True)]
    if "symbol" in product.columns:
        product = product[product["symbol"].fillna("").astype(str).str.strip().ne("")]
    return product.copy()


def _closed_results_pool(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Wider pool for stale/closed detection — allows prior-active missing_real_data rows,
    but always excludes pure demo/legacy rows."""
    if snapshots.empty:
        return snapshots.copy()
    filtered = filter_research_snapshots(snapshots)
    if filtered.empty:
        return filtered
    pool = filtered.copy()
    if "data_source" in pool.columns:
        excluded = {"demo_generated", "legacy_unknown", "unknown_legacy"}
        pool = pool[~pool["data_source"].fillna("").astype(str).str.lower().isin(excluded)]
    if "used_demo_data" in pool.columns:
        pool = pool[pool["used_demo_data"].fillna(0).astype(int).eq(0)]
    pure_demo_dq = frozenset({"demo_data", "intraday_fallback_demo"})
    if "tony_data_quality_read" in pool.columns:
        pool = pool[
            ~pool["tony_data_quality_read"].fillna("").astype(str).str.lower().isin(pure_demo_dq)
        ]
    if "snapshot_provider" in pool.columns:
        pool = pool[
            ~pool["snapshot_provider"].fillna("").astype(str).str.lower().str.contains("demo_generated", regex=False)
        ]
    if "symbol" in pool.columns:
        pool = pool[pool["symbol"].fillna("").astype(str).str.strip().ne("")]
    return pool.copy()


def _is_stale_tracked_position(row: dict[str, Any] | pd.Series) -> bool:
    """True for a prior-active triggered position that lost real data with no closure record."""
    if isinstance(row, pd.Series):
        row = dict(row)
    entry_triggered_raw = row.get("entry_triggered")
    if is_missing_scalar(entry_triggered_raw) or int(entry_triggered_raw) != 1:
        return False
    tracking_status = str(row.get("tracking_status") or "").strip().lower()
    if tracking_status != "missing_real_data":
        return False
    return not is_missing_scalar(
        row.get("original_entry_price")
        or row.get("actual_entry_price")
        or row.get("entry_trigger_price")
    )


def build_stale_tracking_rows(snapshots: pd.DataFrame) -> pd.DataFrame:
    """One stale-tracking row per prior-active symbol that lost real data coverage.

    These symbols had entry_triggered=1 but update-snapshots could not fetch real bars.
    They appear in Tony Watchlist as stale_tracking_needs_review — not silently dropped.
    """
    pool = _closed_results_pool(snapshots)
    if pool.empty or "symbol" not in pool.columns:
        return pd.DataFrame()
    records: list[dict[str, Any]] = []
    for symbol, group in pool.groupby(pool["symbol"].astype(str).str.upper(), sort=False):
        if not symbol:
            continue
        candidates = group[group.apply(_is_stale_tracked_position, axis=1)].copy()
        if candidates.empty:
            continue
        candidates["_sort_time"] = _product_sort_series(
            candidates, ("tracking_started_at", "actual_entry_time", "snapshot_time")
        )
        candidates = candidates.sort_values("_sort_time", ascending=False, na_position="last")
        record = dict(candidates.iloc[0].drop(labels=["_sort_time"], errors="ignore"))
        record["symbol"] = symbol
        record["lifecycle_state"] = "stale_tracking_needs_review"
        records.append(record)
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _effective_tracking_target(row: dict[str, Any] | pd.Series) -> Any:
    if isinstance(row, pd.Series):
        row = dict(row)
    return row.get("current_target_price") or row.get("original_target_price") or row.get("target")


def _effective_tracking_stop(row: dict[str, Any] | pd.Series) -> Any:
    if isinstance(row, pd.Series):
        row = dict(row)
    return row.get("current_stop_price") or row.get("original_stop_price") or row.get("stop")


def _effective_tracking_entry(row: dict[str, Any] | pd.Series) -> Any:
    if isinstance(row, pd.Series):
        row = dict(row)
    return (
        row.get("original_entry_price")
        or row.get("actual_entry_price")
        or row.get("entry_trigger_price")
        or row.get("entry")
    )


def _effective_tracking_started_at(row: dict[str, Any] | pd.Series) -> Any:
    if isinstance(row, pd.Series):
        row = dict(row)
    return (
        row.get("tracking_started_at")
        or row.get("actual_entry_time")
        or row.get("entry_triggered_at")
    )


def _is_valid_active_tracking_anchor(row: dict[str, Any] | pd.Series) -> bool:
    """Anchor rows need a real triggered research entry with fixed plan fields present."""
    if isinstance(row, pd.Series):
        row = dict(row)
    if derive_pick_phase(row) != "tracking":
        return False
    if is_missing_scalar(_effective_tracking_entry(row)):
        return False
    if is_missing_scalar(_effective_tracking_target(row)):
        return False
    if is_missing_scalar(_effective_tracking_stop(row)):
        return False
    if is_missing_scalar(_effective_tracking_started_at(row)):
        return False
    return True


def build_active_tracking_product_rows(snapshots: pd.DataFrame) -> pd.DataFrame:
    """One active tracking row per symbol for product views."""
    product = _product_rows_only(snapshots)
    if product.empty or "symbol" not in product.columns:
        return product

    records: list[dict[str, Any]] = []
    for symbol, group in product.groupby(product["symbol"].astype(str).str.upper(), sort=False):
        if not symbol:
            continue
        anchor_candidates = group[group.apply(_is_valid_active_tracking_anchor, axis=1)].copy()
        if anchor_candidates.empty:
            continue
        anchor_candidates["_anchor_time"] = _product_sort_series(
            anchor_candidates,
            ("tracking_started_at", "actual_entry_time", "entry_triggered_at", "snapshot_time"),
        )
        anchor_candidates = anchor_candidates.sort_values(
            ["_anchor_time", "snapshot_time"],
            ascending=[True, True],
            na_position="last",
        )
        anchor = dict(anchor_candidates.iloc[0].drop(labels=["_anchor_time"], errors="ignore"))

        active_group = group[group.apply(is_fresh_active_tracking, axis=1)].copy()
        if active_group.empty:
            continue
        active_group["_latest_time"] = _product_sort_series(
            active_group,
            ("current_price_at", "last_reassessed_at", "last_checked_at", "snapshot_time"),
        )
        active_group = active_group.sort_values(
            ["_latest_time", "snapshot_time"],
            ascending=[False, False],
            na_position="last",
        )
        latest = dict(active_group.iloc[0].drop(labels=["_latest_time"], errors="ignore"))

        merged = anchor.copy()
        for key in (
            "current_price",
            "current_price_at",
            "research_unrealized_pl_pct",
            "current_target_price",
            "current_stop_price",
            "reassessment_note",
            "last_reassessed_at",
            "invalidation_reason",
            "time_active_minutes",
            "tracking_status",
            "outcome_label",
            "last_checked_at",
            "close",
            "intraday_close",
            "planned_entry_price",
            "planned_entry_rule",
            "pick_phase",
        ):
            value = latest.get(key)
            if not is_missing_scalar(value):
                merged[key] = value
        merged["symbol"] = symbol
        records.append(merged)

    if not records:
        return pd.DataFrame()

    deduped = pd.DataFrame(records)
    deduped["_sort_time"] = _product_sort_series(
        deduped,
        ("tracking_started_at", "actual_entry_time", "entry_triggered_at", "snapshot_time"),
    )
    deduped = deduped.sort_values(["_sort_time", "symbol"], ascending=[False, True], na_position="last")
    return deduped.drop(columns="_sort_time")


def _is_valid_tony_pick_row(row: dict[str, Any] | pd.Series) -> bool:
    if isinstance(row, pd.Series):
        row = dict(row)
    phase = derive_pick_phase(row)
    if phase not in {"pick", "waiting_alert"}:
        return False
    if is_missing_scalar(row.get("target")) or is_missing_scalar(row.get("stop")):
        return False
    # When Tony analysis has run (tony_analysis_version set), require a valid priority label
    if not is_missing_scalar(row.get("tony_analysis_version")) and is_missing_scalar(
        row.get("tony_priority_label")
    ):
        return False
    return True


def build_tony_pick_product_rows(snapshots: pd.DataFrame) -> pd.DataFrame:
    """One Tony Pick row per symbol for product views."""
    product = _product_rows_only(snapshots)
    if product.empty:
        return product

    active_rows = build_active_tracking_product_rows(product)
    active_symbols = set()
    if not active_rows.empty and "symbol" in active_rows.columns:
        active_symbols = set(active_rows["symbol"].astype(str).str.upper().tolist())
    records: list[dict[str, Any]] = []
    for symbol, group in product.groupby(product["symbol"].astype(str).str.upper(), sort=False):
        if not symbol or symbol in active_symbols:
            continue
        candidates = group[group.apply(_is_valid_tony_pick_row, axis=1)].copy()
        if candidates.empty:
            continue
        candidates["_selection_rank"] = candidates.apply(
            lambda row: 0
            if derive_pick_phase(row) == "waiting_alert" and has_valid_planned_entry(row)
            else (1 if has_valid_planned_entry(row) else 2),
            axis=1,
        )
        candidates["_latest_time"] = _product_sort_series(candidates, ("snapshot_time",))
        candidates = candidates.sort_values(
            ["_selection_rank", "_latest_time"],
            ascending=[True, False],
            na_position="last",
        )
        record = dict(
            candidates.iloc[0].drop(labels=["_selection_rank", "_latest_time"], errors="ignore")
        )
        record["symbol"] = symbol
        records.append(record)

    if not records:
        return pd.DataFrame()

    deduped = pd.DataFrame(records)
    deduped["_home_sort"] = deduped.apply(
        lambda row: 0 if has_valid_planned_entry(row) and derive_pick_phase(row) == "waiting_alert" else 1,
        axis=1,
    )
    deduped["_sort_time"] = _product_sort_series(deduped, ("snapshot_time",))
    deduped = deduped.sort_values(
        ["_home_sort", "_sort_time", "symbol"],
        ascending=[True, False, True],
        na_position="last",
    )
    return deduped.drop(columns=["_home_sort", "_sort_time"])


def derive_pick_phase(row: dict[str, Any] | pd.Series) -> str:
    """Classify a watchlist record: pick | waiting_alert | tracking | closed."""
    if isinstance(row, pd.Series):
        row = dict(row)
    outcome = str(row.get("outcome_label") or "unreviewed").strip().lower()
    entry_status = str(row.get("entry_status") or "").strip().lower()
    entry_triggered_raw = row.get("entry_triggered")
    entry_triggered = 0 if is_missing_scalar(entry_triggered_raw) else int(entry_triggered_raw)

    if outcome in TERMINAL_OUTCOMES:
        return "closed"
    if entry_status in ("expired", "missing_real_data", "not_triggered") and entry_triggered == 0:
        return "closed"
    if entry_status == "triggered" or entry_triggered == 1:
        # Invalidated tracking state → symbol must surface in Results, not stay on Watchlist
        tracking_status = str(row.get("tracking_status") or "").strip().lower()
        reassessment_label = str(row.get("reassessment_label") or "").strip().lower()
        if tracking_status == "invalidated" or reassessment_label == "invalidated":
            return "closed"
        if outcome in _TRACKING_OUTCOMES or outcome == "":
            return "tracking"
        return "closed"
    if entry_status in ("pending", "no_intraday_trigger", ""):
        if entry_status == "pending":
            return "waiting_alert"
        return "pick"
    return "pick"


def format_tony_rating(priority_label: str | None) -> str:
    """Plain-English Tony rating from priority label."""
    key = str(priority_label or "").strip().lower()
    return _TONY_RATING_PLAIN.get(key, "Not rated")


def format_pick_status(phase: str) -> str:
    """Plain-English label for pick phase."""
    return _PICK_STATUS_PLAIN.get(phase, "Unknown")


def format_outcome_plain(outcome_label: str | None) -> str:
    """Plain-English result label."""
    key = str(outcome_label or "unreviewed").strip().lower()
    return _OUTCOME_PLAIN.get(key, key.replace("_", " ").title() if key else "Still active")


def is_missing_scalar(value: Any) -> bool:
    """Return True for None, NaN, empty string, or other unusable scalar values."""
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip().lower()
        return stripped in ("", "nan", "none", "null")
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def clean_text_or_default(value: Any, *, default: str) -> str:
    """Return cleaned text or a default when missing/NaN."""
    if is_missing_scalar(value):
        return default
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "null"):
        return default
    return text


def format_money_or_missing(value: Any, *, missing: str = "Not set yet") -> str:
    """Format a price for UI; never show $nan."""
    if is_missing_scalar(value):
        return missing
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return missing
    if math.isnan(amount) or math.isinf(amount):
        return missing
    return f"${amount:,.2f}"


def format_percent_or_missing(value: Any, *, missing: str = "Waiting for live price") -> str:
    """Format a research P/L percent; never show +nan%."""
    if is_missing_scalar(value):
        return missing
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return missing
    if math.isnan(pct) or math.isinf(pct):
        return missing
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def format_number_or_missing(value: Any, *, missing: str = "Not set yet") -> str:
    """Format a generic numeric value for UI."""
    if is_missing_scalar(value):
        return missing
    try:
        number = float(value)
    except (TypeError, ValueError):
        return missing
    if math.isnan(number) or math.isinf(number):
        return missing
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:,.2f}"


def calculate_risk_reward(entry_price: Any, target_price: Any, stop_price: Any) -> float | None:
    """Calculate planned upside/downside ratio; returns None when invalid."""
    if is_missing_scalar(entry_price) or is_missing_scalar(target_price) or is_missing_scalar(stop_price):
        return None
    try:
        entry = float(entry_price)
        target = float(target_price)
        stop = float(stop_price)
    except (TypeError, ValueError):
        return None
    downside = entry - stop
    upside = target - entry
    if entry <= 0 or downside <= 0 or upside <= 0:
        return None
    ratio = upside / downside
    if math.isnan(ratio) or math.isinf(ratio):
        return None
    return round(ratio, 2)


def format_risk_reward_or_missing(value: Any, *, missing: str = "N/A") -> str:
    """Format risk/reward as 2.0x style text."""
    if is_missing_scalar(value):
        return missing
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return missing
    if math.isnan(ratio) or math.isinf(ratio) or ratio <= 0:
        return missing
    return f"{ratio:.1f}x"


def risk_reward_definition_text() -> str:
    """Plain-English explanation for product UI."""
    return (
        "Risk/reward compares planned upside to planned downside: "
        "(target - entry) / (entry - stop). Example: 2.0x means planned upside is "
        "twice planned downside. It does not guarantee success."
    )


def calculate_research_pl_pct(
    tracked_from_price: float | None,
    current_price: float | None,
) -> float | None:
    """Research-only unrealized P/L percent (not a trading P/L claim)."""
    if is_missing_scalar(tracked_from_price) or is_missing_scalar(current_price):
        return None
    try:
        entry = float(tracked_from_price)
        current = float(current_price)
    except (TypeError, ValueError):
        return None
    if math.isnan(entry) or math.isnan(current) or entry <= 0:
        return None
    result = (current - entry) / entry * 100.0
    if math.isnan(result) or math.isinf(result):
        return None
    return round(result, 2)


def current_price_label(*, now: datetime | None = None) -> str:
    """Dynamic price label: live during session, closing after session."""
    ref = now if now is not None else datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    now_et = ref.astimezone(_US_EASTERN)
    return "Current price" if is_within_us_eastern_market_hours(now_et) else "Closing price"


def current_price_missing_text(*, now: datetime | None = None) -> str:
    return "No live price yet"


def calculate_trigger_distance_pct(current_price: Any, entry_trigger: Any) -> float | None:
    """Distance from current price to trigger: (current - trigger) / trigger * 100."""
    if is_missing_scalar(current_price) or is_missing_scalar(entry_trigger):
        return None
    try:
        current = float(current_price)
        trigger = float(entry_trigger)
    except (TypeError, ValueError):
        return None
    if trigger <= 0 or math.isnan(current) or math.isnan(trigger):
        return None
    result = (current - trigger) / trigger * 100.0
    if math.isnan(result) or math.isinf(result):
        return None
    return round(result, 2)


def format_trigger_distance(current_price: Any, entry_trigger: Any) -> str:
    """Human-readable trigger distance for Tony Picks."""
    distance = calculate_trigger_distance_pct(current_price, entry_trigger)
    if distance is None:
        return "N/A"
    if abs(distance) <= 0.1:
        return "At trigger area"
    if distance < 0:
        return f"{abs(distance):.1f}% below trigger"
    return f"{distance:.1f}% above trigger, awaiting confirmation"


def short_complete_sentence(text: Any, *, default: str) -> str:
    """Return one short sentence without clipping mid-sentence."""
    if is_missing_scalar(text):
        return default
    raw = " ".join(str(text).strip().split())
    if not raw:
        return default
    for marker in (". ", "? ", "! "):
        if marker in raw:
            sentence = raw.split(marker, 1)[0].strip()
            sentence = sentence.rstrip(".!?")
            return f"{sentence}."
    words = raw.split()
    if len(words) > 18:
        return " ".join(words[:18]).rstrip(",;:") + "."
    return raw if raw.endswith((".", "!", "?")) else raw + "."


def trigger_explanation(row: dict[str, Any] | pd.Series) -> str:
    """Product explanation for why Tony is waiting on the trigger."""
    if isinstance(row, pd.Series):
        row = dict(row)
    setup = format_setup_type_plain(row.get("tony_setup_read"), row.get("setup_category"))
    trigger = row.get("planned_entry_price")
    current = row.get("current_price") or row.get("intraday_close") or row.get("close")
    distance = calculate_trigger_distance_pct(current, trigger)
    if setup == "Speculative Watchlist":
        return "Watching only. No valid trigger yet."
    if setup == "Breakout Watch":
        if distance is not None and distance >= 0:
            return "Needs confirmation from a valid future 5Min bar."
        return "Waiting for breakout confirmation. Tony does not mark this active until price reaches the trigger."
    if setup == "Pullback Watch":
        return "Waiting for reclaim confirmation. Tony does not mark this active until price confirms the reclaim."
    if setup == "Momentum Continuation":
        return "Waiting for momentum confirmation before tracking."
    if is_missing_scalar(trigger):
        return "Watching only. No valid trigger yet."
    return "Waiting for trigger confirmation before tracking."


def trigger_reason_label(row: dict[str, Any] | pd.Series) -> str:
    """Short reason line for the entry trigger."""
    if isinstance(row, pd.Series):
        row = dict(row)
    setup = format_setup_type_plain(row.get("tony_setup_read"), row.get("setup_category"))
    mapping = {
        "Breakout Watch": "Breakout confirmation trigger",
        "Pullback Watch": "Reclaim confirmation trigger",
        "Momentum Continuation": "Momentum confirmation trigger",
        "Speculative Watchlist": "Watching only",
    }
    return mapping.get(setup, "Technical confirmation trigger")


def format_time_active(
    tracked_from_time: str | None,
    *,
    now: datetime | None = None,
) -> str:
    """Human-readable time active since trigger."""
    if not tracked_from_time:
        return "unknown"
    try:
        ts = datetime.fromisoformat(str(tracked_from_time).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ref = now if now is not None else datetime.now(timezone.utc)
        minutes = int((ref - ts).total_seconds() / 60)
        if minutes < 1:
            return "just started"
        if minutes < 60:
            return f"{minutes}m active"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h active"
        return f"{hours // 24}d active"
    except Exception:
        return "unknown"


def _format_trigger_date(ts_str: Any) -> str:
    """Short formatted trigger/entry date for Results table."""
    if is_missing_scalar(ts_str):
        return "—"
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_et = ts.astimezone(_US_EASTERN)
        return ts_et.strftime("%b %d, %I:%M %p").replace(" 0", " ")
    except Exception:
        text = str(ts_str).strip()
        return text[:16] if text else "—"


def _parse_json_list(raw: Any) -> list[str]:
    """Parse JSON/list/dict/scalar DB values into string items; never raises."""
    if is_missing_scalar(raw):
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if not is_missing_scalar(item)]
    if isinstance(raw, dict):
        for key in ("reasons", "concerns", "items", "tags"):
            nested = raw.get(key)
            if isinstance(nested, list):
                return [str(item) for item in nested if not is_missing_scalar(item)]
        return []
    if isinstance(raw, (int, float)):
        return []
    if not isinstance(raw, str):
        return []
    text = raw.strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if not is_missing_scalar(item)]
    if isinstance(value, dict):
        return _parse_json_list(value)
    return []


def _first_concern_as_invalidation(concerns_json: Any) -> str | None:
    concerns = _parse_json_list(concerns_json)
    if concerns:
        return str(concerns[0])
    return None


def _first_reason_as_confirmation(reasons_json: Any, candidate_summary: Any) -> str | None:
    reasons = _parse_json_list(reasons_json)
    if reasons:
        return str(reasons[0])
    if not is_missing_scalar(candidate_summary):
        text = str(candidate_summary).strip()
        if text and text.lower() not in ("nan", "none"):
            return text[:120] + ("..." if len(text) > 120 else "")
    return None


def _status_tone_for_pick(phase: str, entry_status: str | None, risk_level: str) -> str:
    if phase == "waiting_alert":
        return "warning"
    if "High volatility" in risk_level or "Higher volatility" in risk_level:
        return "risk"
    if phase == "pick":
        return "info"
    return "neutral"


def _status_tone_for_tracking(outcome: str, pl_pct: float | None) -> str:
    outcome_key = str(outcome or "").lower()
    if outcome_key in ("stop_hit", "stop_before_target", "failed_setup"):
        return "negative"
    if outcome_key in ("target_hit", "target_before_stop"):
        return "positive"
    if pl_pct is not None:
        if pl_pct > 0:
            return "positive"
        if pl_pct < 0:
            return "negative"
    return "info"


def has_valid_planned_entry(row: dict[str, Any] | pd.Series) -> bool:
    """Return True when planned_entry_price is a usable number."""
    if isinstance(row, pd.Series):
        row = dict(row)
    return not is_missing_scalar(row.get("planned_entry_price"))


def sort_rows_for_home_picks(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Prefer Tony Picks with a valid planned entry alert for Home."""
    if snapshots.empty:
        return snapshots
    priority = snapshots.apply(
        lambda row: 0 if has_valid_planned_entry(row) else 1,
        axis=1,
    )
    ordered = snapshots.copy()
    ordered["_home_sort"] = priority
    if "snapshot_time" in ordered.columns:
        ordered = ordered.sort_values(["_home_sort", "snapshot_time"], ascending=[True, False])
    else:
        ordered = ordered.sort_values("_home_sort")
    return ordered.drop(columns="_home_sort")


def is_fresh_active_tracking(row: dict[str, Any] | pd.Series) -> bool:
    """Return True for actively tracked setups (not historical/closed)."""
    if isinstance(row, pd.Series):
        row = dict(row)
    if derive_pick_phase(row) != "tracking":
        return False
    outcome = str(row.get("outcome_label") or "unreviewed").strip().lower()
    if outcome in TERMINAL_OUTCOMES:
        return False
    entry_status = str(row.get("entry_status") or "").strip().lower()
    return entry_status == "triggered" or int(row.get("entry_triggered") or 0) == 1


_HOME_CALM_NOT_SCANNING = "Tony is not currently scanning."


def _is_meaningful_watch_error(watch_status: str, watch_error_message: str | None) -> bool:
    """True only for unexpected watch failures (not empty after-hours error rows)."""
    if watch_status != "error":
        return False
    text = (watch_error_message or "").strip()
    if not text:
        return False
    lowered = text.lower()
    benign_markers = (
        "max_cycles",
        "max cycles",
        "market closed",
        "market hours",
        "waiting for market",
        "outside market",
        "user stopped",
        "stop file",
        "ctrl+c",
        "keyboard interrupt",
    )
    return not any(marker in lowered for marker in benign_markers)


def tony_status_home_message(
    beginner_status: str,
    watch_status: str,
    *,
    waiting_for_market: bool = False,
    has_data_issues: bool = False,
    watch_error_message: str | None = None,
) -> str:
    """Plain-English Tony status for Home (avoid implying failure after hours)."""
    if waiting_for_market or beginner_status == "Waiting":
        return "Tony is waiting for the next market session."

    if _is_meaningful_watch_error(watch_status, watch_error_message):
        return "Tony stopped with an error. Check System Health."

    if watch_status in ("stopped", "no_run", "error"):
        return _HOME_CALM_NOT_SCANNING

    if watch_status == "stale":
        if beginner_status in ("Needs attention", "Stopped", "Not started", "Waiting"):
            return _HOME_CALM_NOT_SCANNING
        return "Tony's heartbeat is late. Check the watch window or System Health."

    if has_data_issues and watch_status not in ("running",):
        return "Last scan had missing data. Check System Health."

    if beginner_status in ("Stopped", "Not started"):
        return _HOME_CALM_NOT_SCANNING

    return beginner_status


def format_home_missing_data_summary(symbols: list[str]) -> str:
    """Count-only missing-data line for Home (symbol names live in Settings)."""
    if not symbols:
        return ""
    count = len(symbols)
    noun = "symbol" if count == 1 else "symbols"
    return f"Missing live data: {count} {noun}. See Settings."


HOME_PICK_PREVIEW_FIELDS = (
    "symbol",
    "tony_rating",
    "setup_type",
    "risk_level",
    "status",
    "why",
    "entry_trigger",
    "target",
    "stop",
    "status_tone",
    "home_summary",
)

HOME_TRACKING_PREVIEW_FIELDS = (
    "symbol",
    "research_pl_pct",
    "tracked_from_price",
    "price_value",
    "target",
    "stop",
    "time_active",
    "tony_status",
    "pl_tone",
    "status_tone",
    "home_summary",
)


def select_home_preview_picks(snapshots: pd.DataFrame, *, limit: int = 3) -> pd.DataFrame:
    """Top Tony Picks for Home briefing only."""
    if snapshots.empty:
        return snapshots
    return sort_rows_for_home_picks(snapshots).head(limit)


def home_briefing_review_items(
    *,
    interesting_count: int,
    risky_count: int,
    pending_triggers: int,
    missing_symbols: list[str],
) -> list[str]:
    """Short 'what to review today' list for Home."""
    items: list[str] = []
    if pending_triggers:
        items.append(f"{pending_triggers} planned entry alert(s) still waiting.")
    if interesting_count:
        items.append(f"{interesting_count} interesting name(s) worth a quick look.")
    if risky_count:
        items.append(f"{risky_count} higher-risk name(s) — review before trusting the list.")
    if missing_symbols:
        summary = format_home_missing_data_summary(missing_symbols)
        if summary:
            items.append(summary)
    if not items:
        items.append("No urgent items. Open Tony Picks when you want the full watchlist.")
    return items


def select_home_tracking_rows(snapshots: pd.DataFrame, *, limit: int = 3) -> pd.DataFrame:
    """Home Active Tracking: fresh triggered rows only."""
    if snapshots.empty:
        return snapshots
    mask = snapshots.apply(is_fresh_active_tracking, axis=1)
    fresh = snapshots[mask].copy()
    if fresh.empty:
        return fresh
    fresh["_sort_time"] = _product_sort_series(
        fresh,
        ("tracking_started_at", "actual_entry_time", "entry_triggered_at", "snapshot_time"),
    )
    fresh = fresh.sort_values("_sort_time", ascending=False, na_position="last").drop(columns="_sort_time")
    return fresh.head(limit)


def build_pick_card_model(row: dict[str, Any] | pd.Series) -> dict[str, str]:
    """Build a Tony Pick card model from a snapshot row."""
    if isinstance(row, pd.Series):
        row = dict(row)
    phase = derive_pick_phase(row)
    risk_level = format_risk_level_plain(row.get("tony_risk_read"))
    if str(risk_level).strip().lower() == "unknown":
        risk_level = "N/A"
    data_quality = format_data_quality_plain(row.get("tony_data_quality_read"))
    has_planned = has_valid_planned_entry(row)
    why = clean_text_or_default(
        row.get("tony_hypothesis") or row.get("candidate_summary"),
        default="Tony has not written a plain-English reason yet.",
    )
    rule_raw = row.get("planned_entry_rule")
    planned_rule = (
        str(rule_raw).replace("_", " ")
        if not is_missing_scalar(rule_raw)
        else "N/A"
    )
    current_price_value = row.get("current_price") or row.get("intraday_close") or row.get("close")
    trigger_price = row.get("planned_entry_price")
    status = "Waiting for trigger" if has_planned else "Watching only — no actionable trigger yet"
    return {
        "symbol": str(row.get("symbol", "?")).upper(),
        "tony_rating": format_tony_rating(row.get("tony_priority_label")),
        "setup_type": format_setup_type_plain(row.get("tony_setup_read"), row.get("setup_category")),
        "why": why[:200],
        "home_summary": short_complete_sentence(
            why,
            default="Tony is watching this setup.",
        ),
        "entry_trigger": format_money_or_missing(
            trigger_price,
            missing="N/A",
        ),
        "planned_entry_alert": format_money_or_missing(
            trigger_price,
            missing="N/A",
        ),
        "active_entry": "N/A",
        "planned_entry_rule": planned_rule,
        "price_label": current_price_label(),
        "current_price": format_money_or_missing(
            current_price_value,
            missing=current_price_missing_text(),
        ),
        "target": format_money_or_missing(row.get("target")) if has_planned else "N/A",
        "stop": format_money_or_missing(row.get("stop")) if has_planned else "N/A",
        "needed_before_entry": "" if has_planned else "Tony has not created an actionable trigger yet.",
        "distance_to_trigger": format_trigger_distance(current_price_value, trigger_price),
        "risk_reward": format_risk_reward_or_missing(
            calculate_risk_reward(trigger_price, row.get("target"), row.get("stop"))
        ),
        "trigger_reason": trigger_reason_label(row),
        "trigger_explanation": trigger_explanation(row),
        "risk_level": risk_level,
        "status": status,
        "entry_alert_status": "Not triggered yet",
        "confirms_if": _first_reason_as_confirmation(
            row.get("tony_reasons_json"), row.get("candidate_summary")
        )
        or "Price holds above support with acceptable volume.",
        "invalidates_if": _first_concern_as_invalidation(row.get("tony_concerns_json"))
        or "Breaks stop level or loses key support.",
        "data_quality": "N/A" if "unknown" in data_quality.lower() else data_quality,
        "phase": phase,
        "has_planned_alert": "yes" if has_planned else "no",
        "status_tone": _status_tone_for_pick(phase, row.get("entry_status"), risk_level),
    }


def build_tracked_setup_card_model(
    row: dict[str, Any] | pd.Series,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Build an Active Tracking card model from a triggered snapshot row."""
    if isinstance(row, pd.Series):
        row = dict(row)
    tracked_from = (
        row.get("original_entry_price")
        or row.get("actual_entry_price")
        or row.get("entry_trigger_price")
        or row.get("entry")
    )
    current = row.get("current_price") or row.get("intraday_close") or row.get("close")
    stored_pl = row.get("research_unrealized_pl_pct")
    pl_pct = (
        float(stored_pl)
        if not is_missing_scalar(stored_pl)
        else calculate_research_pl_pct(tracked_from, current)
    )
    outcome = str(row.get("outcome_label") or "unreviewed")
    tracking_status = str(row.get("tracking_status") or "").strip().lower()
    tracked_time = (
        row.get("tracking_started_at")
        or row.get("actual_entry_time")
        or row.get("entry_triggered_at")
    )
    time_label = "N/A"
    if not is_missing_scalar(tracked_time):
        time_label = str(tracked_time)[:19]
    target_level = _effective_tracking_target(row)
    stop_level = _effective_tracking_stop(row)
    price_label = current_price_label(now=now)
    reassessment = clean_text_or_default(row.get("reassessment_note"), default="")
    plan_note = (
        "Original active entry, target, and stop were frozen when the trigger fired. "
        "Research tracking only, not a trade."
    )
    home_summary = short_complete_sentence(
        f"{format_tracking_status_plain(tracking_status, outcome)} from "
        f"{format_money_or_missing(tracked_from, missing='N/A')}.",
        default="Tony is tracking this research position.",
    )
    time_active = format_time_active_minutes_label(
        row.get("time_active_minutes"),
        fallback_started_at=tracked_time,
        now=now,
    )
    return {
        "symbol": str(row.get("symbol", "?")).upper(),
        "planned_entry": format_money_or_missing(row.get("planned_entry_price"), missing="N/A"),
        "entry_trigger": format_money_or_missing(row.get("planned_entry_price"), missing="N/A"),
        "tracked_from_price": format_money_or_missing(tracked_from, missing="N/A"),
        "tracked_from_time": time_label,
        "price_label": price_label,
        "price_value": format_money_or_missing(current, missing=current_price_missing_text(now=now)),
        "current_price": format_money_or_missing(current, missing=current_price_missing_text(now=now)),
        "research_pl_pct": format_percent_or_missing(pl_pct, missing="N/A"),
        "target": format_money_or_missing(target_level),
        "stop": format_money_or_missing(stop_level),
        "risk_reward": format_risk_reward_or_missing(
            calculate_risk_reward(tracked_from, target_level, stop_level)
        ),
        "time_active": "N/A" if str(time_active).lower() == "unknown" else time_active,
        "tony_status": format_tracking_status_plain(tracking_status, outcome),
        "setup_type": format_setup_type_plain(row.get("tony_setup_read"), row.get("setup_category")),
        "original_entry": format_money_or_missing(
            row.get("original_entry_price") or tracked_from,
            missing="N/A",
        ),
        "original_target": format_money_or_missing(
            row.get("original_target_price") or row.get("target"),
        ),
        "original_stop": format_money_or_missing(
            row.get("original_stop_price") or row.get("stop"),
        ),
        "plan_note": plan_note,
        "reassessment_note": reassessment,
        "home_summary": home_summary,
        "tracking_status": tracking_status,
        "phase": str(row.get("pick_phase") or derive_pick_phase(row)),
        "pl_tone": _status_tone_for_tracking(outcome, pl_pct),
        "status_tone": _status_tone_for_tracking(outcome, pl_pct),
        "is_fresh": "yes" if is_fresh_active_tracking(row) else "no",
    }


def split_snapshots_by_phase(snapshots: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split research snapshots into pick phases."""
    buckets: dict[str, list[dict[str, Any]]] = {
        "pick": [],
        "waiting_alert": [],
        "tracking": [],
        "closed": [],
    }
    if snapshots.empty:
        return {key: pd.DataFrame() for key in buckets}
    for _, row in snapshots.iterrows():
        phase = derive_pick_phase(row)
        buckets.setdefault(phase, []).append(dict(row))
    return {
        phase: pd.DataFrame(rows) if rows else pd.DataFrame()
        for phase, rows in buckets.items()
    }


def summarize_research_pl(snapshots: pd.DataFrame) -> dict[str, Any]:
    """Summarize open tracked research P/L (derivable only)."""
    active_rows = build_active_tracking_product_rows(snapshots)
    if active_rows.empty:
        return {"count": 0, "avg_pl_pct": None, "label": "No active tracked setups"}
    pl_values: list[float] = []
    for _, row in active_rows.iterrows():
        tracked = row.get("original_entry_price") or row.get("actual_entry_price") or row.get("entry")
        current = row.get("current_price") or row.get("intraday_close") or row.get("close")
        stored_pl = row.get("research_unrealized_pl_pct")
        pl = (
            float(stored_pl)
            if not is_missing_scalar(stored_pl)
            else calculate_research_pl_pct(tracked, current)
        )
        if pl is not None:
            pl_values.append(pl)
    if not pl_values:
        return {"count": 0, "avg_pl_pct": None, "label": "Waiting for live price on active tracked setups"}
    avg = round(sum(pl_values) / len(pl_values), 2)
    avg_display = format_percent_or_missing(avg)
    return {
        "count": len(pl_values),
        "avg_pl_pct": avg,
        "label": f"{len(pl_values)} active · avg {avg_display} research P/L (not a trading result)",
    }


RESULT_PERIODS = ("Today", "This week", "All time")

RESULTS_FILTERS = (
    "All",
    "Active",
    "Closed",
    "Target reached",
    "Stop reached",
    "Partial move",
    "Expired / not triggered",
    "Waiting for trigger",
    "Insufficient data",
)


def _result_sort_time(frame: pd.DataFrame) -> pd.Series:
    return _product_sort_series(
        frame,
        (
            "last_checked_at",
            "current_price_at",
            "last_reassessed_at",
            "tracking_started_at",
            "actual_entry_time",
            "entry_triggered_at",
            "snapshot_time",
        ),
    )


def _is_valid_closed_result_row(row: dict[str, Any] | pd.Series) -> bool:
    if isinstance(row, pd.Series):
        row = dict(row)
    if derive_pick_phase(row) != "closed":
        return False
    if is_missing_scalar(row.get("target")) or is_missing_scalar(row.get("stop")):
        return False
    if int(row.get("entry_triggered") or 0) == 1 and is_missing_scalar(_effective_tracking_entry(row)):
        return False
    return True


def build_closed_results_product_rows(
    snapshots: pd.DataFrame,
    *,
    active_rows: pd.DataFrame | None = None,
    pick_rows: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """One closed result row per symbol, excluding current waiting/active product symbols."""
    product = _product_rows_only(snapshots)
    if product.empty or "symbol" not in product.columns:
        return pd.DataFrame()
    excluded: set[str] = set()
    if active_rows is not None and not active_rows.empty and "symbol" in active_rows.columns:
        excluded.update(active_rows["symbol"].astype(str).str.upper().tolist())
    if pick_rows is not None and not pick_rows.empty and "symbol" in pick_rows.columns:
        excluded.update(pick_rows["symbol"].astype(str).str.upper().tolist())

    records: list[dict[str, Any]] = []
    for symbol, group in product.groupby(product["symbol"].astype(str).str.upper(), sort=False):
        if not symbol or symbol in excluded:
            continue
        candidates = group[group.apply(_is_valid_closed_result_row, axis=1)].copy()
        if candidates.empty:
            continue
        candidates["_sort_time"] = _result_sort_time(candidates)
        candidates = candidates.sort_values(
            ["_sort_time", "snapshot_time"],
            ascending=[False, False],
            na_position="last",
        )
        record = dict(candidates.iloc[0].drop(labels=["_sort_time"], errors="ignore"))
        record["symbol"] = symbol
        records.append(record)

    if not records:
        return pd.DataFrame()
    closed = pd.DataFrame(records)
    closed["_sort_time"] = _result_sort_time(closed)
    closed = closed.sort_values(["_sort_time", "symbol"], ascending=[False, True], na_position="last")
    return closed.drop(columns="_sort_time")


def _result_bucket_for_row(row: dict[str, Any] | pd.Series) -> str:
    if isinstance(row, pd.Series):
        row = dict(row)
    phase = derive_pick_phase(row)
    outcome = str(row.get("outcome_label") or "").strip().lower()
    if phase == "tracking":
        if outcome == "partial_move":
            return "Partial move"
        if outcome == "insufficient_future_data":
            return "Insufficient data"
        return "Active"
    if phase in {"pick", "waiting_alert"}:
        return "Waiting for trigger"
    if outcome in {"target_hit", "target_before_stop"}:
        return "Target reached"
    if outcome in {"stop_hit", "stop_before_target", "failed_setup"}:
        return "Stop reached"
    if outcome == "partial_move":
        return "Partial move"
    if outcome in {"entry_not_triggered", "expired_no_trigger"}:
        return "Expired / not triggered"
    if outcome == "insufficient_future_data":
        return "Insufficient data"
    return "Closed"


def build_results_product_rows(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Build one current clean product-state row per symbol for Results.

    Order: active tracking first, then closed, then waiting_alert picks only.
    Watching-only (no planned entry trigger) picks are excluded from Results.
    Stale tracking rows are excluded (they appear in Tony Watchlist instead).
    """
    if snapshots.empty or "symbol" not in snapshots.columns:
        return pd.DataFrame()
    active = build_active_tracking_product_rows(snapshots)
    # Build closed without pick_rows exclusion — prevents PATH's old pick row blocking it
    closed = build_closed_results_product_rows(snapshots, active_rows=active)
    # Only waiting_alert picks (with a real planned entry trigger) belong in Results
    all_picks = build_tony_pick_product_rows(snapshots)
    waiting_picks = pd.DataFrame()
    if not all_picks.empty:
        mask = all_picks.apply(
            lambda row: derive_pick_phase(row) == "waiting_alert" and has_valid_planned_entry(row),
            axis=1,
        )
        waiting_picks = all_picks[mask].copy()
    frames: list[pd.DataFrame] = []
    for phase_name, frame in (("active", active), ("closed", closed), ("waiting", waiting_picks)):
        if frame.empty:
            continue
        enriched = frame.copy()
        enriched["results_phase"] = phase_name
        enriched["results_filter"] = enriched.apply(_result_bucket_for_row, axis=1)
        frames.append(enriched)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined["_sort_time"] = _result_sort_time(combined)
    combined = combined.sort_values(["_sort_time", "symbol"], ascending=[False, True], na_position="last")
    return combined.drop(columns="_sort_time")


def _watchlist_lifecycle_state(row: dict[str, Any] | pd.Series) -> str:
    """Assign a WATCHLIST_LIFECYCLE_STATES value to a watchlist row."""
    if isinstance(row, pd.Series):
        row = dict(row)
    phase = derive_pick_phase(row)
    if phase == "waiting_alert":
        return "waiting_for_trigger"
    if phase == "pick":
        return "watching"
    reassessment = str(row.get("reassessment_label") or "").strip().lower()
    if reassessment == "weakening":
        return "weakening"
    return "active"


def build_tony_watchlist_rows(
    snapshots: pd.DataFrame,
    *,
    quarantine_symbols: set[str] | None = None,
) -> pd.DataFrame:
    """Unified Tony Watchlist: one card per symbol combining picks and active tracking.

    Active tracking rows take priority over pick rows for the same symbol.
    Stale tracking rows (prior-active, lost real data) appear below active.
    Closed/invalidated/expired symbols are excluded — they appear in Results.
    Quarantined symbols are filtered out entirely.
    """
    quarantine: set[str] = {s.upper() for s in (quarantine_symbols or set())}

    active = build_active_tracking_product_rows(snapshots)
    picks = build_tony_pick_product_rows(snapshots)
    stale = build_stale_tracking_rows(snapshots)

    active_symbols: set[str] = set()
    stale_symbols: set[str] = set()
    frames: list[pd.DataFrame] = []

    if not active.empty:
        active_copy = active.copy()
        active_copy = active_copy[~active_copy["symbol"].astype(str).str.upper().isin(quarantine)]
        if not active_copy.empty:
            active_symbols = set(active_copy["symbol"].astype(str).str.upper().tolist())
            active_copy["lifecycle_state"] = active_copy.apply(_watchlist_lifecycle_state, axis=1)
            frames.append(active_copy)

    if not stale.empty:
        stale_copy = stale.copy()
        stale_copy = stale_copy[~stale_copy["symbol"].astype(str).str.upper().isin(quarantine | active_symbols)]
        if not stale_copy.empty:
            stale_symbols = set(stale_copy["symbol"].astype(str).str.upper().tolist())
            frames.append(stale_copy)

    if not picks.empty:
        excluded = quarantine | active_symbols | stale_symbols
        pick_filtered = picks[~picks["symbol"].astype(str).str.upper().isin(excluded)].copy()
        if not pick_filtered.empty:
            pick_filtered["lifecycle_state"] = pick_filtered.apply(_watchlist_lifecycle_state, axis=1)
            frames.append(pick_filtered)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["_lifecycle_priority"] = combined["lifecycle_state"].map(
        lambda s: _LIFECYCLE_SORT_PRIORITY.get(str(s), 99)
    )
    combined["_sort_time"] = _product_sort_series(
        combined,
        ("tracking_started_at", "actual_entry_time", "snapshot_time"),
    )
    combined = combined.sort_values(
        ["_lifecycle_priority", "_sort_time", "symbol"],
        ascending=[True, False, True],
        na_position="last",
    )
    return combined.drop(columns=["_lifecycle_priority", "_sort_time"])


def filter_result_rows_by_period(rows: pd.DataFrame, period: str) -> pd.DataFrame:
    """Filter result rows by time period. Active tracking rows always shown (open positions)."""
    if rows.empty or period == "All time":
        return rows.copy()
    active_mask = (
        rows["results_phase"].astype(str).eq("active")
        if "results_phase" in rows.columns
        else pd.Series(False, index=rows.index)
    )
    time_cols = [c for c in ("snapshot_time", "tracking_started_at", "entry_triggered_at") if c in rows.columns]
    if not time_cols:
        return rows[active_mask].copy()
    # Build the most-specific available date per row.
    # snapshot_time is first (lowest priority); later columns overwrite it when present,
    # so entry_triggered_at (most specific trade date) wins over tracking_started_at
    # which wins over snapshot_time (scan time, always set but least precise).
    row_dates = pd.Series("", index=rows.index, dtype=str)
    for col in time_cols:
        filled = rows[col].fillna("").astype(str).str.slice(0, 10)
        row_dates = filled.where(filled.gt(""), row_dates)
    if period == "Today":
        cutoff = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
        period_mask = row_dates.eq(cutoff)
    else:  # This week
        cutoff = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        period_mask = row_dates.ge(cutoff)
    return rows[active_mask | period_mask].copy()


def filter_results_product_rows(rows: pd.DataFrame, filter_name: str) -> pd.DataFrame:
    """Filter current Results rows using product-facing labels."""
    if rows.empty or filter_name == "All":
        return rows.copy()
    if filter_name == "Closed":
        return rows[rows["results_phase"].astype(str).eq("closed")].copy()
    return rows[rows["results_filter"].astype(str).eq(filter_name)].copy()


def summarize_results_product_counts(rows: pd.DataFrame) -> dict[str, int]:
    """Summary counts aligned with deduped dashboard product semantics."""
    if rows.empty:
        return {
            "watched": 0,
            "triggered": 0,
            "active": 0,
            "closed": 0,
            "target_reached": 0,
            "stop_reached": 0,
            "partial_moves": 0,
            "waiting": 0,
            "expired": 0,
            "insufficient_data": 0,
        }
    filters = rows["results_filter"].fillna("").astype(str)
    phases = rows["results_phase"].fillna("").astype(str)
    triggered = int(
        phases.eq("active").sum()
        + rows[phases.eq("closed")]["entry_triggered"].fillna(0).astype(int).sum()
    )
    return {
        "watched": int(len(rows)),
        "triggered": triggered,
        "active": int(phases.eq("active").sum()),
        "closed": int(phases.eq("closed").sum()),
        "target_reached": int(filters.eq("Target reached").sum()),
        "stop_reached": int(filters.eq("Stop reached").sum()),
        "partial_moves": int(filters.eq("Partial move").sum()),
        "waiting": int(filters.eq("Waiting for trigger").sum()),
        "expired": int(filters.eq("Expired / not triggered").sum()),
        "insufficient_data": int(filters.eq("Insufficient data").sum()),
    }


def summarize_product_reconciliation(snapshots: pd.DataFrame) -> dict[str, int]:
    """Summarize raw snapshot rows versus current product-view rows.

    This is used by reporting surfaces to prove that dashboard dedupe/hiding does
    not delete raw history from storage. Counts here are research/product counts only.
    """
    empty = {
        "raw_snapshot_rows": 0,
        "raw_triggered_entry_rows": 0,
        "product_eligible_rows": 0,
        "product_visible_symbols": 0,
        "deduped_active_positions": 0,
        "deduped_waiting_picks": 0,
        "deduped_closed_results": 0,
        "target_hits": 0,
        "stop_hits": 0,
        "partial_moves": 0,
        "pending_triggers": 0,
        "expired_no_trigger": 0,
        "insufficient_data": 0,
        "incomplete_rows_hidden_from_product_views": 0,
        "history_rows_hidden_from_product_views": 0,
    }
    if snapshots.empty:
        return empty

    raw = snapshots.copy()
    raw_triggered = 0
    if "entry_triggered" in raw.columns:
        raw_triggered = int(raw["entry_triggered"].fillna(0).astype(int).sum())

    product_base = _product_rows_only(raw)
    active_rows = build_active_tracking_product_rows(raw)
    pick_rows = build_tony_pick_product_rows(raw)
    result_rows = build_results_product_rows(raw)
    result_counts = summarize_results_product_counts(result_rows)

    pending_triggers = 0
    if not pick_rows.empty:
        pending_triggers = int(
            pick_rows.apply(
                lambda row: str(row.get("entry_status") or "").strip().lower() == "pending",
                axis=1,
            ).sum()
        )

    incomplete_hidden = 0
    if not product_base.empty:
        for _, row in product_base.iterrows():
            phase = derive_pick_phase(row)
            if phase == "tracking" and not _is_valid_active_tracking_anchor(row):
                incomplete_hidden += 1
                continue
            if phase in {"pick", "waiting_alert"} and not _is_valid_tony_pick_row(row):
                incomplete_hidden += 1
                continue
            if phase == "closed" and not _is_valid_closed_result_row(row):
                incomplete_hidden += 1

    visible_symbols = int(len(result_rows))
    history_hidden = max(0, int(len(product_base)) - incomplete_hidden - visible_symbols)
    return {
        "raw_snapshot_rows": int(len(raw)),
        "raw_triggered_entry_rows": raw_triggered,
        "product_eligible_rows": int(len(product_base)),
        "product_visible_symbols": visible_symbols,
        "deduped_active_positions": int(len(active_rows)),
        "deduped_waiting_picks": int(len(pick_rows)),
        "deduped_closed_results": int(result_counts["closed"]),
        "target_hits": int(result_counts["target_reached"]),
        "stop_hits": int(result_counts["stop_reached"]),
        "partial_moves": int(result_counts["partial_moves"]),
        "pending_triggers": pending_triggers,
        "expired_no_trigger": int(result_counts["expired"]),
        "insufficient_data": int(result_counts["insufficient_data"]),
        "incomplete_rows_hidden_from_product_views": incomplete_hidden,
        "history_rows_hidden_from_product_views": history_hidden,
    }


def result_explanation(row: dict[str, Any] | pd.Series) -> str:
    """Plain-English explanation for the current result state."""
    if isinstance(row, pd.Series):
        row = dict(row)
    phase = derive_pick_phase(row)
    if phase in {"pick", "waiting_alert"}:
        return trigger_explanation(row)
    outcome = str(row.get("outcome_label") or "").strip().lower()
    if phase == "tracking":
        return "Trigger fired and Tony is tracking the research position."
    explanations = {
        "target_hit": "Target was reached before the setup failed.",
        "target_before_stop": "Target was reached before the stop level failed.",
        "stop_hit": "Stop was reached before the setup recovered.",
        "stop_before_target": "Stop was reached before the target was reached.",
        "failed_setup": "The setup failed before reaching its target.",
        "partial_move": "The setup moved partway toward target but did not complete.",
        "entry_not_triggered": "Price never confirmed the entry trigger.",
        "expired_no_trigger": "The setup expired before the trigger confirmed.",
        "insufficient_future_data": "There is not enough follow-up data yet to score the outcome.",
    }
    return explanations.get(outcome, "Tony reviewed the setup outcome.")


def build_result_card_model(
    row: dict[str, Any] | pd.Series,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Unified Results card model for waiting, active, and closed product states."""
    if isinstance(row, pd.Series):
        row = dict(row)
    phase = derive_pick_phase(row)
    price_value = row.get("current_price") or row.get("intraday_close") or row.get("close")
    setup_type = format_setup_type_plain(row.get("tony_setup_read"), row.get("setup_category"))
    why = clean_text_or_default(
        row.get("tony_hypothesis") or row.get("candidate_summary"),
        default="Tony has not written a plain-English reason yet.",
    )
    entry_trigger = row.get("planned_entry_price")
    if phase == "tracking":
        active_card = build_tracked_setup_card_model(row, now=now)
        trigger_time = (
            row.get("tracking_started_at") or row.get("actual_entry_time") or row.get("entry_triggered_at")
        )
        return {
            "symbol": active_card["symbol"],
            "setup_type": setup_type,
            "status": active_card["tony_status"],
            "price_label": active_card["price_label"],
            "price_value": active_card["price_value"],
            "exit_price": active_card["price_value"],
            "exit_price_label": active_card["price_label"],
            "entry_trigger": active_card["entry_trigger"],
            "active_entry": active_card["tracked_from_price"],
            "research_pl_pct": active_card["research_pl_pct"],
            "target": active_card["target"],
            "stop": active_card["stop"],
            "risk_reward": active_card["risk_reward"],
            "trigger_date": _format_trigger_date(trigger_time),
            "reason": short_complete_sentence(why, default="Tony is tracking this setup."),
            "result_explanation": result_explanation(row),
            "results_filter": _result_bucket_for_row(row),
            "phase": phase,
            "outcome_label": str(row.get("outcome_label") or "unreviewed"),
        }
    if phase in {"pick", "waiting_alert"}:
        pick_card = build_pick_card_model(row)
        return {
            "symbol": pick_card["symbol"],
            "setup_type": setup_type,
            "status": pick_card["status"],
            "price_label": pick_card["price_label"],
            "price_value": pick_card["current_price"],
            "exit_price": "N/A",
            "exit_price_label": "No Exit",
            "entry_trigger": pick_card["entry_trigger"],
            "active_entry": "N/A",
            "research_pl_pct": "N/A",
            "target": pick_card["target"],
            "stop": pick_card["stop"],
            "risk_reward": pick_card["risk_reward"],
            "trigger_date": "Not triggered",
            "reason": short_complete_sentence(why, default="Tony is watching this setup."),
            "result_explanation": pick_card["trigger_explanation"],
            "results_filter": _result_bucket_for_row(row),
            "phase": phase,
            "outcome_label": str(row.get("outcome_label") or "unreviewed"),
        }
    # ── Closed phase ───────────────────────────────────────────────────────────
    outcome = str(row.get("outcome_label") or "").strip().lower()
    active_entry = _effective_tracking_entry(row)
    # For terminal outcomes use the final exit price, not live/current price.
    # target_hit → exit at target; stop_hit → exit at stop; others → current price.
    if outcome in ("target_hit", "target_before_stop"):
        exit_price_raw = _effective_tracking_target(row)
        exit_label = "Target Hit"
    elif outcome in ("stop_hit", "stop_before_target", "failed_setup"):
        exit_price_raw = _effective_tracking_stop(row)
        exit_label = "Stop Hit"
    elif outcome in ("entry_not_triggered", "expired_no_trigger"):
        exit_price_raw = None
        exit_label = "No Exit"
    else:
        exit_price_raw = price_value
        exit_label = current_price_label(now=now)
    # P/L: prefer stored result_eod; fall back to entry → exit (not entry → live).
    stored_result = row.get("result_eod")
    research_pl_pct = None
    if not is_missing_scalar(stored_result):
        try:
            research_pl_pct = float(stored_result) * 100.0
        except (TypeError, ValueError):
            research_pl_pct = None
    if research_pl_pct is None and not is_missing_scalar(active_entry) and not is_missing_scalar(exit_price_raw):
        research_pl_pct = calculate_research_pl_pct(active_entry, exit_price_raw)
    rr_entry = active_entry if not is_missing_scalar(active_entry) else entry_trigger
    trigger_time = (
        row.get("tracking_started_at") or row.get("actual_entry_time") or row.get("entry_triggered_at")
    )
    return {
        "symbol": str(row.get("symbol", "?")).upper(),
        "setup_type": setup_type,
        "status": format_outcome_plain(row.get("outcome_label")),
        "price_label": exit_label,
        "price_value": format_money_or_missing(exit_price_raw, missing=current_price_missing_text(now=now)),
        "exit_price": format_money_or_missing(exit_price_raw, missing="N/A"),
        "exit_price_label": exit_label,
        "entry_trigger": format_money_or_missing(entry_trigger, missing="N/A"),
        "active_entry": format_money_or_missing(active_entry, missing="N/A"),
        "research_pl_pct": format_percent_or_missing(research_pl_pct, missing="N/A"),
        "target": format_money_or_missing(row.get("target")),
        "stop": format_money_or_missing(row.get("stop")),
        "risk_reward": format_risk_reward_or_missing(
            calculate_risk_reward(rr_entry, row.get("target"), row.get("stop"))
        ),
        "trigger_date": _format_trigger_date(trigger_time),
        "reason": short_complete_sentence(why, default="Tony reviewed this setup."),
        "result_explanation": result_explanation(row),
        "results_filter": _result_bucket_for_row(row),
        "phase": phase,
        "outcome_label": outcome,
    }


def summarize_results_plain_english(
    prepared: pd.DataFrame,
    *,
    period_label: str = "All time",
    active_tracking_rows: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Plain-English results summary for the Results tab."""
    empty: dict[str, Any] = {
        "period_label": period_label,
        "watched_setups": 0,
        "triggered": 0,
        "active": 0,
        "closed": 0,
        "target_hits": 0,
        "stop_hits": 0,
        "partial_moves": 0,
        "waiting": 0,
        "expired_no_trigger": 0,
        "insufficient_data": 0,
        "still_active": 0,
        "best_setup_category": None,
        "weakest_setup_category": None,
        "disclaimer": "Research outcomes only. No edge proven. Not investment advice.",
    }
    if prepared.empty:
        return empty

    outcomes = prepared["outcome_label"].fillna("unreviewed").astype(str)
    triggered = int(prepared["entry_triggered"].fillna(0).astype(int).sum()) if "entry_triggered" in prepared.columns else 0
    target_hits = int(outcomes.isin(["target_hit", "target_before_stop"]).sum())
    stop_hits = int(outcomes.isin(["stop_hit", "stop_before_target", "failed_setup"]).sum())
    partial = int(outcomes.eq("partial_move").sum())
    expired = int(outcomes.isin(["entry_not_triggered", "expired_no_trigger"]).sum())
    insufficient = int(outcomes.eq("insufficient_future_data").sum())
    if active_tracking_rows is None:
        active_rows = (
            build_active_tracking_product_rows(prepared)
            if "symbol" in prepared.columns
            else pd.DataFrame()
        )
    else:
        active_rows = active_tracking_rows
    still_active = int(len(active_rows))
    result_rows = build_results_product_rows(prepared)
    counts = summarize_results_product_counts(result_rows)

    best_setup = weakest_setup = None
    if "setup_category" in prepared.columns and triggered > 0:
        triggered_rows = prepared[prepared["entry_triggered"].fillna(0).astype(int).eq(1)]
        if not triggered_rows.empty:
            by_setup = triggered_rows.groupby("setup_category")["outcome_label"].apply(
                lambda s: float(s.isin(["target_hit", "target_before_stop"]).mean())
            )
            if not by_setup.empty:
                best_setup = str(by_setup.idxmax())
                weakest_setup = str(by_setup.idxmin())

    return {
        "period_label": period_label,
        "watched_setups": counts["watched"] or len(prepared),
        "triggered": counts["triggered"] or triggered,
        "active": counts["active"],
        "closed": counts["closed"],
        "target_hits": counts["target_reached"] or target_hits,
        "stop_hits": counts["stop_reached"] or stop_hits,
        "partial_moves": counts["partial_moves"] or partial,
        "waiting": counts["waiting"],
        "expired_no_trigger": counts["expired"] or expired,
        "insufficient_data": counts["insufficient_data"] or insufficient,
        "still_active": counts["active"] or still_active,
        "best_setup_category": best_setup,
        "weakest_setup_category": weakest_setup,
        "disclaimer": "Research outcomes only. No edge proven. Not investment advice.",
    }


def summarize_system_health(
    *,
    watch_status: str,
    beginner_status: str,
    real_data_only: bool,
    provider: str,
    demo_blocked: bool,
    missing_symbols: list[str],
    quarantined_symbols: list[str],
    last_scan_age: str,
    api_requests: Any,
    symbols_scanned: Any,
    rate_limit_count: int,
    health_issues: list[str],
) -> dict[str, Any]:
    """Bundle system health fields for Settings tab."""
    return {
        "watch_status": watch_status,
        "tony_status": beginner_status,
        "real_data_only": real_data_only,
        "provider": provider,
        "demo_blocked": demo_blocked,
        "missing_symbols": missing_symbols,
        "quarantined_symbols": quarantined_symbols,
        "last_scan_age": last_scan_age,
        "api_requests": api_requests,
        "symbols_scanned": symbols_scanned,
        "rate_limit_count": rate_limit_count,
        "health_issues": health_issues,
    }
