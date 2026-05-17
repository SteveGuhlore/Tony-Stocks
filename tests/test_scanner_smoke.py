from argparse import Namespace
from pathlib import Path

import pandas as pd

from trading_bot.cli import run_scan, run_seed_demo_snapshots, run_update_snapshots, run_watch
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
