"""V15.8 active tracking: frozen original plan + live research price refresh."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from trading_bot.dashboard.helpers import build_tracked_setup_card_model
from trading_bot.snapshots.active_tracking import (
    REASSESSMENT_INVALIDATED,
    REASSESSMENT_NEEDS_REVIEW,
    REASSESSMENT_STILL_VALID,
    REASSESSMENT_WEAKENING,
    TRACKING_STATUS_ACTIVE,
    TRACKING_STATUS_MISSING_REAL_DATA,
    TRACKING_STATUS_STOP_HIT,
    TRACKING_STATUS_TARGET_HIT,
    build_active_tracking_refresh_updates,
    build_original_plan_freeze_updates,
    compute_research_unrealized_pl_pct,
    compute_time_active_minutes,
    derive_reassessment_state,
    map_tracking_status_from_outcome,
)
from trading_bot.snapshots.entry_triggers import ENTRY_STATUS_TRIGGERED
from trading_bot.snapshots.followup import OUTCOME_PARTIAL_MOVE, OUTCOME_STOP_HIT, OUTCOME_TARGET_HIT
from trading_bot.storage.database import connect, initialize_database
from trading_bot.storage.repositories import ScannerRepository


def _triggered_snapshot(**overrides) -> dict:
    base = {
        "symbol": "PLTR",
        "entry_status": ENTRY_STATUS_TRIGGERED,
        "entry_triggered": 1,
        "actual_entry_price": 100.0,
        "actual_entry_time": "2026-05-18T14:30:00+00:00",
        "target": 110.0,
        "stop": 95.0,
        "outcome_label": "still_open",
    }
    base.update(overrides)
    return base


class TestOriginalPlanFreeze:
    def test_freeze_on_trigger_sets_original_fields(self) -> None:
        updates = build_original_plan_freeze_updates(_triggered_snapshot())
        assert updates["original_entry_price"] == 100.0
        assert updates["original_target_price"] == 110.0
        assert updates["original_stop_price"] == 95.0
        assert updates["current_target_price"] == 110.0
        assert updates["current_stop_price"] == 95.0
        assert updates["tracking_status"] == TRACKING_STATUS_ACTIVE
        assert updates["pick_phase"] == "tracking"

    def test_freeze_does_not_overwrite_existing_original(self) -> None:
        snap = _triggered_snapshot(original_entry_price=99.0, original_target_price=105.0)
        assert build_original_plan_freeze_updates(snap) == {}

    def test_not_triggered_returns_empty(self) -> None:
        assert build_original_plan_freeze_updates({"entry_status": "pending"}) == {}


class TestCurrentPriceRefresh:
    def _bars(self) -> pd.DataFrame:
        idx = pd.date_range("2026-05-18 14:35:00", periods=3, freq="5min")
        return pd.DataFrame({"close": [101.0, 102.0, 103.5], "high": [101.5, 102.5, 104.0]}, index=idx)

    def test_refresh_computes_pl_and_current_price(self) -> None:
        snap = _triggered_snapshot()
        snap.update(build_original_plan_freeze_updates(snap))
        updates = build_active_tracking_refresh_updates(
            snap,
            self._bars(),
            real_data_only=True,
            provider_name="alpaca_iex",
            now=datetime(2026, 5, 18, 16, 0, tzinfo=timezone.utc),
        )
        assert updates["current_price"] == 103.5
        assert updates["research_unrealized_pl_pct"] == pytest.approx(3.5, rel=1e-3)
        assert updates.get("time_active_minutes") is not None

    def test_demo_provider_skips_current_price(self) -> None:
        snap = _triggered_snapshot()
        snap.update(build_original_plan_freeze_updates(snap))
        updates = build_active_tracking_refresh_updates(
            snap,
            self._bars(),
            real_data_only=True,
            provider_name="demo_generated",
        )
        assert "current_price" not in updates
        assert updates["reassessment_label"] == REASSESSMENT_NEEDS_REVIEW

    def test_missing_real_data_tracking_status(self) -> None:
        snap = _triggered_snapshot(entry_status="missing_real_data")
        updates = build_active_tracking_refresh_updates(
            snap,
            self._bars(),
            real_data_only=True,
            provider_name="alpaca_iex",
        )
        assert updates.get("tracking_status") == TRACKING_STATUS_MISSING_REAL_DATA
        assert "current_price" not in updates

    def test_refresh_keeps_original_active_entry_fixed(self) -> None:
        snap = _triggered_snapshot(original_entry_price=100.0, tracking_started_at="2026-05-18T14:30:00+00:00")
        snap.update(build_original_plan_freeze_updates(snap))
        snap["original_entry_price"] = 100.0
        snap["actual_entry_price"] = 104.0
        updates = build_active_tracking_refresh_updates(
            snap,
            self._bars(),
            real_data_only=True,
            provider_name="alpaca_iex",
        )
        assert "original_entry_price" not in updates
        assert snap["original_entry_price"] == 100.0


class TestReassessmentLabels:
    def test_still_valid_label(self) -> None:
        label, reason = derive_reassessment_state(
            {
                "original_entry_price": 100.0,
                "target": 110.0,
                "stop": 95.0,
                "tracking_status": TRACKING_STATUS_ACTIVE,
                "outcome_label": "still_open",
                "research_unrealized_pl_pct": 2.0,
            },
            current_price=102.0,
        )
        assert label == REASSESSMENT_STILL_VALID
        assert "still valid" in reason.lower()

    def test_weakening_label(self) -> None:
        label, reason = derive_reassessment_state(
            {
                "original_entry_price": 100.0,
                "target": 110.0,
                "stop": 95.0,
                "tracking_status": TRACKING_STATUS_ACTIVE,
                "outcome_label": "still_open",
                "research_unrealized_pl_pct": -1.5,
            },
            current_price=98.5,
        )
        assert label == REASSESSMENT_WEAKENING
        assert "below the active research entry" in reason.lower()

    def test_invalidated_label(self) -> None:
        label, reason = derive_reassessment_state(
            {
                "original_entry_price": 100.0,
                "target": 110.0,
                "stop": 95.0,
                "tracking_status": TRACKING_STATUS_ACTIVE,
                "outcome_label": "still_open",
            },
            current_price=94.5,
        )
        assert label == REASSESSMENT_INVALIDATED
        assert "below the tracked stop" in reason.lower()

    def test_needs_review_label(self) -> None:
        label, reason = derive_reassessment_state(
            {
                "original_entry_price": 100.0,
                "target": 110.0,
                "stop": 95.0,
                "tracking_status": TRACKING_STATUS_MISSING_REAL_DATA,
                "entry_status": "missing_real_data",
                "outcome_label": "still_open",
            },
            current_price=None,
        )
        assert label == REASSESSMENT_NEEDS_REVIEW
        assert "missing real intraday context" in reason.lower()


class TestTrackingStatusMapping:
    def test_maps_target_hit(self) -> None:
        assert (
            map_tracking_status_from_outcome(OUTCOME_TARGET_HIT, ENTRY_STATUS_TRIGGERED, has_original_plan=True)
            == TRACKING_STATUS_TARGET_HIT
        )

    def test_maps_stop_hit(self) -> None:
        assert (
            map_tracking_status_from_outcome(OUTCOME_STOP_HIT, ENTRY_STATUS_TRIGGERED, has_original_plan=True)
            == TRACKING_STATUS_STOP_HIT
        )

    def test_active_when_still_open(self) -> None:
        assert (
            map_tracking_status_from_outcome("still_open", ENTRY_STATUS_TRIGGERED, has_original_plan=True)
            == TRACKING_STATUS_ACTIVE
        )


class TestTimeAndPlHelpers:
    def test_time_active_minutes(self) -> None:
        started = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
        minutes = compute_time_active_minutes(started)
        assert minutes is not None
        assert 44 <= minutes <= 46

    def test_research_pl_pct(self) -> None:
        assert compute_research_unrealized_pl_pct(100.0, 105.0) == pytest.approx(5.0)

    def test_research_pl_none_without_prices(self) -> None:
        assert compute_research_unrealized_pl_pct(None, 105.0) is None


class TestDashboardCardModel:
    def test_uses_frozen_original_and_current_fields(self) -> None:
        row = _triggered_snapshot(
            original_entry_price=100.0,
            original_target_price=110.0,
            original_stop_price=95.0,
            current_price=103.0,
            current_target_price=110.0,
            current_stop_price=95.0,
            research_unrealized_pl_pct=3.0,
            tracking_status=TRACKING_STATUS_ACTIVE,
            time_active_minutes=120,
        )
        card = build_tracked_setup_card_model(row)
        assert card["tracked_from_price"] == "$100.00"
        assert card["current_price"] == "$103.00"
        assert card["research_pl_pct"] == "+3.00%"
        assert "frozen" in card["plan_note"].lower()
        assert "V15.8" not in card["plan_note"]

    def test_legacy_row_without_tracking_fields_does_not_crash(self) -> None:
        card = build_tracked_setup_card_model(
            {
                "symbol": "X",
                "actual_entry_price": 50.0,
                "intraday_close": 51.0,
                "entry_status": ENTRY_STATUS_TRIGGERED,
                "entry_triggered": 1,
                "target": 55.0,
                "stop": 48.0,
            }
        )
        assert card["symbol"] == "X"
        assert card["tracked_from_price"] == "$50.00"


class TestDatabaseMigrations:
    def test_v158_columns_exist(self, tmp_path) -> None:
        db = tmp_path / "v158.db"
        initialize_database(db)
        with connect(db) as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(candidate_snapshots)").fetchall()}
        assert "original_entry_price" in cols
        assert "research_unrealized_pl_pct" in cols
        assert "pick_phase" in cols
        assert "reassessment_label" in cols

    def test_repository_accepts_tracking_updates(self, tmp_path) -> None:
        from tests.test_database import sample_scored_stock

        db = tmp_path / "repo.db"
        repo = ScannerRepository(db)
        run_id = repo.create_scan_run(1, "demo_generated", {"provider": "demo_generated"})
        config = {
            "enabled": True,
            "min_score": 0,
            "allowed_setup_categories": ["Breakout Watch"],
            "allowed_universe_roles": ["primary_candidate"],
            "exclude_invalid_trade_plans": False,
            "dedupe_hours": 0,
        }
        ids = repo.create_candidate_snapshots(run_id, [sample_scored_stock()], config)
        repo.update_candidate_snapshot_followup(
            ids[0],
            entry_status=ENTRY_STATUS_TRIGGERED,
            entry_triggered=1,
            actual_entry_price=42.0,
            original_entry_price=42.0,
            tracking_status=TRACKING_STATUS_ACTIVE,
            reassessment_label=REASSESSMENT_STILL_VALID,
            reassessment_note="Still valid: test note.",
        )
        row = repo.latest_candidate_snapshots().iloc[0]
        assert row["original_entry_price"] == 42.0
        assert row["reassessment_label"] == REASSESSMENT_STILL_VALID

    def test_reassessment_update_does_not_delete_snapshot_rows(self, tmp_path) -> None:
        from tests.test_database import sample_scored_stock

        db = tmp_path / "repo_reassess.db"
        repo = ScannerRepository(db)
        run_id = repo.create_scan_run(1, "alpaca_iex", {"provider": "alpaca_iex"})
        config = {
            "enabled": True,
            "min_score": 0,
            "allowed_setup_categories": ["Breakout Watch"],
            "allowed_universe_roles": ["primary_candidate"],
            "exclude_invalid_trade_plans": False,
            "dedupe_hours": 0,
        }
        ids = repo.create_candidate_snapshots(run_id, [sample_scored_stock()], config)
        before = len(repo.latest_candidate_snapshots())
        repo.update_candidate_snapshot_followup(
            ids[0],
            reassessment_label=REASSESSMENT_WEAKENING,
            reassessment_note="Weakening: test note.",
        )
        after_df = repo.latest_candidate_snapshots()
        assert len(after_df) == before
        assert after_df.iloc[0]["reassessment_label"] == REASSESSMENT_WEAKENING


class TestNoBrokerBehavior:
    def test_freeze_updates_have_no_order_fields(self) -> None:
        updates = build_original_plan_freeze_updates(_triggered_snapshot())
        forbidden = {"order", "broker", "paper_trade", "live_trade", "shares"}
        assert not forbidden.intersection(updates.keys())
