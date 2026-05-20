import pandas as pd
from types import SimpleNamespace

import trading_bot.cli as cli
from trading_bot.analytics import (
    CURRENT_STRATEGY_VERSION,
    SUGGESTION_STATUSES,
    OutcomeAnalytics,
    build_daily_tony_memory_summary,
    build_replay_summary,
    build_strategy_version_report,
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


# ── V19: strategy versioning ───────────────────────────────────────────────────

def test_current_strategy_version_defaults_to_v1():
    assert CURRENT_STRATEGY_VERSION == "v1"
    assert "needs_review" in SUGGESTION_STATUSES
    assert "approved" in SUGGESTION_STATUSES
    assert "rejected" in SUGGESTION_STATUSES
    assert "applied_later" in SUGGESTION_STATUSES


def test_suggestions_attach_strategy_version(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    for _ in range(4):
        create_snapshot(repo, stock("BO", 90, "Breakout Watch"), "target_hit", provider="alpaca_iex")

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    suggestions = generate_tony_rule_suggestions(analytics.prepared())

    assert all("strategy_version" in s for s in suggestions)
    assert all(s["strategy_version"] == CURRENT_STRATEGY_VERSION for s in suggestions)
    assert all(s["strategy_version"] == "v1" for s in suggestions)


def test_suggestions_no_data_fallback_has_version():
    suggestions = generate_tony_rule_suggestions(pd.DataFrame())
    assert len(suggestions) == 1
    assert suggestions[0]["strategy_version"] == CURRENT_STRATEGY_VERSION
    assert suggestions[0]["status"] == "needs_review"


def test_build_strategy_version_report_structure(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    for _ in range(4):
        create_snapshot(repo, stock("BO", 90, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    for _ in range(3):
        create_snapshot(repo, stock("PB", 80, "Pullback Watch"), "stop_hit", provider="alpaca_iex")

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    suggestions = generate_tony_rule_suggestions(analytics.prepared())
    report = build_strategy_version_report(suggestions)

    assert report["current_version"] == "v1"
    assert report["pending_suggestions"] == len([s for s in suggestions if s["status"] == "needs_review"])
    assert "needs_review" in report["status_counts"]
    assert "suggestions" in report
    assert "note" in report
    assert "v1" in report["note"]
    assert "never applied automatically" in report["note"]


def test_strategy_version_report_no_scoring_changes(tmp_path):
    repo = ScannerRepository(tmp_path / "analytics.db")
    for _ in range(3):
        create_snapshot(repo, stock("BO", 90, "Breakout Watch"), "target_hit", provider="alpaca_iex")

    analytics = OutcomeAnalytics(repo.list_snapshots_for_analytics(), real_only=True)
    suggestions_before = generate_tony_rule_suggestions(analytics.prepared())
    report = build_strategy_version_report(suggestions_before)
    # Calling the report does not mutate suggestions or change prepared data
    suggestions_after = generate_tony_rule_suggestions(analytics.prepared())

    assert report["current_version"] == CURRENT_STRATEGY_VERSION
    assert len(suggestions_before) == len(suggestions_after)
    assert all(s["status"] == "needs_review" for s in suggestions_before)
    assert all(s["status"] == "needs_review" for s in suggestions_after)


def test_eod_report_includes_strategy_version_report(tmp_path, monkeypatch, capsys):
    repo = ScannerRepository(tmp_path / "analytics.db")
    snap = create_snapshot(repo, stock("VER", 88, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET snapshot_time='2026-05-20T01:00:00+00:00' WHERE id=?",
            (snap,),
        )

    monkeypatch.setattr(
        cli, "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path, provider="alpaca_iex",
            tony_stocks=SimpleNamespace(), symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", _make_dummy_tony())
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    result = cli.run_eod_report(SimpleNamespace(config="ignored", date=None))
    output = capsys.readouterr().out

    assert "strategy_version_report" in result
    assert result["strategy_version_report"]["current_version"] == "v1"
    assert "Strategy version: v1" in output
    assert "Pending suggestions:" in output


# --- V20: Backtest replay foundation ---

def test_build_replay_summary_empty_rows():
    result = build_replay_summary(pd.DataFrame())
    assert result["strategy_version"] == "v1"
    assert result["total_rows"] == 0
    assert result["total_triggered"] == 0
    assert result["total_conclusive"] == 0
    assert result["total_insufficient_future_data"] == 0
    assert result["setups"] == []
    assert any("No real-only rows" in n for n in result["notes"])


def test_build_replay_summary_from_sample_rows(tmp_path):
    repo = ScannerRepository(tmp_path / "replay.db")
    create_snapshot(repo, stock("AAPL", 90, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    create_snapshot(repo, stock("TSLA", 82, "Breakout Watch"), "stop_hit", provider="alpaca_iex")
    create_snapshot(repo, stock("NVDA", 85, "Pullback Watch"), "target_hit", provider="alpaca_iex")
    create_snapshot(repo, stock("AMZN", 78, "Breakout Watch"), "insufficient_future_data", provider="alpaca_iex")

    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True, limit=10000)
    analytics = OutcomeAnalytics(snapshots, real_only=True)
    rows = analytics.prepared()

    result = build_replay_summary(rows)

    assert result["strategy_version"] == "v1"
    assert result["total_rows"] == 4
    assert result["total_insufficient_future_data"] == 1
    assert result["total_conclusive"] >= 1

    setup_names = [s["setup"] for s in result["setups"]]
    assert "Breakout Watch" in setup_names
    assert "Pullback Watch" in setup_names

    bw = next(s for s in result["setups"] if s["setup"] == "Breakout Watch")
    assert bw["target_hits"] >= 1
    assert bw["stop_hits"] >= 1
    assert bw["insufficient_future_data"] == 1
    assert bw["target_rate"] is not None

    pw = next(s for s in result["setups"] if s["setup"] == "Pullback Watch")
    assert pw["target_hits"] == 1
    assert pw["stop_hits"] == 0

    assert any("insufficient_future_data" in n for n in result["notes"])


def test_build_replay_summary_no_conclusive_rows(tmp_path):
    repo = ScannerRepository(tmp_path / "replay_noconcl.db")
    create_snapshot(repo, stock("X1", 80, "Breakout Watch"), "insufficient_future_data", provider="alpaca_iex")
    create_snapshot(repo, stock("X2", 78, "Breakout Watch"), "insufficient_future_data", provider="alpaca_iex")

    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True, limit=10000)
    rows = OutcomeAnalytics(snapshots, real_only=True).prepared()

    result = build_replay_summary(rows)
    assert result["total_conclusive"] == 0
    bw = next((s for s in result["setups"] if s["setup"] == "Breakout Watch"), None)
    assert bw is not None
    assert bw["target_rate"] is None
    assert bw["stop_rate"] is None
    assert any("No conclusive outcomes" in n for n in result["notes"])


def test_build_replay_summary_real_only_excludes_demo(tmp_path):
    repo = ScannerRepository(tmp_path / "replay_demo.db")
    create_snapshot(repo, stock("REAL", 88, "Breakout Watch"), "target_hit", provider="alpaca_iex", data_source="real_alpaca")
    create_snapshot(repo, stock("DEMO", 85, "Breakout Watch"), "target_hit", provider="alpaca_iex", data_source="demo_generated")

    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True, limit=10000)
    rows = OutcomeAnalytics(snapshots, real_only=True).prepared()

    result = build_replay_summary(rows)
    assert result["total_rows"] == 1


def test_build_replay_summary_strategy_version_attached(tmp_path):
    repo = ScannerRepository(tmp_path / "replay_ver.db")
    create_snapshot(repo, stock("VER", 90, "Breakout Watch"), "target_hit", provider="alpaca_iex")

    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True, limit=10000)
    rows = OutcomeAnalytics(snapshots, real_only=True).prepared()

    result = build_replay_summary(rows, strategy_version="v2")
    assert result["strategy_version"] == "v2"
    for entry in result["setups"]:
        assert entry["strategy_version"] == "v2"


def test_eod_report_includes_replay_summary(tmp_path, monkeypatch, capsys):
    repo = ScannerRepository(tmp_path / "replay_eod.db")
    snap = create_snapshot(repo, stock("RPL", 88, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET snapshot_time='2026-05-20T01:00:00+00:00' WHERE id=?",
            (snap,),
        )

    monkeypatch.setattr(
        cli, "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path, provider="alpaca_iex",
            tony_stocks=SimpleNamespace(), symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", _make_dummy_tony())
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    result = cli.run_eod_report(SimpleNamespace(config="ignored", date=None))
    output = capsys.readouterr().out

    assert "replay_summary" in result
    assert result["replay_summary"]["strategy_version"] == "v1"
    assert "Replay summary" in output
    assert "Strategy version: v1" in output
    assert "research-only" in output


# --- V21: After-market review package ---

def _sample_eod_result(report_date="2026-05-19"):
    return {
        "date": report_date,
        "cycles_completed": 3,
        "latest_watch_status": "stopped",
        "provider": "alpaca_iex",
        "symbols_scanned": 100,
        "real_symbols_scanned": 97,
        "api_requests": 200,
        "fallback_symbols": [],
        "missing_real_data_symbols": [],
        "configured_quarantined_symbols": [],
        "configured_quarantine_entries": [],
        "replacement_symbols": [],
        "real_intraday_count": 5,
        "stale_intraday_count": 0,
        "snapshots_created_today": 3,
        "snapshots_updated_today": 2,
        "real_only_snapshots_reviewed": 3,
        "demo_rows_excluded": 0,
        "legacy_unknown_rows_excluded": 0,
        "missing_real_data_rows_excluded": 0,
        "reconciliation": {
            "raw_snapshot_rows": 10,
            "raw_triggered_entry_rows": 2,
            "product_eligible_rows": 8,
            "product_visible_symbols": 5,
            "deduped_active_positions": 1,
            "deduped_waiting_picks": 3,
            "deduped_closed_results": 2,
            "target_hits": 1,
            "stop_hits": 1,
            "partial_moves": 0,
            "pending_triggers": 2,
            "expired_no_trigger": 1,
            "insufficient_data": 0,
            "incomplete_rows_hidden_from_product_views": 0,
            "history_rows_hidden_from_product_views": 2,
        },
        "tony_memory_summary": {
            "setup_counts": {"Breakout Watch": 2},
            "triggered_count": 1,
            "active_count": 1,
            "closed_count": 0,
            "target_hit_count": 0,
            "stop_hit_count": 0,
            "partial_move_count": 0,
            "reassessment_label_counts": {},
            "best_setup_note": "none",
            "worst_setup_note": "none",
            "data_quality_notes": [],
            "report_date": report_date,
        },
        "tony_self_review": {
            "strongest_setup": "Breakout Watch",
            "weakest_setup": "none",
            "what_worked": ["Breakout Watch: 1 target hit"],
            "what_failed": [],
            "needs_more_data": [],
            "tomorrow_watch": ["1 active position(s) carry over"],
            "active_symbols": ["AAPL"],
            "deduped_active_positions": 1,
            "raw_triggered_rows": 1,
            "waiting_picks": 3,
            "pending_triggers": 2,
            "rule_suggestions": [{
                "suggestion": "Consider prioritizing Breakout Watch",
                "reason": "High target rate",
                "confidence": "medium",
                "status": "needs_review",
                "strategy_version": "v1",
            }],
            "research_only": True,
        },
        "strategy_version_report": {
            "current_version": "v1",
            "pending_suggestions": 1,
            "status_counts": {"needs_review": 1},
            "suggestions": [],
            "note": "Research-only.",
        },
        "replay_summary": {
            "strategy_version": "v1",
            "total_rows": 3,
            "total_triggered": 1,
            "total_conclusive": 1,
            "total_insufficient_future_data": 0,
            "setups": [{
                "setup": "Breakout Watch",
                "total_rows": 3,
                "triggered": 1,
                "target_hits": 1,
                "stop_hits": 0,
                "partial_moves": 0,
                "insufficient_future_data": 0,
                "conclusive_rows": 1,
                "target_rate": 1.0,
                "stop_rate": 0.0,
                "strategy_version": "v1",
            }],
            "notes": ["This is a research-only replay."],
        },
    }


def test_after_market_review_creates_report_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result(args.date or "2026-05-19"))
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 3, "symbols": ["AAPL"], "date_filter": "2026-05-19"})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    result = cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=False,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    ))

    assert result["report_date"] == "2026-05-19"
    assert len(result["files_created"]) == 9  # eod json+md, analytics json, approval json+md, proposal json+md, replay json+md

    report_dir = tmp_path / "reports" / "2026-05-19"
    assert (report_dir / "eod_report.json").exists()
    assert (report_dir / "eod_report.md").exists()
    assert (report_dir / "outcome_analytics.json").exists()
    assert (report_dir / "approval_package.json").exists()
    assert (report_dir / "approval_package.md").exists()
    assert (report_dir / "strategy_proposal.json").exists()
    assert (report_dir / "strategy_proposal.md").exists()


def test_after_market_review_uses_et_date(tmp_path, monkeypatch):
    captured = {}
    def fake_eod(args):
        captured["date"] = args.date
        return _sample_eod_result(args.date)
    def fake_analytics(args):
        captured["analytics_date"] = args.date
        return {"snapshots_reviewed": 0, "symbols": [], "date_filter": args.date}

    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", fake_eod)
    monkeypatch.setattr(cli, "run_outcome_analytics", fake_analytics)
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        output_dir=str(tmp_path / "reports"),
    ))

    assert captured["date"] == "2026-05-19"
    assert captured["analytics_date"] == "2026-05-19"


def test_after_market_review_date_override(tmp_path, monkeypatch):
    captured = {}
    def fake_eod(args):
        captured["date"] = args.date
        return _sample_eod_result(args.date)

    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", fake_eod)
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": args.date})

    cli.run_after_market_review(SimpleNamespace(
        config="ignored", date="2026-05-18", skip_update_snapshots=True,
        output_dir=str(tmp_path / "reports"),
    ))

    assert captured["date"] == "2026-05-18"
    report_dir = tmp_path / "reports" / "2026-05-18"
    assert (report_dir / "eod_report.json").exists()


def test_after_market_review_skip_update_snapshots(tmp_path, monkeypatch):
    update_called = []
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: update_called.append(True) or {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        output_dir=str(tmp_path / "reports"),
    ))
    assert update_called == []


def test_after_market_review_real_only_analytics(tmp_path, monkeypatch):
    captured = {}
    def fake_analytics(args):
        captured["real_only"] = getattr(args, "real_only", False)
        captured["include_demo"] = getattr(args, "include_demo", False)
        return {"snapshots_reviewed": 0, "symbols": [], "date_filter": args.date}

    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", fake_analytics)
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        output_dir=str(tmp_path / "reports"),
    ))

    assert captured["real_only"] is True
    assert captured["include_demo"] is False


def test_after_market_review_no_auto_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    result = cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        output_dir=str(tmp_path / "reports"),
    ))

    sr = result["eod_report"].get("tony_self_review", {})
    for suggestion in sr.get("rule_suggestions", []):
        assert suggestion["status"] == "needs_review"
        assert suggestion.get("applied") is not True


def test_after_market_review_json_files_valid(tmp_path, monkeypatch):
    import json as json_mod
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 2, "symbols": ["AAPL"], "date_filter": "2026-05-19"})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        output_dir=str(tmp_path / "reports"),
    ))

    report_dir = tmp_path / "reports" / "2026-05-19"
    eod_data = json_mod.loads((report_dir / "eod_report.json").read_text(encoding="utf-8"))
    analytics_data = json_mod.loads((report_dir / "outcome_analytics.json").read_text(encoding="utf-8"))
    assert eod_data["date"] == "2026-05-19"
    assert analytics_data["snapshots_reviewed"] == 2


def test_after_market_review_markdown_contains_key_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        output_dir=str(tmp_path / "reports"),
    ))

    md = (tmp_path / "reports" / "2026-05-19" / "eod_report.md").read_text(encoding="utf-8")
    assert "After-Market Review" in md
    assert "2026-05-19" in md
    assert "Research only" in md
    assert "Tony Self-Review" in md
    assert "Rule Suggestions" in md
    assert "Replay Summary" in md
    assert "Not Applied" in md


# --- V21A: After-hours review guard ---

from datetime import datetime as _dt
from zoneinfo import ZoneInfo as _ZoneInfo

def _make_et_time(hour, minute, weekday=0):
    """Return a timezone-aware ET datetime for the given weekday (0=Mon…4=Fri, 5=Sat, 6=Sun)."""
    from datetime import date, timedelta
    base = _dt(2026, 5, 18, hour, minute, 0, tzinfo=_ZoneInfo("America/New_York"))
    # 2026-05-18 is a Monday (weekday=0)
    delta = weekday - base.weekday()
    return base + timedelta(days=delta)


def _amr_base_patches(monkeypatch, tmp_path):
    """Apply common monkeypatches for after-market-review tests."""
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result(args.date or "2026-05-19"))
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": args.date})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")


def test_outside_hours_skips_refresh_by_default(tmp_path, monkeypatch, capsys):
    update_called = []
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: update_called.append(True) or {})
    _amr_base_patches(monkeypatch, tmp_path)
    # 18:00 ET weekday — after close
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=False,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    ))
    output = capsys.readouterr().out

    assert update_called == []
    assert result["snapshot_refresh_ran"] is False
    assert result["market_hours_active"] is False
    assert "Outside market hours" in output
    assert "skipping live snapshot refresh" in output


def test_force_update_runs_despite_outside_hours(tmp_path, monkeypatch, capsys):
    update_called = []
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: update_called.append(True) or {})
    _amr_base_patches(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=False,
        force_update_snapshots=True, output_dir=str(tmp_path / "reports"),
    ))
    output = capsys.readouterr().out

    assert update_called == [True]
    assert result["snapshot_refresh_ran"] is True
    assert "--force-update-snapshots" in output


def test_inside_hours_runs_refresh_normally(tmp_path, monkeypatch):
    update_called = []
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: update_called.append(True) or {})
    _amr_base_patches(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: True)

    result = cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=False,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    ))

    assert update_called == [True]
    assert result["snapshot_refresh_ran"] is True
    assert result["market_hours_active"] is True


def test_skip_flag_still_skips_even_during_hours(tmp_path, monkeypatch):
    update_called = []
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: update_called.append(True) or {})
    _amr_base_patches(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: True)

    result = cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    ))

    assert update_called == []
    assert result["snapshot_refresh_ran"] is False


def test_outside_hours_still_creates_report_files(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    _amr_base_patches(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=False,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    ))

    report_dir = tmp_path / "reports" / "2026-05-19"
    assert (report_dir / "eod_report.json").exists()
    assert (report_dir / "eod_report.md").exists()
    assert (report_dir / "outcome_analytics.json").exists()
    assert (report_dir / "approval_package.json").exists()
    assert (report_dir / "approval_package.md").exists()
    assert (report_dir / "strategy_proposal.json").exists()
    assert (report_dir / "strategy_proposal.md").exists()
    assert len(result["files_created"]) == 9


def test_market_hours_helper_weekday_inside():
    et = _make_et_time(10, 0, weekday=2)  # Wednesday 10:00 ET
    assert cli._is_within_regular_market_hours(now=et) is True


def test_market_hours_helper_weekday_before_open():
    et = _make_et_time(8, 0, weekday=1)  # Tuesday 08:00 ET
    assert cli._is_within_regular_market_hours(now=et) is False


def test_market_hours_helper_weekday_after_close():
    et = _make_et_time(17, 0, weekday=3)  # Thursday 17:00 ET
    assert cli._is_within_regular_market_hours(now=et) is False


def test_market_hours_helper_saturday():
    et = _make_et_time(11, 0, weekday=5)  # Saturday 11:00 ET
    assert cli._is_within_regular_market_hours(now=et) is False


def test_market_hours_helper_sunday():
    et = _make_et_time(14, 0, weekday=6)  # Sunday 14:00 ET
    assert cli._is_within_regular_market_hours(now=et) is False


# --- V21B: Report cleanup consistency ---

def test_self_review_no_negative_conclusive_count(tmp_path):
    repo = ScannerRepository(tmp_path / "neg.db")
    # Create 2 insufficient_future_data rows with triggered=1 each — conclusive should be 0 not -1
    create_snapshot(repo, stock("X1", 80, "Breakout Watch"), "insufficient_future_data", triggered=1, provider="alpaca_iex")
    create_snapshot(repo, stock("X2", 78, "Breakout Watch"), "insufficient_future_data", triggered=1, provider="alpaca_iex")

    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True, limit=10000)
    rows = OutcomeAnalytics(snapshots, real_only=True).prepared()
    mem = build_daily_tony_memory_summary(rows, reconciliation=None, exclusions=None)
    result = build_tony_self_review(rows, mem, reconciliation=None)

    for item in result["needs_more_data"]:
        # Ensure no negative number appears (e.g. "-1 row(s)")
        import re
        numbers = re.findall(r"-\d+", item)
        assert numbers == [], f"Negative count found in needs_more_data: {item!r}"


def test_self_review_insufficient_wording_not_triggered(tmp_path):
    repo = ScannerRepository(tmp_path / "insuf.db")
    create_snapshot(repo, stock("PEND", 82, "Pullback Watch"), "insufficient_future_data", triggered=1, provider="alpaca_iex")

    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True, limit=10000)
    rows = OutcomeAnalytics(snapshots, real_only=True).prepared()
    mem = build_daily_tony_memory_summary(rows, reconciliation=None, exclusions=None)
    result = build_tony_self_review(rows, mem, reconciliation=None)

    needs_more = " ".join(result["needs_more_data"])
    assert "triggered row" not in needs_more  # should NOT say "triggered row(s)"
    assert "insufficient_future_data" in needs_more
    assert "not failure" in needs_more or "not failures" in needs_more


def test_print_dataframe_nan_renders_as_na(capsys):
    import pandas as pd
    df = pd.DataFrame({"setup": ["Breakout Watch", "Pullback Watch"], "target_rate": [0.5, float("nan")]})
    cli._print_dataframe(df)
    output = capsys.readouterr().out
    assert "NaN" not in output
    assert "N/A" in output


def test_eod_report_data_quality_notes_include_row_type_guide(tmp_path, monkeypatch, capsys):
    repo = ScannerRepository(tmp_path / "notes.db")
    snap = create_snapshot(repo, stock("RNG", 88, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET snapshot_time='2026-05-20T01:00:00+00:00' WHERE id=?",
            (snap,),
        )
    monkeypatch.setattr(
        cli, "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path, provider="alpaca_iex",
            tony_stocks=SimpleNamespace(), symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", _make_dummy_tony())
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    cli.run_eod_report(SimpleNamespace(config="ignored", date=None))
    output = capsys.readouterr().out

    assert "raw rows" in output.lower()
    assert "product rows" in output.lower()
    assert "insufficient_future_data" in output
    assert "conclusive rows" in output.lower()


def test_eod_report_reconciliation_section_has_clarifying_note(tmp_path, monkeypatch, capsys):
    repo = ScannerRepository(tmp_path / "rec_note.db")
    snap = create_snapshot(repo, stock("REC", 85, "Breakout Watch"), "target_hit", provider="alpaca_iex")
    with connect(repo.database_path) as conn:
        conn.execute(
            "UPDATE candidate_snapshots SET snapshot_time='2026-05-20T01:00:00+00:00' WHERE id=?",
            (snap,),
        )
    monkeypatch.setattr(
        cli, "load_scanner_settings",
        lambda _: SimpleNamespace(
            database_path=repo.database_path, provider="alpaca_iex",
            tony_stocks=SimpleNamespace(), symbol_quarantine={},
        ),
    )
    monkeypatch.setattr(cli, "TonyStocksService", _make_dummy_tony())
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    cli.run_eod_report(SimpleNamespace(config="ignored", date=None))
    output = capsys.readouterr().out

    assert "Raw rows" in output or "raw rows" in output.lower()
    assert "deduped" in output.lower()


# --- V22: Approval package ---

def _sample_eod_with_suggestions(report_date="2026-05-19"):
    result = _sample_eod_result(report_date)
    result["tony_self_review"]["rule_suggestions"] = [
        {
            "suggestion": "Consider prioritizing Breakout Watch",
            "reason": "Target rate 80% across 5 conclusive rows",
            "confidence": "high",
            "status": "needs_review",
            "strategy_version": "v1",
        }
    ]
    result["strategy_version_report"]["pending_suggestions"] = 1
    return result


def _amr_args(tmp_path, date=None):
    return SimpleNamespace(
        config="ignored", date=date, skip_update_snapshots=True,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    )


def test_approval_package_files_created(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_with_suggestions())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(_amr_args(tmp_path))

    report_dir = tmp_path / "reports" / "2026-05-19"
    assert (report_dir / "approval_package.json").exists()
    assert (report_dir / "approval_package.md").exists()
    assert "approval_package" in result
    assert str(report_dir / "approval_package.json") in result["files_created"]
    assert str(report_dir / "approval_package.md") in result["files_created"]


def test_approval_package_includes_suggestions(tmp_path, monkeypatch):
    import json as json_mod
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_with_suggestions())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(_amr_args(tmp_path))

    pkg = result["approval_package"]
    assert pkg["pending_count"] == 1
    assert pkg["suggestions"][0]["status"] == "needs_review"
    assert pkg["strategy_version"] == "v1"
    assert pkg["research_only"] is True

    # Verify JSON file content
    report_dir = tmp_path / "reports" / "2026-05-19"
    data = json_mod.loads((report_dir / "approval_package.json").read_text(encoding="utf-8"))
    assert data["pending_count"] == 1
    assert data["suggestions"][0]["suggestion"] == "Consider prioritizing Breakout Watch"


def test_approval_package_empty_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())  # has 1 suggestion from fixture
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    # Use eod result with empty suggestions
    empty_eod = _sample_eod_result()
    empty_eod["tony_self_review"]["rule_suggestions"] = []
    monkeypatch.setattr(cli, "run_eod_report", lambda args: empty_eod)

    result = cli.run_after_market_review(_amr_args(tmp_path))
    pkg = result["approval_package"]

    assert pkg["pending_count"] == 0
    assert pkg["suggestions"] == []

    md = (tmp_path / "reports" / "2026-05-19" / "approval_package.md").read_text(encoding="utf-8")
    assert "No approval items today." in md


def test_approval_package_no_auto_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_with_suggestions())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(_amr_args(tmp_path))

    pkg = result["approval_package"]
    for s in pkg["suggestions"]:
        assert s["status"] == "needs_review"
        assert s.get("applied") is not True
    assert "not_applied_note" in pkg
    assert "not been applied" in pkg["not_applied_note"]


def test_approval_package_markdown_structure(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_with_suggestions())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    cli.run_after_market_review(_amr_args(tmp_path))

    md = (tmp_path / "reports" / "2026-05-19" / "approval_package.md").read_text(encoding="utf-8")
    assert "Approval Package" in md
    assert "needs_review" in md
    assert "Research only" in md
    assert "Not applied" in md
    assert "[HIGH]" in md  # confidence label
    assert "not been applied" in md or "Not applied" in md


def test_after_market_review_total_files_count(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(_amr_args(tmp_path))

    # eod json+md, analytics json, approval json+md, proposal json+md, replay json+md
    assert len(result["files_created"]) == 9


# --- V23: Human approval gate ---

def _write_approval_package(tmp_path, date="2026-05-19", suggestions=None):
    """Write a minimal approval_package.json for record-suggestion-decision tests."""
    import json as _json
    if suggestions is None:
        suggestions = [
            {
                "suggestion": "Consider prioritizing Breakout Watch",
                "reason": "High target rate",
                "confidence": "high",
                "status": "needs_review",
                "strategy_version": "v1",
            }
        ]
    pkg = {
        "report_date": date,
        "strategy_version": "v1",
        "pending_count": len(suggestions),
        "decided_count": 0,
        "suggestions": suggestions,
        "not_applied_note": "Not applied.",
        "research_only": True,
    }
    report_dir = tmp_path / "reports" / date
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "approval_package.json").write_text(_json.dumps(pkg, indent=2), encoding="utf-8")
    return pkg


def test_record_decision_approve(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    _write_approval_package(tmp_path)

    result = cli.run_record_suggestion_decision(SimpleNamespace(
        date="2026-05-19", index=1, status="approved", note="Looks good",
        output_dir=str(tmp_path / "reports"),
    ))

    assert result["status"] == "approved"
    assert result["not_applied"] is True

    decisions_path = tmp_path / "reports" / "suggestion_decisions.json"
    assert decisions_path.exists()
    import json as _json
    records = _json.loads(decisions_path.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["status"] == "approved"
    assert records[0]["not_applied"] is True
    assert records[0]["note"] == "Looks good"


def test_record_decision_reject(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    _write_approval_package(tmp_path)

    result = cli.run_record_suggestion_decision(SimpleNamespace(
        date="2026-05-19", index=1, status="rejected", note="Not enough data",
        output_dir=str(tmp_path / "reports"),
    ))

    assert result["status"] == "rejected"
    assert result["not_applied"] is True
    import json as _json
    records = _json.loads((tmp_path / "reports" / "suggestion_decisions.json").read_text(encoding="utf-8"))
    assert records[0]["status"] == "rejected"


def test_approved_decision_not_applied(tmp_path, monkeypatch):
    """Approved status must never trigger scoring or strategy changes."""
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    _write_approval_package(tmp_path)

    result = cli.run_record_suggestion_decision(SimpleNamespace(
        date="2026-05-19", index=1, status="approved", note="",
        output_dir=str(tmp_path / "reports"),
    ))

    # The decision record must carry not_applied=True
    assert result["not_applied"] is True
    # Verify the stored record also marks it not applied
    import json as _json
    records = _json.loads((tmp_path / "reports" / "suggestion_decisions.json").read_text(encoding="utf-8"))
    assert records[0]["not_applied"] is True
    assert records[0]["status"] == "approved"


def test_record_decision_missing_package(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")

    result = cli.run_record_suggestion_decision(SimpleNamespace(
        date="2026-05-19", index=1, status="approved", note="",
        output_dir=str(tmp_path / "reports"),
    ))

    assert result.get("error") == "approval_package_not_found"


def test_record_decision_index_out_of_range(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    _write_approval_package(tmp_path)

    result = cli.run_record_suggestion_decision(SimpleNamespace(
        date="2026-05-19", index=99, status="approved", note="",
        output_dir=str(tmp_path / "reports"),
    ))

    assert result.get("error") == "index_out_of_range"


def test_prior_decisions_shown_in_approval_package(tmp_path, monkeypatch):
    """After a decision is recorded, rebuild shows it in the enriched suggestions."""
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    _write_approval_package(tmp_path)

    # Record an approval decision
    cli.run_record_suggestion_decision(SimpleNamespace(
        date="2026-05-19", index=1, status="approved", note="Confirmed",
        output_dir=str(tmp_path / "reports"),
    ))

    # Load the decisions and rebuild the package
    decisions = cli._load_suggestion_decisions(str(tmp_path / "reports"))
    suggestions = [
        {
            "suggestion": "Consider prioritizing Breakout Watch",
            "reason": "High target rate",
            "confidence": "high",
            "status": "needs_review",
            "strategy_version": "v1",
        }
    ]
    pkg = cli._build_approval_package("2026-05-19", suggestions, "v1", decisions=decisions)

    assert pkg["decided_count"] == 1
    assert pkg["pending_count"] == 0
    assert pkg["suggestions"][0]["status"] == "approved"
    assert pkg["suggestions"][0]["decision_note"] == "Confirmed"
    assert pkg["suggestions"][0]["not_applied"] is True


def test_suggestion_key_is_stable():
    key1 = cli._suggestion_key("Consider prioritizing Breakout Watch", "v1")
    key2 = cli._suggestion_key("Consider prioritizing Breakout Watch", "v1")
    key3 = cli._suggestion_key("Consider prioritizing Breakout Watch", "v2")
    assert key1 == key2
    assert key1 != key3
    assert len(key1) == 12


# --- V24: Strategy proposal package ---

def _approved_decisions(output_dir, tmp_path):
    """Write a suggestion_decisions.json with one approved decision."""
    import json as _json
    record = {
        "suggestion_key": cli._suggestion_key("Consider prioritizing Breakout Watch", "v1"),
        "suggestion": "Consider prioritizing Breakout Watch",
        "reason": "High target rate",
        "confidence": "high",
        "strategy_version": "v1",
        "status": "approved",
        "decided_at": "2026-05-19T17:00:00-04:00",
        "note": "Looks solid",
        "date": "2026-05-19",
        "not_applied": True,
    }
    decisions_path = tmp_path / "reports" / "suggestion_decisions.json"
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    decisions_path.write_text(_json.dumps([record], indent=2), encoding="utf-8")
    return record


def test_proposal_created_from_approved_suggestions(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    _approved_decisions("reports", tmp_path)

    result = cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    ))

    proposal = result["strategy_proposal"]
    assert proposal["approved_count"] == 1
    assert proposal["current_version"] == "v1"
    assert proposal["proposed_version"] == "v1.1"
    assert proposal["research_only"] is True
    assert "not been applied" in proposal["not_applied_note"]

    report_dir = tmp_path / "reports" / "2026-05-19"
    assert (report_dir / "strategy_proposal.json").exists()
    assert (report_dir / "strategy_proposal.md").exists()


def test_proposal_empty_fallback(tmp_path, monkeypatch):
    """No approved decisions → proposal says 'No strategy proposal today.'"""
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(_amr_args(tmp_path))

    proposal = result["strategy_proposal"]
    assert proposal["approved_count"] == 0
    assert proposal["proposed_version"] == proposal["current_version"]  # no bump when empty

    md = (tmp_path / "reports" / "2026-05-19" / "strategy_proposal.md").read_text(encoding="utf-8")
    assert "No strategy proposal today." in md


def test_proposal_not_applied(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)
    _approved_decisions("reports", tmp_path)

    result = cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    ))

    proposal = result["strategy_proposal"]
    assert proposal["research_only"] is True
    assert "Approved does not mean applied" in proposal["not_applied_note"]
    for s in proposal["approved_suggestions"]:
        assert s.get("applied") is not True


def test_proposal_json_valid(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)
    _approved_decisions("reports", tmp_path)

    cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    ))

    data = _json.loads((tmp_path / "reports" / "2026-05-19" / "strategy_proposal.json").read_text(encoding="utf-8"))
    assert data["proposed_version"] == "v1.1"
    assert data["approved_count"] == 1
    assert data["research_only"] is True


def test_next_proposed_version():
    assert cli._next_proposed_version("v1") == "v1.1"
    assert cli._next_proposed_version("v1.1") == "v1.2"
    assert cli._next_proposed_version("v1.9") == "v1.10"
    assert cli._next_proposed_version("v2") == "v2.1"
    assert cli._next_proposed_version("v2.3") == "v2.4"


def test_proposal_markdown_contains_key_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)
    _approved_decisions("reports", tmp_path)

    cli.run_after_market_review(SimpleNamespace(
        config="ignored", date=None, skip_update_snapshots=True,
        force_update_snapshots=False, output_dir=str(tmp_path / "reports"),
    ))

    md = (tmp_path / "reports" / "2026-05-19" / "strategy_proposal.md").read_text(encoding="utf-8")
    assert "Strategy Proposal" in md
    assert "v1.1" in md
    assert "Not applied" in md
    assert "Research only" in md
    assert "Approved does not mean applied" in md


# --- V25: Replay strategy proposal ---


def _amr_args_v25(tmp_path, date=None):
    return SimpleNamespace(
        config="ignored",
        date=date,
        skip_update_snapshots=True,
        force_update_snapshots=False,
        output_dir=str(tmp_path / "reports"),
    )


def _baseline_replay_with_conclusive(n=5):
    """Return a minimal replay_summary dict with n conclusive rows."""
    return {
        "strategy_version": "v1",
        "total_rows": n,
        "total_triggered": n,
        "total_conclusive": n,
        "total_insufficient_future_data": 0,
        "setups": [
            {
                "setup": "Breakout Watch",
                "total_rows": n,
                "triggered": n,
                "target_hits": n,
                "stop_hits": 0,
                "partial_moves": 0,
                "insufficient_future_data": 0,
                "conclusive_rows": n,
                "target_rate": 1.0,
                "stop_rate": 0.0,
                "strategy_version": "v1",
            }
        ],
        "notes": [],
    }


def test_proposal_replay_files_created(tmp_path, monkeypatch):
    """After-market-review creates proposal_replay.json and proposal_replay.md."""
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(_amr_args_v25(tmp_path))

    report_dir = tmp_path / "reports" / "2026-05-19"
    assert (report_dir / "proposal_replay.json").exists()
    assert (report_dir / "proposal_replay.md").exists()
    assert "proposal_replay" in result
    assert len(result["files_created"]) == 9


def test_proposal_replay_no_approved_fallback(tmp_path, monkeypatch):
    """No approved suggestions → validation_status is no_approved_suggestions."""
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0, "symbols": [], "date_filter": None})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)
    # no decisions written → no approved suggestions

    result = cli.run_after_market_review(_amr_args_v25(tmp_path))

    replay = result["proposal_replay"]
    assert replay["validation_status"] == "no_approved_suggestions"
    assert replay["validated"] is False
    assert replay["research_only"] is True
    assert replay["approved_suggestions"] == []


def test_proposal_replay_insufficient_data(tmp_path, monkeypatch):
    """Approved suggestions but zero conclusive rows → insufficient_data."""
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    # replay_summary has 0 conclusive rows
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {
        "snapshots_reviewed": 0,
        "symbols": [],
        "date_filter": None,
        "replay_summary": {"total_conclusive": 0, "setups": [], "notes": []},
    })
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)
    _approved_decisions("reports", tmp_path)

    result = cli.run_after_market_review(_amr_args_v25(tmp_path))

    replay = result["proposal_replay"]
    assert replay["validation_status"] == "insufficient_data"
    assert replay["validated"] is False
    assert any("cannot be validated" in n for n in replay["notes"])


def test_proposal_replay_validated(tmp_path, monkeypatch):
    """Approved suggestions + enough conclusive rows → validated status."""
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {
        "snapshots_reviewed": 5,
        "symbols": [],
        "date_filter": None,
        "replay_summary": _baseline_replay_with_conclusive(5),
    })
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)
    _approved_decisions("reports", tmp_path)

    result = cli.run_after_market_review(_amr_args_v25(tmp_path))

    replay = result["proposal_replay"]
    assert replay["validation_status"] == "validated"
    assert replay["validated"] is True
    assert len(replay["approved_suggestions"]) == 1
    assert replay["approved_suggestions"][0]["baseline_total_conclusive"] == 5


def test_proposal_replay_not_applied(tmp_path, monkeypatch):
    """Proposal replay always carries not_applied_note and research_only."""
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {"snapshots_reviewed": 0})
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)

    result = cli.run_after_market_review(_amr_args_v25(tmp_path))

    replay = result["proposal_replay"]
    assert "not_applied_note" in replay
    assert "Approved does not mean applied" in replay["not_applied_note"]
    assert replay["research_only"] is True


def test_proposal_replay_json_valid(tmp_path, monkeypatch):
    """proposal_replay.json is valid JSON with required keys."""
    import json as _json
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {
        "snapshots_reviewed": 5,
        "replay_summary": _baseline_replay_with_conclusive(5),
    })
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)
    _approved_decisions("reports", tmp_path)

    cli.run_after_market_review(_amr_args_v25(tmp_path))

    raw = (tmp_path / "reports" / "2026-05-19" / "proposal_replay.json").read_text(encoding="utf-8")
    data = _json.loads(raw)
    for key in ("report_date", "current_version", "proposed_version", "validated",
                "validation_status", "baseline_replay", "approved_suggestions",
                "notes", "not_applied_note", "research_only"):
        assert key in data, f"Missing key: {key}"


def test_proposal_replay_markdown_contains_key_sections(tmp_path, monkeypatch):
    """proposal_replay.md contains expected sections."""
    monkeypatch.setattr(cli, "run_update_snapshots", lambda args: {})
    monkeypatch.setattr(cli, "run_eod_report", lambda args: _sample_eod_result())
    monkeypatch.setattr(cli, "run_outcome_analytics", lambda args: {
        "snapshots_reviewed": 5,
        "replay_summary": _baseline_replay_with_conclusive(5),
    })
    monkeypatch.setattr(cli, "new_york_market_date", lambda now=None: "2026-05-19")
    monkeypatch.setattr(cli, "_is_within_regular_market_hours", lambda now=None: False)
    _approved_decisions("reports", tmp_path)

    cli.run_after_market_review(_amr_args_v25(tmp_path))

    md = (tmp_path / "reports" / "2026-05-19" / "proposal_replay.md").read_text(encoding="utf-8")
    assert "Proposal Replay" in md
    assert "Approved does not mean applied" in md
    assert "Research only" in md
    assert "Not applied" in md
