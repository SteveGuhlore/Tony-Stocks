import pandas as pd

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


def create_snapshot(repo, result, outcome, triggered=1, result_5d=0.02, provider="alpaca_iex", data_source="real_alpaca"):
    run_id = repo.create_scan_run(1, provider, {"provider": provider})
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
        tony_analyses={
            result.symbol: {
                "data_quality_read": "daily_real_alpaca" if provider == "alpaca_iex" else "demo_data",
                "data_source": data_source,
                "data_source_provider": provider,
                "used_demo_data": provider == "demo_generated",
                "used_fallback_data": False,
                "real_data_only_run": provider == "alpaca_iex",
            }
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
    analytics_with_seeded = OutcomeAnalytics(
        snapshots_with_seeded,
        include_seeded_demo=True,
        real_only=False,
        include_demo=True,
    )
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


def test_snapshot_data_source_classification(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    real_id = create_snapshot(repo, stock("REAL"), "unreviewed", provider="alpaca_iex")
    demo_id = create_snapshot(
        repo,
        stock("DEMO", warnings=["Demo data only; do not use for real trade decisions."]),
        "unreviewed",
        provider="demo_generated",
        data_source="demo_generated",
    )
    missing_id = create_snapshot(
        repo,
        stock("MISS", warnings=["provider_missing"]),
        "unreviewed",
        provider="alpaca_iex",
        data_source="missing_real_data",
    )
    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET tony_data_quality_read = 'daily_real_alpaca' WHERE id = ?",
            (real_id,),
        )
        conn.execute("UPDATE candidate_snapshots SET scan_run_id = 9998, warnings_json = '[]', data_source = 'legacy_unknown' WHERE id = ?", (demo_id,))

    prepared = OutcomeAnalytics(
        repo.list_snapshots_for_analytics(include_seeded_demo=True),
        include_seeded_demo=True,
        real_only=False,
        include_legacy=True,
    ).prepared()
    classes = dict(zip(prepared["symbol"], prepared["data_source_classification"]))
    assert classes["REAL"] == "real_alpaca"
    assert classes["DEMO"] == "legacy_unknown"
    assert "MISS" not in classes


def test_real_only_excludes_demo_and_legacy_rows(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    real_id = create_snapshot(repo, stock("REAL"), "target_hit", provider="alpaca_iex")
    create_snapshot(
        repo,
        stock("DEMO", warnings=["Demo data only; do not use for real trade decisions."]),
        "target_hit",
        provider="demo_generated",
        data_source="demo_generated",
    )
    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET tony_data_quality_read = 'daily_real_alpaca' WHERE id = ?",
            (real_id,),
        )

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(include_seeded_demo=True), include_seeded_demo=True, real_only=True)
    prepared = analytics.prepared()
    assert list(prepared["symbol"]) == ["REAL"]


def test_today_and_provider_filters(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    real_id = create_snapshot(repo, stock("TODAY"), "target_hit", provider="alpaca_iex")
    old_id = create_snapshot(repo, stock("OLD"), "target_hit", provider="alpaca_iex")
    create_snapshot(repo, stock("DEMO"), "target_hit", provider="demo_generated", data_source="demo_generated")
    today = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    with connect(repo.database_path) as conn:
        conn.execute("UPDATE candidate_snapshots SET snapshot_time = ? WHERE id = ?", (f"{today}T12:00:00+00:00", real_id))
        conn.execute("UPDATE candidate_snapshots SET snapshot_time = ? WHERE id = ?", ("2026-01-01T12:00:00+00:00", old_id))

    analytics = OutcomeAnalytics(
        repo.list_snapshots_for_analytics(include_seeded_demo=True),
        include_seeded_demo=True,
        today=True,
        provider="alpaca_iex",
    )
    assert list(analytics.prepared()["symbol"]) == ["TODAY"]
