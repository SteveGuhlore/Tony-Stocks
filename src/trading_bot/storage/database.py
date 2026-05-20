from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    universe_count INTEGER NOT NULL,
    provider TEXT NOT NULL,
    config_snapshot_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    final_score REAL NOT NULL,
    setup_category TEXT NOT NULL DEFAULT 'Uncategorized',
    tags_json TEXT NOT NULL DEFAULT '[]',
    universe_role TEXT NOT NULL DEFAULT 'primary_candidate',
    name TEXT NOT NULL DEFAULT '',
    sector TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    demo_profile TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    candidate_summary TEXT NOT NULL DEFAULT '',
    trend_score REAL NOT NULL,
    momentum_score REAL NOT NULL,
    volume_score REAL NOT NULL,
    risk_score REAL NOT NULL,
    setup_quality_score REAL NOT NULL,
    latest_close REAL NOT NULL,
    avg_volume_20 REAL NOT NULL,
    dollar_volume_20 REAL NOT NULL,
    return_5d REAL NOT NULL,
    return_10d REAL NOT NULL DEFAULT 0,
    return_20d REAL NOT NULL,
    atr_14 REAL NOT NULL,
    atr_percent REAL NOT NULL DEFAULT 0,
    volatility_20d REAL NOT NULL,
    relative_volume REAL NOT NULL DEFAULT 0,
    suggested_entry REAL NOT NULL,
    suggested_stop REAL NOT NULL,
    suggested_target_1 REAL NOT NULL,
    risk_reward_ratio REAL NOT NULL,
    trade_plan_valid INTEGER NOT NULL DEFAULT 1,
    trade_plan_status TEXT NOT NULL DEFAULT 'valid',
    reasons_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id)
);

CREATE TABLE IF NOT EXISTS manual_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    scan_run_id INTEGER,
    picked_at TEXT NOT NULL,
    planned_entry REAL,
    planned_stop REAL,
    planned_target REAL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'watching',
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id)
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    picked_at TEXT,
    entry_date TEXT,
    entry_price REAL,
    stop_price REAL,
    target_price REAL,
    exit_date TEXT,
    exit_price REAL,
    shares REAL,
    pnl REAL,
    pnl_pct REAL,
    status TEXT NOT NULL DEFAULT 'open',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS candidate_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    universe_role TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    setup_category TEXT NOT NULL,
    total_score REAL NOT NULL,
    close REAL NOT NULL,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    target REAL NOT NULL,
    risk_reward REAL NOT NULL,
    trade_plan_valid INTEGER NOT NULL DEFAULT 1,
    trade_plan_status TEXT NOT NULL DEFAULT 'valid',
    dollar_volume REAL NOT NULL,
    relative_volume REAL NOT NULL,
    atr_percent REAL NOT NULL,
    reasons_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    candidate_summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open/watch',
    entry_trigger_price REAL,
    entry_triggered INTEGER NOT NULL DEFAULT 0,
    entry_triggered_at TEXT,
    highest_price_seen REAL,
    lowest_price_seen REAL,
    last_checked_at TEXT,
    result_1h REAL,
    result_eod REAL,
    result_3d REAL,
    result_5d REAL,
    result_10d REAL,
    result_20d REAL,
    outcome_label TEXT,
    notes TEXT,
    tony_priority_label TEXT,
    tony_recommended_action TEXT,
    tony_setup_read TEXT,
    tony_volume_read TEXT,
    tony_risk_read TEXT,
    tony_market_context_read TEXT,
    tony_data_quality_read TEXT,
    tony_outcome_context TEXT,
    tony_hypothesis TEXT,
    tony_reasons_json TEXT,
    tony_concerns_json TEXT,
    tony_analysis_version TEXT,
    tony_intraday_read TEXT,
    intraday_timeframe TEXT,
    intraday_close REAL,
    intraday_vwap REAL,
    intraday_above_vwap INTEGER,
    intraday_day_change_percent REAL,
    intraday_relative_volume REAL,
    intraday_opening_range_status TEXT,
    data_source TEXT,
    data_source_provider TEXT,
    used_demo_data INTEGER,
    used_fallback_data INTEGER,
    real_data_only_run INTEGER,
    missing_real_data_reason TEXT,
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id)
);

CREATE TABLE IF NOT EXISTS tony_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    symbol TEXT,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    dismissed INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS watch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    last_heartbeat_at TEXT,
    stopped_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    stop_reason TEXT,
    provider TEXT NOT NULL DEFAULT '',
    interval_minutes REAL NOT NULL DEFAULT 5,
    market_hours_only INTEGER NOT NULL DEFAULT 0,
    cycles_completed INTEGER NOT NULL DEFAULT 0,
    latest_scan_run_id INTEGER,
    latest_symbols_selected INTEGER,
    latest_symbols_scored INTEGER,
    latest_snapshots_created INTEGER,
    latest_api_requests_used INTEGER,
    latest_rate_limit_warnings INTEGER,
    latest_fallback_count INTEGER,
    latest_error_message TEXT
);
"""


MIGRATIONS = (
    "ALTER TABLE scan_results ADD COLUMN setup_category TEXT NOT NULL DEFAULT 'Uncategorized'",
    "ALTER TABLE scan_results ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE scan_results ADD COLUMN universe_role TEXT NOT NULL DEFAULT 'primary_candidate'",
    "ALTER TABLE scan_results ADD COLUMN name TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE scan_results ADD COLUMN sector TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE scan_results ADD COLUMN industry TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE scan_results ADD COLUMN demo_profile TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE scan_results ADD COLUMN notes TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE scan_results ADD COLUMN candidate_summary TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE scan_results ADD COLUMN return_10d REAL NOT NULL DEFAULT 0",
    "ALTER TABLE scan_results ADD COLUMN atr_percent REAL NOT NULL DEFAULT 0",
    "ALTER TABLE scan_results ADD COLUMN relative_volume REAL NOT NULL DEFAULT 0",
    "ALTER TABLE scan_results ADD COLUMN trade_plan_valid INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE scan_results ADD COLUMN trade_plan_status TEXT NOT NULL DEFAULT 'valid'",
)


CANDIDATE_SNAPSHOT_MIGRATIONS = (
    "ALTER TABLE candidate_snapshots ADD COLUMN notes TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN trade_plan_valid INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE candidate_snapshots ADD COLUMN trade_plan_status TEXT NOT NULL DEFAULT 'valid'",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_priority_label TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_recommended_action TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_setup_read TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_volume_read TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_risk_read TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_market_context_read TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_data_quality_read TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_outcome_context TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_hypothesis TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_reasons_json TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_concerns_json TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_analysis_version TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tony_intraday_read TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN intraday_timeframe TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN intraday_close REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN intraday_vwap REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN intraday_above_vwap INTEGER",
    "ALTER TABLE candidate_snapshots ADD COLUMN intraday_day_change_percent REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN intraday_relative_volume REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN intraday_opening_range_status TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN data_source TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN data_source_provider TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN used_demo_data INTEGER",
    "ALTER TABLE candidate_snapshots ADD COLUMN used_fallback_data INTEGER",
    "ALTER TABLE candidate_snapshots ADD COLUMN real_data_only_run INTEGER",
    "ALTER TABLE candidate_snapshots ADD COLUMN missing_real_data_reason TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN snapshot_price REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN snapshot_bar_time TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN planned_entry_price REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN planned_entry_rule TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN planned_entry_buffer_pct REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN actual_entry_price REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN actual_entry_time TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN entry_status TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN entry_trigger_source TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN entry_trigger_timeframe TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN entry_trigger_notes TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN original_entry_price REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN original_target_price REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN original_stop_price REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN original_plan_captured_at TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tracking_status TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN tracking_started_at TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN current_price REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN current_price_at TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN research_unrealized_pl_pct REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN current_target_price REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN current_stop_price REAL",
    "ALTER TABLE candidate_snapshots ADD COLUMN reassessment_label TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN reassessment_note TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN last_reassessed_at TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN invalidation_reason TEXT",
    "ALTER TABLE candidate_snapshots ADD COLUMN time_active_minutes INTEGER",
    "ALTER TABLE candidate_snapshots ADD COLUMN pick_phase TEXT",
)

WATCH_RUN_MIGRATIONS: tuple[str, ...] = ()  # reserved for future additive columns


def connect(database_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection and return rows as sqlite Row objects."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(database_path: str | Path) -> None:
    """Create V1 scanner database tables if needed."""
    with connect(database_path) as conn:
        conn.executescript(SCHEMA)
        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(scan_results)").fetchall()
        }
        for statement in MIGRATIONS:
            column_name = statement.split(" ADD COLUMN ", 1)[1].split(" ", 1)[0]
            if column_name not in existing_columns:
                conn.execute(statement)
        snapshot_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(candidate_snapshots)").fetchall()
        }
        for statement in CANDIDATE_SNAPSHOT_MIGRATIONS:
            column_name = statement.split(" ADD COLUMN ", 1)[1].split(" ", 1)[0]
            if column_name not in snapshot_columns:
                conn.execute(statement)
        watch_run_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(watch_runs)").fetchall()
        }
        for statement in WATCH_RUN_MIGRATIONS:
            column_name = statement.split(" ADD COLUMN ", 1)[1].split(" ", 1)[0]
            if column_name not in watch_run_columns:
                conn.execute(statement)
