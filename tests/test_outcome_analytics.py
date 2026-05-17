from trading_bot.analytics import OutcomeAnalytics, score_bucket
from trading_bot.scoring.score_models import ScoredStock
from trading_bot.storage.database import connect
from trading_bot.storage.repositories import ScannerRepository


def stock(symbol="TEST", score=80, category="Breakout Watch", role="primary_candidate", warnings=None):
    return ScoredStock(
        symbol=symbol,
        scanned_at="2026-05-17T00:00:00+00:00",
        final_score=score,
        setup_category=category,
        tags=["mid_cap", "watchlist"],
        universe_role=role,
        name=symbol,
        sector="technology",
        industry="software",
        demo_profile="clean_breakout",
        notes="",
        candidate_summary="Test candidate.",
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
        warnings=warnings or [],
    )


def create_snapshot(repo, result, outcome, triggered=1, result_5d=0.02):
    run_id = repo.create_scan_run(1, "demo_generated", {"provider": "demo_generated"})
    ids = repo.create_candidate_snapshots(
        run_id,
        [result],
        {
            "enabled": True,
            "min_score": 0,
            "include_roles": [result.universe_role],
            "include_categories": [result.setup_category],
            "dedupe_minutes": 0,
        },
    )
    repo.update_candidate_snapshot_followup(
        ids[0],
        entry_triggered=triggered,
        last_checked_at="2026-05-18T00:00:00+00:00",
        outcome_label=outcome,
        result_eod=0.01,
        result_3d=0.015,
        result_5d=result_5d,
    )
    return ids[0]


def test_score_bucket_assignment():
    assert score_bucket(95) == "90-100"
    assert score_bucket(85) == "80-89"
    assert score_bucket(75) == "70-79"
    assert score_bucket(65) == "60-69"
    assert score_bucket(10) == "below 60"


def test_outcome_analytics_excludes_seeded_demo_by_default(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    create_snapshot(repo, stock("REAL", 91), "target_hit")
    run_id = repo.create_scan_run(1, "demo_generated_demo_seed", {"testing_only": True})
    repo.create_demo_candidate_snapshot(
        {
            "scan_run_id": run_id,
            "symbol": "SEED",
            "snapshot_time": "2026-05-01T00:00:00",
            "universe_role": "primary_candidate",
            "tags": ["demo_seeded", "outcome_fixture"],
            "setup_category": "Demo Outcome Fixture",
            "total_score": 70,
            "close": 100,
            "entry": 100,
            "stop": 95,
            "target": 110,
            "risk_reward": 2,
            "notes": "Demo seeded snapshot test - expected target_hit.",
        },
        dedupe=False,
    )

    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=False)
    analytics = OutcomeAnalytics(snapshots)

    assert len(analytics.prepared()) == 1
    assert analytics.prepared().iloc[0]["symbol"] == "REAL"

    snapshots_with_seeded = repo.list_snapshots_for_analytics(include_seeded_demo=True)
    analytics_with_seeded = OutcomeAnalytics(snapshots_with_seeded, include_seeded_demo=True)
    assert len(analytics_with_seeded.prepared()) == 2
    assert analytics_with_seeded.prepared()["is_seeded_demo"].sum() == 1


def test_grouping_by_setup_role_and_score_bucket(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    create_snapshot(repo, stock("BO", 94, "Breakout Watch", "primary_candidate"), "target_hit")
    create_snapshot(repo, stock("PB", 82, "Pullback Watch", "primary_candidate"), "stop_hit", result_5d=-0.03)
    create_snapshot(repo, stock("SP", 72, "Speculative Watchlist", "speculative_candidate"), "partial_move")
    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics())

    by_setup = analytics.grouped_by("setup_category")
    assert set(by_setup["setup_category"]) == {"Breakout Watch", "Pullback Watch", "Speculative Watchlist"}
    assert float(by_setup[by_setup["setup_category"] == "Breakout Watch"].iloc[0]["target_hit_rate"]) == 1.0

    by_role = analytics.grouped_by("universe_role")
    assert set(by_role["universe_role"]) == {"primary_candidate", "speculative_candidate"}

    by_bucket = analytics.grouped_by("score_bucket")
    assert {"90-100", "80-89", "70-79"}.issubset(set(by_bucket["score_bucket"]))


def test_rates_handle_zero_denominators(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    create_snapshot(repo, stock("NEW", 80), "insufficient_future_data", triggered=0, result_5d=None)
    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics())
    row = analytics.grouped_by("setup_category").iloc[0]
    assert row["target_hit_rate"] == 0
    assert row["failure_rate"] == 0


def test_warning_parsing_handles_missing_or_invalid_json(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    snapshot_id = create_snapshot(repo, stock("WARN", 80, warnings=["ATR risk is wide"]), "failed_setup")
    with connect(repo.database_path) as conn:
        conn.execute("UPDATE candidate_snapshots SET warnings_json = ? WHERE id = ?", ("not-json", snapshot_id))

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics())
    warnings = analytics.warning_type_summary()
    assert not warnings.empty
    assert "No warning" in set(warnings["warning_type"])
