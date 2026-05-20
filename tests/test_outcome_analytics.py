import pandas as pd
from types import SimpleNamespace

import trading_bot.cli as cli
from trading_bot.analytics import (
    OutcomeAnalytics,
    build_daily_tony_memory_summary,
    build_tony_self_review,
    generate_tony_rule_suggestions,
    market_date_mask,
    new_york_market_date,
    score_bucket,
)
from trading_bot.dashboard.helpers import summarize_product_reconciliation
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
    market_date = "2026-05-19"
    with connect(repo.database_path) as conn:
        conn.execute("UPDATE candidate_snapshots SET snapshot_time = ? WHERE id = ?", ("2026-05-20T01:00:00+00:00", real_id))
        conn.execute("UPDATE candidate_snapshots SET snapshot_time = ? WHERE id = ?", ("2026-05-20T05:30:00+00:00", old_id))

    original = OutcomeAnalytics.prepared.__globals__["new_york_market_date"]
    OutcomeAnalytics.prepared.__globals__["new_york_market_date"] = lambda now=None: market_date
    try:
        analytics = OutcomeAnalytics(
            repo.list_snapshots_for_analytics(include_seeded_demo=True),
            include_seeded_demo=True,
            today=True,
            provider="alpaca_iex",
        )
        assert list(analytics.prepared()["symbol"]) == ["TODAY"]
    finally:
        OutcomeAnalytics.prepared.__globals__["new_york_market_date"] = original


def test_new_york_market_date_uses_et_boundary():
    assert new_york_market_date(pd.Timestamp("2026-05-20T01:30:00+00:00")) == "2026-05-19"
    assert market_date_mask(pd.Series(["2026-05-20T01:30:00+00:00", "2026-05-20T05:30:00+00:00"]), "2026-05-19").tolist() == [True, False]


def test_run_eod_report_defaults_to_new_york_market_date_and_matches_memory(tmp_path, monkeypatch, capsys):
    repo = ScannerRepository(tmp_path / "analytics.db")
    snapshot_id = create_snapshot(repo, stock("ETDAY", 88, "Breakout Watch"), "still_open", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET snapshot_time = '2026-05-20T01:15:00+00:00',
                last_checked_at = '2026-05-20T02:00:00+00:00',
                entry_status = 'triggered',
                actual_entry_price = 100.0,
                actual_entry_time = '2026-05-20T01:20:00+00:00',
                target = 108.0,
                stop = 96.0,
                current_price = 101.0,
                tracking_status = 'active',
                reassessment_label = 'still_valid'
            WHERE id = ?
            """,
            (snapshot_id,),
        )

    class DummyTony:
        def __init__(self, repo, config):
            self.repo = repo
            self.config = config

        def start_cycle(self):
            return None

        def record_tony_learning_updated(self, **kwargs):
            return None

    monkeypatch.setattr(
        cli,
        "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path,
            provider="alpaca_iex",
            tony_stocks=SimpleNamespace(),
            symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", DummyTony)
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    result = cli.run_eod_report(SimpleNamespace(config="ignored", date=None))
    output = capsys.readouterr().out

    assert result["date"] == "2026-05-19"
    assert result["tony_memory_summary"]["report_date"] == "2026-05-19"
    assert result["real_only_snapshots_reviewed"] == 1
    assert "Report date: 2026-05-19 America/New_York" in output


def test_run_eod_report_date_override_uses_explicit_market_date(tmp_path, monkeypatch):
    repo = ScannerRepository(tmp_path / "analytics.db")
    snapshot_id = create_snapshot(repo, stock("OVRD", 84, "Pullback Watch"), "target_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET snapshot_time = '2026-05-19T02:30:00+00:00' WHERE id = ?",
            (snapshot_id,),
        )

    class DummyTony:
        def __init__(self, repo, config):
            pass

        def start_cycle(self):
            return None

        def record_tony_learning_updated(self, **kwargs):
            return None

    monkeypatch.setattr(
        cli,
        "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path,
            provider="alpaca_iex",
            tony_stocks=SimpleNamespace(),
            symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", DummyTony)
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-20")

    analytics = OutcomeAnalytics(
        repo.list_snapshots_for_analytics(include_seeded_demo=True),
        include_seeded_demo=True,
        real_only=True,
    )
    assert analytics.daily_tony_memory_summary(report_date="2026-05-18")["report_date"] == "2026-05-18"

    result = cli.run_eod_report(SimpleNamespace(config="ignored", date="2026-05-18"))
    assert result["date"] == "2026-05-18"
    assert result["tony_memory_summary"]["report_date"] == "2026-05-18"


def test_classified_snapshots_and_reconciliation_distinguish_raw_vs_product(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    first = create_snapshot(repo, stock("ARM", 88, "Breakout Watch"), "still_open", provider="alpaca_iex")
    second = create_snapshot(repo, stock("ARM", 89, "Breakout Watch"), "still_open", provider="alpaca_iex")
    waiting = create_snapshot(repo, stock("DKNG", 84, "Breakout Watch"), "unreviewed", triggered=0, provider="alpaca_iex")
    closed = create_snapshot(repo, stock("OXY", 82, "Pullback Watch"), "target_hit", provider="alpaca_iex")
    create_snapshot(
        repo,
        stock("DEMO", 75, "Speculative Watchlist"),
        "unreviewed",
        triggered=0,
        provider="demo_generated",
        data_source="demo_generated",
    )
    create_snapshot(
        repo,
        stock("MISS", 70, "Pullback Watch", warnings=["provider_missing"]),
        "unreviewed",
        triggered=0,
        provider="alpaca_iex",
        data_source="missing_real_data",
    )
    with connect(repo.database_path) as conn:
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'triggered',
                actual_entry_price = 120.0,
                actual_entry_time = '2026-05-19T14:05:00+00:00',
                target = 128.0,
                stop = 116.0,
                current_price = 125.0,
                tracking_status = 'active'
            WHERE id = ?
            """,
            (first,),
        )
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'triggered',
                actual_entry_price = 124.0,
                actual_entry_time = '2026-05-19T15:05:00+00:00',
                target = 130.0,
                stop = 118.0,
                current_price = 126.5,
                tracking_status = 'active'
            WHERE id = ?
            """,
            (second,),
        )
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'pending',
                planned_entry_price = 41.5,
                target = 45.0,
                stop = 39.5,
                current_price = 40.9
            WHERE id = ?
            """,
            (waiting,),
        )
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'triggered',
                planned_entry_price = 48.0,
                actual_entry_price = 48.2,
                actual_entry_time = '2026-05-19T15:10:00+00:00',
                target = 52.0,
                stop = 46.0,
                close = 52.0,
                tracking_status = 'closed'
            WHERE id = ?
            """,
            (closed,),
        )

    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True)
    analytics = OutcomeAnalytics(snapshots, include_seeded_demo=True, real_only=False, include_demo=True, include_legacy=True)
    classified = analytics.classified_snapshots()
    assert set(classified["data_source_classification"]) >= {"real_alpaca", "demo_generated", "missing_real_data"}

    prepared = OutcomeAnalytics(
        snapshots,
        include_seeded_demo=True,
        real_only=True,
        include_demo=False,
        include_legacy=False,
    ).prepared()
    reconciliation = summarize_product_reconciliation(prepared)
    assert reconciliation["raw_snapshot_rows"] == 4
    assert reconciliation["raw_triggered_entry_rows"] == 3
    assert reconciliation["product_visible_symbols"] == 3
    assert reconciliation["deduped_active_positions"] == 1
    assert reconciliation["deduped_waiting_picks"] == 1
    assert reconciliation["deduped_closed_results"] == 1
    assert reconciliation["target_hits"] == 1
    assert reconciliation["pending_triggers"] == 1
    assert reconciliation["history_rows_hidden_from_product_views"] == 1


def test_reconciliation_counts_incomplete_hidden_rows_without_deleting_history(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    valid = create_snapshot(repo, stock("OXY", 82, "Pullback Watch"), "still_open", provider="alpaca_iex")
    invalid = create_snapshot(repo, stock("JOBY", 71, "Momentum Continuation"), "still_open", provider="alpaca_iex")

    with connect(repo.database_path) as conn:
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'triggered',
                actual_entry_price = 48.0,
                actual_entry_time = '2026-05-19T14:05:00+00:00',
                target = 52.0,
                stop = 46.0,
                current_price = 49.0,
                tracking_status = 'active'
            WHERE id = ?
            """,
            (valid,),
        )
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'triggered',
                actual_entry_price = NULL,
                actual_entry_time = NULL,
                target = 8.0,
                stop = 6.5,
                tracking_status = 'active'
            WHERE id = ?
            """,
            (invalid,),
        )

    snapshots_before = repo.list_snapshots_for_analytics(include_seeded_demo=True)
    prepared = OutcomeAnalytics(snapshots_before, include_seeded_demo=True, real_only=True).prepared()
    before_count = len(snapshots_before)
    reconciliation = summarize_product_reconciliation(prepared)
    snapshots_after = repo.list_snapshots_for_analytics(include_seeded_demo=True)

    assert reconciliation["raw_snapshot_rows"] == 2
    assert reconciliation["deduped_active_positions"] == 1
    assert reconciliation["incomplete_rows_hidden_from_product_views"] == 1
    assert len(snapshots_after) == before_count
    assert set(snapshots_after["symbol"]) == {"OXY", "JOBY"}


def test_daily_tony_memory_summary_counts_real_only_rows(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    closed = create_snapshot(repo, stock("ARM", 90, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    active = create_snapshot(repo, stock("OXY", 82, "Pullback Watch"), "still_open", provider="alpaca_iex")
    create_snapshot(
        repo,
        stock("DEMO", 75, "Speculative Watchlist"),
        "target_hit",
        provider="demo_generated",
        data_source="demo_generated",
    )

    with connect(repo.database_path) as conn:
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'triggered',
                actual_entry_price = 120.0,
                actual_entry_time = '2026-05-19T14:05:00+00:00',
                target = 128.0,
                stop = 116.0,
                tracking_status = 'closed',
                reassessment_label = 'still_valid'
            WHERE id = ?
            """,
            (closed,),
        )
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'triggered',
                actual_entry_price = 48.0,
                actual_entry_time = '2026-05-19T15:05:00+00:00',
                target = 52.0,
                stop = 46.0,
                current_price = 49.0,
                tracking_status = 'active',
                reassessment_label = 'weakening'
            WHERE id = ?
            """,
            (active,),
        )

    analytics = OutcomeAnalytics(
        repo.list_snapshots_for_analytics(include_seeded_demo=True),
        include_seeded_demo=True,
        real_only=True,
    )
    memory = analytics.daily_tony_memory_summary(
        report_date="2026-05-19",
        reconciliation={
            "deduped_active_positions": 1,
            "deduped_closed_results": 1,
            "target_hits": 1,
            "stop_hits": 0,
            "partial_moves": 0,
            "history_rows_hidden_from_product_views": 0,
            "incomplete_rows_hidden_from_product_views": 0,
        },
        exclusions=analytics.exclusion_counts(),
    )

    assert memory["report_date"] == "2026-05-19"
    assert memory["row_count"] == 2
    assert memory["setup_counts"] == {"Breakout Watch": 1, "Pullback Watch": 1}
    assert memory["triggered_count"] == 2
    assert memory["active_count"] == 1
    assert memory["closed_count"] == 1
    assert memory["target_hit_count"] == 1
    assert memory["stop_hit_count"] == 0
    assert memory["partial_move_count"] == 0
    assert memory["reassessment_label_counts"] == {"still_valid": 1, "weakening": 1}
    assert "Breakout Watch" in memory["best_setup_note"]
    assert "Pullback Watch" in memory["worst_setup_note"]
    assert any("research-only" in note.lower() for note in memory["data_quality_notes"])
    assert any("demo row(s) were excluded" in note for note in memory["data_quality_notes"])


def test_daily_tony_memory_summary_filters_demo_and_legacy_rows(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    create_snapshot(repo, stock("REAL", 88, "Breakout Watch"), "still_open", provider="alpaca_iex")
    create_snapshot(
        repo,
        stock("DEMO", 75, "Speculative Watchlist"),
        "target_hit",
        provider="demo_generated",
        data_source="demo_generated",
    )
    legacy_id = create_snapshot(repo, stock("LEG", 70, "Momentum Continuation"), "stop_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute("UPDATE candidate_snapshots SET data_source = 'legacy_unknown' WHERE id = ?", (legacy_id,))

    analytics = OutcomeAnalytics(
        repo.list_snapshots_for_analytics(include_seeded_demo=True),
        include_seeded_demo=True,
        real_only=True,
    )
    memory = build_daily_tony_memory_summary(analytics.prepared(), exclusions=analytics.exclusion_counts())

    assert memory["row_count"] == 1
    assert memory["setup_counts"] == {"Breakout Watch": 1}
    assert memory["triggered_count"] == 1
    assert "DEMO" not in str(memory)
    assert "LEG" not in str(memory)


def test_daily_tony_memory_summary_preserves_raw_history_notes(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    first = create_snapshot(repo, stock("ARM", 88, "Breakout Watch"), "still_open", provider="alpaca_iex")
    second = create_snapshot(repo, stock("ARM", 89, "Breakout Watch"), "still_open", provider="alpaca_iex")

    with connect(repo.database_path) as conn:
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'triggered',
                actual_entry_price = 120.0,
                actual_entry_time = '2026-05-19T14:05:00+00:00',
                target = 128.0,
                stop = 116.0,
                current_price = 125.0,
                tracking_status = 'active',
                reassessment_label = 'still_valid'
            WHERE id = ?
            """,
            (first,),
        )
        conn.execute(
            """
            UPDATE candidate_snapshots
            SET entry_status = 'triggered',
                actual_entry_price = 124.0,
                actual_entry_time = '2026-05-19T15:05:00+00:00',
                target = 130.0,
                stop = 118.0,
                current_price = 126.5,
                tracking_status = 'active',
                reassessment_label = 'needs_review'
            WHERE id = ?
            """,
            (second,),
        )

    analytics = OutcomeAnalytics(
        repo.list_snapshots_for_analytics(include_seeded_demo=True),
        include_seeded_demo=True,
        real_only=True,
    )
    reconciliation = summarize_product_reconciliation(analytics.prepared())
    memory = analytics.daily_tony_memory_summary(
        report_date="2026-05-19",
        reconciliation=reconciliation,
        exclusions=analytics.exclusion_counts(),
    )
    snapshots_after = repo.list_snapshots_for_analytics(include_seeded_demo=True)

    assert memory["row_count"] == 2
    assert memory["active_count"] == 1
    assert memory["triggered_count"] == 2
    assert memory["reassessment_label_counts"] == {"needs_review": 1, "still_valid": 1}
    assert any("hidden from current product views" in note for note in memory["data_quality_notes"])
    assert len(snapshots_after) == 2


def test_tony_self_review_from_sample_rows(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    closed = create_snapshot(repo, stock("ARM", 90, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    stopped = create_snapshot(repo, stock("OXY", 82, "Pullback Watch"), "stop_hit", result_5d=-0.03, provider="alpaca_iex")
    active = create_snapshot(repo, stock("DKNG", 84, "Momentum Continuation"), "still_open", provider="alpaca_iex")

    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET entry_status='triggered', actual_entry_price=120.0, tracking_status='closed', reassessment_label='still_valid' WHERE id=?",
            (closed,),
        )
        conn.execute(
            "UPDATE candidate_snapshots SET entry_status='triggered', actual_entry_price=48.0, tracking_status='closed', reassessment_label='weakening' WHERE id=?",
            (stopped,),
        )
        conn.execute(
            "UPDATE candidate_snapshots SET entry_status='triggered', actual_entry_price=41.0, current_price=42.0, tracking_status='active', reassessment_label='needs_review' WHERE id=?",
            (active,),
        )

    analytics = OutcomeAnalytics(
        repo.list_snapshots_for_analytics(include_seeded_demo=True),
        include_seeded_demo=True,
        real_only=True,
    )
    prepared = analytics.prepared()
    reconciliation = summarize_product_reconciliation(prepared)
    memory = analytics.daily_tony_memory_summary(report_date="2026-05-19", reconciliation=reconciliation)
    review = build_tony_self_review(prepared, memory, reconciliation=reconciliation)

    assert review["research_only"] is True
    assert "Breakout Watch" in review["strongest_setup"]
    assert any("Breakout Watch" in item for item in review["what_worked"])
    assert any("Pullback Watch" in item for item in review["what_failed"])
    assert any("needs_review" in item or "Momentum Continuation" in item for item in review["needs_more_data"])
    assert any("active position" in item for item in review["tomorrow_watch"])
    assert any("weakening" in item for item in review["tomorrow_watch"])


def test_tony_self_review_empty_day_fallback():
    empty_df = pd.DataFrame()
    memory = {
        "best_setup_note": "No real-only setup groups were available for Tony memory today.",
        "worst_setup_note": "No real-only setup groups were available for Tony memory today.",
        "active_count": 0,
        "reassessment_label_counts": {},
    }
    review = build_tony_self_review(empty_df, memory)

    assert review["research_only"] is True
    assert "No real-only rows" in review["strongest_setup"]
    assert review["what_worked"] == ["No real-only rows were available today."]
    assert review["what_failed"] == ["No real-only rows were available today."]
    assert "real data" in review["needs_more_data"][0]
    assert "tomorrow" in review["tomorrow_watch"][0].lower() or "No specific" in review["tomorrow_watch"][0]


def test_tony_self_review_real_only_filtering(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    create_snapshot(repo, stock("REAL", 88, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    create_snapshot(
        repo,
        stock("DEMO", 75, "Speculative Watchlist"),
        "target_hit",
        provider="demo_generated",
        data_source="demo_generated",
    )

    analytics = OutcomeAnalytics(
        repo.list_snapshots_for_analytics(include_seeded_demo=True),
        include_seeded_demo=True,
        real_only=True,
    )
    prepared = analytics.prepared()
    memory = analytics.daily_tony_memory_summary()
    review = build_tony_self_review(prepared, memory)

    assert prepared["symbol"].tolist() == ["REAL"]
    assert any("Breakout Watch" in item for item in review["what_worked"])
    assert "DEMO" not in str(review)
    assert "Speculative Watchlist" not in str(review)


def test_eod_report_includes_self_review(tmp_path, monkeypatch, capsys):
    repo = ScannerRepository(tmp_path / "analytics.db")
    snap_id = create_snapshot(repo, stock("NVDA", 91, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET snapshot_time='2026-05-20T01:00:00+00:00', entry_status='triggered', actual_entry_price=100.0, tracking_status='closed' WHERE id=?",
            (snap_id,),
        )

    class DummyTony:
        def __init__(self, repo, config):
            self.repo = repo
            self.config = config

        def start_cycle(self):
            return None

        def record_tony_learning_updated(self, **kwargs):
            self._last_kwargs = kwargs
            return None

    dummy_tony_instance = None

    class CapturingDummyTony(DummyTony):
        def __init__(self, repo, config):
            super().__init__(repo, config)
            nonlocal dummy_tony_instance
            dummy_tony_instance = self

    monkeypatch.setattr(
        cli,
        "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path,
            provider="alpaca_iex",
            tony_stocks=SimpleNamespace(),
            symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", CapturingDummyTony)
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    result = cli.run_eod_report(SimpleNamespace(config="ignored", date=None))
    output = capsys.readouterr().out

    assert "tony_self_review" in result
    assert result["tony_self_review"]["research_only"] is True
    assert "Tony self-review:" in output
    assert "Research only" in output
    assert dummy_tony_instance is not None
    assert "self_review" in dummy_tony_instance._last_kwargs.get("memory_summary", {})


# ── V18: rule suggestions ──────────────────────────────────────────────────────

def test_rule_suggestions_generated_when_data_supports_them(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    for _ in range(4):
        create_snapshot(repo, stock("BO", 90, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    for _ in range(3):
        create_snapshot(repo, stock("PB", 82, "Pullback Watch"), "stop_hit", result_5d=-0.03, provider="alpaca_iex")

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    suggestions = generate_tony_rule_suggestions(analytics.prepared())

    statuses = {s["status"] for s in suggestions}
    assert statuses == {"needs_review"}, "All suggestions must be needs_review — never auto-applied"
    confidences = {s["confidence"] for s in suggestions}
    assert confidences <= {"low", "medium", "high"}

    texts = [s["suggestion"] for s in suggestions]
    assert any("Breakout Watch" in t and "prioritiz" in t for t in texts), "Should suggest prioritizing Breakout Watch"
    assert any("Pullback Watch" in t and ("threshold" in t or "frequency" in t) for t in texts), "Should flag Pullback Watch"


def test_rule_suggestions_low_data_fallback(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    create_snapshot(repo, stock("SOLO", 80, "Breakout Watch"), "target_hit", provider="alpaca_iex")

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    suggestions = generate_tony_rule_suggestions(analytics.prepared())

    assert len(suggestions) == 1
    assert suggestions[0]["confidence"] == "low"
    assert "not enough" in suggestions[0]["suggestion"].lower() or "no rule changes" in suggestions[0]["suggestion"].lower()
    assert suggestions[0]["status"] == "needs_review"


def test_rule_suggestions_empty_rows_fallback():
    suggestions = generate_tony_rule_suggestions(pd.DataFrame())
    assert len(suggestions) == 1
    assert suggestions[0]["status"] == "needs_review"
    assert suggestions[0]["confidence"] == "low"


def test_rule_suggestions_not_applied_to_scoring(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    for _ in range(5):
        create_snapshot(repo, stock("STOP", 75, "Pullback Watch"), "stop_hit", result_5d=-0.04, provider="alpaca_iex")

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    prepared_before = analytics.prepared().copy()
    suggestions = generate_tony_rule_suggestions(prepared_before)
    prepared_after = analytics.prepared()

    assert all(s["status"] == "needs_review" for s in suggestions)
    assert len(prepared_before) == len(prepared_after), "Suggestions must not alter the dataset"
    assert list(prepared_before["symbol"]) == list(prepared_after["symbol"])


def test_self_review_includes_rule_suggestions(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    for _ in range(3):
        create_snapshot(repo, stock("MC", 88, "Momentum Continuation"), "target_hit", provider="alpaca_iex")

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    prepared = analytics.prepared()
    memory = analytics.daily_tony_memory_summary()
    review = build_tony_self_review(prepared, memory)

    assert "rule_suggestions" in review
    assert isinstance(review["rule_suggestions"], list)
    assert len(review["rule_suggestions"]) >= 1
    assert all(s["status"] == "needs_review" for s in review["rule_suggestions"])
    assert review["research_only"] is True


# ── V16B: date consistency ──────────────────────────────────────────────────────

def _make_dummy_tony():
    class DummyTony:
        def __init__(self, repo, config):
            pass
        def start_cycle(self):
            return None
        def record_tony_learning_updated(self, **kwargs):
            return None
        def record_outcome_analytics(self, summary):
            return None
    return DummyTony


def test_outcome_analytics_date_filter(tmp_path, monkeypatch):
    repo = ScannerRepository(tmp_path / "analytics.db")
    snap_may19 = create_snapshot(repo, stock("MAY19", 88, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    snap_may20 = create_snapshot(repo, stock("MAY20", 84, "Pullback Watch"), "stop_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute("UPDATE candidate_snapshots SET snapshot_time='2026-05-19T14:00:00+00:00' WHERE id=?", (snap_may19,))
        conn.execute("UPDATE candidate_snapshots SET snapshot_time='2026-05-20T14:00:00+00:00' WHERE id=?", (snap_may20,))

    monkeypatch.setattr(
        cli, "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path, provider="alpaca_iex",
            tony_stocks=SimpleNamespace(), symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", _make_dummy_tony())

    result_19 = cli.run_outcome_analytics(SimpleNamespace(
        config="ignored", date="2026-05-19", today=False, include_seeded=False,
        days=None, min_score=None, real_only=True,
        include_demo=False, include_legacy=False, exclude_demo=False,
        provider=None, group_by=None,
    ))
    result_20 = cli.run_outcome_analytics(SimpleNamespace(
        config="ignored", date="2026-05-20", today=False, include_seeded=False,
        days=None, min_score=None, real_only=True,
        include_demo=False, include_legacy=False, exclude_demo=False,
        provider=None, group_by=None,
    ))

    assert result_19["snapshots_reviewed"] == 1
    assert result_19["symbols"] == ["MAY19"]
    assert result_20["snapshots_reviewed"] == 1
    assert result_20["symbols"] == ["MAY20"]


def test_outcome_analytics_date_prints_header(tmp_path, monkeypatch, capsys):
    repo = ScannerRepository(tmp_path / "analytics.db")
    snap = create_snapshot(repo, stock("HDR", 85, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute("UPDATE candidate_snapshots SET snapshot_time='2026-05-19T15:00:00+00:00' WHERE id=?", (snap,))

    monkeypatch.setattr(
        cli, "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path, provider="alpaca_iex",
            tony_stocks=SimpleNamespace(), symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", _make_dummy_tony())

    cli.run_outcome_analytics(SimpleNamespace(
        config="ignored", date="2026-05-19", today=False, include_seeded=False,
        days=None, min_score=None, real_only=True,
        include_demo=False, include_legacy=False, exclude_demo=False,
        provider=None, group_by=None,
    ))
    output = capsys.readouterr().out
    assert "Report date: 2026-05-19 America/New_York" in output


def test_eod_report_watch_run_scoped_to_report_date(tmp_path, monkeypatch):
    repo = ScannerRepository(tmp_path / "analytics.db")
    snap = create_snapshot(repo, stock("DATE", 88, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute("UPDATE candidate_snapshots SET snapshot_time='2026-05-19T14:00:00+00:00' WHERE id=?", (snap,))

    # Insert a watch run that belongs to 2026-05-19 and one on 2026-05-20
    with connect(repo.database_path) as conn:
        conn.execute(
            "INSERT INTO watch_runs (started_at, status, cycles_completed) VALUES (?, 'stopped', 5)",
            ("2026-05-19T18:00:00+00:00",),
        )
        conn.execute(
            "INSERT INTO watch_runs (started_at, status, cycles_completed) VALUES (?, 'stopped', 12)",
            ("2026-05-20T14:00:00+00:00",),
        )

    monkeypatch.setattr(
        cli, "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path, provider="alpaca_iex",
            tony_stocks=SimpleNamespace(), symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", _make_dummy_tony())
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-21")

    # Request 2026-05-19 — should see 5 cycles (the May-19 run), not 12
    result_19 = cli.run_eod_report(SimpleNamespace(config="ignored", date="2026-05-19"))
    assert result_19["cycles_completed"] == 5

    # Request 2026-05-20 — should see 12 cycles (the May-20 run), not 5
    result_20 = cli.run_eod_report(SimpleNamespace(config="ignored", date="2026-05-20"))
    assert result_20["cycles_completed"] == 12

    # Request 2026-05-21 (no runs) — should see 0
    result_21 = cli.run_eod_report(SimpleNamespace(config="ignored", date="2026-05-21"))
    assert result_21["cycles_completed"] == 0


def test_eod_report_snapshot_count_scoped_to_date(tmp_path, monkeypatch):
    repo = ScannerRepository(tmp_path / "analytics.db")
    s19 = create_snapshot(repo, stock("S19", 88, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    s20 = create_snapshot(repo, stock("S20", 85, "Pullback Watch"), "stop_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute("UPDATE candidate_snapshots SET snapshot_time='2026-05-19T14:00:00+00:00' WHERE id=?", (s19,))
        conn.execute("UPDATE candidate_snapshots SET snapshot_time='2026-05-20T14:00:00+00:00' WHERE id=?", (s20,))

    monkeypatch.setattr(
        cli, "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path, provider="alpaca_iex",
            tony_stocks=SimpleNamespace(), symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", _make_dummy_tony())
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-21")

    result_19 = cli.run_eod_report(SimpleNamespace(config="ignored", date="2026-05-19"))
    result_20 = cli.run_eod_report(SimpleNamespace(config="ignored", date="2026-05-20"))

    assert result_19["real_only_snapshots_reviewed"] == 1
    assert result_20["real_only_snapshots_reviewed"] == 1


# ── V18A: active vs future outcome wording ─────────────────────────────────────

def test_self_review_deduped_active_count_from_reconciliation(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    # Two raw rows for the same symbol ARM (history + current), one waiting pick DKNG
    first = create_snapshot(repo, stock("ARM", 90, "Breakout Watch"), "still_open", provider="alpaca_iex")
    second = create_snapshot(repo, stock("ARM", 91, "Breakout Watch"), "still_open", provider="alpaca_iex")
    waiting = create_snapshot(repo, stock("DKNG", 84, "Breakout Watch"), "unreviewed", triggered=0, provider="alpaca_iex")

    with connect(repo.database_path) as conn:
        for snap_id in (first, second):
            conn.execute(
                "UPDATE candidate_snapshots SET entry_status='triggered', actual_entry_price=120.0, "
                "actual_entry_time='2026-05-19T14:05:00+00:00', target=128.0, stop=116.0, "
                "current_price=125.0, tracking_status='active' WHERE id=?", (snap_id,)
            )
        conn.execute(
            "UPDATE candidate_snapshots SET entry_status='pending', planned_entry_price=41.5, "
            "target=45.0, stop=39.5 WHERE id=?", (waiting,)
        )

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    prepared = analytics.prepared()
    from trading_bot.dashboard.helpers import summarize_product_reconciliation
    reconciliation = summarize_product_reconciliation(prepared)
    memory = analytics.daily_tony_memory_summary(reconciliation=reconciliation)
    review = build_tony_self_review(prepared, memory, reconciliation=reconciliation)

    # reconciliation dedupes ARM to 1 active position; raw rows = 2 triggered
    assert review["deduped_active_positions"] == reconciliation["deduped_active_positions"]
    assert review["raw_triggered_rows"] == 2
    assert review["waiting_picks"] == reconciliation["deduped_waiting_picks"]
    assert any("active position" in item for item in review["tomorrow_watch"])
    # history note should appear because raw > deduped
    assert any("history row" in item for item in review["tomorrow_watch"])


def test_self_review_insufficient_future_data_labeled_not_failure(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    snap = create_snapshot(repo, stock("NEW", 85, "Momentum Continuation"),
                           "insufficient_future_data", triggered=1, provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET entry_status='triggered', actual_entry_price=50.0 WHERE id=?",
            (snap,)
        )

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    prepared = analytics.prepared()
    memory = analytics.daily_tony_memory_summary()
    review = build_tony_self_review(prepared, memory)

    assert any("insufficient_future_data" in item or "still open" in item.lower() or "outcome windows" in item
               for item in review["needs_more_data"]), \
        "insufficient_future_data rows should be labeled as pending, not failures"
    # Should not appear in what_failed
    combined_failed = " ".join(review["what_failed"])
    assert "insufficient_future_data" not in combined_failed


def test_rule_suggestions_exclude_insufficient_future_data(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    # 4 triggered rows all labeled insufficient_future_data — should not generate suggestions
    for _ in range(4):
        snap = create_snapshot(repo, stock("WAIT", 82, "Breakout Watch"),
                               "insufficient_future_data", triggered=1, provider="alpaca_iex")
        with connect(repo.database_path) as conn:
            conn.execute(
                "UPDATE candidate_snapshots SET entry_status='triggered', actual_entry_price=80.0 WHERE id=?",
                (snap,)
            )

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    suggestions = generate_tony_rule_suggestions(analytics.prepared())

    assert len(suggestions) == 1
    assert suggestions[0]["confidence"] == "low"
    assert "conclusive" in suggestions[0]["reason"] or "future data" in suggestions[0]["reason"]


def test_rule_suggestions_use_conclusive_rows_not_total(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    # 3 conclusive target hits + 2 insufficient_future_data for same setup
    for _ in range(3):
        create_snapshot(repo, stock("BO", 90, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    for _ in range(2):
        snap = create_snapshot(repo, stock("BO2", 88, "Breakout Watch"),
                               "insufficient_future_data", triggered=1, provider="alpaca_iex")
        with connect(repo.database_path) as conn:
            conn.execute(
                "UPDATE candidate_snapshots SET entry_status='triggered', actual_entry_price=90.0 WHERE id=?",
                (snap,)
            )

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    suggestions = generate_tony_rule_suggestions(analytics.prepared())

    # Rate should be based on 3 conclusive rows (all targets), not 5 total
    texts = [s["suggestion"] for s in suggestions]
    assert any("prioritiz" in t for t in texts), "Should still suggest prioritizing BO based on conclusive rows"
    reasons = [s["reason"] for s in suggestions]
    assert any("3 of 3" in r or "conclusive" in r for r in reasons)
