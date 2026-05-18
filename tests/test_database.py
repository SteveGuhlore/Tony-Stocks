from trading_bot.scoring.score_models import ScoredStock
from trading_bot.storage.database import connect
from trading_bot.storage.repositories import ScannerRepository


def sample_scored_stock(symbol: str = "AAPL") -> ScoredStock:
    return ScoredStock(
        symbol=symbol,
        scanned_at="2026-05-17T00:00:00+00:00",
        final_score=80,
        setup_category="Breakout Watch",
        tags=["tech"],
        universe_role="primary_candidate",
        name="Apple",
        sector="technology",
        industry="hardware",
        demo_profile="clean_breakout",
        notes="test note",
        candidate_summary="Primary candidate worth manual review.",
        trend_score=80,
        momentum_score=80,
        volume_score=80,
        risk_score=80,
        setup_quality_score=80,
        latest_close=100,
        avg_volume_20=1000000,
        dollar_volume_20=100000000,
        return_5d=0.01,
        return_10d=0.02,
        return_20d=0.05,
        atr_14=2,
        atr_percent=0.02,
        volatility_20d=0.02,
        relative_volume=1.3,
        suggested_entry=100,
        suggested_stop=95,
        suggested_target_1=110,
        risk_reward_ratio=2,
        trade_plan_valid=True,
        trade_plan_status="valid",
        reasons=["test"],
        warnings=[],
    )


def test_database_saves_scan_results(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    run_id = repo.create_scan_run(1, "demo_generated", {"provider": "demo_generated"})
    repo.save_scan_results(run_id, [sample_scored_stock()])
    latest = repo.latest_scan_results()
    assert len(latest) == 1
    assert latest.iloc[0]["symbol"] == "AAPL"
    assert latest.iloc[0]["setup_category"] == "Breakout Watch"
    assert latest.iloc[0]["universe_role"] == "primary_candidate"
    assert latest.iloc[0]["relative_volume"] == 1.3
    assert latest.iloc[0]["trade_plan_valid"] == 1
    assert latest.iloc[0]["trade_plan_status"] == "valid"


def test_candidate_snapshot_table_exists(tmp_path):
    db = tmp_path / "scanner.db"
    ScannerRepository(db)
    with connect(db) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(candidate_snapshots)").fetchall()}
    assert {"symbol", "snapshot_time", "total_score", "entry_triggered", "result_5d", "outcome_label", "trade_plan_valid"}.issubset(columns)
    assert {
        "tony_intraday_read",
        "intraday_timeframe",
        "intraday_close",
        "intraday_vwap",
        "intraday_above_vwap",
        "intraday_day_change_percent",
        "intraday_relative_volume",
        "intraday_opening_range_status",
    }.issubset(columns)
    assert {
        "data_source",
        "data_source_provider",
        "used_demo_data",
        "used_fallback_data",
        "real_data_only_run",
        "missing_real_data_reason",
    }.issubset(columns)
    assert {
        "snapshot_price",
        "snapshot_bar_time",
        "planned_entry_price",
        "planned_entry_rule",
        "planned_entry_buffer_pct",
        "actual_entry_price",
        "actual_entry_time",
        "entry_status",
        "entry_trigger_source",
        "entry_trigger_timeframe",
        "entry_trigger_notes",
    }.issubset(columns)


def test_tony_event_table_exists(tmp_path):
    db = tmp_path / "scanner.db"
    ScannerRepository(db)
    with connect(db) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tony_events)").fetchall()}
    assert {
        "created_at",
        "event_type",
        "severity",
        "symbol",
        "title",
        "message",
        "payload_json",
        "acknowledged",
        "dismissed",
    }.issubset(columns)


def test_create_and_list_tony_events_with_filters(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    repo.create_tony_event(
        event_type="high_score_candidate",
        severity="watch",
        symbol="PLTR",
        title="Tony Stocks: PLTR high-score candidate",
        message="PLTR entered Breakout Watch with score 92.",
        payload={"score": 92},
    )
    repo.create_tony_event(
        event_type="warning_summary",
        severity="warning",
        title="Tony Stocks: Scan warnings",
        message="Warnings require review.",
        payload={"warnings_count": 3},
    )

    latest = repo.list_tony_events(limit=10)
    assert len(latest) == 2
    warnings = repo.list_tony_events(limit=10, severity="warning")
    assert len(warnings) == 1
    assert warnings.iloc[0]["event_type"] == "warning_summary"
    symbol_events = repo.list_tony_events(limit=10, symbol="PLTR")
    assert len(symbol_events) == 1
    assert symbol_events.iloc[0]["severity"] == "watch"
    assert repo.count_tony_events(event_type="high_score_candidate") == 1


def test_create_and_list_candidate_snapshots(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    run_id = repo.create_scan_run(1, "demo_generated", {"provider": "demo_generated"})
    created = repo.create_candidate_snapshots(
        run_id,
        [sample_scored_stock()],
        {
            "enabled": True,
            "min_score": 60,
            "include_roles": ["primary_candidate"],
            "include_categories": ["Breakout Watch"],
            "exclude_categories": ["Weak / Avoid"],
            "dedupe_minutes": 60,
        },
    )
    assert len(created) == 1
    snapshots = repo.list_candidate_snapshots(status="open/watch", setup_category="Breakout Watch", universe_role="primary_candidate")
    assert len(snapshots) == 1
    assert snapshots.iloc[0]["symbol"] == "AAPL"
    assert snapshots.iloc[0]["trade_plan_valid"] == 1
    assert snapshots.iloc[0]["tony_intraday_read"] is None
    assert snapshots.iloc[0]["intraday_vwap"] is None
    assert repo.count_open_candidate_snapshots() == 1
    assert repo.count_triggered_candidate_snapshots() == 0
    assert repo.count_candidate_snapshots_by_category().iloc[0]["setup_category"] == "Breakout Watch"


def test_candidate_snapshot_dedupe_window(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    run_id = repo.create_scan_run(1, "demo_generated", {"provider": "demo_generated"})
    config = {
        "enabled": True,
        "min_score": 60,
        "include_roles": ["primary_candidate"],
        "include_categories": ["Breakout Watch"],
        "dedupe_minutes": 60,
    }
    assert len(repo.create_candidate_snapshots(run_id, [sample_scored_stock()], config)) == 1
    assert len(repo.create_candidate_snapshots(run_id, [sample_scored_stock()], config)) == 0


def test_candidate_snapshots_exclude_invalid_trade_plans_by_default(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    run_id = repo.create_scan_run(1, "demo_generated", {"provider": "demo_generated"})
    invalid = sample_scored_stock("BAD")
    invalid = ScoredStock(
        **{
            **invalid.to_dict(),
            "trade_plan_valid": False,
            "trade_plan_status": "invalid_target",
            "setup_category": "Invalid Trade Plan",
            "warnings": ["Invalid long trade plan: target is not above entry."],
        }
    )
    config = {
        "enabled": True,
        "min_score": 0,
        "include_roles": ["primary_candidate"],
        "include_categories": ["Invalid Trade Plan"],
        "allow_invalid_trade_plans": False,
    }
    assert repo.create_candidate_snapshots(run_id, [invalid], config) == []


def test_candidate_snapshot_followup_update_fields(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    run_id = repo.create_scan_run(1, "demo_generated", {"provider": "demo_generated"})
    created = repo.create_candidate_snapshots(
        run_id,
        [sample_scored_stock()],
        {
            "enabled": True,
            "min_score": 60,
            "include_roles": ["primary_candidate"],
            "include_categories": ["Breakout Watch"],
        },
    )
    snapshot_id = created[0]
    open_snapshots = repo.list_open_candidate_snapshots()
    assert len(open_snapshots) == 1
    repo.update_candidate_snapshot_followup(
        snapshot_id,
        entry_triggered=1,
        entry_triggered_at="2026-05-18T00:00:00",
        highest_price_seen=112,
        lowest_price_seen=98,
        last_checked_at="2026-05-19T00:00:00+00:00",
        result_eod=0.02,
        result_3d=0.05,
        outcome_label="target_before_stop",
    )
    updated = repo.latest_candidate_snapshots()
    assert updated.iloc[0]["entry_triggered"] == 1
    assert updated.iloc[0]["highest_price_seen"] == 112
    assert updated.iloc[0]["lowest_price_seen"] == 98
    assert updated.iloc[0]["outcome_label"] == "target_before_stop"
    assert repo.count_candidate_snapshots_by_outcome().iloc[0]["outcome_label"] == "target_before_stop"


def test_candidate_snapshot_stores_optional_intraday_tony_fields(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    run_id = repo.create_scan_run(1, "alpaca_iex", {"provider": "alpaca_iex"})
    created = repo.create_candidate_snapshots(
        run_id,
        [sample_scored_stock("PLTR")],
        {
            "enabled": True,
            "min_score": 60,
            "include_roles": ["primary_candidate"],
            "include_categories": ["Breakout Watch"],
        },
        tony_analyses={
            "PLTR": {
                "priority_label": "high_priority",
                "recommended_action": "snapshot_only",
                "setup_read": "breakout_candidate",
                "volume_read": "volume_confirmation",
                "risk_read": "acceptable_risk",
                "market_context_read": "market_supportive",
                "data_quality_read": "daily_real_alpaca",
                "outcome_context": "not_enough_history",
                "tony_hypothesis": "PLTR intraday context stored. Tony is analyzing, not trading.",
                "reasons": ["above VWAP"],
                "concerns": [],
                "tony_analysis_version": "v1",
                "intraday_read": "above_vwap",
                "intraday_timeframe": "5Min",
                "intraday_close": 101.5,
                "intraday_vwap": 100.25,
                "intraday_above_vwap": True,
                "intraday_day_change_percent": 0.015,
                "intraday_relative_volume": 1.2,
                "intraday_opening_range_status": "opening_range_breakout_watch",
            }
        },
    )
    assert len(created) == 1
    row = repo.latest_candidate_snapshots().iloc[0]
    assert row["tony_intraday_read"] == "above_vwap"
    assert row["intraday_timeframe"] == "5Min"
    assert row["intraday_above_vwap"] == 1
    assert row["intraday_opening_range_status"] == "opening_range_breakout_watch"
    assert row["data_source"] is None


def test_snapshots_for_analytics_include_nullable_provider_context(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    run_id = repo.create_scan_run(1, "alpaca_iex", {"provider": "alpaca_iex"})
    repo.create_candidate_snapshots(
        run_id,
        [sample_scored_stock("PLTR")],
        {
            "enabled": True,
            "min_score": 60,
            "include_roles": ["primary_candidate"],
            "include_categories": ["Breakout Watch"],
        },
    )

    rows = repo.list_snapshots_for_analytics(include_seeded_demo=True)
    assert rows.iloc[0]["snapshot_provider"] == "alpaca_iex"
    assert "data_source" in rows.columns
    assert "scan_created_at" in rows.columns
