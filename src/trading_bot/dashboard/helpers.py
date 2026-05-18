"""Pure, Streamlit-free helper functions for the Trading Bot dashboard.

Extracted here so they can be unit-tested without importing Streamlit.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd


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
