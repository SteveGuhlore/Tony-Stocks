"""Tests for V13 Tony Hypothesis-to-Outcome Tracking.

Covers:
- Schema migration: Tony fields added to candidate_snapshots
- Saving snapshots with Tony analysis attached
- Saving snapshots without Tony analysis (legacy compatibility)
- Outcome analytics grouped by Tony fields
- Analysis version constant and storage
- Seeded demo exclusion
- No broker/order/paper-trade behavior
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from trading_bot.storage.database import connect, initialize_database
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.tony.analysis import (
    TONY_ANALYSIS_VERSION,
    CandidateAnalysis,
    ACTION_SNAPSHOT,
    ACTION_WATCH,
    PRI_HIGH,
    PRI_WATCH,
    SETUP_BREAKOUT,
    SETUP_PULLBACK,
    RISK_ACCEPTABLE,
    RISK_WIDE_ATR,
    MKT_SUPPORTIVE,
    DQ_ALPACA_IEX,
    DQ_DEMO,
    OC_NOT_ENOUGH,
)
from trading_bot.analytics.outcomes import OutcomeAnalytics
from trading_bot.tony.events import TonyStocksService, TonyConfig


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path: Path):
    path = tmp_path / "test_v13.db"
    initialize_database(path)
    return path


@pytest.fixture()
def repo(db: Path):
    return ScannerRepository(db)


def _make_scan_run(repo: ScannerRepository) -> int:
    return repo.create_scan_run(universe_count=10, provider="demo_generated", config_snapshot={})


def _make_scored_stock(symbol: str = "DVN", score: float = 85.0, category: str = "Breakout Watch", role: str = "primary_candidate"):
    """Minimal ScoredStock-like object for snapshot creation tests."""
    from trading_bot.scoring.score_models import ScoredStock
    return ScoredStock(
        symbol=symbol,
        final_score=score,
        setup_category=category,
        universe_role=role,
        tags=["mid_cap"],
        name=symbol,
        sector="Energy",
        industry="Oil & Gas",
        demo_profile="",
        notes="",
        candidate_summary="Test candidate.",
        trend_score=80.0,
        momentum_score=75.0,
        volume_score=70.0,
        risk_score=80.0,
        setup_quality_score=85.0,
        latest_close=50.0,
        avg_volume_20=1_000_000.0,
        dollar_volume_20=50_000_000.0,
        return_5d=0.03,
        return_10d=0.05,
        return_20d=0.08,
        atr_14=1.5,
        atr_percent=0.03,
        volatility_20d=0.025,
        relative_volume=1.2,
        suggested_entry=50.0,
        suggested_stop=47.0,
        suggested_target_1=55.5,
        risk_reward_ratio=1.83,
        trade_plan_valid=True,
        trade_plan_status="valid",
        reasons=["Strong breakout setup."],
        warnings=[],
        scanned_at="2026-05-17T10:00:00+00:00",
    )


def _make_tony_analysis(symbol: str = "DVN", priority: str = PRI_HIGH, action: str = ACTION_SNAPSHOT) -> dict[str, Any]:
    """Minimal Tony analysis dict (as produced by CandidateAnalysis.to_dict() + version)."""
    return {
        "symbol": symbol,
        "priority_label": priority,
        "recommended_action": action,
        "setup_read": SETUP_BREAKOUT,
        "technical_read": f"{symbol} breakout candidate.",
        "volume_read": "volume_confirmation",
        "risk_read": RISK_ACCEPTABLE,
        "market_context_read": MKT_SUPPORTIVE,
        "data_quality_read": DQ_DEMO,
        "tony_hypothesis": f"{symbol} is approaching a potential breakout. Tony is analyzing, not trading.",
        "outcome_context": OC_NOT_ENOUGH,
        "reasons": ["Strong setup.", "Volume confirms."],
        "concerns": ["Demo data."],
        "tony_analysis_version": TONY_ANALYSIS_VERSION,
    }


def _snapshot_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "min_score": 60,
        "include_roles": ["primary_candidate", "speculative_candidate"],
        "include_categories": ["Breakout Watch", "Pullback Watch", "Momentum Continuation"],
        "exclude_categories": ["Weak / Avoid", "Overextended / Wait"],
        "include_benchmarks": False,
        "include_references": False,
        "allow_invalid_trade_plans": False,
        "dedupe_minutes": 0,
    }


# ── TestV13SchemaColumns ──────────────────────────────────────────────────────

class TestV13SchemaColumns:
    """Tony hypothesis fields exist in candidate_snapshots after init."""

    EXPECTED_TONY_COLUMNS = {
        "tony_priority_label",
        "tony_recommended_action",
        "tony_setup_read",
        "tony_volume_read",
        "tony_risk_read",
        "tony_market_context_read",
        "tony_data_quality_read",
        "tony_outcome_context",
        "tony_hypothesis",
        "tony_reasons_json",
        "tony_concerns_json",
        "tony_analysis_version",
    }

    def test_tony_columns_present(self, db: Path) -> None:
        with connect(db) as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(candidate_snapshots)").fetchall()}
        assert self.EXPECTED_TONY_COLUMNS.issubset(cols)

    def test_double_init_is_safe(self, tmp_path: Path) -> None:
        path = tmp_path / "db2.db"
        initialize_database(path)
        initialize_database(path)  # must not raise
        with connect(path) as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(candidate_snapshots)").fetchall()}
        assert self.EXPECTED_TONY_COLUMNS.issubset(cols)

    def test_all_expected_columns_present(self, db: Path) -> None:
        with connect(db) as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(candidate_snapshots)").fetchall()}
        for col in self.EXPECTED_TONY_COLUMNS:
            assert col in cols, f"Missing column: {col}"


# ── TestSnapshotWithTonyAnalysis ──────────────────────────────────────────────

class TestSnapshotWithTonyAnalysis:
    """Tony fields are stored when analysis is provided at snapshot creation time."""

    def test_tony_priority_label_stored(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis(priority=PRI_HIGH)
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        assert not snaps.empty
        assert snaps.iloc[0]["tony_priority_label"] == PRI_HIGH

    def test_tony_recommended_action_stored(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis(action=ACTION_SNAPSHOT)
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        assert snaps.iloc[0]["tony_recommended_action"] == ACTION_SNAPSHOT

    def test_tony_setup_read_stored(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        assert snaps.iloc[0]["tony_setup_read"] == SETUP_BREAKOUT

    def test_tony_analysis_version_stored(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        assert snaps.iloc[0]["tony_analysis_version"] == TONY_ANALYSIS_VERSION

    def test_tony_hypothesis_stored(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        assert "breakout" in str(snaps.iloc[0]["tony_hypothesis"]).lower()

    def test_tony_reasons_json_stored(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        raw = snaps.iloc[0]["tony_reasons_json"]
        assert raw is not None
        parsed = json.loads(raw)
        assert isinstance(parsed, list)
        assert len(parsed) > 0

    def test_tony_concerns_json_stored(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        raw = snaps.iloc[0]["tony_concerns_json"]
        assert raw is not None
        parsed = json.loads(raw)
        assert isinstance(parsed, list)

    def test_tony_risk_read_stored(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        assert snaps.iloc[0]["tony_risk_read"] == RISK_ACCEPTABLE

    def test_multiple_symbols_each_gets_their_analysis(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        dvn = _make_scored_stock("DVN", 85.0)
        dkng = _make_scored_stock("DKNG", 80.0)
        analyses = {
            "DVN": _make_tony_analysis("DVN", PRI_HIGH, ACTION_SNAPSHOT),
            "DKNG": _make_tony_analysis("DKNG", PRI_WATCH, ACTION_WATCH),
        }
        repo.create_candidate_snapshots(run_id, [dvn, dkng], _snapshot_config(), tony_analyses=analyses)
        snaps = repo.list_candidate_snapshots(limit=10)
        assert len(snaps) == 2
        by_symbol = {row["symbol"]: row for row in snaps.to_dict("records")}
        assert by_symbol["DVN"]["tony_priority_label"] == PRI_HIGH
        assert by_symbol["DKNG"]["tony_priority_label"] == PRI_WATCH


# ── TestSnapshotWithoutTonyAnalysis ───────────────────────────────────────────

class TestSnapshotWithoutTonyAnalysis:
    """Snapshots without Tony analysis have NULL Tony fields (legacy compatibility)."""

    def test_none_analyses_does_not_fail(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ids = repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses=None)
        assert len(ids) == 1

    def test_snapshot_without_analysis_tony_fields_null(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses=None)
        snaps = repo.list_candidate_snapshots(limit=10)
        row = snaps.iloc[0]
        assert row["tony_priority_label"] is None or str(row.get("tony_priority_label", "")) in ("", "None", "nan")
        assert row["tony_analysis_version"] is None or str(row.get("tony_analysis_version", "")) in ("", "None", "nan")

    def test_empty_tony_analyses_dict_does_not_fail(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ids = repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={})
        assert len(ids) == 1

    def test_symbol_not_in_analyses_gets_null_tony_fields(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock("DVN")
        # Analyses only contain DKNG, not DVN
        repo.create_candidate_snapshots(
            run_id, [stock], _snapshot_config(),
            tony_analyses={"DKNG": _make_tony_analysis("DKNG")},
        )
        snaps = repo.list_candidate_snapshots(limit=10)
        assert len(snaps) == 1
        assert snaps.iloc[0]["symbol"] == "DVN"
        val = snaps.iloc[0]["tony_priority_label"]
        assert val is None or str(val) in ("", "None", "nan")

    def test_existing_snapshots_core_fields_unaffected(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock("DVN", 85.0, "Breakout Watch")
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses=None)
        snaps = repo.list_candidate_snapshots(limit=10)
        row = snaps.iloc[0]
        assert row["symbol"] == "DVN"
        assert float(row["total_score"]) == 85.0
        assert row["setup_category"] == "Breakout Watch"
        assert row["status"] == "open/watch"


# ── TestTonyAnalysisVersion ───────────────────────────────────────────────────

class TestTonyAnalysisVersion:
    def test_version_constant_is_v1(self) -> None:
        assert TONY_ANALYSIS_VERSION == "v1"

    def test_version_stored_in_snapshot(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        assert ta["tony_analysis_version"] == "v1"
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        assert snaps.iloc[0]["tony_analysis_version"] == "v1"

    def test_version_is_string(self) -> None:
        assert isinstance(TONY_ANALYSIS_VERSION, str)

    def test_version_starts_with_v(self) -> None:
        assert TONY_ANALYSIS_VERSION.startswith("v")


# ── TestTonyOutcomeAnalyticsGroups ────────────────────────────────────────────

class TestTonyOutcomeAnalyticsGroups:
    """OutcomeAnalytics.grouped_by works on Tony fields when snapshots have analysis."""

    def _make_snapshots_df(self, with_tony: bool = True) -> Any:
        import pandas as pd
        rows = []
        for i, (symbol, priority, action, setup) in enumerate([
            ("DVN", PRI_HIGH, ACTION_SNAPSHOT, SETUP_BREAKOUT),
            ("DKNG", PRI_WATCH, ACTION_WATCH, SETUP_PULLBACK),
            ("OXY", PRI_HIGH, ACTION_SNAPSHOT, SETUP_BREAKOUT),
        ]):
            row: dict[str, Any] = {
                "id": i + 1,
                "symbol": symbol,
                "snapshot_time": "2026-05-17T10:00:00+00:00",
                "universe_role": "primary_candidate",
                "setup_category": "Breakout Watch",
                "total_score": 85.0,
                "close": 50.0,
                "entry": 50.0,
                "stop": 47.0,
                "target": 55.5,
                "risk_reward": 1.83,
                "trade_plan_valid": 1,
                "trade_plan_status": "valid",
                "status": "open/watch",
                "entry_triggered": 0,
                "outcome_label": "target_hit" if i == 0 else ("stop_hit" if i == 1 else None),
                "result_5d": 0.05 if i == 0 else -0.03,
                "notes": "",
                "tags_json": '["mid_cap"]',
                "warnings_json": "[]",
            }
            if with_tony:
                row["tony_priority_label"] = priority
                row["tony_recommended_action"] = action
                row["tony_setup_read"] = setup
                row["tony_risk_read"] = RISK_ACCEPTABLE
                row["tony_data_quality_read"] = DQ_ALPACA_IEX
                row["data_source"] = "real_alpaca"
                row["data_source_provider"] = "alpaca_iex"
                row["used_demo_data"] = 0
                row["used_fallback_data"] = 0
                row["tony_analysis_version"] = TONY_ANALYSIS_VERSION
            rows.append(row)
        return pd.DataFrame(rows)

    def test_grouped_by_tony_priority_label(self) -> None:
        df = self._make_snapshots_df(with_tony=True)
        analytics = OutcomeAnalytics(df, include_seeded_demo=False)
        result = analytics.grouped_by("tony_priority_label")
        assert not result.empty
        assert "tony_priority_label" in result.columns
        assert "total_snapshots" in result.columns

    def test_grouped_by_tony_recommended_action(self) -> None:
        df = self._make_snapshots_df(with_tony=True)
        analytics = OutcomeAnalytics(df, include_seeded_demo=False)
        result = analytics.grouped_by("tony_recommended_action")
        assert not result.empty
        assert "tony_recommended_action" in result.columns

    def test_grouped_by_tony_setup_read(self) -> None:
        df = self._make_snapshots_df(with_tony=True)
        analytics = OutcomeAnalytics(df, include_seeded_demo=False)
        result = analytics.grouped_by("tony_setup_read")
        assert not result.empty

    def test_grouped_by_nonexistent_column_returns_empty(self) -> None:
        df = self._make_snapshots_df(with_tony=False)
        analytics = OutcomeAnalytics(df, include_seeded_demo=False)
        result = analytics.grouped_by("tony_priority_label")
        assert result.empty

    def test_high_priority_rows_in_analytics(self) -> None:
        df = self._make_snapshots_df(with_tony=True)
        analytics = OutcomeAnalytics(df, include_seeded_demo=False)
        result = analytics.grouped_by("tony_priority_label")
        labels = list(result["tony_priority_label"])
        assert PRI_HIGH in labels

    def test_seeded_demo_excluded_from_tony_groups(self) -> None:
        import pandas as pd
        df = self._make_snapshots_df(with_tony=True)
        # Add a seeded demo row
        seeded_row = df.iloc[0].to_dict()
        seeded_row["notes"] = "Demo seeded snapshot for testing"
        seeded_row["id"] = 99
        df = pd.concat([df, pd.DataFrame([seeded_row])], ignore_index=True)
        analytics = OutcomeAnalytics(df, include_seeded_demo=False)
        prepared = analytics.prepared()
        # Seeded row should be excluded
        assert len(prepared) == len(df) - 1

    def test_total_snapshots_count_correct(self) -> None:
        df = self._make_snapshots_df(with_tony=True)
        analytics = OutcomeAnalytics(df, include_seeded_demo=False)
        result = analytics.grouped_by("tony_priority_label")
        total = int(result["total_snapshots"].sum())
        assert total == len(df)

    def test_grouped_by_tony_risk_read(self) -> None:
        df = self._make_snapshots_df(with_tony=True)
        analytics = OutcomeAnalytics(df, include_seeded_demo=False)
        result = analytics.grouped_by("tony_risk_read")
        assert not result.empty


# ── TestTonyLearningEvent ────────────────────────────────────────────────────

class TestTonyLearningEvent:
    """TonyStocksService.record_tony_learning_updated creates the expected event."""

    def test_tony_learning_event_created(self, repo: ScannerRepository) -> None:
        tony = TonyStocksService(repo, {"enabled": True, "create_events_for": ["tony_learning_updated"]})
        tony.start_cycle()
        event_id = tony.record_tony_learning_updated(snapshot_count=50, analyzed_count=30)
        assert event_id is not None
        events = repo.list_tony_events(limit=5)
        assert not events.empty
        assert "tony_learning_updated" in events["event_type"].values

    def test_tony_learning_event_message_has_early_tracking(self, repo: ScannerRepository) -> None:
        tony = TonyStocksService(repo, {"enabled": True, "create_events_for": ["tony_learning_updated"]})
        tony.start_cycle()
        tony.record_tony_learning_updated(snapshot_count=10, analyzed_count=5)
        events = repo.list_tony_events(limit=5)
        msg = events.iloc[0]["message"]
        assert "early tracking" in msg.lower() or "research mode" in msg.lower()

    def test_tony_learning_event_not_fired_when_disabled(self, repo: ScannerRepository) -> None:
        tony = TonyStocksService(repo, {"enabled": True, "create_events_for": []})
        tony.start_cycle()
        result = tony.record_tony_learning_updated(snapshot_count=10, analyzed_count=5)
        assert result is None

    def test_tony_learning_event_payload_has_counts(self, repo: ScannerRepository) -> None:
        tony = TonyStocksService(repo, {"enabled": True, "create_events_for": ["tony_learning_updated"]})
        tony.start_cycle()
        tony.record_tony_learning_updated(snapshot_count=20, analyzed_count=15, by_priority={"high_priority": 5})
        events = repo.list_tony_events(limit=5)
        payload = json.loads(events.iloc[0]["payload_json"])
        assert payload["snapshot_count"] == 20
        assert payload["analyzed_count"] == 15


# ── TestNoBrokerBehavior ──────────────────────────────────────────────────────

class TestNoBrokerBehavior:
    """Tony learning fields contain no broker terms; no orders or trades are created."""

    BROKER_TERMS = {"buy", "sell", "short", "cover", "order", "execute", "position", "broker", "live_trade", "paper_trade"}

    def test_tony_analysis_version_has_no_broker_terms(self) -> None:
        assert not (self.BROKER_TERMS & {TONY_ANALYSIS_VERSION.lower()})

    def test_allowed_actions_have_no_broker_terms(self) -> None:
        from trading_bot.tony.analysis import ALLOWED_ACTIONS
        for action in ALLOWED_ACTIONS:
            assert action.lower() not in self.BROKER_TERMS, f"Broker term found in action: {action}"

    def test_snapshot_with_tony_creates_no_paper_trades(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        picks = repo.manual_picks()
        paper = repo.paper_trades()
        assert len(picks) == 0
        assert len(paper) == 0

    def test_tony_hypothesis_field_has_no_order_language(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        snaps = repo.list_candidate_snapshots(limit=10)
        hypothesis = str(snaps.iloc[0]["tony_hypothesis"]).lower()
        for term in ("place order", "buy now", "sell now", "execute trade"):
            assert term not in hypothesis

    def test_tony_learning_event_has_no_broker_language(self, repo: ScannerRepository) -> None:
        tony = TonyStocksService(repo, {"enabled": True, "create_events_for": ["tony_learning_updated"]})
        tony.start_cycle()
        tony.record_tony_learning_updated(snapshot_count=5, analyzed_count=3)
        events = repo.list_tony_events(limit=5)
        msg = events.iloc[0]["message"].lower()
        for term in ("buy", "sell", "order", "execute"):
            assert term not in msg

    def test_create_candidate_snapshots_returns_ids_not_trades(self, repo: ScannerRepository) -> None:
        run_id = _make_scan_run(repo)
        stock = _make_scored_stock()
        ta = _make_tony_analysis()
        result = repo.create_candidate_snapshots(run_id, [stock], _snapshot_config(), tony_analyses={"DVN": ta})
        assert isinstance(result, list)
        assert all(isinstance(item, int) for item in result)
