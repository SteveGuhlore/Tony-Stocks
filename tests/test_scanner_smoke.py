from argparse import Namespace
from pathlib import Path

import pandas as pd

from trading_bot.cli import (
    _build_intraday_summary,
    run_data_check,
    run_outcome_analytics,
    run_scan,
    run_seed_demo_snapshots,
    run_update_snapshots,
    run_watch,
)
from trading_bot.intraday.features import IntradayFeatures
from trading_bot.settings import load_scanner_settings


def test_scanner_writes_required_csv_fields(tmp_path: Path):
    outputs_dir = tmp_path / "outputs"
    cache_dir = tmp_path / "cache"
    database_path = tmp_path / "scanner.db"
    universe_path = tmp_path / "universe.yaml"
    config_path = tmp_path / "default_config.yaml"

    universe_path.write_text(
        """
symbols:
  - symbol: SPY
    tags: [etf, benchmark]
    universe_role: benchmark
    demo_profile: benchmark_index
  - symbol: PLTR
    tags: [mid_cap, software, breakout_candidate]
    universe_role: primary_candidate
    demo_profile: clean_breakout
csv_path:
filters:
  max_universe_size: 5
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {database_path.as_posix()}
outputs_dir: {outputs_dir.as_posix()}
cache_dir: {cache_dir.as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 5
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
""",
        encoding="utf-8",
    )

    run_scan(Namespace(config=str(config_path), symbols="", save_snapshots=False))

    csv_path = outputs_dir / "latest_scan_results.csv"
    assert csv_path.exists()
    results = pd.read_csv(csv_path)
    required_fields = {
        "symbol",
        "final_score",
        "setup_category",
        "latest_close",
        "suggested_entry",
        "suggested_stop",
        "suggested_target_1",
        "risk_reward_ratio",
        "trade_plan_valid",
        "trade_plan_status",
        "tags",
        "reasons",
        "warnings",
        "dollar_volume_20",
        "relative_volume",
        "atr_percent",
    }
    assert required_fields.issubset(results.columns)
    assert set(results["symbol"]) == {"SPY", "PLTR"}


def test_scanner_can_save_candidate_snapshots(tmp_path: Path):
    outputs_dir = tmp_path / "outputs"
    cache_dir = tmp_path / "cache"
    database_path = tmp_path / "scanner.db"
    universe_path = tmp_path / "universe.yaml"
    config_path = tmp_path / "default_config.yaml"

    universe_path.write_text(
        """
symbols:
  - symbol: PLTR
    tags: [mid_cap, software, breakout_candidate]
    universe_role: primary_candidate
    demo_profile: clean_breakout
csv_path:
filters:
  max_universe_size: 5
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {database_path.as_posix()}
outputs_dir: {outputs_dir.as_posix()}
cache_dir: {cache_dir.as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 5
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
candidate_snapshots:
  enabled: true
  min_score: 60
  include_roles: [primary_candidate]
  include_categories: [Breakout Watch, Pullback Watch, Momentum Continuation]
  exclude_categories: [Weak / Avoid, Overextended / Wait, ETF / Benchmark Reference]
  include_benchmarks: false
  include_references: false
  allow_invalid_trade_plans: false
  dedupe_minutes: 60
""",
        encoding="utf-8",
    )

    run_scan(Namespace(config=str(config_path), symbols="", save_snapshots=True))

    from trading_bot.storage.repositories import ScannerRepository

    snapshots = ScannerRepository(database_path).latest_candidate_snapshots()
    assert len(snapshots) == 1
    assert snapshots.iloc[0]["symbol"] == "PLTR"
    assert snapshots.iloc[0]["entry_triggered"] == 0
    assert snapshots.iloc[0]["trade_plan_valid"] == 1
    tony_events = ScannerRepository(database_path).list_tony_events(limit=20)
    assert {"scan_started", "scan_completed", "snapshots_created"} & set(tony_events["event_type"])

    run_update_snapshots(Namespace(config=str(config_path), limit=50))
    updated = ScannerRepository(database_path).latest_candidate_snapshots()
    assert updated.iloc[0]["last_checked_at"]
    assert updated.iloc[0]["outcome_label"] in {"insufficient_future_data", "entry_not_triggered", "still_open", "partial_move", "target_before_stop", "stop_before_target"}


def test_scanner_csv_trade_levels_are_valid_for_eligible_candidates(tmp_path: Path):
    outputs_dir = tmp_path / "outputs"
    cache_dir = tmp_path / "cache"
    database_path = tmp_path / "scanner.db"
    universe_path = tmp_path / "universe.yaml"
    config_path = tmp_path / "default_config.yaml"

    universe_path.write_text(
        """
symbols:
  - symbol: SPY
    tags: [etf, benchmark]
    universe_role: benchmark
    demo_profile: benchmark_index
  - symbol: PLTR
    tags: [mid_cap, software, breakout_candidate]
    universe_role: primary_candidate
    demo_profile: clean_breakout
  - symbol: RIVN
    tags: [speculative, high_beta]
    universe_role: speculative_candidate
    demo_profile: overextended_runner
  - symbol: WEAK
    tags: [watchlist]
    universe_role: excluded_by_default
    demo_profile: weak_downtrend
csv_path:
filters:
  max_universe_size: 10
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {database_path.as_posix()}
outputs_dir: {outputs_dir.as_posix()}
cache_dir: {cache_dir.as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 10
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
""",
        encoding="utf-8",
    )

    run_scan(Namespace(config=str(config_path), symbols="", save_snapshots=False))

    results = pd.read_csv(outputs_dir / "latest_scan_results.csv")
    excluded_categories = {"Weak / Avoid", "Insufficient Data", "Invalid Trade Plan", "ETF / Benchmark Reference", "Overextended / Wait"}
    excluded_roles = {"benchmark", "reference", "excluded_by_default"}
    eligible = results[
        ~results["setup_category"].isin(excluded_categories)
        & ~results["universe_role"].isin(excluded_roles)
    ]
    failures = []
    for row in eligible.to_dict("records"):
        if not bool(row["trade_plan_valid"]):
            failures.append(f"{row['symbol']}: trade_plan_valid is false")
        if not (row["suggested_stop"] < row["suggested_entry"]):
            failures.append(f"{row['symbol']}: stop {row['suggested_stop']} >= entry {row['suggested_entry']}")
        if not (row["suggested_target_1"] > row["suggested_entry"]):
            failures.append(f"{row['symbol']}: target {row['suggested_target_1']} <= entry {row['suggested_entry']}")
        if not (row["risk_reward_ratio"] > 0):
            failures.append(f"{row['symbol']}: risk_reward_ratio {row['risk_reward_ratio']} <= 0")
    assert not failures, "; ".join(failures)


def test_seed_demo_snapshots_creates_dedupes_and_updates_outcomes(tmp_path: Path):
    database_path = tmp_path / "scanner.db"
    cache_dir = tmp_path / "cache"
    universe_path = tmp_path / "universe.yaml"
    config_path = tmp_path / "default_config.yaml"
    universe_path.write_text(
        """
symbols:
  - symbol: PLTR
    tags: [mid_cap, software, demo_seeded]
    universe_role: primary_candidate
    demo_profile: clean_breakout
  - symbol: UPST
    tags: [small_cap, high_beta, demo_seeded]
    universe_role: speculative_candidate
    demo_profile: high_volatility_whipsaw
  - symbol: SOFI
    tags: [mid_cap, fintech, demo_seeded]
    universe_role: speculative_candidate
    demo_profile: momentum_continuation
  - symbol: U
    tags: [small_cap, software, demo_seeded]
    universe_role: speculative_candidate
    demo_profile: failed_breakout
  - symbol: ROKU
    tags: [mid_cap, consumer, demo_seeded]
    universe_role: primary_candidate
    demo_profile: pullback_in_uptrend
  - symbol: HIMS
    tags: [mid_cap, healthcare, demo_seeded]
    universe_role: primary_candidate
    demo_profile: clean_breakout
csv_path:
filters:
  max_universe_size: 10
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {database_path.as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {cache_dir.as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 140
timeframe: daily
max_symbols: 10
min_price: 1
max_price: 1000
min_avg_volume: 1
min_dollar_volume: 1
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
snapshot_followup:
  same_bar_target_stop_policy: conservative_stop_first
  expire_after_trading_days: 20
demo_snapshot_seed:
  enabled: true
  count: 6
  days_back_start: 25
  dedupe: true
  note_prefix: "Demo seeded snapshot test"
""",
        encoding="utf-8",
    )

    args = Namespace(config=str(config_path), force=False)
    run_seed_demo_snapshots(args)
    from trading_bot.storage.repositories import ScannerRepository

    repo = ScannerRepository(database_path)
    seeded = repo.latest_candidate_snapshots(limit=20)
    assert len(seeded) >= 4
    assert seeded["notes"].str.contains("Demo seeded snapshot test").all()

    run_seed_demo_snapshots(args)
    assert len(repo.latest_candidate_snapshots(limit=20)) == len(seeded)

    run_update_snapshots(Namespace(config=str(config_path), limit=50))
    updated = repo.latest_candidate_snapshots(limit=20)
    outcomes = set(updated["outcome_label"].dropna())
    assert outcomes - {"insufficient_future_data"}
    assert "target_hit" in outcomes or "stop_hit" in outcomes or "partial_move" in outcomes


def test_watch_mode_one_cycle_creates_snapshots_updates_and_no_paper_trades(tmp_path: Path):
    database_path = tmp_path / "watch.db"
    universe_path = tmp_path / "universe.yaml"
    stop_file = tmp_path / "STOP_WATCH_MODE"
    config_path = tmp_path / "default_config.yaml"
    universe_path.write_text(
        """
symbols:
  - symbol: PLTR
    tags: [mid_cap, software, breakout_candidate]
    universe_role: primary_candidate
    demo_profile: clean_breakout
csv_path:
filters:
  max_universe_size: 5
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {database_path.as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {(tmp_path / "cache").as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 5
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
candidate_snapshots:
  enabled: true
  min_score: 60
  include_roles: [primary_candidate]
  include_categories: [Breakout Watch, Pullback Watch, Momentum Continuation]
  exclude_categories: [Weak / Avoid, Overextended / Wait, ETF / Benchmark Reference, Invalid Trade Plan]
  include_benchmarks: false
  include_references: false
  allow_invalid_trade_plans: false
  dedupe_minutes: 0
snapshot_followup:
  same_bar_target_stop_policy: conservative_stop_first
  expire_after_trading_days: 20
scheduled_watch:
  enabled: true
  interval_minutes: 0
  run_snapshot_update_after_scan: true
  max_cycles: 1
  market_hours_only: false
  start_time: "09:35"
  end_time: "16:10"
  timezone: "America/New_York"
  write_heartbeat_log: true
  stop_file: {stop_file.as_posix()}
tony_stocks:
  enabled: true
  agent_name: "Tony Stocks"
  mode: "watcher"
  create_events_for: [scan_started, scan_completed, snapshots_created, snapshots_updated, high_score_candidate, outcome_updated, warning_summary, watch_cycle_completed, intraday_analysis_summary]
  high_score_threshold: 60
  include_seeded_demo_events: false
  max_events_per_cycle: 20
""",
        encoding="utf-8",
    )

    settings = load_scanner_settings(config_path)
    assert settings.scheduled_watch
    assert settings.scheduled_watch["interval_minutes"] == 0

    summary = run_watch(Namespace(config=str(config_path), max_cycles=1, once=False))

    from trading_bot.storage.repositories import ScannerRepository

    repo = ScannerRepository(database_path)
    snapshots = repo.latest_candidate_snapshots()
    assert summary["cycles_completed"] == 1
    assert summary["stopped_by"] == "max_cycles"
    assert len(snapshots) == 1
    assert snapshots.iloc[0]["symbol"] == "PLTR"
    assert snapshots.iloc[0]["last_checked_at"]
    assert repo.paper_trades().empty
    events = repo.list_tony_events(limit=50)
    event_types = set(events["event_type"])
    assert "scan_completed" in event_types
    assert "watch_cycle_completed" in event_types
    assert "high_score_candidate" in event_types


def test_watch_mode_stops_before_cycle_when_stop_file_exists(tmp_path: Path):
    database_path = tmp_path / "watch.db"
    universe_path = tmp_path / "universe.yaml"
    stop_file = tmp_path / "STOP_WATCH_MODE"
    config_path = tmp_path / "default_config.yaml"
    stop_file.write_text("stop", encoding="utf-8")
    universe_path.write_text(
        """
symbols:
  - symbol: PLTR
    tags: [mid_cap, software, breakout_candidate]
    universe_role: primary_candidate
    demo_profile: clean_breakout
csv_path:
filters:
  max_universe_size: 5
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {database_path.as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {(tmp_path / "cache").as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 5
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
scheduled_watch:
  enabled: true
  interval_minutes: 0
  run_snapshot_update_after_scan: false
  max_cycles: 3
  market_hours_only: false
  stop_file: {stop_file.as_posix()}
""",
        encoding="utf-8",
    )

    summary = run_watch(Namespace(config=str(config_path), max_cycles=3, once=False))

    assert summary["cycles_completed"] == 0
    assert summary["stopped_by"] == "stop_file"


def test_outcome_analytics_cli_prints_summary(tmp_path: Path, capsys):
    database_path = tmp_path / "scanner.db"
    config_path = tmp_path / "default_config.yaml"
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {database_path.as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {(tmp_path / "cache").as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 5
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: config/universe_swing_research_config.yaml
tony_stocks:
  enabled: true
  create_events_for: [outcome_analytics_updated]
  max_events_per_cycle: 5
""",
        encoding="utf-8",
    )
    from tests.test_database import sample_scored_stock
    from trading_bot.storage.repositories import ScannerRepository

    repo = ScannerRepository(database_path)
    run_id = repo.create_scan_run(1, "demo_generated", {})
    ids = repo.create_candidate_snapshots(
        run_id,
        [sample_scored_stock("PLTR")],
        {"enabled": True, "min_score": 0, "include_roles": ["primary_candidate"], "include_categories": ["Breakout Watch"]},
    )
    repo.update_candidate_snapshot_followup(ids[0], outcome_label="target_hit", entry_triggered=1)

    run_outcome_analytics(Namespace(config=str(config_path), include_seeded=False, days=None, group_by=["setup_category"], min_score=None))
    output = capsys.readouterr().out

    assert "Outcome analytics" in output
    assert "Seeded demo fixture rows are excluded by default." in output
    assert "Breakout Watch" in output
    assert repo.count_tony_events(event_type="outcome_analytics_updated") == 1


def test_data_check_supports_intraday_timeframe_in_demo_mode(tmp_path: Path, capsys):
    config_path = tmp_path / "default_config.yaml"
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {(tmp_path / "scanner.db").as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {(tmp_path / "cache").as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 5
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: config/universe_swing_research_config.yaml
intraday:
  enabled: false
  timeframe: 5Min
  lookback_days: 5
  use_for_scoring: false
  use_for_tony_analysis: true
  require_real_provider: true
  allow_demo_fallback: false
""",
        encoding="utf-8",
    )
    settings = load_scanner_settings(config_path)
    assert settings.intraday
    assert settings.intraday["timeframe"] == "5Min"

    run_data_check(Namespace(config=str(config_path), symbol="PLTR", symbols="PLTR,SOFI", lookback_days=1, timeframe="5Min"))
    output = capsys.readouterr().out
    assert "Requested timeframe: 5Min" in output
    assert "Intraday read:" in output
    assert "VWAP:" in output


def test_scan_intraday_enabled_attaches_tony_reads_to_snapshots(tmp_path: Path):
    database_path = tmp_path / "scanner.db"
    universe_path = tmp_path / "universe.yaml"
    config_path = tmp_path / "default_config.yaml"
    universe_path.write_text(
        """
symbols:
  - symbol: PLTR
    tags: [mid_cap, software, breakout_candidate]
    universe_role: primary_candidate
    demo_profile: clean_breakout
csv_path:
filters:
  max_universe_size: 5
""",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
provider: demo_generated
database_path: {database_path.as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {(tmp_path / "cache").as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
lookback_days: 120
timeframe: daily
max_symbols: 5
min_price: 1
max_price: 1000
min_avg_volume: 100000
min_dollar_volume: 1000000
score_threshold_watchlist: 70
score_threshold_high_quality: 80
live_trading_enabled: false
scoring_config_path: config/scoring_config.yaml
universe_config_path: {universe_path.as_posix()}
candidate_snapshots:
  enabled: true
  min_score: 60
  include_roles: [primary_candidate]
  include_categories: [Breakout Watch, Pullback Watch, Momentum Continuation]
  exclude_categories: [Weak / Avoid, Overextended / Wait, ETF / Benchmark Reference, Invalid Trade Plan]
  include_benchmarks: false
  include_references: false
  allow_invalid_trade_plans: false
  dedupe_minutes: 0
intraday:
  enabled: true
  timeframe: 5Min
  lookback_days: 2
  max_symbols_per_cycle: 5
  use_for_scoring: false
  use_for_tony_analysis: true
  require_real_provider: false
  allow_demo_fallback: true
tony_stocks:
  enabled: true
  agent_name: "Tony Stocks"
  mode: "watcher"
  create_events_for: [scan_started, scan_completed, snapshots_created, analyst_candidate_hypothesis, intraday_analysis_summary]
  high_score_threshold: 60
  include_seeded_demo_events: false
  max_events_per_cycle: 20
""",
        encoding="utf-8",
    )

    summary = run_scan(Namespace(config=str(config_path), symbols="", save_snapshots=True))

    from trading_bot.storage.repositories import ScannerRepository

    repo = ScannerRepository(database_path)
    snapshots = repo.latest_candidate_snapshots()
    assert len(snapshots) == 1
    row = snapshots.iloc[0]
    assert row["tony_intraday_read"] not in (None, "", "nan")
    assert row["intraday_timeframe"] == "5Min"
    assert row["intraday_close"] is not None
    assert summary["intraday_analysis"]["symbols_requested"] == 1
    assert summary["intraday_analysis"]["symbols_with_intraday"] == 1
    events = repo.list_tony_events(event_type="intraday_analysis_summary", limit=5)
    assert len(events) == 1
    assert repo.paper_trades().empty


def test_intraday_summary_counts_reads_without_orders():
    features = {
        "PLTR": IntradayFeatures(
            symbol="PLTR",
            timeframe="5Min",
            data_available=True,
            status="ok",
            latest_close=105,
            day_open=100,
            high_of_day=105,
            low_of_day=99,
            vwap=102,
            price_above_vwap=True,
            opening_range_breakout_candidate=True,
        ),
        "SOFI": IntradayFeatures(
            symbol="SOFI",
            timeframe="5Min",
            data_available=True,
            status="ok",
            latest_close=95,
            day_open=100,
            high_of_day=101,
            low_of_day=94,
            vwap=98,
            price_above_vwap=False,
            opening_range_breakdown_warning=True,
        ),
        "HOOD": IntradayFeatures(symbol="HOOD", timeframe="5Min", data_available=False, status="intraday_data_missing"),
    }

    summary = _build_intraday_summary("5Min", ["PLTR", "SOFI", "HOOD"], features, fallback_count=1)

    assert summary["symbols_requested"] == 3
    assert summary["symbols_with_intraday"] == 2
    assert summary["missing_count"] == 1
    assert summary["intraday_fallback_count"] == 1
    assert summary["above_vwap_count"] == 1
    assert summary["below_vwap_count"] == 1
    assert summary["opening_range_breakout_count"] == 1
    assert summary["opening_range_breakdown_count"] == 1
