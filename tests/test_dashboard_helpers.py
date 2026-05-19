"""Tests for dashboard helper functions (no Streamlit dependency)."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from trading_bot.dashboard.helpers import (
    build_active_tracking_product_rows,
    build_pick_card_model,
    build_result_card_model,
    build_results_product_rows,
    build_tony_pick_product_rows,
    build_top_watch_rows,
    build_tracked_setup_card_model,
    calculate_risk_reward,
    calculate_research_pl_pct,
    collect_health_issues,
    count_hypothesis_by_priority,
    count_interesting_and_risky_stocks,
    current_price_label,
    derive_pick_phase,
    eod_outcome_summary_today,
    event_age_label,
    filter_events_by_type,
    filter_results_product_rows,
    format_data_quality_plain,
    format_entry_trigger_status_label,
    format_risk_reward_or_missing,
    HOME_PICK_PREVIEW_FIELDS,
    HOME_TRACKING_PREVIEW_FIELDS,
    format_home_missing_data_summary,
    format_money_or_missing,
    format_percent_or_missing,
    format_risk_level_plain,
    format_trigger_distance,
    format_time_active,
    format_tony_rating,
    clean_text_or_default,
    has_valid_planned_entry,
    is_missing_scalar,
    home_briefing_review_items,
    select_home_preview_picks,
    select_home_tracking_rows,
    sort_rows_for_home_picks,
    tony_status_home_message,
    human_review_items,
    is_current_cycle_event,
    is_fallback_provider,
    is_seeded_demo_snapshot,
    is_waiting_for_market_open,
    latest_event_of_type,
    market_context_plain_english,
    missing_symbols_from_events,
    snapshots_today_count,
    summarize_results_product_counts,
    summarize_results_plain_english,
    summarize_research_pl,
    summarize_symbol_list,
    summarize_system_health,
    tony_status_beginner_label,
    trigger_explanation,
    trigger_tracker_summary,
)
from trading_bot.dashboard.helpers import _parse_json_list


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

    def test_top_watch_rows_no_broker_wording(self) -> None:
        events = pd.DataFrame([
            {
                "symbol": "PLTR",
                "message": "Tony is analyzing, not trading.",
                "payload_json": json.dumps({
                    "priority_label": "watch",
                    "recommended_action": "watch_only",
                    "setup_read": "breakout_candidate",
                    "risk_read": "acceptable_risk",
                    "data_quality_read": "intraday_real_alpaca",
                }),
            }
        ])
        rows = build_top_watch_rows(events, {"PLTR": {"entry_status": "pending", "setup_category": "Breakout Watch"}})
        text = json.dumps(rows).lower()
        assert "buy" not in text
        assert "sell" not in text
        assert "order" not in text


# ── TestSnapshotsTodayCount ────────────────────────────────────────────────────

class TestSnapshotsTodayCount:
    def test_excludes_seeded_demo_snapshots(self) -> None:
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


# ── V15.5 Command Center helpers ───────────────────────────────────────────────

class TestTonyStatusBeginnerLabel:
    def test_running(self) -> None:
        assert tony_status_beginner_label("running") == "Running"

    def test_waiting_overrides(self) -> None:
        assert tony_status_beginner_label("running", waiting_for_market=True) == "Waiting"

    def test_error(self) -> None:
        assert tony_status_beginner_label("error") == "Error"


class TestBeginnerFriendlyLabels:
    def test_entry_trigger_plain(self) -> None:
        assert format_entry_trigger_status_label("pending") == "Waiting for alert"
        assert format_entry_trigger_status_label("triggered") == "Alert triggered — tracking"

    def test_data_quality_plain(self) -> None:
        assert "Good" in format_data_quality_plain("intraday_real_alpaca")
        assert "Demo" in format_data_quality_plain("demo_data")

    def test_market_context_plain(self) -> None:
        headline, line = market_context_plain_english("market_weak", "Benchmarks are soft.")
        assert headline == "Weak"
        assert "soft" in line.lower()


class TestTriggerTrackerSummary:
    def test_returns_expected_keys(self) -> None:
        summary = trigger_tracker_summary(
            planned_today=3,
            triggered_today=1,
            pending=2,
            expired_not_triggered=4,
            missing_real_data=1,
        )
        assert summary["planned_entry_alerts_today"] == 3
        assert summary["triggered_entries"] == 1


class TestTopWatchCardFormatting:
    def test_build_top_watch_rows_columns(self) -> None:
        events = pd.DataFrame([
            {
                "symbol": "DVN",
                "message": "Breakout watch with volume.",
                "payload_json": json.dumps({
                    "setup_read": "breakout_candidate",
                    "risk_read": "acceptable_risk",
                    "data_quality_read": "daily_real_alpaca",
                }),
            }
        ])
        rows = build_top_watch_rows(events, {"DVN": {"entry_status": "pending"}})
        assert rows[0]["Symbol"] == "DVN"
        assert "Planned entry alert" in rows[0]


class TestMissingAndQuarantineSummaries:
    def test_missing_symbols_from_events(self) -> None:
        events = pd.DataFrame([
            {"payload_json": json.dumps({"missing_real_data_symbols": ["HCP", "SQ"]})},
            {"payload_json": json.dumps({"missing_real_data_symbols": ["HCP"]})},
        ])
        assert "HCP" in missing_symbols_from_events(events)

    def test_summarize_symbol_list_truncates(self) -> None:
        text = summarize_symbol_list(["A", "B", "C", "D", "E", "F", "G", "H", "I"], max_show=3)
        assert "more" in text


class TestHealthAndReview:
    def test_collect_health_issues_demo_provider(self) -> None:
        issues = collect_health_issues(
            watch_status="running",
            real_data_only=True,
            provider="demo_generated",
            demo_blocked=True,
            rate_limit_count=0,
            all_fallback=False,
        )
        assert any("real market data" in i.lower() for i in issues)

    def test_human_review_items_when_empty(self) -> None:
        items = human_review_items(
            interesting_count=0,
            risky_count=0,
            pending_triggers=0,
            missing_symbols=[],
            quarantined_symbols=[],
            health_issues=[],
        )
        assert len(items) >= 1


class TestEodOutcomeSummary:
    def test_outcome_counts(self) -> None:
        snaps = pd.DataFrame([
            {"outcome_label": "target_hit"},
            {"outcome_label": "insufficient_future_data"},
            {"outcome_label": None},
        ])
        summary = eod_outcome_summary_today(snaps)
        assert summary["target_hit"] == 1
        assert summary["insufficient_future_data"] == 1
        assert summary["still_open"] == 1


class TestWaitingForMarket:
    def test_detects_recent_waiting_event(self) -> None:
        events = pd.DataFrame([
            {
                "event_type": "watch_waiting_for_market_open",
                "created_at": _ts(timedelta(minutes=5)),
                "payload_json": "{}",
            }
        ])
        assert is_waiting_for_market_open(events) is True


class TestInterestingRiskyCounts:
    def test_counts(self) -> None:
        events = pd.DataFrame([
            {"payload_json": json.dumps({"priority_label": "high_priority", "risk_read": "acceptable_risk"})},
            {"payload_json": json.dumps({"priority_label": "avoid", "risk_read": "wide_atr_concern"})},
        ])
        interesting, risky = count_interesting_and_risky_stocks(events)
        assert interesting == 1
        assert risky == 1


# ── V15.7 Trading-app dashboard helpers ───────────────────────────────────────

class TestDerivePickPhase:
    def test_waiting_alert(self) -> None:
        assert derive_pick_phase({"entry_status": "pending", "outcome_label": "unreviewed"}) == "waiting_alert"

    def test_tracking(self) -> None:
        assert derive_pick_phase({
            "entry_status": "triggered",
            "entry_triggered": 1,
            "outcome_label": "still_open",
        }) == "tracking"

    def test_closed_target(self) -> None:
        assert derive_pick_phase({"entry_status": "triggered", "outcome_label": "target_hit"}) == "closed"

    def test_pick_default(self) -> None:
        assert derive_pick_phase({"entry_status": "no_intraday_trigger", "outcome_label": "unreviewed"}) == "pick"


class TestResearchPlAndTimeActive:
    def test_calculate_research_pl_pct(self) -> None:
        assert calculate_research_pl_pct(100.0, 101.0) == 1.0
        assert calculate_research_pl_pct(100.0, 99.0) == -1.0

    def test_calculate_research_pl_none(self) -> None:
        assert calculate_research_pl_pct(None, 100.0) is None
        assert calculate_research_pl_pct(0, 100.0) is None

    def test_format_time_active(self) -> None:
        ts = _ts(timedelta(minutes=30))
        label = format_time_active(ts, now=datetime.now(timezone.utc))
        assert "active" in label


class TestCardModels:
    def test_build_pick_card_model(self) -> None:
        card = build_pick_card_model({
            "symbol": "DVN",
            "tony_priority_label": "watch",
            "setup_category": "Breakout Watch",
            "tony_hypothesis": "Volume expansion.",
            "planned_entry_price": 42.1,
            "target": 46.0,
            "stop": 40.5,
            "entry_status": "pending",
            "tony_risk_read": "acceptable_risk",
            "tony_data_quality_read": "intraday_real_alpaca",
        })
        assert card["symbol"] == "DVN"
        assert card["tony_rating"] == "On watch"
        assert "$42.10" in card["entry_trigger"]
        assert card["active_entry"] == "N/A"

    def test_build_tracked_setup_card_model(self) -> None:
        card = build_tracked_setup_card_model({
            "symbol": "AVGO",
            "actual_entry_price": 427.45,
            "actual_entry_time": _ts(timedelta(hours=1)),
            "intraday_close": 431.2,
            "target": 450.0,
            "stop": 415.0,
            "entry_status": "triggered",
            "entry_triggered": 1,
            "outcome_label": "still_open",
        })
        assert card["symbol"] == "AVGO"
        assert "+" in card["research_pl_pct"] or card["research_pl_pct"] != "—"
        assert "frozen" in card["plan_note"].lower()
        assert card["entry_trigger"] == "N/A"

    def test_empty_snapshots_no_crash(self) -> None:
        empty = pd.DataFrame()
        pl = summarize_research_pl(empty)
        assert pl["count"] == 0
        results = summarize_results_plain_english(empty)
        assert results["watched_setups"] == 0


class TestResultsAndSystemHealth:
    def test_summarize_results_plain_english(self) -> None:
        prepared = pd.DataFrame([
            {
                "outcome_label": "target_hit",
                "entry_triggered": 1,
                "setup_category": "Breakout Watch",
                "snapshot_time": "2026-05-18T10:00:00+00:00",
            },
            {
                "outcome_label": "unreviewed",
                "entry_triggered": 0,
                "setup_category": "Pullback Watch",
                "snapshot_time": "2026-05-18T11:00:00+00:00",
            },
        ])
        summary = summarize_results_plain_english(prepared, period_label="Today")
        assert summary["watched_setups"] == 2
        assert summary["target_hits"] == 1
        assert "no edge proven" in summary["disclaimer"].lower()

    def test_summarize_system_health(self) -> None:
        health = summarize_system_health(
            watch_status="running",
            beginner_status="Running",
            real_data_only=True,
            provider="alpaca_iex",
            demo_blocked=True,
            missing_symbols=["HCP"],
            quarantined_symbols=["SQ"],
            last_scan_age="5m ago",
            api_requests=2,
            symbols_scanned=97,
            rate_limit_count=0,
            health_issues=[],
        )
        assert health["provider"] == "alpaca_iex"
        assert health["missing_symbols"] == ["HCP"]

    def test_format_tony_rating(self) -> None:
        assert format_tony_rating("high_priority") == "High attention"


class TestSafetyWording:
    def test_results_disclaimer_no_profit_claim(self) -> None:
        summary = summarize_results_plain_english(pd.DataFrame())
        text = summary["disclaimer"].lower()
        assert "no edge proven" in text
        assert "broker" not in text
        assert "live trade" not in text


# ── V15.7A crash fix + display helpers ────────────────────────────────────────

class TestParseJsonList:
    def test_nan_float(self) -> None:
        assert _parse_json_list(float("nan")) == []

    def test_none(self) -> None:
        assert _parse_json_list(None) == []

    def test_float_number(self) -> None:
        assert _parse_json_list(123.4) == []

    def test_empty_string(self) -> None:
        assert _parse_json_list("") == []

    def test_invalid_json_string(self) -> None:
        assert _parse_json_list("not json") == []

    def test_json_list_string(self) -> None:
        assert _parse_json_list('["a", "b"]') == ["a", "b"]

    def test_json_dict_reasons(self) -> None:
        assert _parse_json_list('{"reasons": ["breakout", "volume"]}') == ["breakout", "volume"]

    def test_python_list(self) -> None:
        assert _parse_json_list(["x", "y"]) == ["x", "y"]


class TestDisplayHelpers:
    def test_format_money_nan(self) -> None:
        assert format_money_or_missing(float("nan")) == "Not set yet"
        assert format_money_or_missing(None, missing="No planned alert yet") == "No planned alert yet"

    def test_format_percent_nan(self) -> None:
        assert format_percent_or_missing(float("nan")) == "Waiting for live price"
        assert format_percent_or_missing(1.25) == "+1.25%"

    def test_clean_text_default(self) -> None:
        assert clean_text_or_default(float("nan"), default="Tony has not written a plain-English reason yet.") == (
            "Tony has not written a plain-English reason yet."
        )

    def test_is_missing_scalar(self) -> None:
        assert is_missing_scalar(float("nan")) is True
        assert is_missing_scalar("nan") is True
        assert is_missing_scalar(42.0) is False

    def test_distance_to_trigger_formatting(self) -> None:
        assert format_trigger_distance(97.2, 100.0) == "2.8% below trigger"
        assert format_trigger_distance(100.6, 100.0) == "0.6% above trigger, awaiting confirmation"
        assert format_trigger_distance(100.05, 100.0) == "At trigger area"

    def test_risk_reward_calculation_and_fallback(self) -> None:
        assert calculate_risk_reward(100.0, 110.0, 95.0) == 2.0
        assert format_risk_reward_or_missing(2.0) == "2.0x"
        assert format_risk_reward_or_missing(None) == "N/A"


class TestPickCardNanSafety:
    def test_build_pick_card_model_nan_reasons(self) -> None:
        card = build_pick_card_model({
            "symbol": "TEST",
            "tony_reasons_json": float("nan"),
            "tony_concerns_json": float("nan"),
            "planned_entry_price": float("nan"),
            "target": float("nan"),
            "tony_hypothesis": float("nan"),
            "entry_status": "no_intraday_trigger",
        })
        assert card["symbol"] == "TEST"
        assert card["planned_entry_alert"] == "N/A"
        assert "$nan" not in card["planned_entry_alert"]
        assert "nan" not in card["why"].lower() or "not written" in card["why"].lower()

    def test_tracked_card_no_nan_pl(self) -> None:
        card = build_tracked_setup_card_model({
            "symbol": "X",
            "actual_entry_price": 100.0,
            "intraday_close": float("nan"),
            "entry_status": "triggered",
            "entry_triggered": 1,
            "outcome_label": "still_open",
        })
        assert "+nan" not in card["research_pl_pct"].lower()
        assert card["current_price"] == "No live price yet"


class TestTriggerExplanations:
    def test_breakout_explanation_below_trigger(self) -> None:
        explanation = trigger_explanation({
            "setup_category": "Breakout Watch",
            "planned_entry_price": 100.0,
            "current_price": 98.0,
        })
        assert "breakout confirmation" in explanation.lower()

    def test_breakout_explanation_above_trigger_needs_future_bar(self) -> None:
        explanation = trigger_explanation({
            "setup_category": "Breakout Watch",
            "planned_entry_price": 100.0,
            "current_price": 101.0,
            "entry_status": "pending",
        })
        assert "future 5min bar" in explanation.lower()

    def test_pullback_explanation(self) -> None:
        explanation = trigger_explanation({"setup_category": "Pullback Watch"})
        assert "reclaim confirmation" in explanation.lower()

    def test_momentum_explanation(self) -> None:
        explanation = trigger_explanation({"setup_category": "Momentum Continuation"})
        assert "momentum confirmation" in explanation.lower()

    def test_speculative_explanation(self) -> None:
        explanation = trigger_explanation({"setup_category": "Speculative Watchlist"})
        assert "watching only" in explanation.lower()


class TestHomePickSorting:
    def test_sort_prefers_planned_entry(self) -> None:
        df = pd.DataFrame([
            {"symbol": "A", "planned_entry_price": float("nan"), "entry_status": "pending"},
            {"symbol": "B", "planned_entry_price": 42.0, "entry_status": "pending"},
        ])
        sorted_df = sort_rows_for_home_picks(df)
        assert sorted_df.iloc[0]["symbol"] == "B"
        assert has_valid_planned_entry(sorted_df.iloc[0]) is True

    def test_select_home_preview_picks_caps_at_three(self) -> None:
        df = pd.DataFrame([
            {"symbol": f"S{i}", "planned_entry_price": float(i), "entry_status": "pending"}
            for i in range(8)
        ])
        preview = select_home_preview_picks(df, limit=3)
        assert len(preview) == 3

    def test_select_home_preview_picks_empty(self) -> None:
        assert select_home_preview_picks(pd.DataFrame(), limit=3).empty


class TestTonyStatusHomeMessage:
    def test_waiting_for_market_not_failure(self) -> None:
        msg = tony_status_home_message("Waiting", "running", waiting_for_market=True)
        assert "next market session" in msg.lower()

    def test_stopped_not_alarming(self) -> None:
        msg = tony_status_home_message("Stopped", "stopped", has_data_issues=True)
        assert msg == "Tony is not currently scanning."
        assert "stopped with an error" not in msg.lower()

    def test_missing_data_message_when_watch_not_running(self) -> None:
        msg = tony_status_home_message("Unknown", "unknown", has_data_issues=True)
        assert "missing data" in msg.lower()
        assert "system health" in msg.lower()

    def test_briefing_uses_short_missing_data_summary(self) -> None:
        items = home_briefing_review_items(
            interesting_count=0,
            risky_count=0,
            pending_triggers=0,
            missing_symbols=[f"S{i}" for i in range(100)],
        )
        assert any("100 symbols" in item for item in items)
        assert not any("+93" in item for item in items)
        assert not any("S0" in item for item in items)

    def test_error_without_message_not_alarming(self) -> None:
        msg = tony_status_home_message("Error", "error", watch_error_message="")
        assert msg == "Tony is not currently scanning."
        assert "stopped with an error" not in msg.lower()

    def test_error_with_message_is_alarming(self) -> None:
        msg = tony_status_home_message(
            "Error",
            "error",
            watch_error_message="TimeoutError: broker unreachable",
        )
        assert "stopped with an error" in msg.lower()
        assert "system health" in msg.lower()

    def test_benign_error_message_not_alarming(self) -> None:
        msg = tony_status_home_message(
            "Error",
            "error",
            watch_error_message="Stopped: max_cycles reached",
        )
        assert msg == "Tony is not currently scanning."
        assert "stopped with an error" not in msg.lower()

    def test_stale_after_hours_not_alarming(self) -> None:
        msg = tony_status_home_message("Needs attention", "stale")
        assert msg == "Tony is not currently scanning."


class TestHomeMissingDataSummary:
    def test_many_symbols_shows_count_only(self) -> None:
        symbols = [f"S{i}" for i in range(101)]
        summary = format_home_missing_data_summary(symbols)
        assert summary == "Missing live data: 101 symbols. See Settings."
        assert "+93" not in summary
        assert "S0" not in summary

    def test_single_symbol_still_count_only(self) -> None:
        summary = format_home_missing_data_summary(["AAPL"])
        assert summary == "Missing live data: 1 symbol. See Settings."
        assert "AAPL" not in summary


class TestHomePreviewCardModels:
    def test_pick_model_has_home_preview_fields(self) -> None:
        row = {
            "symbol": "PLTR",
            "tony_priority_label": "watch",
            "tony_setup_read": "breakout_candidate",
            "setup_category": "Breakout Watch",
            "tony_risk_read": "acceptable_risk",
            "tony_hypothesis": "Strong volume and trend alignment.",
            "planned_entry_price": 25.5,
            "target": 30.0,
            "stop": 23.0,
            "entry_status": "pending",
        }
        card = build_pick_card_model(row)
        for key in HOME_PICK_PREVIEW_FIELDS:
            assert key in card
            assert card[key]
        assert len(card["why"]) <= 200

    def test_tracking_model_has_home_preview_fields(self) -> None:
        row = {
            "symbol": "SOFI",
            "actual_entry_price": 10.0,
            "intraday_close": 10.5,
            "target": 12.0,
            "stop": 9.5,
            "actual_entry_time": "2026-05-18T14:30:00+00:00",
            "outcome_label": "still_open",
            "entry_status": "triggered",
            "entry_triggered": 1,
        }
        card = build_tracked_setup_card_model(row)
        for key in HOME_TRACKING_PREVIEW_FIELDS:
            assert key in card
            assert card[key]


class TestHomeBriefingReview:
    def test_default_review_item_when_clear(self) -> None:
        items = home_briefing_review_items(
            interesting_count=0,
            risky_count=0,
            pending_triggers=0,
            missing_symbols=[],
        )
        assert any("Tony Picks" in item for item in items)


class TestProductSymbolLevelViews:
    def test_duplicate_tony_picks_collapse_to_one_symbol(self) -> None:
        rows = pd.DataFrame([
            {
                "symbol": "DKNG",
                "snapshot_time": "2026-05-19T14:35:00+00:00",
                "planned_entry_price": 41.5,
                "entry_status": "pending",
                "target": 45.0,
                "stop": 39.5,
            },
            {
                "symbol": "DKNG",
                "snapshot_time": "2026-05-19T14:40:00+00:00",
                "planned_entry_price": float("nan"),
                "entry_status": "no_intraday_trigger",
                "target": 46.0,
                "stop": 39.0,
            },
        ])
        picks = build_tony_pick_product_rows(rows)
        assert picks["symbol"].tolist() == ["DKNG"]
        assert float(picks.iloc[0]["planned_entry_price"]) == 41.5

    def test_duplicate_active_tracking_rows_collapse_to_one_card(self) -> None:
        rows = pd.DataFrame([
            {
                "symbol": "OXY",
                "snapshot_time": "2026-05-19T14:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 48.0,
                "actual_entry_time": "2026-05-19T14:05:00+00:00",
                "target": 52.0,
                "stop": 46.0,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
            {
                "symbol": "OXY",
                "snapshot_time": "2026-05-19T15:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 49.0,
                "actual_entry_time": "2026-05-19T15:05:00+00:00",
                "target": 53.0,
                "stop": 47.0,
                "current_price": 50.5,
                "research_unrealized_pl_pct": 5.21,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
        ])
        tracking = build_active_tracking_product_rows(rows)
        assert tracking["symbol"].tolist() == ["OXY"]

    def test_first_valid_triggered_entry_stays_fixed(self) -> None:
        rows = pd.DataFrame([
            {
                "symbol": "ARM",
                "snapshot_time": "2026-05-19T13:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 120.0,
                "actual_entry_time": "2026-05-19T13:05:00+00:00",
                "target": 128.0,
                "stop": 116.0,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
            {
                "symbol": "ARM",
                "snapshot_time": "2026-05-19T15:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 124.0,
                "actual_entry_time": "2026-05-19T15:05:00+00:00",
                "target": 130.0,
                "stop": 118.0,
                "current_price": 126.5,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
        ])
        tracking = build_active_tracking_product_rows(rows)
        card = build_tracked_setup_card_model(tracking.iloc[0])
        assert card["tracked_from_price"] == "$120.00"
        assert card["current_price"] == "$126.50"

    def test_latest_current_price_updates_active_card(self) -> None:
        rows = pd.DataFrame([
            {
                "symbol": "SMCI",
                "snapshot_time": "2026-05-19T13:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 900.0,
                "actual_entry_time": "2026-05-19T13:05:00+00:00",
                "target": 960.0,
                "stop": 860.0,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
            {
                "symbol": "SMCI",
                "snapshot_time": "2026-05-19T15:10:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 905.0,
                "actual_entry_time": "2026-05-19T15:15:00+00:00",
                "target": 965.0,
                "stop": 865.0,
                "current_price": 918.0,
                "research_unrealized_pl_pct": 2.0,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
        ])
        tracking = build_active_tracking_product_rows(rows)
        assert float(tracking.iloc[0]["current_price"]) == 918.0
        assert float(tracking.iloc[0]["research_unrealized_pl_pct"]) == 2.0

    def test_incomplete_nan_tracking_rows_hidden_from_main_active_tracking(self) -> None:
        rows = pd.DataFrame([
            {
                "symbol": "JOBY",
                "snapshot_time": "2026-05-19T14:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": float("nan"),
                "actual_entry_time": None,
                "target": 8.0,
                "stop": 6.5,
                "outcome_label": "still_open",
                "tracking_status": "active",
            }
        ])
        tracking = build_active_tracking_product_rows(rows)
        assert tracking.empty

    def test_home_has_no_duplicate_symbols(self) -> None:
        rows = pd.DataFrame([
            {
                "symbol": "DKNG",
                "snapshot_time": "2026-05-19T14:35:00+00:00",
                "planned_entry_price": 41.5,
                "entry_status": "pending",
                "target": 45.0,
                "stop": 39.5,
            },
            {
                "symbol": "DKNG",
                "snapshot_time": "2026-05-19T14:40:00+00:00",
                "planned_entry_price": 41.7,
                "entry_status": "pending",
                "target": 45.2,
                "stop": 39.6,
            },
            {
                "symbol": "OXY",
                "snapshot_time": "2026-05-19T15:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 48.0,
                "actual_entry_time": "2026-05-19T15:05:00+00:00",
                "target": 52.0,
                "stop": 46.0,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
            {
                "symbol": "OXY",
                "snapshot_time": "2026-05-19T15:20:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 48.5,
                "actual_entry_time": "2026-05-19T15:25:00+00:00",
                "target": 52.5,
                "stop": 46.5,
                "current_price": 49.2,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
        ])
        home_picks = select_home_preview_picks(build_tony_pick_product_rows(rows), limit=3)
        home_tracking = select_home_tracking_rows(build_active_tracking_product_rows(rows), limit=3)
        assert home_picks["symbol"].tolist() == ["DKNG"]
        assert home_tracking["symbol"].tolist() == ["OXY"]

    def test_planned_entry_vs_active_entry_display(self) -> None:
        pick_card = build_pick_card_model({
            "symbol": "DKNG",
            "planned_entry_price": 41.5,
            "current_price": 40.9,
            "target": 45.0,
            "stop": 39.5,
            "entry_status": "pending",
        })
        assert pick_card["entry_trigger"] == "$41.50"
        assert pick_card["active_entry"] == "N/A"
        assert pick_card["current_price"] == "$40.90"
        assert pick_card["distance_to_trigger"] == "1.4% below trigger"

        tracking_card = build_tracked_setup_card_model({
            "symbol": "OXY",
            "planned_entry_price": 47.8,
            "original_entry_price": 48.0,
            "actual_entry_time": "2026-05-19T15:05:00+00:00",
            "current_price": 49.2,
            "target": 52.0,
            "stop": 46.0,
            "entry_status": "triggered",
            "entry_triggered": 1,
            "outcome_label": "still_open",
            "tracking_status": "active",
        })
        assert tracking_card["entry_trigger"] == "$47.80"
        assert tracking_card["tracked_from_price"] == "$48.00"

    def test_results_active_count_aligns_with_deduped_active_cards(self) -> None:
        prepared = pd.DataFrame([
            {
                "symbol": "ARM",
                "snapshot_time": "2026-05-19T13:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 120.0,
                "actual_entry_time": "2026-05-19T13:05:00+00:00",
                "target": 128.0,
                "stop": 116.0,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
            {
                "symbol": "ARM",
                "snapshot_time": "2026-05-19T15:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "actual_entry_price": 124.0,
                "actual_entry_time": "2026-05-19T15:05:00+00:00",
                "target": 130.0,
                "stop": 118.0,
                "current_price": 126.5,
                "outcome_label": "still_open",
                "tracking_status": "active",
            },
            {
                "symbol": "DKNG",
                "snapshot_time": "2026-05-19T14:35:00+00:00",
                "planned_entry_price": 41.5,
                "entry_status": "pending",
                "target": 45.0,
                "stop": 39.5,
                "outcome_label": "unreviewed",
                "entry_triggered": 0,
            },
        ])
        active_rows = build_active_tracking_product_rows(prepared)
        summary = summarize_results_plain_english(
            prepared,
            period_label="Today",
            active_tracking_rows=active_rows,
        )
        assert len(active_rows) == 1
        assert summary["still_active"] == 1
        assert summary["active"] == 1


class TestProductSemanticsV158B:
    def test_after_market_price_label_switches_to_closing_price(self) -> None:
        now = datetime(2026, 5, 19, 20, 30, tzinfo=timezone.utc)
        card = build_tracked_setup_card_model({
            "symbol": "ARM",
            "original_entry_price": 120.0,
            "actual_entry_time": "2026-05-19T15:05:00+00:00",
            "close": 126.5,
            "target": 130.0,
            "stop": 118.0,
            "entry_status": "triggered",
            "entry_triggered": 1,
            "outcome_label": "still_open",
            "tracking_status": "active",
        }, now=now)
        assert card["price_label"] == "Closing price"
        assert card["price_value"] == "$126.50"
        assert current_price_label(now=now) == "Closing price"

    def test_results_filters_and_symbols_align_with_product_rows(self) -> None:
        rows = pd.DataFrame([
            {
                "symbol": "DKNG",
                "snapshot_time": "2026-05-19T14:35:00+00:00",
                "planned_entry_price": 41.5,
                "current_price": 40.9,
                "target": 45.0,
                "stop": 39.5,
                "entry_status": "pending",
                "setup_category": "Breakout Watch",
            },
            {
                "symbol": "ARM",
                "snapshot_time": "2026-05-19T15:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "planned_entry_price": 120.0,
                "actual_entry_price": 120.0,
                "actual_entry_time": "2026-05-19T15:05:00+00:00",
                "current_price": 126.5,
                "target": 130.0,
                "stop": 118.0,
                "outcome_label": "still_open",
                "tracking_status": "active",
                "setup_category": "Momentum Continuation",
            },
            {
                "symbol": "OXY",
                "snapshot_time": "2026-05-19T16:00:00+00:00",
                "entry_status": "triggered",
                "entry_triggered": 1,
                "planned_entry_price": 48.0,
                "actual_entry_price": 48.2,
                "actual_entry_time": "2026-05-19T15:10:00+00:00",
                "close": 52.0,
                "target": 52.0,
                "stop": 46.0,
                "outcome_label": "target_hit",
                "tracking_status": "closed",
                "setup_category": "Pullback Watch",
            },
        ])
        result_rows = build_results_product_rows(rows)
        assert set(result_rows["symbol"]) == {"DKNG", "ARM", "OXY"}
        active_rows = filter_results_product_rows(result_rows, "Active")
        assert active_rows["symbol"].tolist() == ["ARM"]
        closed_rows = filter_results_product_rows(result_rows, "Closed")
        assert closed_rows["symbol"].tolist() == ["OXY"]
        waiting_rows = filter_results_product_rows(result_rows, "Waiting for trigger")
        assert waiting_rows["symbol"].tolist() == ["DKNG"]

        counts = summarize_results_product_counts(result_rows)
        assert counts["active"] == 1
        assert counts["closed"] == 1
        assert counts["waiting"] == 1
        assert counts["target_reached"] == 1

        closed_card = build_result_card_model(closed_rows.iloc[0], now=datetime(2026, 5, 19, 20, 30, tzinfo=timezone.utc))
        assert closed_card["symbol"] == "OXY"
        assert closed_card["active_entry"] == "$48.20"
        assert closed_card["price_label"] == "Closing price"
        assert closed_card["risk_reward"] == "1.7x"

    def test_no_nan_or_unknown_strings_in_product_cards(self) -> None:
        pick_card = build_pick_card_model({
            "symbol": "JOBY",
            "planned_entry_price": float("nan"),
            "current_price": float("nan"),
            "target": 8.0,
            "stop": 6.5,
            "entry_status": "no_intraday_trigger",
            "setup_category": "Speculative Watchlist",
        })
        tracking_card = build_tracked_setup_card_model({
            "symbol": "SMCI",
            "original_entry_price": 900.0,
            "actual_entry_time": "2026-05-19T15:05:00+00:00",
            "current_price": float("nan"),
            "target": 960.0,
            "stop": 860.0,
            "entry_status": "triggered",
            "entry_triggered": 1,
            "outcome_label": "still_open",
            "tracking_status": "active",
            "setup_category": "Momentum Continuation",
        })
        for card in (pick_card, tracking_card):
            for value in card.values():
                text = str(value).lower()
                assert "$nan" not in text
                assert "+nan" not in text
                assert "unknown" not in text
