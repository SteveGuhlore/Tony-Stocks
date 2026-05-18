"""Tests for dashboard helper functions (no Streamlit dependency)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from trading_bot.dashboard.helpers import (
    count_hypothesis_by_priority,
    event_age_label,
    filter_events_by_type,
    is_current_cycle_event,
    is_fallback_provider,
    is_seeded_demo_snapshot,
    latest_event_of_type,
    snapshots_today_count,
)


def _ts(delta: timedelta | None = None) -> str:
    base = datetime.now(timezone.utc)
    if delta:
        base = base - delta
    return base.isoformat()


# ── TestEventAgeLabel ──────────────────────────────────────────────────────────

class TestEventAgeLabel:
    def test_none_returns_unknown(self) -> None:
        assert event_age_label(None) == "unknown"

    def test_empty_string_returns_unknown(self) -> None:
        assert event_age_label("") == "unknown"

    def test_just_now(self) -> None:
        assert event_age_label(_ts(timedelta(seconds=30))) == "just now"

    def test_minutes_ago(self) -> None:
        result = event_age_label(_ts(timedelta(minutes=7)))
        assert "m ago" in result
        assert "7" in result

    def test_hours_ago(self) -> None:
        result = event_age_label(_ts(timedelta(hours=3)))
        assert "h ago" in result
        assert "3" in result

    def test_days_ago(self) -> None:
        result = event_age_label(_ts(timedelta(days=2)))
        assert "d ago" in result
        assert "2" in result

    def test_invalid_string_returns_truncated(self) -> None:
        result = event_age_label("not-a-valid-date")
        assert isinstance(result, str)
        assert len(result) <= 16

    def test_z_suffix_handled(self) -> None:
        ts = _ts(timedelta(minutes=5)).replace("+00:00", "Z")
        result = event_age_label(ts)
        assert "m ago" in result


# ── TestIsFallbackProvider ─────────────────────────────────────────────────────

class TestIsFallbackProvider:
    def test_demo_generated_is_fallback(self) -> None:
        assert is_fallback_provider("demo_generated") is True

    def test_fallback_is_fallback(self) -> None:
        assert is_fallback_provider("fallback") is True

    def test_demo_is_fallback(self) -> None:
        assert is_fallback_provider("demo") is True

    def test_alpaca_iex_is_not_fallback(self) -> None:
        assert is_fallback_provider("alpaca_iex") is False

    def test_unknown_provider_is_not_fallback(self) -> None:
        assert is_fallback_provider("some_real_provider") is False

    def test_empty_string_is_not_fallback(self) -> None:
        assert is_fallback_provider("") is False


# ── TestFilterEventsByType ─────────────────────────────────────────────────────

class TestFilterEventsByType:
    def _events(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"event_type": "scan_completed", "message": "done"},
            {"event_type": "analyst_candidate_hypothesis", "message": "hyp1"},
            {"event_type": "analyst_candidate_hypothesis", "message": "hyp2"},
            {"event_type": "watch_cycle_completed", "message": "watch"},
        ])

    def test_filters_by_type(self) -> None:
        result = filter_events_by_type(self._events(), "analyst_candidate_hypothesis")
        assert len(result) == 2

    def test_empty_df_returns_empty(self) -> None:
        assert filter_events_by_type(pd.DataFrame(), "scan_completed").empty

    def test_no_match_returns_empty(self) -> None:
        assert filter_events_by_type(self._events(), "nonexistent_event").empty

    def test_no_event_type_column_returns_empty(self) -> None:
        events = pd.DataFrame([{"message": "no event_type column"}])
        assert filter_events_by_type(events, "scan_completed").empty


# ── TestLatestEventOfType ──────────────────────────────────────────────────────

class TestLatestEventOfType:
    def test_returns_first_row(self) -> None:
        events = pd.DataFrame([
            {"event_type": "scan_completed", "message": "newest"},
            {"event_type": "scan_completed", "message": "older"},
        ])
        result = latest_event_of_type(events, "scan_completed")
        assert result is not None
        assert result["message"] == "newest"

    def test_returns_none_when_empty(self) -> None:
        assert latest_event_of_type(pd.DataFrame(), "scan_completed") is None

    def test_returns_none_when_no_match(self) -> None:
        events = pd.DataFrame([{"event_type": "other_event", "message": "nope"}])
        assert latest_event_of_type(events, "scan_completed") is None

    def test_returns_dict(self) -> None:
        events = pd.DataFrame([{"event_type": "scan_completed", "message": "ok"}])
        result = latest_event_of_type(events, "scan_completed")
        assert isinstance(result, dict)


# ── TestIsCurrentCycleEvent ────────────────────────────────────────────────────

class TestIsCurrentCycleEvent:
    def test_recent_is_current(self) -> None:
        assert is_current_cycle_event(_ts(timedelta(minutes=5)), max_minutes=30) is True

    def test_old_is_not_current(self) -> None:
        assert is_current_cycle_event(_ts(timedelta(hours=2)), max_minutes=30) is False

    def test_none_is_not_current(self) -> None:
        assert is_current_cycle_event(None) is False

    def test_custom_window_allows_older(self) -> None:
        assert is_current_cycle_event(_ts(timedelta(hours=2)), max_minutes=200) is True

    def test_exactly_at_boundary(self) -> None:
        ts = _ts(timedelta(minutes=29, seconds=59))
        assert is_current_cycle_event(ts, max_minutes=30) is True


# ── TestCountHypothesisByPriority ──────────────────────────────────────────────

class TestCountHypothesisByPriority:
    def _make_events(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"payload_json": json.dumps({"priority_label": "high_priority"})},
            {"payload_json": json.dumps({"priority_label": "high_priority"})},
            {"payload_json": json.dumps({"priority_label": "watch"})},
            {"payload_json": json.dumps({"priority_label": "avoid"})},
        ])

    def test_counts_correctly(self) -> None:
        counts = count_hypothesis_by_priority(self._make_events())
        assert counts["high_priority"] == 2
        assert counts["watch"] == 1
        assert counts["avoid"] == 1

    def test_empty_df_returns_empty_dict(self) -> None:
        assert count_hypothesis_by_priority(pd.DataFrame()) == {}

    def test_malformed_payload_skipped(self) -> None:
        events = pd.DataFrame([
            {"payload_json": "not-json"},
            {"payload_json": json.dumps({"priority_label": "watch"})},
        ])
        counts = count_hypothesis_by_priority(events)
        assert counts.get("watch") == 1

    def test_no_broker_actions_in_priorities(self) -> None:
        counts = count_hypothesis_by_priority(self._make_events())
        broker_terms = {"buy", "sell", "short", "cover", "order", "execute", "place", "submit"}
        for key in counts:
            assert key.lower() not in broker_terms, f"Priority label '{key}' looks like a broker command"


# ── TestIsSeededDemoSnapshot ───────────────────────────────────────────────────

class TestIsSeededDemoSnapshot:
    def test_demo_seeded_notes(self) -> None:
        assert is_seeded_demo_snapshot("Demo seeded snapshot for testing", None) is True

    def test_seeded_demo_notes_variant(self) -> None:
        assert is_seeded_demo_snapshot("Seeded demo snapshot 2026-01-01", None) is True

    def test_demo_seeded_tag(self) -> None:
        assert is_seeded_demo_snapshot(None, json.dumps(["demo_seeded", "primary_candidate"])) is True

    def test_outcome_fixture_tag(self) -> None:
        assert is_seeded_demo_snapshot(None, json.dumps(["outcome_fixture"])) is True

    def test_real_snapshot_not_seeded(self) -> None:
        assert is_seeded_demo_snapshot("Real candidate setup", json.dumps(["primary_candidate", "breakout"])) is False

    def test_none_none_not_seeded(self) -> None:
        assert is_seeded_demo_snapshot(None, None) is False

    def test_empty_notes_empty_tags(self) -> None:
        assert is_seeded_demo_snapshot("", "[]") is False

    def test_partial_note_match_not_seeded(self) -> None:
        assert is_seeded_demo_snapshot("Candidate has good momentum", None) is False


# ── TestCurrentVsHistoricalSeparation ─────────────────────────────────────────

class TestCurrentVsHistoricalSeparation:
    def test_recent_events_detected_as_current(self) -> None:
        ts = _ts(timedelta(minutes=3))
        assert is_current_cycle_event(ts, max_minutes=10) is True

    def test_historical_events_not_current(self) -> None:
        ts = _ts(timedelta(hours=6))
        assert is_current_cycle_event(ts, max_minutes=30) is False

    def test_filter_to_current_events_only(self) -> None:
        events = pd.DataFrame([
            {"event_type": "analyst_candidate_hypothesis", "created_at": _ts(timedelta(minutes=2))},
            {"event_type": "analyst_candidate_hypothesis", "created_at": _ts(timedelta(hours=5))},
            {"event_type": "scan_completed", "created_at": _ts(timedelta(minutes=3))},
        ])
        hypothesis_events = filter_events_by_type(events, "analyst_candidate_hypothesis")
        current = hypothesis_events[
            hypothesis_events["created_at"].apply(lambda ts: is_current_cycle_event(ts, max_minutes=30))
        ]
        assert len(current) == 1


# ── TestNoBrokerBehavior ───────────────────────────────────────────────────────

class TestNoBrokerBehavior:
    def test_allowed_actions_do_not_include_broker_commands(self) -> None:
        from trading_bot.tony.analysis import ALLOWED_ACTIONS
        broker_terms = {"buy", "sell", "short", "cover", "order", "execute", "place", "submit"}
        for action in ALLOWED_ACTIONS:
            assert action.lower() not in broker_terms, f"Action '{action}' looks like a broker command"

    def test_is_fallback_provider_returns_bool_only(self) -> None:
        result = is_fallback_provider("alpaca_iex")
        assert isinstance(result, bool)

    def test_count_hypothesis_by_priority_produces_no_orders(self) -> None:
        events = pd.DataFrame([
            {"payload_json": json.dumps({
                "priority_label": "high_priority",
                "recommended_action": "snapshot_only",
            })},
        ])
        counts = count_hypothesis_by_priority(events)
        assert "snapshot_only" not in counts
        assert "high_priority" in counts

    def test_event_age_label_produces_no_side_effects(self) -> None:
        ts = _ts(timedelta(minutes=5))
        result1 = event_age_label(ts)
        result2 = event_age_label(ts)
        assert result1 == result2


# ── TestSnapshotsTodayCount ────────────────────────────────────────────────────

class TestSnapshotsTodayCount:
    def test_excludes_seeded_demo_snapshots(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        class FakeRepo:
            def list_candidate_snapshots(self, date: str | None = None, limit: int = 500) -> pd.DataFrame:
                return pd.DataFrame([
                    {"notes": "Real candidate", "tags_json": '["primary_candidate"]'},
                    {"notes": "Demo seeded snapshot for testing", "tags_json": '["demo_seeded"]'},
                    {"notes": "Real candidate 2", "tags_json": '["primary_candidate"]'},
                ])

        count = snapshots_today_count(FakeRepo())
        assert count == 2

    def test_empty_repo_returns_zero(self) -> None:
        class FakeRepo:
            def list_candidate_snapshots(self, date: str | None = None, limit: int = 500) -> pd.DataFrame:
                return pd.DataFrame()

        assert snapshots_today_count(FakeRepo()) == 0

    def test_all_seeded_returns_zero(self) -> None:
        class FakeRepo:
            def list_candidate_snapshots(self, date: str | None = None, limit: int = 500) -> pd.DataFrame:
                return pd.DataFrame([
                    {"notes": "Demo seeded snapshot", "tags_json": '["demo_seeded"]'},
                    {"notes": "Seeded demo snapshot 2026-01-01", "tags_json": "[]"},
                ])

        assert snapshots_today_count(FakeRepo()) == 0

    def test_repo_error_returns_zero(self) -> None:
        class BrokenRepo:
            def list_candidate_snapshots(self, date: str | None = None, limit: int = 500) -> pd.DataFrame:
                raise RuntimeError("DB error")

        assert snapshots_today_count(BrokenRepo()) == 0
