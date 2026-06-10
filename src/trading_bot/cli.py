from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from trading_bot.analytics import (
    CURRENT_STRATEGY_VERSION,
    OutcomeAnalytics,
    build_daily_tony_memory_summary,
    build_replay_summary,
    build_resolved_outcome_records,
    build_rotation_diagnostics,
    build_signal_scorecard,
    build_strategy_version_report,
    build_terminal_outcome_summary,
    build_tony_self_review,
    market_date_mask,
    new_york_market_date,
)
from trading_bot.backtester import Backtester
from trading_bot.config import load_config
from trading_bot.data import load_csv, load_yfinance, load_yfinance_range
from trading_bot.data.market_data import (
    AlpacaIEXProvider,
    ProviderHealth,
    build_market_data_provider,
    check_provider_health,
)
from trading_bot.data.symbol_quarantine import (
    apply_symbol_quarantine,
    format_quarantine_symbols,
    load_symbol_quarantine_config,
)
from trading_bot.data.universe_rotation import RotationResult, WatchUniverseRotator
from trading_bot.data.universe import load_universe, load_universe_metadata, load_universe_tags
from trading_bot.data.pre_screener import (
    PreScreenResult,
    build_recent_symbol_metrics,
    load_pre_screener_config,
    pre_screen_universe,
)
from trading_bot.intraday import IntradayFeatures, calculate_intraday_features
from trading_bot.logging_config import configure_logging
from trading_bot.risk import RiskManager
from trading_bot.scoring import ScoreEngine, load_scoring_config
from trading_bot.snapshots import (
    ENTRY_STATUS_MISSING_REAL_DATA,
    EntryTriggerSimulationResult,
    build_active_tracking_refresh_updates,
    build_original_plan_freeze_updates,
    calculate_snapshot_followup,
    compute_planned_entry_at_snapshot,
    simulate_entry_trigger,
    summarize_tracked_setup_refresh,
)
from trading_bot.snapshots.seeding import build_demo_seed_snapshots
from trading_bot.strategies import MovingAverageCrossoverStrategy
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.settings import load_scanner_settings, real_data_only_enabled, resolve_effective_provider
from trading_bot.analytics.divergence_calibration import PickRecord, build_divergence_calibration
from trading_bot.analytics.outcomes import score_bucket
from trading_bot.analytics.tony_divergence import teaching_log_path
from trading_bot.tony import TonyStocksService
from trading_bot.tony.analysis import TONY_ANALYSIS_VERSION, MarketContext, analyze_candidates
from trading_bot.utils.time_utils import utc_now_iso
from trading_bot.vault import (
    build_tony_outcomes,
    update_vault_index,
    upsert_ticker_page,
    write_bridge_export,
    write_daily_note,
    write_tony_outcomes,
)


LOGGER = logging.getLogger(__name__)
MARKET_TIMEZONE_LABEL = "America/New_York"
SCAN_SKIP_REASON_KEYS = (
    "liquidity_below_minimums",      # dollar volume below threshold (or legacy combined liquidity)
    "avg_volume_below_minimum",      # average share volume below configured minimum
    "price_outside_bounds",          # latest close outside configured price range
    "not_enough_bars",               # fewer than the required number of OHLCV bars
    "not_enough_data",               # backward-compat: kept for old stored payloads
    "stale_data",                    # data present but Alpaca flagged as stale
    "missing_real_data",             # no real data returned by the provider
    "quarantined",                   # symbol in configured quarantine list
    "no_eligible_setup",             # scored but setup category is weak/invalid/no pattern
    "duplicate_tracked",             # already tracked; skipped by snapshot dedupe
    "other_unknown",                 # score errors or unclassified skips
)

# Human-readable labels for skip reasons (ordered for display).
_SKIP_REASON_LABELS: dict[str, str] = {
    "missing_real_data": "missing real data",
    "quarantined": "quarantined",
    "not_enough_bars": "not enough bars",
    "not_enough_data": "not enough data (legacy)",
    "stale_data": "stale data (scored with stale prices)",
    "avg_volume_below_minimum": "average volume below minimum",
    "liquidity_below_minimums": "dollar volume below minimum",
    "price_outside_bounds": "price outside configured range",
    "no_eligible_setup": "no eligible setup (weak/invalid pattern)",
    "duplicate_tracked": "duplicate / currently tracked",
    "other_unknown": "other / unknown",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trading bot research CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest", help="Run a backtest against historical OHLCV data.")
    source = backtest.add_mutually_exclusive_group(required=False)
    source.add_argument("--ticker", default=None,
                        help="Ticker(s) to fetch via yfinance. Comma-separate for multiple, e.g. SPY,QQQ.")
    source.add_argument("--csv", default=None, help="Path to a local OHLCV CSV file (single symbol).")
    backtest.add_argument("--period", default="1y",
                          help="yfinance download period (e.g. 6mo, 1y, 5y). Ignored when --start/--end set.")
    backtest.add_argument("--start", default=None, help="Start date for historical data (YYYY-MM-DD).")
    backtest.add_argument("--end", default=None, help="End date for historical data (YYYY-MM-DD).")
    backtest.add_argument("--fast-window", type=int, default=None,
                          help="Fast MA window. Overrides config value.")
    backtest.add_argument("--slow-window", type=int, default=None,
                          help="Slow MA window. Overrides config value.")
    backtest.add_argument("--starting-cash", type=float, default=None,
                          help="Starting cash for the backtest. Overrides config value.")
    backtest.add_argument("--save-report", action="store_true",
                          help="Save backtest_report.json and backtest_report.md to --output-dir.")
    backtest.add_argument("--output-dir", default="reports",
                          help="Base directory for saved reports (default: reports/).")
    backtest.add_argument("--config", default="configs/default_config.yaml",
                          help="Path to YAML config file.")

    scan = subparsers.add_parser("scan", help="Run the V1 stock scanner.")
    scan.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    scan.add_argument("--symbols", default="", help="Optional comma-separated symbols to add to the universe.")
    scan.add_argument("--save-snapshots", action="store_true", help="Save eligible candidate snapshots after scanning.")

    snapshot = subparsers.add_parser("snapshot", help="Run a scan and save eligible candidate snapshots.")
    snapshot.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    snapshot.add_argument("--symbols", default="", help="Optional comma-separated symbols to add to the universe.")

    update_snapshots = subparsers.add_parser("update-snapshots", help="Update candidate snapshot follow-up outcomes.")
    update_snapshots.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    update_snapshots.add_argument("--limit", type=int, default=500, help="Maximum open/watch snapshots to check.")

    seed_demo = subparsers.add_parser("seed-demo-snapshots", help="Create demo-only historical snapshots for outcome testing.")
    seed_demo.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    seed_demo.add_argument("--force", action="store_true", help="Allow duplicate demo seeded snapshots.")

    watch = subparsers.add_parser("watch", help="Run scheduled scan/snapshot watch mode.")
    watch.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    watch.add_argument("--max-cycles", type=int, default=None, help="Stop after this many cycles. Useful for tests.")
    watch.add_argument("--once", action="store_true", help="Run one watch cycle and exit.")

    tony_events = subparsers.add_parser("tony-events", help="Print recent Tony Stocks events.")
    tony_events.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    tony_events.add_argument("--limit", type=int, default=20, help="Maximum events to print.")
    tony_events.add_argument("--unacknowledged", action="store_true", help="Only show unacknowledged events.")
    tony_events.add_argument("--severity", default=None, help="Optional severity filter: info, watch, warning, critical.")
    tony_events.add_argument("--event-type", default=None, help="Optional event type filter.")
    tony_events.add_argument("--symbol", default=None, help="Optional symbol filter.")

    outcome_analytics = subparsers.add_parser("outcome-analytics", help="Print candidate snapshot outcome analytics.")
    outcome_analytics.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    outcome_analytics.add_argument("--include-seeded", action="store_true", help="Include demo seeded fixture rows.")
    outcome_analytics.add_argument("--days", type=int, default=None, help="Only include snapshots from the last N days.")
    outcome_analytics.add_argument("--real-only", action="store_true", help="Only include snapshots classified as real rows.")
    outcome_analytics.add_argument("--include-demo", action="store_true", help="Explicitly include old demo-generated rows.")
    outcome_analytics.add_argument("--include-legacy", action="store_true", help="Explicitly include legacy rows with unknown data source.")
    outcome_analytics.add_argument("--exclude-demo", action="store_true", help="Exclude snapshots classified as demo generated rows.")
    outcome_analytics.add_argument("--today", action="store_true", help="Only include snapshots created on today's America/New_York market date.")
    outcome_analytics.add_argument("--date", default=None, help="Only include snapshots from this America/New_York market date (YYYY-MM-DD). Overrides --today.")
    outcome_analytics.add_argument("--provider", default=None, help="Only include snapshots whose scan provider matches this value.")
    outcome_analytics.add_argument(
        "--group-by",
        action="append",
        choices=[
            "setup_category", "score_bucket", "universe_role", "outcome_label", "warning_type", "tag",
            "tony_priority_label", "tony_recommended_action", "tony_setup_read",
            "tony_risk_read", "tony_data_quality_read", "tony_analysis_version",
        ],
        default=None,
        help="Grouping to print. Can be repeated.",
    )
    outcome_analytics.add_argument("--min-score", type=float, default=None, help="Optional minimum snapshot score.")

    data_check = subparsers.add_parser("data-check", help="Test market data provider for one or more symbols. Does not scan or trade.")
    data_check.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    data_check.add_argument("--symbol", default="PLTR", help="Single symbol to test (default: PLTR). Ignored when --symbols is provided.")
    data_check.add_argument("--symbols", default="", help="Comma-separated symbols to test, e.g. PLTR,SOFI,HOOD.")
    data_check.add_argument("--lookback-days", type=int, default=5, help="Lookback days for the test fetch (default: 5).")
    data_check.add_argument("--timeframe", default=None, help="Optional timeframe override, such as 5Min. Does not scan or trade.")

    provider_health = subparsers.add_parser("provider-health", help="Run a provider health check. Does not scan or trade.")
    provider_health.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    provider_health.add_argument("--symbols", default="", help="Comma-separated test symbols (default: PLTR,AAPL,SPY).")
    provider_health.add_argument("--lookback-days", type=int, default=5, help="Lookback days for the health check (default: 5).")
    provider_health.add_argument("--record-event", action="store_true", help="Record the health check result as a Tony Stocks event.")

    eod_report = subparsers.add_parser("eod-report", help="Print a research-only market-day data quality report.")
    eod_report.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    eod_report.add_argument("--date", default=None, help="America/New_York market date to review as YYYY-MM-DD. Defaults to today's market date.")

    after_market = subparsers.add_parser(
        "after-market-review",
        help="Run after-market review: update snapshots, EOD report, outcome analytics, save reports.",
    )
    after_market.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    after_market.add_argument("--date", default=None, help="America/New_York market date as YYYY-MM-DD. Defaults to today.")
    after_market.add_argument("--skip-update-snapshots", action="store_true", help="Skip running update-snapshots before the report.")
    after_market.add_argument("--force-update-snapshots", action="store_true", help="Run update-snapshots even when outside regular market hours.")
    after_market.add_argument("--output-dir", default="reports", help="Base directory for saved reports (default: reports/).")

    backtest_review = subparsers.add_parser(
        "backtest-review",
        help="Research-only backtest review of candidate snapshot outcomes. Does not place trades.",
    )
    backtest_review.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    backtest_review.add_argument("--days", type=int, default=None, help="Only include snapshots from the last N days.")
    backtest_review.add_argument("--save-report", action="store_true", help="Save backtest_review.json and .md to output-dir.")
    backtest_review.add_argument("--output-dir", default="reports", help="Base directory for saved reports (default: reports/).")

    record_decision = subparsers.add_parser(
        "record-suggestion-decision",
        help="Record an approval decision for a pending rule suggestion. Does not apply the suggestion.",
    )
    record_decision.add_argument("--date", default=None, help="America/New_York market date as YYYY-MM-DD. Defaults to today.")
    record_decision.add_argument("--index", type=int, required=True, help="1-based position of the suggestion in the approval package for that date.")
    record_decision.add_argument(
        "--status",
        required=True,
        choices=["approved", "rejected", "needs_review", "applied_later"],
        help="Decision status to record.",
    )
    record_decision.add_argument("--note", default="", help="Optional human note about this decision.")
    record_decision.add_argument("--output-dir", default="reports", help="Base directory where reports are saved (default: reports/).")

    activate_version = subparsers.add_parser(
        "activate-strategy-version",
        help="Key 2: apply an APPROVED weight-calibration proposal to the live scoring weights. Refuses without an approved proposal.",
    )
    activate_version.add_argument("--date", default=None, help="America/New_York market date (YYYY-MM-DD) whose approval package to read. Defaults to today.")
    activate_version.add_argument("--key", default=None, help="suggestion_key of the approved calibration to activate (required only when more than one is approved).")
    activate_version.add_argument("--revert", action="store_true", help="Revert the live weights to the predecessor of the most recent activation.")
    activate_version.add_argument("--output-dir", default="reports", help="Base directory holding reports + suggestion_decisions.json (default: reports/).")
    activate_version.add_argument("--config-dir", default="config", help="Directory holding scoring_config.yaml (default: config/).")

    export_vault = subparsers.add_parser(
        "export-to-vault",
        help="Export latest EOD data to Obsidian vault and bridge. Research only.",
    )
    export_vault.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    export_vault.add_argument("--date", default=None, help="America/New_York market date as YYYY-MM-DD. Defaults to today.")
    export_vault.add_argument("--slot", default=None, choices=["1030", "1300", "1530", "eod"], help="Intraday bridge slot (ET). Omit or 'eod' for the canonical daily drop.")

    emit_outcomes = subparsers.add_parser(
        "emit-outcomes",
        help="Write reports/tony_stocks_outcomes.json from resolved snapshot history. Research only.",
    )
    emit_outcomes.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    emit_outcomes.add_argument("--date", default=None, help="America/New_York market date as YYYY-MM-DD. Defaults to today.")
    emit_outcomes.add_argument("--days", type=int, default=120, help="Lookback window (days) of snapshot history to scan.")

    funnel_eval = subparsers.add_parser(
        "funnel-eval",
        help="Research only: does each funnel stage separate winners from losers in stored outcomes?",
    )
    funnel_eval.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    funnel_eval.add_argument("--days", type=int, default=120, help="Lookback window (days) of snapshot history for signals.")
    funnel_eval.add_argument("--min-sample", type=int, default=5, dest="min_sample", help="Minimum kept/dropped sample per stage before a verdict is given.")
    funnel_eval.add_argument("--save-report", action="store_true", help="Write reports/<date>/funnel_eval.json.")
    funnel_eval.add_argument("--output-dir", default="reports", help="Base directory for saved reports (default: reports/).")

    tony_divergence = subparsers.add_parser(
        "tony-divergence",
        help="Grade Tony's verdicts vs the bot's outcomes into a teaching ledger. Research only; never trades.",
    )
    tony_divergence.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")

    learn_p = subparsers.add_parser(
        "learn",
        help="Nightly self-learning pass: grade outcomes, evolve knowledge, narrate, bridge to CC. Read-only on trading.",
    )
    learn_p.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    learn_p.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default today).")
    learn_p.add_argument("--days", type=int, default=120, help="Lookback window (days) for outcomes/funnel.")
    learn_p.add_argument("--min-sample", type=int, default=None, dest="min_sample",
                         help="Per-dimension sample floor (overrides config learning.min_sample).")
    learn_p.add_argument("--no-llm", action="store_true", help="Force deterministic templates (no Claude call).")
    learn_p.add_argument("--no-bridge", action="store_true", help="Skip pushing the brief to the Command Center.")
    learn_p.add_argument("--reports-dir", default="reports", help="Directory holding outcomes/teaching/funnel JSON.")
    learn_p.add_argument("--vault-dir", default=None, help="Override vault dir (default from config vault.vault_dir).")
    learn_p.add_argument("--command-center-dir", default=None, help="Override CC dir (default from config vault.command_center_dir).")

    off_hours_prep = subparsers.add_parser(
        "off-hours-prep",
        help="Off-hours research prep: scan + enrich + build morning watchlist. Research only; never trades.",
    )
    off_hours_prep.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    off_hours_prep.add_argument("--phase", default=None,
                                help="Override phase (overnight/pre_open/post_close/weekend). Default: derived from clock.")
    off_hours_prep.add_argument("--reports-dir", default="reports", dest="reports_dir",
                                help="Directory for morning_prep report output.")
    off_hours_prep.add_argument("--vault-dir", default=None, dest="vault_dir",
                                help="Vault dir override (default from config vault.vault_dir).")
    off_hours_prep.add_argument("--command-center-dir", default=None, dest="command_center_dir",
                                help="CC dir override (default from config vault.command_center_dir).")

    off_hours_watch = subparsers.add_parser(
        "off-hours-watch",
        help="Inverse watch loop: runs off-hours prep once per phase per ET day; skips during market hours. Research only.",
    )
    off_hours_watch.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    off_hours_watch.add_argument("--max-cycles", type=int, default=None, dest="max_cycles",
                                 help="Maximum loop iterations (for testing / one-shot runs).")
    off_hours_watch.add_argument("--cadence-minutes", type=float, default=None, dest="cadence_minutes",
                                 help="Sleep interval between cycles in minutes (overrides config off_hours.cadence_minutes).")

    paper_status = subparsers.add_parser("paper-status", help="Show paper-trading account/positions status. Read-only.")
    paper_status.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")

    paper_flatten = subparsers.add_parser("paper-flatten", help="Kill switch: close ALL open paper positions.")
    paper_flatten.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")

    paper_check = subparsers.add_parser("paper-check", help="Verify the Alpaca paper account connects (optionally send a test trade).")
    paper_check.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    paper_check.add_argument("--test-order", default=None, metavar="SYMBOL", help="Submit a 1-share test bracket for SYMBOL then flatten it.")

    paper_reprotect = subparsers.add_parser(
        "paper-reprotect",
        help="Re-attach GTC stop/target (OCO) protection to open paper positions whose bracket legs are missing/expired.",
    )
    paper_reprotect.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")

    return parser


def run_backtest(args: argparse.Namespace) -> dict[str, Any]:
    """Run a strategy backtest against yfinance historical data. Research only."""
    config = load_config(args.config)

    _fw = getattr(args, "fast_window", None)
    fast_window = _fw if _fw is not None else config.strategy.fast_window
    _sw = getattr(args, "slow_window", None)
    slow_window = _sw if _sw is not None else config.strategy.slow_window
    _sc = getattr(args, "starting_cash", None)
    starting_cash = float(_sc if _sc is not None else config.backtest.starting_cash)

    strategy = MovingAverageCrossoverStrategy(fast_window=fast_window, slow_window=slow_window)
    risk_manager = RiskManager(
        starting_cash=starting_cash,
        max_position_fraction=config.risk.max_position_fraction,
        max_risk_per_trade_fraction=config.risk.max_risk_per_trade_fraction,
        max_drawdown_fraction=config.risk.max_drawdown_fraction,
        allow_shorting=config.risk.allow_shorting,
        allow_margin=config.risk.allow_margin,
        live_trading_enabled=config.risk.live_trading_enabled,
    )
    backtester = Backtester(
        strategy=strategy,
        risk_manager=risk_manager,
        starting_cash=starting_cash,
        fee_per_trade=config.backtest.fee_per_trade,
        slippage_fraction=config.backtest.slippage_fraction,
    )

    backtest_results: dict[str, Any] = {}

    if getattr(args, "csv", None):
        data = load_csv(args.csv)
        result = backtester.run(data)
        print(f"Data rows: {len(data)}")
        result.print_summary()
        backtest_results["CSV"] = result
    else:
        ticker_str = getattr(args, "ticker", None) or "SPY"
        tickers = [t.strip().upper() for t in ticker_str.split(",") if t.strip()]
        start = getattr(args, "start", None)
        end = getattr(args, "end", None)

        for ticker in tickers:
            if start or end:
                data = load_yfinance_range(ticker, start=start, end=end)
            else:
                data = load_yfinance(ticker=ticker, period=args.period)
            result = backtester.run(data)
            print(f"\n--- {ticker} ---")
            print(f"Data rows: {len(data)}")
            result.print_summary()
            backtest_results[ticker] = result

    if getattr(args, "save_report", False):
        _save_backtest_report(backtest_results, args, strategy.name)

    return {
        "symbols": {
            ticker: {
                "starting_cash": r.metrics.starting_cash,
                "ending_equity": r.metrics.ending_equity,
                "total_return_pct": round(r.metrics.total_return_fraction * 100, 2),
                "max_drawdown_pct": round(r.metrics.max_drawdown_fraction * 100, 2),
                "trade_count": r.metrics.trade_count,
                "win_rate_pct": (
                    round(r.metrics.win_rate_fraction * 100, 2)
                    if r.metrics.win_rate_fraction is not None else None
                ),
            }
            for ticker, r in backtest_results.items()
        }
    }


def _save_backtest_report(
    results: dict[str, Any],
    args: argparse.Namespace,
    strategy_name: str,
) -> None:
    """Save backtest results as JSON and markdown. Research only."""
    from datetime import datetime as _dt
    report_date = _dt.now().strftime("%Y-%m-%d")
    output_base = Path(getattr(args, "output_dir", "reports")) / report_date
    output_base.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "report_date": report_date,
        "strategy": strategy_name,
        "research_only": True,
        "not_applied_note": "This is a research simulation. No orders were placed.",
        "symbols": {
            ticker: {
                "starting_cash": r.metrics.starting_cash,
                "ending_equity": r.metrics.ending_equity,
                "total_return_pct": round(r.metrics.total_return_fraction * 100, 2),
                "max_drawdown_pct": round(r.metrics.max_drawdown_fraction * 100, 2),
                "trade_count": r.metrics.trade_count,
                "win_rate_pct": (
                    round(r.metrics.win_rate_fraction * 100, 2)
                    if r.metrics.win_rate_fraction is not None else None
                ),
            }
            for ticker, r in results.items()
        },
    }
    json_path = output_base / "backtest_report.json"
    md_path = output_base / "backtest_report.md"
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_build_backtest_markdown(summary), encoding="utf-8")
    print(f"\nReport saved: {json_path}")
    print(f"Report saved: {md_path}")


def _build_backtest_markdown(summary: dict[str, Any]) -> str:
    """Build human-readable markdown from a backtest summary dict."""
    lines = [
        f"# Backtest Report — {summary['report_date']}",
        "",
        f"_Strategy: {summary['strategy']}_",
        "",
        "_Research only. Simulated returns using historical data. Not evidence of future performance. No orders placed._",
        "",
        "## Results by Symbol",
        "",
        "| Symbol | Return % | Max DD % | Trades | Win Rate % |",
        "|--------|----------|----------|--------|------------|",
    ]
    for ticker, data in summary.get("symbols", {}).items():
        wr = data.get("win_rate_pct")
        lines.append(
            f"| {ticker} | {data['total_return_pct']:.2f}% | "
            f"{data['max_drawdown_pct']:.2f}% | {data['trade_count']} | "
            f"{'—' if wr is None else f'{wr:.1f}%'} |"
        )
    lines += ["", "_End of report._"]
    return "\n".join(lines)


def run_scan(args: argparse.Namespace) -> dict[str, Any]:
    settings = load_scanner_settings(args.config)
    configure_logging(settings.log_dir)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)

    tags_by_symbol = load_universe_tags(settings.universe_config_path)
    metadata_by_symbol = load_universe_metadata(settings.universe_config_path)
    profiles_by_symbol = {
        symbol: metadata.demo_profile
        for symbol, metadata in metadata_by_symbol.items()
        if metadata.demo_profile
    }
    effective_provider = resolve_effective_provider(settings)
    real_only = real_data_only_enabled(settings)
    if real_only and effective_provider in {"demo_generated", "demo_csv"}:
        raise ValueError(
            f"real_data_only is true; provider {effective_provider!r} is not allowed for scan/watch runs."
        )
    provider = build_market_data_provider(
        effective_provider,
        settings.cache_dir,
        profiles_by_symbol=profiles_by_symbol,
        market_data_config=settings.market_data,
    )

    # Resolve symbol list — rotation result takes priority over universe loading
    override_symbols = getattr(args, "override_symbols", None)
    if override_symbols is not None:
        symbols: list[str] = list(override_symbols)
    else:
        manual_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        symbols = load_universe(settings.universe_config_path, manual_symbols=manual_symbols)
        symbols = symbols[: settings.max_symbols]

    symbols, quarantined_entries = apply_symbol_quarantine(symbols, settings, real_only)
    if quarantined_entries:
        excluded = format_quarantine_symbols(quarantined_entries)
        print(
            f"Symbol quarantine (real-data-only): excluded {len(quarantined_entries)} symbol(s) "
            f"from scan/watch — {excluded}"
        )
        for entry in quarantined_entries:
            print(f"  {entry.symbol}: {entry.reason}")

    # Apply Alpaca per-scan symbol cap and reset cycle state
    if isinstance(provider, AlpacaIEXProvider):
        alpaca_cfg = (settings.market_data or {}).get("alpaca") or {}
        max_alpaca = int(alpaca_cfg.get("max_symbols_per_scan", 175))
        if len(symbols) > max_alpaca:
            LOGGER.info("Alpaca IEX: limiting scan to %d symbols (was %d)", max_alpaca, len(symbols))
            symbols = symbols[:max_alpaca]
        provider.reset_cycle_state()

    scoring_config = load_scoring_config(settings.scoring_config_path)
    engine = ScoreEngine(scoring_config)
    repo = ScannerRepository(settings.database_path)
    tony = TonyStocksService(repo, settings.tony_stocks)
    tony.start_cycle()
    tony.record_scan_started(symbols_loaded=len(symbols), provider=provider.name)

    # --- Fetch OHLCV (batch when available, per-symbol otherwise) ---
    ohlcv_by_symbol: dict[str, Any] = {}
    if isinstance(provider, AlpacaIEXProvider) and provider.batch_requests_enabled and len(symbols) > 1:
        LOGGER.info("Alpaca IEX: batch fetching %d symbols", len(symbols))
        try:
            ohlcv_by_symbol = provider.fetch_ohlcv_batch(symbols, settings.lookback_days, settings.timeframe)
        except Exception as exc:
            LOGGER.warning("Batch fetch failed; marking symbols missing real data: %s", exc)
            if real_only:
                provider.missing_symbols.extend(s.upper() for s in symbols)
                ohlcv_by_symbol = {s: pd.DataFrame(columns=["open", "high", "low", "close", "volume"]) for s in symbols}
            else:
                raise
    else:
        for symbol in symbols:
            try:
                ohlcv_by_symbol[symbol] = provider.fetch_ohlcv(symbol, settings.lookback_days, settings.timeframe)
            except Exception as exc:
                LOGGER.warning("Skipping %s: %s", symbol, exc)
                if isinstance(provider, AlpacaIEXProvider):
                    provider.missing_symbols.append(symbol.upper())

    # --- Filter by price / liquidity ---
    market_data: dict[str, object] = {}
    spy_data = None
    skipped_count = 0
    missing_real_data_symbols: set[str] = set()
    skip_reason_counts: Counter[str] = Counter()
    score_error_count = 0

    for symbol in symbols:
        data = ohlcv_by_symbol.get(symbol)
        if data is None or data.empty:
            if real_only and "alpaca_iex" in provider.name:
                LOGGER.warning("Skipping %s: missing real data", symbol)
                skip_reason_counts["missing_real_data"] += 1
                missing_real_data_symbols.add(symbol.upper())
            else:
                LOGGER.warning("Skipping %s: not enough data", symbol)
                skip_reason_counts["not_enough_data"] += 1
            skipped_count += 1
            continue
        if len(data) < 60:
            LOGGER.warning("Skipping %s: not enough bars (%d)", symbol, len(data))
            skip_reason_counts["not_enough_bars"] += 1
            skipped_count += 1
            continue
        latest_close = float(data["close"].iloc[-1])
        avg_volume_20 = float(data["volume"].tail(20).mean())
        dollar_volume_20 = float((data["close"].tail(20) * data["volume"].tail(20)).mean())
        if not (settings.min_price <= latest_close <= settings.max_price):
            LOGGER.info("Skipping %s: latest close outside configured price bounds", symbol)
            skip_reason_counts["price_outside_bounds"] += 1
            skipped_count += 1
            continue
        if avg_volume_20 < settings.min_avg_volume:
            LOGGER.info("Skipping %s: average volume below minimum", symbol)
            skip_reason_counts["avg_volume_below_minimum"] += 1
            skipped_count += 1
            continue
        if dollar_volume_20 < settings.min_dollar_volume:
            LOGGER.info("Skipping %s: dollar volume below minimum (liquidity)", symbol)
            skip_reason_counts["liquidity_below_minimums"] += 1
            skipped_count += 1
            continue
        market_data[symbol] = data
        if symbol == "SPY":
            spy_data = data

    if spy_data is None and "SPY" not in market_data:
        try:
            spy_data = provider.fetch_ohlcv("SPY", settings.lookback_days, settings.timeframe)
        except Exception:
            spy_data = None

    market_data_source = "real" if "alpaca_iex" in provider.name else "demo"
    if real_only:
        market_data_source = "real"
    results: list[Any] = []
    for symbol, data in market_data.items():
        try:
            results.append(
                engine.score(
                    symbol,
                    data,
                    spy_data=spy_data,
                    tags=tags_by_symbol.get(symbol, ()),
                    metadata=metadata_by_symbol.get(symbol),
                    market_data_source=market_data_source,
                )
            )
        except Exception as exc:
            LOGGER.warning("Could not score %s: %s", symbol, exc)
            score_error_count += 1
            skip_reason_counts["other_unknown"] += 1

    results.sort(key=lambda item: item.final_score, reverse=True)

    _NO_ACTIONABLE_SETUP = frozenset({
        "Weak / Avoid", "Overextended / Wait", "Invalid Trade Plan", "Insufficient Data",
    })
    # Count scored symbols with no actionable setup. These are NOT skipped — they passed
    # all filters and were scored — so they go into a separate "not_scored" bucket rather
    # than skip_reason_counts, which tracks pre-scoring drops only.
    no_eligible_setup_count = sum(
        1 for r in results
        if not str(r.setup_category or "").strip()
        or str(r.setup_category or "").strip() in _NO_ACTIONABLE_SETUP
    )

    scan_run_id = repo.create_scan_run(
        universe_count=len(symbols),
        provider=provider.name,
        config_snapshot=asdict(settings),
    )
    repo.save_scan_results(scan_run_id, results)
    high_priority_symbols = [
        r.symbol for r in results if r.final_score >= settings.score_threshold_high_quality
    ]
    summary: dict[str, Any] = {
        "scan_run_id": scan_run_id,
        "provider": provider.name,
        "symbols_loaded": len(symbols),
        "symbols_scanned": len(market_data),
        "symbols_scored": len(results),
        "symbols_skipped": skipped_count,
        "warnings_count": sum(len(result.warnings) for result in results),
        "high_priority_symbols": high_priority_symbols,
        "real_data_only": real_only,
        "selected_symbols": sorted(str(symbol).upper() for symbol in symbols),
        "scored_symbols": sorted(result.symbol for result in results),
        "quarantined_symbols": [entry.symbol for entry in quarantined_entries],
        "quarantined_count": len(quarantined_entries),
        "skip_reason_counts": {
            key: int(skip_reason_counts.get(key, 0))
            for key in SCAN_SKIP_REASON_KEYS
        },
        "no_eligible_setup_count": no_eligible_setup_count,
        "score_error_count": int(score_error_count),
    }
    if quarantined_entries:
        tony.record_symbol_quarantine_applied(quarantined_entries, real_data_only=real_only)
    if isinstance(provider, AlpacaIEXProvider):
        alpaca_cfg = (settings.market_data or {}).get("alpaca") or {}
        stale_minutes = int(alpaca_cfg.get("stale_data_minutes", 20))
        cycle_stats = provider.get_cycle_stats()
        scanned_count = len(symbols)
        missing_real_data_symbols.update(s.upper() for s in provider.missing_symbols)
        fallback_count = len(provider.fallback_symbols)
        missing_count = len(missing_real_data_symbols)
        real_data_count = max(0, len(market_data) - fallback_count)
        summary["skip_reason_counts"]["missing_real_data"] = max(
            int(summary["skip_reason_counts"].get("missing_real_data", 0)),
            missing_count,
        )
        summary.update({
            "api_requests_used": cycle_stats.get("api_requests_used", 0),
            "batch_requests_used": cycle_stats.get("batch_requests_used", 0),
            "rate_limit_warnings": cycle_stats.get("rate_limit_warnings", 0),
            "batch_mode": cycle_stats.get("batch_mode", False),
            "fallback_count": fallback_count,
            "missing_real_data_count": missing_count,
            "missing_real_data_symbols": sorted(missing_real_data_symbols),
            "real_data_symbols": max(0, len(symbols) - missing_count),
        })
        if real_only and missing_count:
            tony.record_data_provider_fallback(sorted(missing_real_data_symbols), provider.name)
            tony.record_provider_fallback_summary(provider.name, missing_count, scanned_count)
        elif fallback_count > 0 and fallback_count >= scanned_count:
            print(
                f"\nWARNING: ALL {fallback_count} symbol(s) fell back to demo data from {provider.name}. "
                "Scan results reflect demo prices. Check Alpaca keys and connectivity."
            )
            tony.record_all_symbol_fallback(provider.name, fallback_count)
        elif fallback_count > 0:
            tony.record_data_provider_fallback(provider.fallback_symbols, provider.name)
            tony.record_provider_fallback_summary(provider.name, fallback_count, scanned_count)
        if real_data_count > 0:
            tony.record_real_provider_active(provider.name, real_data_count)
            if scanned_count >= 50:
                tony.record_real_data_scan_scaled(
                    provider.name,
                    real_data_count,
                    cycle_stats.get("api_requests_used", 0),
                    cycle_stats.get("batch_requests_used", 0),
                )
        if cycle_stats.get("batch_mode") and scanned_count > 1:
            tony.record_batch_fetch_summary(
                provider.name,
                scanned_count,
                cycle_stats.get("api_requests_used", 0),
                cycle_stats.get("batch_requests_used", 0),
                missing_count if real_only else fallback_count,
            )
        if cycle_stats.get("rate_limit_warnings", 0) > 0:
            rl = provider._rate_limiter
            waits_count = rl.total_waits if rl is not None else 0
            tony.record_rate_limit_warning(provider.name, cycle_stats["rate_limit_warnings"], waits_count)
        tony.record_stale_data_warning(provider.stale_symbols, provider.name, stale_minutes)
        stale_count = len(provider.stale_symbols)
        if stale_count:
            summary["skip_reason_counts"]["stale_data"] = stale_count
            summary["stale_data_count"] = stale_count
            summary["stale_data_symbols"] = sorted(str(s).upper() for s in provider.stale_symbols)
    else:
        summary["real_data_symbols"] = len(market_data)
    summary["skip_reason_counts"]["quarantined"] = len(quarantined_entries)

    # ── Tony analyst reads — run BEFORE snapshot creation so reads attach to new snapshots ──
    # No LLMs, no paper trades, no orders. Tony is analyzing, not trading.
    tony_analyses: dict[str, Any] = {}
    intraday_features_by_symbol: dict[str, IntradayFeatures] = {}
    intraday_cfg = settings.intraday or {}
    intraday_tony_enabled = bool(
        intraday_cfg.get("enabled", False) and intraday_cfg.get("use_for_tony_analysis", True)
    )
    if results and tony.enabled:
        benchmark_rows = [r for r in results if r.universe_role in ("benchmark", "reference")]
        candidate_rows = [r for r in results if r.universe_role not in ("benchmark", "reference")]
        fallback_syms = [] if real_only else (list(provider.fallback_symbols) if isinstance(provider, AlpacaIEXProvider) else [])
        stale_syms = list(provider.stale_symbols) if isinstance(provider, AlpacaIEXProvider) else []
        effective_provider_name = provider.name

        outcome_snaps: Any = None
        try:
            raw_outcome_snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False, limit=2000)
            outcome_snaps = OutcomeAnalytics(raw_outcome_snaps, include_seeded_demo=False, real_only=True).prepared()
        except Exception:
            pass
        intraday_features_by_symbol, intraday_summary = _fetch_intraday_features_for_tony(
            settings=settings,
            provider=provider,
            symbols=[row.symbol for row in candidate_rows],
        )
        if intraday_summary:
            summary["intraday_analysis"] = intraday_summary

        analyses = analyze_candidates(
            candidates=candidate_rows,
            benchmark_rows=benchmark_rows,
            provider_name=effective_provider_name,
            fallback_symbols=fallback_syms,
            stale_symbols=stale_syms,
            outcome_snapshots=outcome_snaps if (outcome_snaps is not None and not outcome_snaps.empty) else None,
            include_seeded_demo=False,
            intraday_features_by_symbol=intraday_features_by_symbol,
            intraday_enabled=intraday_tony_enabled,
            intraday_fallback_symbols=intraday_summary.get("intraday_fallback_symbols", []),
            intraday_stale_symbols=intraday_summary.get("intraday_stale_symbols", []),
        )
        tony_analyses = {
            a.symbol: {
                **a.to_dict(),
                "tony_analysis_version": TONY_ANALYSIS_VERSION,
                **_intraday_snapshot_fields(intraday_features_by_symbol.get(a.symbol)),
                **_snapshot_data_source_fields(provider.name, real_only),
            }
            for a in analyses
        }

        # Market context event (once per scan)
        mkt = MarketContext(benchmark_rows)
        tony.record_analyst_market_context(
            context_label=mkt.context_label(),
            description=mkt.description(),
            benchmark_symbols=[r.symbol for r in benchmark_rows],
        )

        # Data quality summary event (once per scan)
        dq_counts: Counter[str] = Counter(a.data_quality_read for a in analyses)
        dq_summary = dict(dq_counts)
        if intraday_summary:
            # Stale real Alpaca intraday bars still count as intraday_real_alpaca per candidate;
            # expose stale count separately so it matches intraday summary real_intraday counts.
            dq_summary["stale_intraday"] = int(intraday_summary.get("intraday_stale_count", 0) or 0)
        tony.record_analyst_data_quality(
            dq_summary=dq_summary,
            provider_name=effective_provider_name,
            total_candidates=len(analyses),
        )
        if intraday_summary:
            tony.record_intraday_analysis_summary(intraday_summary)

        # Risk warning event (once per scan, for symbols with elevated risk)
        risk_symbols = [a.symbol for a in analyses if a.risk_read in ("wide_atr_concern", "high_volatility_concern", "avoid_invalid_plan")]
        risk_types = [a.risk_read for a in analyses if a.risk_read in ("wide_atr_concern", "high_volatility_concern", "avoid_invalid_plan")]
        tony.record_analyst_risk_warning(risk_symbols, risk_types, effective_provider_name)

        # Hypothesis events for high-priority candidates
        for analysis in analyses:
            if analysis.priority_label in ("high_priority", "watch"):
                tony.record_analyst_candidate_hypothesis(
                    symbol=analysis.symbol,
                    priority_label=analysis.priority_label,
                    recommended_action=analysis.recommended_action,
                    hypothesis=analysis.tony_hypothesis,
                    setup_read=analysis.setup_read,
                    payload=analysis.to_dict(),
                )

    # ── Create candidate snapshots WITH Tony analysis attached ────────────────
    snapshot_ids = []
    if getattr(args, "save_snapshots", False):
        source_fields = _snapshot_data_source_fields(provider.name, real_only)
        entry_trigger_cfg = settings.entry_trigger_simulation or {}
        entry_plans: dict[str, dict[str, Any]] = {}
        for result in results:
            tony_analyses.setdefault(result.symbol, {}).update(source_fields)
            if entry_trigger_cfg.get("enabled", True):
                ta = tony_analyses.get(result.symbol, {})
                features = intraday_features_by_symbol.get(result.symbol) if intraday_tony_enabled else None
                plan = compute_planned_entry_at_snapshot(
                    {
                        "setup_category": result.setup_category,
                        "close": result.latest_close,
                        "intraday_close": ta.get("intraday_close"),
                        "data_source": ta.get("data_source"),
                        "missing_real_data_reason": ta.get("missing_real_data_reason"),
                    },
                    features,
                    None,
                    default_buffer_pct=float(entry_trigger_cfg.get("default_buffer_pct", 0.001)),
                    real_data_only=real_only,
                    data_source=ta.get("data_source"),
                )
                entry_plans[result.symbol] = plan.to_snapshot_fields()
        snapshot_ids = repo.create_candidate_snapshots(
            scan_run_id=scan_run_id,
            results=results,
            snapshot_config=settings.candidate_snapshots or {},
            tony_analyses=tony_analyses,
            entry_plans=entry_plans,
        )
        if entry_plans:
            _print_entry_trigger_planned_summary(entry_plans)

    export_rows = [result.to_dict() for result in results]
    output_path = Path(settings.outputs_dir) / "latest_scan_results.csv"
    if export_rows:
        pd.DataFrame(export_rows).to_csv(output_path, index=False)
    else:
        output_path.write_text("", encoding="utf-8")

    print(f"Scan run id: {scan_run_id}")
    print(f"Provider: {provider.name}")
    print(f"Symbols loaded: {len(symbols)}")
    print(f"Symbols scored: {len(results)}")
    print(f"CSV export: {output_path}")
    if summary.get("intraday_analysis"):
        _print_intraday_summary(summary["intraday_analysis"])
    if getattr(args, "save_snapshots", False):
        _print_snapshot_summary(results=results, snapshot_count=len(snapshot_ids))
    print("\nTop ranked stocks:")
    for result in results[:10]:
        warning_text = f" warnings={len(result.warnings)}" if result.warnings else ""
        print(
            f"{result.symbol:6} score={result.final_score:5.2f} "
            f"category={result.setup_category:25} "
            f"close={result.latest_close:8.2f} entry={result.suggested_entry:8.2f} "
            f"stop={result.suggested_stop:8.2f} target={result.suggested_target_1:8.2f}{warning_text}"
        )

    summary["snapshots_created"] = len(snapshot_ids)
    summary["csv_path"] = str(output_path)
    tony.record_scan_completed(summary, results=results, snapshot_ids=snapshot_ids)
    return summary


def run_update_snapshots(args: argparse.Namespace) -> dict[str, Any]:
    """Update open candidate snapshots from configured OHLCV provider data."""
    settings = load_scanner_settings(args.config)
    configure_logging(settings.log_dir)
    real_only = real_data_only_enabled(settings)
    metadata_by_symbol = load_universe_metadata(settings.universe_config_path)
    profiles_by_symbol = {
        symbol: metadata.demo_profile
        for symbol, metadata in metadata_by_symbol.items()
        if metadata.demo_profile
    }
    provider = build_market_data_provider(
        resolve_effective_provider(settings),
        settings.cache_dir,
        profiles_by_symbol=profiles_by_symbol,
        market_data_config=settings.market_data,
    )
    repo = ScannerRepository(settings.database_path)
    tony = TonyStocksService(repo, settings.tony_stocks)
    tony.start_cycle()
    snapshots = repo.list_open_candidate_snapshots(limit=args.limit)
    followup_config = settings.snapshot_followup or {}
    entry_trigger_cfg = settings.entry_trigger_simulation or {}
    same_bar_policy = str(followup_config.get("same_bar_target_stop_policy", "conservative_stop_first"))
    expire_after = int(followup_config.get("expire_after_trading_days", 20))
    intraday_timeframe = str(entry_trigger_cfg.get("intraday_timeframe", "5Min"))
    trigger_expire = int(entry_trigger_cfg.get("expire_after_trading_days", 1))
    use_planned_fill = bool(entry_trigger_cfg.get("use_planned_price_as_fill", True))
    intraday_lookback = int((settings.intraday or {}).get("lookback_days", 5))

    checked = 0
    updated = 0
    outcomes: dict[str, int] = {}
    triggered_count = 0
    target_count = 0
    stop_count = 0
    insufficient_count = 0
    still_open_count = 0
    entry_status_counts: Counter[str] = Counter()
    planned_with_trigger = 0
    pending_triggers = 0
    expired_no_trigger = 0
    missing_real_trigger = 0
    tracked_refresh_rows: list[dict[str, Any]] = []

    for snapshot in snapshots.to_dict("records"):
        checked += 1
        try:
            working = dict(snapshot)
            intraday_bars = None
            if entry_trigger_cfg.get("enabled", True):
                if not real_only or provider.name == "alpaca_iex":
                    try:
                        intraday_bars = provider.fetch_ohlcv(
                            str(snapshot["symbol"]),
                            max(intraday_lookback, 5),
                            intraday_timeframe,
                        )
                    except Exception as intraday_exc:
                        LOGGER.warning(
                            "Intraday trigger bars unavailable for %s: %s",
                            snapshot.get("symbol"),
                            intraday_exc,
                        )
                if real_only and provider.name != "alpaca_iex":
                    trigger_result = EntryTriggerSimulationResult(
                        entry_status=ENTRY_STATUS_MISSING_REAL_DATA,
                        actual_entry_price=None,
                        actual_entry_time=None,
                        entry_triggered=False,
                        entry_triggered_at=None,
                        entry_trigger_source=working.get("entry_trigger_source"),
                        entry_trigger_timeframe=intraday_timeframe,
                        entry_trigger_notes="Real Alpaca 5Min bars required; demo provider skipped.",
                        last_checked_at=utc_now_iso(),
                    )
                else:
                    trigger_result = simulate_entry_trigger(
                        working,
                        intraday_bars,
                        expire_after_trading_days=trigger_expire,
                        use_planned_price_as_fill=use_planned_fill,
                    )
                repo.update_candidate_snapshot_followup(int(snapshot["id"]), **trigger_result.to_update_fields())
                working.update(trigger_result.to_update_fields())
                entry_status_counts[trigger_result.entry_status] += 1
                if working.get("planned_entry_price") not in (None, ""):
                    planned_with_trigger += 1
                if trigger_result.entry_status == "pending":
                    pending_triggers += 1
                if trigger_result.entry_status in ("expired", "not_triggered"):
                    expired_no_trigger += 1
                if trigger_result.entry_status == "missing_real_data":
                    missing_real_trigger += 1

                freeze_updates = build_original_plan_freeze_updates(working)
                if freeze_updates:
                    repo.update_candidate_snapshot_followup(int(snapshot["id"]), **freeze_updates)
                    working.update(freeze_updates)

            data = provider.fetch_ohlcv(str(snapshot["symbol"]), max(settings.lookback_days, 140, expire_after + 40), settings.timeframe)
            result = calculate_snapshot_followup(
                snapshot=working,
                ohlcv=data,
                same_bar_target_stop_policy=same_bar_policy,
                expire_after_trading_days=expire_after,
            )
            repo.update_candidate_snapshot_followup(int(snapshot["id"]), **result.to_update_fields())
            working.update(result.to_update_fields())

            tracking_updates = build_active_tracking_refresh_updates(
                working,
                intraday_bars,
                real_data_only=real_only,
                provider_name=provider.name,
            )
            if tracking_updates:
                repo.update_candidate_snapshot_followup(int(snapshot["id"]), **tracking_updates)
                working.update(tracking_updates)
                if working.get("original_entry_price") not in (None, ""):
                    tracked_refresh_rows.append(dict(working))

            updated += 1
            outcomes[result.outcome_label] = outcomes.get(result.outcome_label, 0) + 1
            if result.entry_triggered or working.get("entry_status") == "triggered":
                triggered_count += 1
            if "target" in result.outcome_label:
                target_count += 1
            if "stop" in result.outcome_label:
                stop_count += 1
            if result.outcome_label == "insufficient_future_data":
                insufficient_count += 1
            if result.outcome_label == "still_open":
                still_open_count += 1
        except Exception as exc:
            LOGGER.warning("Could not update snapshot %s %s: %s", snapshot.get("id"), snapshot.get("symbol"), exc)

    top_outcomes = ", ".join(f"{label}: {count}" for label, count in sorted(outcomes.items(), key=lambda item: (-item[1], item[0]))[:8])
    print("Candidate snapshot follow-up update")
    print(f"Provider: {provider.name}")
    print(f"Snapshots checked: {checked}")
    print(f"Snapshots updated: {updated}")
    print(f"Planned triggers (with price): {planned_with_trigger}")
    print(f"Triggered entries: {triggered_count}")
    print(f"Pending triggers: {pending_triggers}")
    print(f"Expired/no-trigger: {expired_no_trigger}")
    print(f"Missing real-data triggers: {missing_real_trigger}")
    print(f"Target hit: {target_count}")
    print(f"Stop hit: {stop_count}")
    print(f"Insufficient future data: {insufficient_count}")
    print(f"Still open: {still_open_count}")
    print(f"Top outcomes: {top_outcomes or 'none'}")
    summary = {
        "provider": provider.name,
        "checked": checked,
        "updated": updated,
        "entry_triggered": triggered_count,
        "planned_triggers": planned_with_trigger,
        "pending_triggers": pending_triggers,
        "expired_no_trigger": expired_no_trigger,
        "missing_real_data_triggers": missing_real_trigger,
        "entry_status_counts": dict(entry_status_counts),
        "target_hit": target_count,
        "stop_hit": stop_count,
        "insufficient_future_data": insufficient_count,
        "still_open": still_open_count,
        "outcomes": outcomes,
    }
    tony.record_snapshot_update(summary)
    if entry_trigger_cfg.get("enabled", True):
        tony.record_entry_trigger_summary(summary)
    if tracked_refresh_rows:
        tony.record_tracked_setup_updated(summarize_tracked_setup_refresh(tracked_refresh_rows))
    return summary


def run_seed_demo_snapshots(args: argparse.Namespace) -> None:
    """Seed demo-only historical snapshots for dashboard/outcome testing."""
    settings = load_scanner_settings(args.config)
    configure_logging(settings.log_dir)
    seed_config = settings.demo_snapshot_seed or {}
    if not seed_config.get("enabled", True):
        print("Demo snapshot seeding is disabled in config.")
        return
    metadata_by_symbol = load_universe_metadata(settings.universe_config_path)
    profiles_by_symbol = {
        symbol: metadata.demo_profile
        for symbol, metadata in metadata_by_symbol.items()
        if metadata.demo_profile
    }
    provider = build_market_data_provider(
        resolve_effective_provider(settings),
        settings.cache_dir,
        profiles_by_symbol=profiles_by_symbol,
        market_data_config=settings.market_data,
    )
    repo = ScannerRepository(settings.database_path)
    scan_run_id = repo.create_scan_run(
        universe_count=int(seed_config.get("count", 12)),
        provider=f"{provider.name}_demo_seed",
        config_snapshot={"demo_snapshot_seed": seed_config, "testing_only": True},
    )
    snapshots = build_demo_seed_snapshots(
        provider=provider,
        metadata_by_symbol=metadata_by_symbol,
        scan_run_id=scan_run_id,
        count=int(seed_config.get("count", 12)),
        days_back_start=int(seed_config.get("days_back_start", 25)),
        note_prefix=str(seed_config.get("note_prefix", "Demo seeded snapshot")),
        lookback_days=max(settings.lookback_days, 140),
        timeframe=settings.timeframe,
    )
    dedupe = bool(seed_config.get("dedupe", True)) and not args.force
    created = 0
    skipped = 0
    for snapshot in snapshots:
        snapshot_id = repo.create_demo_candidate_snapshot(snapshot, dedupe=dedupe)
        if snapshot_id is None:
            skipped += 1
        else:
            created += 1

    expected_counts: dict[str, int] = {}
    for snapshot in snapshots:
        note = str(snapshot.get("notes", ""))
        if "expected " in note:
            outcome = note.split("expected ", 1)[1].split(".", 1)[0]
            expected_counts[outcome] = expected_counts.get(outcome, 0) + 1
    summary = ", ".join(f"{outcome}: {count}" for outcome, count in sorted(expected_counts.items()))
    print("Demo snapshot seed")
    print("Testing only: seeded snapshots are not evidence of real market edge.")
    print(f"Scan run id: {scan_run_id}")
    print(f"Snapshots built: {len(snapshots)}")
    print(f"Snapshots created: {created}")
    print(f"Skipped as duplicates: {skipped}")
    print(f"Expected outcome mix: {summary or 'none'}")


def _build_paper_broker(settings: Any) -> tuple[Any, Any]:
    """Build the paper broker if paper_trading is enabled. Returns (broker|None, config).

    Guarded: a missing key / config problem disables paper trading without stopping
    the watch loop. Independent of live_trading_enabled (which stays false).
    """
    from trading_bot.execution import build_alpaca_paper_broker, load_paper_trading_config  # noqa: PLC0415

    cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
    if not cfg.enabled:
        if cfg.disabled_reason:
            print(f"Paper trading disabled (fail-closed): {cfg.disabled_reason}")
        return None, cfg
    try:
        broker = build_alpaca_paper_broker(cfg)
        account = broker.account()
        print(
            f"Paper trading ENABLED — account '{cfg.account_label}': "
            f"equity ${account.equity:,.0f} @ {cfg.base_url}"
        )
        return broker, cfg
    except Exception as exc:  # never break the watch loop on broker init
        print(f"Paper trading could not start ({exc}); continuing without it.")
        LOGGER.warning("Paper broker init failed: %s", exc)
        return None, cfg


def _run_paper_trading_cycle(repo: Any, broker: Any, cfg: Any, now_et: datetime, stop_file_dir: Path) -> None:
    """Submit/reconcile paper trades for one watch cycle. No-op when disabled."""
    if broker is None or not getattr(cfg, "enabled", False):
        return
    from trading_bot.execution import cc_exit_symbols, load_cc_verdicts, run_paper_cycle  # noqa: PLC0415

    try:
        day = now_et.strftime("%Y-%m-%d")
        kill_switch = (stop_file_dir / "STOP_PAPER_TRADING").exists()
        market_open = _is_within_regular_market_hours(now_et)
        picks = repo.triggerable_paper_picks(day=day)
        # CC-verdict exit hook: flatten positions the Command Center says to close/sell.
        cc_exits = cc_exit_symbols(load_cc_verdicts()) if cfg.close_on_command_center_exit else set()
        summary = run_paper_cycle(
            broker=broker, repo=repo, config=cfg, triggered_picks=picks,
            account_label=cfg.account_label, market_open=market_open, kill_switch=kill_switch,
            cc_exits=cc_exits, now_iso=utc_now_iso(), day=day,
        )
        if summary["submitted"] or summary["reconciled"] or summary["cc_closed"] or summary["rejected"]:
            print(
                f"  Paper trading: submitted={len(summary['submitted'])} "
                f"reconciled={len(summary['reconciled'])} cc_closed={len(summary['cc_closed'])} "
                f"rejected={len(summary['rejected'])}"
            )
            for item in summary["submitted"]:
                LOGGER.info("Paper order submitted: %s", item)
            # Surface sector-cap blocks (the new concentration gate) so the operator can see
            # the cap working. Other rejections (duplicate/already-held) are high-volume every
            # cycle, so only the sector-cap reason is logged to avoid spamming the journal.
            sector_capped = sorted(
                {r["symbol"] for r in summary["rejected"]
                 if "sector cap" in str(r.get("reason", "")).lower()}
            )
            if sector_capped:
                LOGGER.info("Paper sector-cap blocked %d pick(s): %s", len(sector_capped), sector_capped)
    except Exception as exc:  # never break the watch loop on a paper-trading error
        LOGGER.warning("Paper trading cycle failed: %s", exc)


def run_watch(args: argparse.Namespace) -> dict[str, Any]:
    """Run scheduled scanning plus candidate snapshot collection.

    This mode only creates scan records and candidate snapshots. It does not
    create paper trades, broker orders, or live orders.
    """
    settings = load_scanner_settings(args.config)
    configure_logging(settings.log_dir)
    repo = ScannerRepository(settings.database_path)
    tony = TonyStocksService(repo, settings.tony_stocks)
    watch_config = settings.scheduled_watch or {}
    if not watch_config.get("enabled", True):
        print("Scheduled Watch Mode is disabled in config.")
        return {"cycles_completed": 0, "stopped_by": "disabled"}

    interval_minutes = float(watch_config.get("interval_minutes", 15) or 0)
    interval_seconds = max(0, int(interval_minutes * 60))
    max_cycles = _resolve_watch_max_cycles(args, watch_config)
    run_updates = bool(watch_config.get("run_snapshot_update_after_scan", True))
    market_hours_only = bool(watch_config.get("market_hours_only", False))
    heartbeat_enabled = bool(watch_config.get("heartbeat_enabled", True))
    stale_heartbeat_minutes = int(watch_config.get("stale_heartbeat_minutes", 10))
    timezone_name = str(watch_config.get("timezone", "America/New_York"))
    stop_file = Path(str(watch_config.get("stop_file", "data/STOP_WATCH_MODE")))
    if not stop_file.is_absolute():
        stop_file = Path.cwd() / stop_file

    effective_provider_name = resolve_effective_provider(settings)
    market_data_cfg = settings.market_data or {}
    alpaca_cfg_watch = market_data_cfg.get("alpaca") or {}
    real_enabled = bool(market_data_cfg.get("real_provider_enabled", False))

    print("Scheduled Watch Mode")
    print("Research mode only: no paper trades, broker execution, or live trading.")
    print(f"Config: {args.config}")
    print(f"Configured provider: {settings.provider}")
    print(f"Effective provider:  {effective_provider_name} (real_provider_enabled={real_enabled})")
    print(f"Real-data-only: {real_data_only_enabled(settings)}")
    if effective_provider_name == "alpaca_iex":
        feed = str(alpaca_cfg_watch.get("feed", "iex")).upper()
        timeframe = str(alpaca_cfg_watch.get("timeframe", "1Day"))
        max_syms = int(alpaca_cfg_watch.get("max_symbols_per_scan", 30))
        print(f"Feed: {feed}  Timeframe: {timeframe}  Max symbols/scan: {max_syms}")
        print("NOTE: Alpaca IEX is a single-exchange feed and may differ from consolidated SIP data.")
        print("      Do not treat Alpaca IEX as full market tape. Research and scanning only.")
    intraday_cfg = settings.intraday or {}
    print(f"Intraday enabled: {bool(intraday_cfg.get('enabled', False))}")
    print(f"Intraday timeframe: {intraday_cfg.get('timeframe', '5Min')}")
    print(f"Intraday use_for_tony_analysis: {bool(intraday_cfg.get('use_for_tony_analysis', True))}")
    print(f"Intraday use_for_scoring: {bool(intraday_cfg.get('use_for_scoring', False))}")
    print(f"Intraday fallback allowed: {bool(intraday_cfg.get('allow_demo_fallback', False))}")
    print(f"Interval minutes: {interval_minutes:g}")
    print(f"Snapshot update after scan: {run_updates}")
    print(f"Max cycles: {max_cycles if max_cycles is not None else 'unlimited'}")
    print(f"Market hours only: {market_hours_only}")
    print(f"Stop file: {stop_file}")
    print(f"To stop cleanly: press Ctrl+C or create the stop file above.")
    LOGGER.info("Scheduled Watch Mode started. interval_minutes=%s max_cycles=%s effective_provider=%s", interval_minutes, max_cycles, effective_provider_name)

    # Universe rotation — initialized once; state carries forward across cycles
    rotation_cfg = settings.watch_universe_rotation or {}
    rotator: WatchUniverseRotator | None = None
    # Funnel state (set below when the funnel is enabled). Declared at function scope
    # so the per-cycle cache-warming step is always bound, even when rotation/funnel
    # are off — otherwise the loop hits an UnboundLocalError.
    funnel_reco_cache = None
    funnel_providers: dict[str, Any] | None = None
    funnel_warm_symbols: list[str] = []
    funnel_enrich_per_run = 0
    if rotation_cfg.get("enabled", False):
        universe_symbols = load_universe(settings.universe_config_path)
        universe_symbols, watch_quarantined = apply_symbol_quarantine(
            universe_symbols,
            settings,
            real_data_only_enabled(settings),
        )
        if watch_quarantined:
            print(
                f"Symbol quarantine: {len(watch_quarantined)} symbol(s) removed from rotation pool — "
                f"{format_quarantine_symbols(watch_quarantined)}"
            )
        # Pre-screener: filter discovery pool using cached scan data.
        # Runs once here — no extra API calls per cycle.
        pre_screener_cfg = load_pre_screener_config(settings.pre_screener)
        pre_screen_result: PreScreenResult | None = None
        if pre_screener_cfg.get("enabled", True) and pre_screener_cfg.get("use_snapshot_cache", True):
            try:
                max_cache_age = int(pre_screener_cfg.get("max_cache_age_days", 7))
                raw_metrics_rows = repo.get_recent_scan_result_metrics(max_age_days=max_cache_age)
                recent_metrics = build_recent_symbol_metrics(
                    raw_metrics_rows, max_cache_age_days=max_cache_age
                )
                pre_screen_result = pre_screen_universe(
                    universe_symbols,
                    recent_metrics=recent_metrics,
                    min_price=float(settings.min_price),
                    max_price=float(settings.max_price),
                    min_avg_volume=float(settings.min_avg_volume),
                    min_symbols_after_filter=int(
                        pre_screener_cfg.get("min_symbols_after_filter", 50)
                    ),
                )
                universe_symbols = pre_screen_result.symbols
                _log_pre_screen_result(pre_screen_result)
            except Exception as exc:
                LOGGER.warning("Pre-screener failed; using full universe list: %s", exc)

        # Research Funnel v2 (default off): rank + shortlist the pre-screened universe
        # via advisory enrichment (earnings blackout, news sentiment, analyst recs).
        # Runs once here; never breaks the loop — any failure falls back to the
        # pre-screened universe. See docs/superpowers/specs/2026-06-03-research-funnel-design.md.
        funnel_cfg = settings.research_funnel or {}
        funnel_enrich_per_run = int(
            funnel_cfg.get("enrich_per_run", funnel_cfg.get("enrich_limit", 50))
        )
        if funnel_cfg.get("enabled", False):
            try:
                from trading_bot.data.research_funnel import FunnelStageConfig, build_funnel
                from trading_bot.data.research_providers import (
                    RecommendationCache,
                    build_providers_from_env,
                    gather_funnel_signals,
                )

                _funnel_today = datetime.now(ZoneInfo("America/New_York")).date()
                funnel_providers = build_providers_from_env()
                funnel_reco_cache = RecommendationCache(
                    Path("reports") / "finnhub_reco_cache.json",
                    ttl_days=int(funnel_cfg.get("reco_cache_ttl_days", 1)),
                ).load()
                # The funnel ranks over this pre-screened set; warm the cache over the
                # same set each cycle so every name eventually carries a score.
                funnel_warm_symbols = list(universe_symbols)
                _signals = gather_funnel_signals(
                    universe_symbols,
                    today=_funnel_today,
                    fmp=funnel_providers["fmp"],
                    finnhub=funnel_providers["finnhub"],
                    enrich_limit=int(funnel_cfg.get("enrich_limit", 150)),
                    earnings_blackout_days=int(funnel_cfg.get("earnings_blackout_days", 0)),
                    use_news_sentiment=bool(funnel_cfg.get("use_news_sentiment", True)),
                    reco_cache=funnel_reco_cache,
                    enrich_per_run=funnel_enrich_per_run,
                )
                _core = {s.upper() for s in (rotation_cfg.get("core_symbols") or [])}
                _funnel = build_funnel(
                    universe_symbols,
                    _signals,
                    FunnelStageConfig.from_dict(funnel_cfg),
                    _funnel_today,
                    always_include=_core,
                )
                universe_symbols = _funnel.shortlist
                _cached_count = sum(
                    1 for s in funnel_warm_symbols if funnel_reco_cache.is_fresh(s, _funnel_today)
                )
                LOGGER.info(
                    "Research funnel applied: %s (reco cache fresh for %d/%d symbols)",
                    _funnel.to_dict(), _cached_count, len(funnel_warm_symbols),
                )
                print(
                    f"Research funnel: {_funnel.to_dict()['stage_counts']} "
                    f"(reco cache {_cached_count}/{len(funnel_warm_symbols)} warm)"
                )
            except Exception as exc:  # never break the watch loop on funnel failure
                LOGGER.warning("Research funnel failed; using pre-screened universe: %s", exc)
                funnel_reco_cache = None
                funnel_providers = None

        rotator = WatchUniverseRotator(universe_symbols, rotation_cfg)
        LOGGER.info(
            "Universe rotation enabled: %d symbols available, max %d per cycle",
            len(universe_symbols),
            rotation_cfg.get("max_symbols_per_cycle", 175),
        )
        print(f"Universe rotation: enabled ({len(universe_symbols)} symbols, max {rotation_cfg.get('max_symbols_per_cycle', 175)}/cycle)")

    # Watch run state — track heartbeat for dashboard monitoring
    watch_run_id: int | None = None
    if heartbeat_enabled:
        prev_run = repo.latest_watch_run()
        if prev_run and prev_run.get("status") == "running":
            prev_hb = prev_run.get("last_heartbeat_at")
            if _is_heartbeat_stale(prev_hb, stale_heartbeat_minutes):
                LOGGER.warning("Previous watch run (id=%s) heartbeat stale; marking as error.", prev_run["id"])
                repo.update_watch_run_error(prev_run["id"], "Process exited without clean shutdown (stale heartbeat detected at restart)")
                tony.record_watch_heartbeat_stale(prev_run["id"], prev_hb or "", stale_heartbeat_minutes)
        watch_run_id = repo.create_watch_run(
            provider=effective_provider_name,
            interval_minutes=interval_minutes,
            market_hours_only=market_hours_only,
        )
        tony.record_watch_run_started(watch_run_id, effective_provider_name, interval_minutes, market_hours_only)

    cycles_completed = 0
    stopped_by = "max_cycles" if max_cycles == 0 else ""
    summaries: list[dict[str, Any]] = []
    _waiting_logged = False
    bridge_emitted_slots: set[str] = set()
    bridge_date: str | None = None
    daily_anchor_date: str | None = None
    paper_broker, paper_cfg = _build_paper_broker(settings)
    try:
        while max_cycles is None or cycles_completed < max_cycles:
            if stop_file.exists():
                stopped_by = "stop_file"
                print(f"Stop file found. Exiting cleanly: {stop_file}")
                LOGGER.info("Stop file detected: %s", stop_file)
                break

            # Intraday/EOD bridge handoffs at US Eastern checkpoints (10:30/13:00/
            # 15:30/16:00). Runs before the market-hours guard so the 16:00 EOD drop
            # still fires after the scan window closes. Resets per Eastern day.
            now_et_bridge = datetime.now(ZoneInfo("America/New_York"))
            et_day = now_et_bridge.strftime("%Y-%m-%d")
            if et_day != bridge_date:
                bridge_date = et_day
                bridge_emitted_slots = set()
            bridge_emitted_slots = _emit_due_bridges(args.config, now_et_bridge, bridge_emitted_slots)

            if market_hours_only and not _within_watch_window(watch_config, timezone_name):
                now_et = datetime.now(ZoneInfo(timezone_name))
                if not _waiting_logged:
                    print(f"Outside configured watch window at {now_et.isoformat()}; waiting.")
                    LOGGER.info("Watch cycle skipped outside configured market window.")
                    tony.start_cycle()
                    tony.record_watch_waiting_for_market_open(timezone_name, now_et.strftime("%H:%M %Z"))
                    _waiting_logged = True
                if max_cycles is not None:
                    cycles_completed += 1
                if not _sleep_until_next_cycle(interval_seconds, stop_file):
                    stopped_by = "stop_file"
                    break
                continue
            else:
                _waiting_logged = False

            cycle_number = cycles_completed + 1
            tony.start_cycle()
            cycle_started = datetime.now(ZoneInfo(timezone_name))
            print(f"\nWatch cycle {cycle_number} started at {cycle_started.isoformat()}")

            # Funnel: warm the analyst-recommendation cache by one budget batch per
            # cycle so the WHOLE universe gets ranked over a few cycles without bursting
            # Finnhub's free ~60/min tier. Fresh entries are skipped, so each cycle
            # advances to the next unwarmed batch. Persists daily; the next watch
            # startup ranks the full universe from cache. Never breaks the loop.
            if funnel_reco_cache is not None and funnel_providers is not None and funnel_warm_symbols:
                try:
                    from trading_bot.data.research_providers import warm_recommendation_cache

                    _warmed = warm_recommendation_cache(
                        funnel_warm_symbols,
                        finnhub=funnel_providers["finnhub"],
                        cache=funnel_reco_cache,
                        today=cycle_started.date(),
                        budget=funnel_enrich_per_run,
                    )
                    if _warmed:
                        LOGGER.info("Funnel reco cache warmed +%d symbols this cycle", _warmed)
                except Exception as exc:  # never break the loop on cache warming
                    LOGGER.warning("Funnel reco cache warm failed: %s", exc)

            # Universe rotation: select symbols for this cycle
            rotation_result: RotationResult | None = None
            if rotator is not None:
                open_snapshots_df = repo.list_open_candidate_snapshots(limit=200)
                open_syms: list[str] = (
                    list(open_snapshots_df["symbol"].dropna().unique())
                    if not open_snapshots_df.empty
                    else []
                )
                rotation_result = rotator.get_cycle_symbols(open_snapshot_symbols=open_syms)
                LOGGER.info(
                    "Rotation bucket %d: %d symbols (core=%d open=%d prev=%d discovery=%d)",
                    rotation_result.bucket_id,
                    rotation_result.total,
                    rotation_result.core_count,
                    rotation_result.open_snapshot_count,
                    rotation_result.previous_candidate_count,
                    rotation_result.discovery_count,
                )
                scan_args = SimpleNamespace(
                    config=args.config,
                    symbols="",
                    save_snapshots=True,
                    override_symbols=rotation_result.symbols,
                )
            else:
                scan_args = SimpleNamespace(config=args.config, symbols="", save_snapshots=True)

            scan_summary = run_scan(scan_args)

            # Update rotator with high-priority symbols for next cycle's continuity
            if rotator is not None and rotation_result is not None:
                high_priority = scan_summary.get("high_priority_symbols", [])
                rotator.update_previous_candidates(high_priority)
                tony.record_universe_rotation_summary(rotation_result.to_dict())

            update_summary: dict[str, Any] | None = None
            if run_updates:
                # Per-cycle refresh is scoped to recent snapshots so a cycle finishes well
                # inside the interval (the full 500-row resolution runs at EOD review).
                update_summary = run_update_snapshots(SimpleNamespace(config=args.config, limit=120))

            # Paper trading: submit risk-sized brackets for today's triggers, reconcile
            # fills -> outcomes. No-op unless paper_trading.enabled. Never breaks the loop.
            _run_paper_trading_cycle(repo, paper_broker, paper_cfg, cycle_started, stop_file.parent)

            # Daily deep-dive anchor: once per ET day after the first scan, so the CC has a
            # full-analysis baseline (a daily YYYY-MM-DD.md) before the intraday light updates.
            et_today = cycle_started.strftime("%Y-%m-%d")
            if daily_anchor_date != et_today and scan_summary.get("scan_run_id"):
                try:
                    _anchor_eod = run_eod_report(SimpleNamespace(config=args.config, date=et_today))
                    _run_vault_export(et_today, _anchor_eod, args.config, slot=None)
                    daily_anchor_date = et_today
                    print(f"Daily bridge anchor dropped for {et_today}")
                except Exception as exc:  # never break the loop on anchor failure
                    LOGGER.warning("Daily anchor emit failed: %s", exc)

            cycles_completed += 1

            warnings_count = int(scan_summary.get("warnings_count", 0))
            snapshots_created = int(scan_summary.get("snapshots_created", 0))
            snapshots_updated = int((update_summary or {}).get("updated", 0))
            next_run = datetime.now(ZoneInfo(timezone_name)) + timedelta(seconds=interval_seconds)
            cycle_summary = {
                "cycle": cycle_number,
                "scan_run_id": scan_summary.get("scan_run_id"),
                "snapshots_created": snapshots_created,
                "snapshots_updated": snapshots_updated,
                "warnings_count": warnings_count,
                "symbols_scanned": scan_summary.get("symbols_scanned", 0),
                "symbols_skipped": scan_summary.get("symbols_skipped", 0),
                "api_requests_used": scan_summary.get("api_requests_used", 0),
                "batch_requests_used": scan_summary.get("batch_requests_used", 0),
                "rate_limit_warnings": scan_summary.get("rate_limit_warnings", 0),
                "rotation_bucket_id": rotation_result.bucket_id if rotation_result else None,
                "intraday_analysis": scan_summary.get("intraday_analysis", {}),
                "next_run_time": next_run.isoformat() if max_cycles is None or cycles_completed < max_cycles else None,
            }
            summaries.append(cycle_summary)
            LOGGER.info("Watch cycle summary: %s", cycle_summary)
            print(
                "Watch cycle summary: "
                f"scan_run_id={cycle_summary['scan_run_id']} "
                f"snapshots_created={snapshots_created} "
                f"snapshots_updated={snapshots_updated} "
                f"warnings={warnings_count}"
            )
            if rotation_result is not None:
                print(
                    f"  Rotation bucket={rotation_result.bucket_id} "
                    f"symbols={rotation_result.total} "
                    f"(core={rotation_result.core_count} open={rotation_result.open_snapshot_count} "
                    f"prev={rotation_result.previous_candidate_count} discovery={rotation_result.discovery_count})"
                )
            if cycle_summary["intraday_analysis"]:
                _print_intraday_summary(cycle_summary["intraday_analysis"], prefix="  ")
            if cycle_summary["next_run_time"]:
                print(f"Next run: {cycle_summary['next_run_time']}")
            tony.record_watch_cycle_completed(cycle_summary)

            # Heartbeat update — update DB state after every cycle
            if heartbeat_enabled and watch_run_id is not None:
                repo.update_watch_run_heartbeat(
                    run_id=watch_run_id,
                    cycles_completed=cycles_completed,
                    latest_scan_run_id=scan_summary.get("scan_run_id"),
                    latest_symbols_selected=scan_summary.get("symbols_loaded"),
                    latest_symbols_scored=scan_summary.get("symbols_scored"),
                    latest_snapshots_created=snapshots_created,
                    latest_api_requests_used=scan_summary.get("api_requests_used"),
                    latest_rate_limit_warnings=scan_summary.get("rate_limit_warnings"),
                    latest_fallback_count=scan_summary.get("fallback_count"),
                )

            if max_cycles is not None and cycles_completed >= max_cycles:
                stopped_by = "max_cycles"
                break
            if not _sleep_until_next_cycle(interval_seconds, stop_file):
                stopped_by = "stop_file"
                break
    except KeyboardInterrupt:
        stopped_by = "keyboard_interrupt"
        print("\nCtrl+C received. Scheduled Watch Mode stopped cleanly.")
    except Exception as exc:
        stopped_by = "error"
        LOGGER.exception("Watch mode stopped due to unexpected error: %s", exc)
        if heartbeat_enabled and watch_run_id is not None:
            repo.update_watch_run_error(watch_run_id, str(exc))
            tony.record_watch_run_error(watch_run_id, str(exc), cycles_completed)
        raise

    stopped_by = stopped_by or "completed"

    # Clean stop — update watch run state and fire Tony event
    if heartbeat_enabled and watch_run_id is not None and stopped_by != "error":
        repo.update_watch_run_stopped(watch_run_id, stopped_by)
        tony.record_watch_run_stopped(watch_run_id, cycles_completed, stopped_by)

    print(f"Scheduled Watch Mode stopped. cycles_completed={cycles_completed} stopped_by={stopped_by}")
    LOGGER.info("Scheduled Watch Mode stopped. cycles_completed=%s stopped_by=%s", cycles_completed, stopped_by)
    return {"cycles_completed": cycles_completed, "stopped_by": stopped_by, "cycle_summaries": summaries}


def run_tony_events(args: argparse.Namespace) -> None:
    """Print recent Tony Stocks internal events."""
    settings = load_scanner_settings(args.config)
    repo = ScannerRepository(settings.database_path)
    tony = TonyStocksService(repo, settings.tony_stocks)
    events = tony.latest_events(
        limit=args.limit,
        severity=args.severity,
        event_type=args.event_type,
        symbol=args.symbol,
        unacknowledged=args.unacknowledged,
    )
    print("Tony Stocks events")
    print("Watcher/analyst only: no paper trades, broker orders, or live trades are placed.")
    if events.empty:
        print("No Tony events found.")
        return
    for row in events.to_dict("records"):
        raw_symbol = row.get("symbol")
        symbol = f" {raw_symbol}" if raw_symbol not in (None, "") and str(raw_symbol).lower() != "nan" else ""
        print(
            f"{row['created_at']} [{row['severity']}] {row['event_type']}{symbol} - "
            f"{row['title']}: {row['message']}"
        )


def run_outcome_analytics(args: argparse.Namespace) -> None:
    """Print research analytics for candidate snapshot outcomes."""
    settings = load_scanner_settings(args.config)
    repo = ScannerRepository(settings.database_path)
    snapshots = repo.list_snapshots_for_analytics(
        include_seeded_demo=args.include_seeded,
        days=args.days,
        min_score=args.min_score,
    )
    explicit_date = getattr(args, "date", None)
    use_today = bool(getattr(args, "today", False)) and not explicit_date
    analytics = OutcomeAnalytics(
        snapshots,
        include_seeded_demo=args.include_seeded,
        real_only=True if getattr(args, "real_only", False) else not (getattr(args, "include_demo", False) or getattr(args, "include_legacy", False)),
        include_demo=bool(getattr(args, "include_demo", False)),
        include_legacy=bool(getattr(args, "include_legacy", False)),
        exclude_demo=bool(getattr(args, "exclude_demo", False)),
        today=use_today,
        provider=getattr(args, "provider", None),
    )
    prepared = analytics.prepared()
    if explicit_date and not prepared.empty and "snapshot_time" in prepared.columns:
        prepared = prepared[market_date_mask(prepared["snapshot_time"], explicit_date)].copy()
    exclusions = analytics.exclusion_counts()
    groups = args.group_by or ["setup_category", "score_bucket", "universe_role", "outcome_label", "warning_type"]

    active_date = explicit_date or (new_york_market_date() if use_today else None)
    print("Outcome analytics")
    print("Research only: analytics evaluate scanner output; they do not create trades or prove an edge.")
    if active_date:
        print(f"Report date: {active_date} {MARKET_TIMEZONE_LABEL}")
    if not getattr(args, "include_demo", False) and not getattr(args, "include_legacy", False):
        print("Real-data rows only. Demo and legacy rows excluded.")
    print(f"Seeded demo rows included: {bool(args.include_seeded)}")
    print(f"Real-only filter: {analytics.real_only}")
    print(f"Include demo rows: {bool(getattr(args, 'include_demo', False))}")
    print(f"Include legacy rows: {bool(getattr(args, 'include_legacy', False))}")
    print(f"Exclude demo filter: {bool(getattr(args, 'exclude_demo', False))}")
    print(f"Today filter: {use_today}")
    if explicit_date:
        print(f"Date filter: {explicit_date} {MARKET_TIMEZONE_LABEL}")
    print(f"Provider filter: {getattr(args, 'provider', None) or 'none'}")
    if args.include_seeded:
        print("Includes seeded demo fixtures; not evidence of real market edge.")
    else:
        print("Seeded demo fixture rows are excluded by default.")
    if not prepared.empty and "data_source_classification" in prepared.columns:
        print("\nData source classification:")
        _print_dataframe(analytics.data_source_counts())
    print("\nExcluded row counts:")
    print(f"Real rows available: {exclusions['real_rows']}")
    print(f"Demo rows excluded: {exclusions['demo_rows_excluded'] if not getattr(args, 'include_demo', False) else 0}")
    print(f"Legacy unknown rows excluded: {exclusions['legacy_unknown_rows_excluded'] if not getattr(args, 'include_legacy', False) else 0}")
    print(f"Fallback/missing rows excluded: {exclusions['missing_real_data_rows_excluded']}")
    print(f"Snapshots reviewed: {len(prepared)}")

    printed_tables: dict[str, pd.DataFrame] = {}
    for group in groups:
        if group == "warning_type":
            table = analytics.warning_type_summary()
        elif group == "tag":
            table = analytics.tag_summary()
        else:
            table = analytics.grouped_by(group)
        printed_tables[group] = table
        print(f"\nBy {group}:")
        _print_dataframe(table)

    outcome_counts = analytics.outcome_counts()
    memory_summary = build_daily_tony_memory_summary(
        prepared,
        reconciliation=None,
        exclusions=exclusions,
    )
    signal_scorecard = build_signal_scorecard(prepared)
    print("\nOutcome counts:")
    _print_dataframe(outcome_counts)
    _print_signal_scorecard(signal_scorecard)

    best_group = _best_target_hit_group(printed_tables.get("setup_category"))
    tony = TonyStocksService(repo, settings.tony_stocks)
    tony.start_cycle()
    tony.record_outcome_analytics(
        {
            "snapshot_count": len(prepared),
            "include_seeded_demo": bool(args.include_seeded),
            "real_only": analytics.real_only,
            "include_demo": bool(getattr(args, "include_demo", False)),
            "include_legacy": bool(getattr(args, "include_legacy", False)),
            "exclude_demo": bool(getattr(args, "exclude_demo", False)),
            "today": bool(getattr(args, "today", False)),
            "provider": getattr(args, "provider", None),
            "groups": groups,
            "best_group": best_group,
        }
    )

    # Tony learning event — count snapshots that have Tony analysis attached
    if not args.include_seeded and analytics.real_only and not getattr(args, "include_demo", False) and not getattr(args, "include_legacy", False):
        analyzed_count = 0
        by_priority: dict[str, Any] = {}
        if not prepared.empty and "tony_analysis_version" in prepared.columns:
            analyzed_count = int(prepared["tony_analysis_version"].notna().sum())
        if not prepared.empty and "tony_priority_label" in prepared.columns:
            pri_counts = prepared["tony_priority_label"].value_counts().to_dict()
            by_priority = {str(k): int(v) for k, v in pri_counts.items()}
        tony.record_tony_learning_updated(
            snapshot_count=len(prepared),
            analyzed_count=analyzed_count,
            by_priority=by_priority,
            memory_summary=memory_summary,
        )

    return {
        "snapshots_reviewed": len(prepared),
        "symbols": sorted(prepared["symbol"].tolist()) if not prepared.empty and "symbol" in prepared.columns else [],
        "date_filter": active_date,
        "signal_scorecard": signal_scorecard,
    }


def run_backtest_review(args: argparse.Namespace) -> dict[str, Any]:
    """Research-only backtest review of candidate snapshot outcomes."""
    from trading_bot.analytics.backtest_review import BacktestReview

    settings = load_scanner_settings(args.config)
    repo = ScannerRepository(settings.database_path)
    snapshots = repo.list_snapshots_for_analytics(
        include_seeded_demo=False,
        days=args.days,
    )

    review = BacktestReview(snapshots)
    result = review.summary()

    print("Backtest Review")
    print(result["research_disclaimer"])
    print(f"Snapshots reviewed: {result['snapshots_reviewed']}")
    print(f"Conclusive outcomes: {result['conclusive_outcomes']}")

    wr = result["win_rate"]
    avg_pl = result["avg_simulated_pl_per_trade"]
    md = result["max_drawdown"]
    print(f"Win rate (conclusive): {f'{wr * 100:.1f}%' if wr is not None else '—  (no conclusive data yet)'}")
    print(f"Avg simulated P/L per trade: {f'{avg_pl * 100:.2f}%' if avg_pl is not None else '—'}")
    print(f"Max simulated drawdown: {f'{md * 100:.1f}%' if md is not None else '—'}")

    print("\nBy Setup Category:")
    _print_dataframe(pd.DataFrame(result["by_setup_category"]))

    print("\nBy Score Bucket:")
    _print_dataframe(pd.DataFrame(result["by_score_bucket"]))

    print("\nBy Universe Role:")
    _print_dataframe(pd.DataFrame(result["by_universe_role"]))

    if getattr(args, "save_report", False):
        report_date = new_york_market_date()
        output_base = Path(args.output_dir) / report_date
        output_base.mkdir(parents=True, exist_ok=True)
        json_path = output_base / "backtest_review.json"
        md_path = output_base / "backtest_review.md"
        json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        md_path.write_text(_build_backtest_review_markdown(result, report_date), encoding="utf-8")
        print(f"\nReport saved: {json_path}")

    return result


def _build_backtest_review_markdown(result: dict[str, Any], date: str) -> str:
    wr = result["win_rate"]
    avg_pl = result["avg_simulated_pl_per_trade"]
    md = result["max_drawdown"]
    lines = [
        f"# Backtest Review — {date}",
        "",
        "_Research only. Simulated from stored scanner outcomes. Not evidence of real market edge. No trades placed._",
        "",
        f"- Snapshots reviewed: {result['snapshots_reviewed']}",
        f"- Conclusive outcomes: {result['conclusive_outcomes']}",
        f"- Win rate (conclusive): {f'{wr * 100:.1f}%' if wr is not None else 'insufficient data'}",
        f"- Avg simulated P/L per trade: {f'{avg_pl * 100:.2f}%' if avg_pl is not None else 'insufficient data'}",
        f"- Max simulated drawdown: {f'{md * 100:.1f}%' if md is not None else 'insufficient data'}",
        "",
    ]
    for label, rows in (
        ("By Setup Category", result.get("by_setup_category", [])),
        ("By Score Bucket", result.get("by_score_bucket", [])),
        ("By Universe Role", result.get("by_universe_role", [])),
    ):
        lines.append(f"## {label}")
        if rows:
            headers = list(rows[0].keys())
            lines.append("| " + " | ".join(str(h) for h in headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in rows:
                lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
        else:
            lines.append("_No data._")
        lines.append("")
    return "\n".join(lines)


def run_eod_report(args: argparse.Namespace) -> dict[str, Any]:
    """Print a research-only end-of-day data quality report."""
    settings = load_scanner_settings(args.config)
    repo = ScannerRepository(settings.database_path)
    report_date = getattr(args, "date", None) or new_york_market_date()
    events = repo.list_tony_events(limit=1000)
    today_events = _events_on_date(events, report_date)
    watch_run, cycles_on_date = _watch_run_summary_for_date(repo, report_date)
    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True, limit=10000)
    analytics = OutcomeAnalytics(snapshots, include_seeded_demo=True, real_only=True)
    classified = analytics.classified_snapshots()
    prepared = analytics.prepared()
    if not classified.empty and "snapshot_time" in classified.columns:
        classified = classified[market_date_mask(classified["snapshot_time"], report_date)].copy()
    if not prepared.empty:
        prepared = prepared[market_date_mask(prepared["snapshot_time"], report_date)].copy()
    source_counts = (
        classified["data_source_classification"]
        .fillna("legacy_unknown")
        .value_counts()
        .to_dict()
        if not classified.empty and "data_source_classification" in classified.columns
        else {}
    )
    exclusions = {
        "demo_rows_excluded": int(source_counts.get("demo_generated", 0)),
        "legacy_unknown_rows_excluded": int(source_counts.get("legacy_unknown", 0)),
        "missing_real_data_rows_excluded": int(source_counts.get("missing_real_data", 0)),
    }
    outcome_counts = _outcome_counts(prepared)
    warning_counts = _warning_counts(prepared)
    reconciliation = _summarize_product_reconciliation(prepared)
    memory_summary = build_daily_tony_memory_summary(
        prepared,
        report_date=report_date,
        reconciliation=reconciliation,
        exclusions=exclusions,
    )
    signal_scorecard = build_signal_scorecard(prepared)
    terminal_outcomes = build_terminal_outcome_summary(prepared)
    scan_coverage = _build_scan_coverage_summary(report_date, repo, settings, today_events)

    latest_watch_status = str(watch_run.get("status", "none")) if watch_run else "none"
    cycles_completed = cycles_on_date
    provider_used = str(watch_run.get("provider", settings.provider)) if watch_run else settings.provider
    symbols_scanned = watch_run.get("latest_symbols_scored") if watch_run else None
    api_requests = watch_run.get("latest_api_requests_used") if watch_run else None

    batch_event = latest_event_of_type_records(today_events, "batch_fetch_summary")
    if batch_event:
        payload = _payload(batch_event)
        provider_used = str(payload.get("provider", provider_used))
        symbols_scanned = payload.get("symbols") or payload.get("symbols_scanned") or payload.get("symbols_fetched") or symbols_scanned
        api_requests = payload.get("api_requests") or payload.get("api_requests_used") or api_requests

    intraday_event = latest_event_of_type_records(today_events, "intraday_analysis_summary")
    intraday_payload = _payload(intraday_event) if intraday_event else {}
    fallback_symbols = repeated_fallback_symbols(today_events)
    quarantine_cfg = load_symbol_quarantine_config(settings)
    configured_quarantine = list(quarantine_cfg.entries)
    real_symbols_scanned = symbols_scanned
    if isinstance(symbols_scanned, int):
        real_symbols_scanned = max(0, symbols_scanned - len(fallback_symbols))
    top_symbols = _top_event_symbols(today_events)
    top_hypotheses = _top_hypotheses(today_events)

    created_today = len(prepared)
    updated_today = int(market_date_mask(prepared["last_checked_at"], report_date).sum()) if not prepared.empty and "last_checked_at" in prepared else 0

    print("End-of-day market data review")
    print("Research only: no trade recommendations, no broker execution, no paper trades, no live trades.")
    print("Tony has no proven edge from this report; it is data-quality review only.")
    print(f"Report date: {report_date} {MARKET_TIMEZONE_LABEL}")
    print(f"Watch cycles completed today: {cycles_completed}")
    print(f"Latest watch status: {latest_watch_status}")
    print(f"Provider used: {provider_used}")
    print(f"Symbols scanned: {symbols_scanned if symbols_scanned is not None else 'unknown'}")
    print(f"API requests: {api_requests if api_requests is not None else 'unknown'}")
    print(f"Real symbols scanned: {real_symbols_scanned if real_symbols_scanned is not None else 'unknown'}")
    print(f"Missing real-data symbols: {', '.join(fallback_symbols) if fallback_symbols else 'none'}")
    print(f"Configured quarantined symbols: {format_quarantine_symbols(configured_quarantine)}")
    if quarantine_cfg.replacement_symbols:
        print(f"Configured replacement symbols: {', '.join(quarantine_cfg.replacement_symbols)}")
    print(f"Real intraday count: {intraday_payload.get('real_intraday_count', 0)}")
    print(f"Stale intraday count: {intraday_payload.get('intraday_stale_count', 0)}")
    print(f"Above VWAP count: {intraday_payload.get('above_vwap_count', 0)}")
    print(f"Below VWAP count: {intraday_payload.get('below_vwap_count', 0)}")
    print(f"Opening range breakout count: {intraday_payload.get('opening_range_breakout_count', 0)}")
    print(f"Opening range breakdown count: {intraday_payload.get('opening_range_breakdown_count', 0)}")
    print(f"Snapshots created today: {created_today}")
    print(f"Snapshots updated today: {updated_today}")
    print(f"Real-only snapshots reviewed: {len(prepared)}")
    print(f"Demo rows excluded: {exclusions['demo_rows_excluded']}")
    print(f"Legacy unknown rows excluded: {exclusions['legacy_unknown_rows_excluded']}")
    print(f"Fallback/missing rows excluded: {exclusions['missing_real_data_rows_excluded']}")
    _print_scan_coverage_summary(scan_coverage)
    print("\nEOD reconciliation (raw history vs product views):")
    print("  Raw rows = full stored history; product rows = deduped, current-state-only view.")
    print(f"Raw snapshot rows kept in history: {reconciliation['raw_snapshot_rows']}")
    print(f"Raw triggered entry rows kept in history: {reconciliation['raw_triggered_entry_rows']}")
    print(f"Product-eligible real rows: {reconciliation['product_eligible_rows']}")
    print(f"Visible product symbols now: {reconciliation['product_visible_symbols']}")
    print(f"Deduped active positions: {reconciliation['deduped_active_positions']}")
    print(f"Deduped waiting picks: {reconciliation['deduped_waiting_picks']}")
    print(f"Deduped closed results: {reconciliation['deduped_closed_results']}")
    print(f"Target hits: {reconciliation['target_hits']}")
    print(f"Stop hits: {reconciliation['stop_hits']}")
    print(f"Partial moves: {reconciliation['partial_moves']}")
    print(f"Pending triggers: {reconciliation['pending_triggers']}")
    print(f"Expired / no trigger: {reconciliation['expired_no_trigger']}")
    print(f"Insufficient data: {reconciliation['insufficient_data']}")
    print(f"Incomplete rows hidden from product views: {reconciliation['incomplete_rows_hidden_from_product_views']}")
    print(f"History rows hidden by dedupe/current-state rules: {reconciliation['history_rows_hidden_from_product_views']}")
    print(f"Missing real-data rows kept in raw history: {exclusions['missing_real_data_rows_excluded']}")
    print(f"Demo rows excluded from product/analytics views: {exclusions['demo_rows_excluded']}")
    print(f"Legacy rows excluded from product/analytics views: {exclusions['legacy_unknown_rows_excluded']}")
    print(f"Top repeated high-priority symbols: {_format_counter(top_symbols)}")
    print(f"Top Tony hypotheses: {_format_counter(top_hypotheses)}")
    print("\nTony memory summary:")
    print("  Research only. This summary is stored for later review and does not auto-apply learning changes.")
    print(f"  Setup counts: {_format_count_dict(memory_summary['setup_counts'])}")
    print(f"  Triggered rows: {memory_summary['triggered_count']}")
    print(f"  Active positions now: {memory_summary['active_count']}")
    print(f"  Closed results now: {memory_summary['closed_count']}")
    print(f"  Target hits: {memory_summary['target_hit_count']}")
    print(f"  Stop hits: {memory_summary['stop_hit_count']}")
    print(f"  Partial moves: {memory_summary['partial_move_count']}")
    print(f"  Reassessment labels: {_format_count_dict(memory_summary['reassessment_label_counts'])}")
    print(f"  Best setup note: {memory_summary['best_setup_note']}")
    print(f"  Worst setup note: {memory_summary['worst_setup_note']}")
    print("  Data-quality notes:")
    for note in memory_summary["data_quality_notes"]:
        print(f"    - {note}")

    self_review = build_tony_self_review(prepared, memory_summary, reconciliation=reconciliation)
    print("\nTony self-review:")
    print("  Research only. No scoring changes. No trigger changes. No trading behavior changes.")
    print(f"  Strongest setup: {self_review['strongest_setup']}")
    print(f"  Weakest setup: {self_review['weakest_setup']}")
    print("  What worked:")
    for item in self_review["what_worked"]:
        print(f"    - {item}")
    print("  What failed:")
    for item in self_review["what_failed"]:
        print(f"    - {item}")
    print("  What needs more data:")
    for item in self_review["needs_more_data"]:
        print(f"    - {item}")
    print("  Same-day summary:")
    print(f"    Deduped active positions: {self_review['deduped_active_positions']}")
    if self_review["active_symbols"]:
        print(f"    Active symbols: {', '.join(self_review['active_symbols'])}")
    print(f"    Waiting picks: {self_review['waiting_picks']}")
    print(f"    Raw triggered rows (history): {self_review['raw_triggered_rows']}")
    print(f"    Pending triggers: {self_review['pending_triggers']}")
    print("  Tomorrow watch:")
    for item in self_review["tomorrow_watch"]:
        print(f"    - {item}")
    strategy_report = build_strategy_version_report(self_review["rule_suggestions"])
    print("  Rule suggestions (research-only, not applied automatically):")
    for s in self_review["rule_suggestions"]:
        print(f"    - [{s['confidence'].upper()}] {s['suggestion']}")
        print(f"      Reason: {s['reason']}")
    print(f"\nStrategy version: {strategy_report['current_version']}")
    print(f"Pending suggestions: {strategy_report['pending_suggestions']}")
    if strategy_report["status_counts"]:
        for status, count in strategy_report["status_counts"].items():
            print(f"  {status}: {count}")
    print(f"Note: {strategy_report['note']}")

    replay = build_replay_summary(prepared)
    print("\nReplay summary (research-only, no behavior changes):")
    print(f"  Strategy version: {replay['strategy_version']}")
    print(f"  Total rows: {replay['total_rows']} | Triggered: {replay['total_triggered']} | Conclusive: {replay['total_conclusive']} | Pending future data: {replay['total_insufficient_future_data']}")
    for entry in replay["setups"]:
        rate_str = f"{entry['target_rate']:.0%}" if entry["target_rate"] is not None else "n/a"
        stop_str = f"{entry['stop_rate']:.0%}" if entry["stop_rate"] is not None else "n/a"
        print(
            f"  {entry['setup']}: triggered={entry['triggered']} "
            f"target={entry['target_hits']} stop={entry['stop_hits']} "
            f"partial={entry['partial_moves']} pending={entry['insufficient_future_data']} "
            f"target_rate={rate_str} stop_rate={stop_str}"
        )
    for note in replay["notes"]:
        print(f"  Note: {note}")
    _print_signal_scorecard(signal_scorecard, header="\nSignal Scorecard:")

    print("\nOutcome counts:")
    _print_dataframe(outcome_counts)
    print("\nWarning counts:")
    _print_dataframe(warning_counts)
    print("\nConfigured symbol quarantine (non-destructive; still in universe YAML):")
    if configured_quarantine:
        for entry in configured_quarantine:
            print(f"  {entry.symbol}: {entry.reason}")
    else:
        print("  none")
    print("\nRepeated missing real-data symbols from today's events:")
    if fallback_symbols:
        for symbol in fallback_symbols:
            in_config = symbol in quarantine_cfg.symbol_set()
            note = " (also in configured quarantine)" if in_config else " (consider adding to symbol_quarantine)"
            print(f"  {symbol}: missing real-data during scan/watch{note}")
    else:
        print("  none")
    print("\nData-quality notes:")
    print("  Active analytics review real-data rows only; demo, missing, and legacy rows are excluded by default.")
    print("  Product dashboard dedupe/hiding changes visibility only; raw candidate snapshot history remains in data/trading_bot.db.")
    print("  Alpaca IEX is a single-exchange feed and may differ from consolidated SIP data.")
    print("  Row-type guide:")
    print("    raw rows          = all stored candidate snapshot history (never deleted)")
    print("    product rows      = deduped, current-state-only view (one per symbol)")
    print("    insufficient_future_data = outcome window still open — not a failure")
    print("    conclusive rows   = rows eligible for target/stop/partial/failure rate calculations")

    tony = TonyStocksService(repo, settings.tony_stocks)
    tony.start_cycle()
    analyzed_count = 0
    if not prepared.empty and "tony_analysis_version" in prepared.columns:
        analyzed_count = int(prepared["tony_analysis_version"].notna().sum())
    tony.record_tony_learning_updated(
        snapshot_count=len(prepared),
        analyzed_count=analyzed_count,
        by_priority=memory_summary["setup_counts"],
        memory_summary={**memory_summary, "self_review": self_review},
    )

    return {
        "date": report_date,
        "cycles_completed": cycles_completed,
        "latest_watch_status": latest_watch_status,
        "provider": provider_used,
        "symbols_scanned": symbols_scanned,
        "real_symbols_scanned": real_symbols_scanned,
        "api_requests": api_requests,
        "fallback_symbols": fallback_symbols,
        "missing_real_data_symbols": fallback_symbols,
        "configured_quarantined_symbols": [entry.symbol for entry in configured_quarantine],
        "configured_quarantine_entries": [entry.to_dict() for entry in configured_quarantine],
        "replacement_symbols": list(quarantine_cfg.replacement_symbols),
        "real_intraday_count": int(intraday_payload.get("real_intraday_count", 0) or 0),
        "stale_intraday_count": int(intraday_payload.get("intraday_stale_count", 0) or 0),
        "snapshots_created_today": created_today,
        "snapshots_updated_today": updated_today,
        "real_only_snapshots_reviewed": len(prepared),
        "demo_rows_excluded": exclusions["demo_rows_excluded"],
        "legacy_unknown_rows_excluded": exclusions["legacy_unknown_rows_excluded"],
        "missing_real_data_rows_excluded": exclusions["missing_real_data_rows_excluded"],
        "reconciliation": reconciliation,
        "tony_memory_summary": memory_summary,
        "tony_self_review": self_review,
        "strategy_version_report": strategy_report,
        "replay_summary": replay,
        "signal_scorecard": signal_scorecard,
        "terminal_outcome_summary": terminal_outcomes,
        "scan_coverage": scan_coverage,
    }


def _build_eod_report_markdown(report_date: str, eod: dict[str, Any]) -> str:
    """Build a markdown summary from the eod-report return dict."""
    lines: list[str] = []
    lines.append(f"# After-Market Review — {report_date}")
    lines.append("")
    lines.append(f"**Report date:** {report_date} America/New_York  ")
    lines.append("**Research only.** No scoring changes, no trading, no suggestions auto-applied.")
    lines.append("")

    # Operational summary
    lines.append("## Operational Summary")
    lines.append(f"- Watch cycles completed: {eod.get('cycles_completed', 0)}")
    lines.append(f"- Latest watch status: {eod.get('latest_watch_status', 'none')}")
    lines.append(f"- Provider: {eod.get('provider', 'unknown')}")
    lines.append(f"- Real-only snapshots reviewed: {eod.get('real_only_snapshots_reviewed', 0)}")
    lines.append(f"- Demo rows excluded: {eod.get('demo_rows_excluded', 0)}")
    lines.append(f"- Legacy rows excluded: {eod.get('legacy_unknown_rows_excluded', 0)}")
    lines.append("")

    coverage = eod.get("scan_coverage") or {}
    if coverage:
        lines.append("## Scan Coverage And Funnel")
        lines.append(f"- Configured universe size: {coverage.get('configured_universe_size', 'unknown') if coverage.get('configured_universe_size') is not None else 'unknown'}")
        lines.append(f"- Symbols selected/loaded: {coverage.get('symbols_selected_loaded', 'unknown') if coverage.get('symbols_selected_loaded') is not None else 'unknown'}")
        lines.append(f"- Real-data symbols: {coverage.get('real_data_symbols', 'unknown') if coverage.get('real_data_symbols') is not None else 'unknown'}")
        lines.append(f"- Scored symbols: {coverage.get('symbols_scored', 'unknown') if coverage.get('symbols_scored') is not None else 'unknown'}")
        lines.append(f"- Not scored: {coverage.get('not_scored_count', 'unknown') if coverage.get('not_scored_count') is not None else 'unknown'}")
        lines.append(f"- Skipped symbols: {coverage.get('symbols_skipped', 'unknown') if coverage.get('symbols_skipped') is not None else 'unknown'}")
        lines.append(f"- Missing real-data symbols: {coverage.get('missing_real_data_count', 0)}")
        lines.append(f"- Quarantined symbols: {coverage.get('quarantined_count', 0)}")
        lines.append(f"- Unique symbols with bar data today (all symbols that returned OHLCV bars across all scan cycles): {coverage.get('unique_symbols_scanned_today', 'unknown') if coverage.get('unique_symbols_scanned_today') is not None else 'unknown'}")
        lines.append(f"- Unique symbols fully scored today: {coverage.get('unique_symbols_scored_today', 'unknown') if coverage.get('unique_symbols_scored_today') is not None else 'unknown'}")
        pct = coverage.get("percent_universe_covered_today")
        lines.append(f"- Percent of universe covered today: {f'{pct:.2f}%' if pct is not None else 'unavailable'}")
        lines.append(
            "- Note: 'bar data' count above includes every symbol that returned OHLCV bars in any scan cycle today. "
            "The rotation diagnostics section below counts only symbols tracked via discovery-rotation metadata — "
            "a subset. The difference between these two counts is expected."
        )
        lines.append(f"- API requests: {coverage.get('api_requests', 'unknown') if coverage.get('api_requests') is not None else 'unknown'}")
        lines.append(f"- Batch requests: {coverage.get('batch_requests', 'unknown') if coverage.get('batch_requests') is not None else 'unknown'}")
        rotation = coverage.get("rotation_bucket_summary") or {}
        if rotation:
            bucket_ids = rotation.get("bucket_ids_today") or []
            lines.append(
                "- Rotation bucket summary: "
                f"latest_bucket={rotation.get('latest_bucket_id', 'unknown')} "
                f"total={rotation.get('latest_total', 'unknown')} "
                f"core={rotation.get('latest_core_count', 'unknown')} "
                f"open={rotation.get('latest_open_snapshot_count', 'unknown')} "
                f"prior={rotation.get('latest_previous_candidate_count', 'unknown')} "
                f"discovery={rotation.get('latest_discovery_count', 'unknown')} "
                f"bucket_ids_today={', '.join(str(item) for item in bucket_ids) if bucket_ids else 'unknown'}"
            )
        skip_counts_md = coverage.get("skip_reason_counts") or {}
        has_skip_data = any(int(v or 0) > 0 for v in skip_counts_md.values())
        if has_skip_data:
            lines.append("- **Skip / not-scored reasons:**")
            for key, label in _SKIP_REASON_LABELS.items():
                count = int(skip_counts_md.get(key, 0) or 0)
                if count or key not in ("not_enough_data", "duplicate_tracked"):
                    lines.append(f"  - {label}: {count}")
        for note in coverage.get("notes") or []:
            lines.append(f"- Note: {note}")
        diag = coverage.get("rotation_diagnostics") or {}
        if diag:
            lines.append("")
            lines.append("### Discovery Rotation Diagnostics")
            lines.append(f"- Note: {diag.get('note', '')}")
            lines.append(
                f"- Unique symbols in rotation tracking (discovery-rotation-selected symbols — "
                f"subset of total bar-data symbols): {diag.get('unique_symbols_scanned', 'unavailable')}"
            )
            lines.append(f"- Total scan appearances: {diag.get('total_scan_appearances', 'unavailable')}")
            lines.append(f"- Symbols with repeat scans: {diag.get('repeat_scan_count', 'unavailable')}")
            pct_u = diag.get("percent_universe_touched")
            lines.append(f"- Percent of configured universe touched: {f'{pct_u:.1f}%' if pct_u is not None else 'unavailable'}")
            fresh = diag.get("estimated_fresh_discovery")
            lines.append(f"- Estimated fresh discovery symbols: {fresh if fresh is not None else 'unavailable'}")
            top = diag.get("top_repeated_symbols") or []
            if top:
                lines.append("- Top repeated symbols:")
                for item in top:
                    label = f" [{item['repeat_label']}]" if item.get("repeat_label") else ""
                    role = f" ({item['universe_role']})" if item.get("universe_role") else ""
                    lines.append(f"  - {item['symbol']}: {item['scan_count']} scans{role}{label}")
            ac = diag.get("active_core_repeats") or []
            if ac:
                lines.append(f"- Active/core expected repeats: {', '.join(r['symbol'] for r in ac)}")
        lines.append("")

    # Reconciliation
    rec = eod.get("reconciliation") or {}
    if rec:
        lines.append("## EOD Reconciliation")
        lines.append(f"- Raw snapshot rows: {rec.get('raw_snapshot_rows', 0)}")
        lines.append(f"- Deduped active positions: {rec.get('deduped_active_positions', 0)}")
        lines.append(f"- Waiting picks: {rec.get('deduped_waiting_picks', 0)}")
        lines.append(f"- Target hits: {rec.get('target_hits', 0)}")
        lines.append(f"- Stop hits: {rec.get('stop_hits', 0)}")
        lines.append(f"- Partial moves: {rec.get('partial_moves', 0)}")
        lines.append(f"- Pending triggers: {rec.get('pending_triggers', 0)}")
        lines.append("")

    # Tony self-review
    sr = eod.get("tony_self_review") or {}
    if sr:
        lines.append("## Tony Self-Review")
        lines.append(f"- **Strongest setup:** {sr.get('strongest_setup', 'none')}")
        lines.append(f"- **Weakest setup:** {sr.get('weakest_setup', 'none')}")
        if sr.get("what_worked"):
            lines.append("### What Worked")
            for item in sr["what_worked"]:
                lines.append(f"- {item}")
        if sr.get("what_failed"):
            lines.append("### What Failed")
            for item in sr["what_failed"]:
                lines.append(f"- {item}")
        if sr.get("needs_more_data"):
            lines.append("### Needs More Data")
            for item in sr["needs_more_data"]:
                lines.append(f"- {item}")
        if sr.get("tomorrow_watch"):
            lines.append("### Tomorrow Watch")
            for item in sr["tomorrow_watch"]:
                lines.append(f"- {item}")
        lines.append("")

    # Rule suggestions
    suggestions = sr.get("rule_suggestions") or []
    if suggestions:
        lines.append("## Rule Suggestions (Research Only — Not Applied)")
        for s in suggestions:
            conf = str(s.get("confidence", "")).upper()
            lines.append(f"- [{conf}] {s.get('suggestion', '')}")
            lines.append(f"  - Reason: {s.get('reason', '')}")
            lines.append(f"  - Status: {s.get('status', 'needs_review')} | Version: {s.get('strategy_version', 'v1')}")
        lines.append("")

    # Strategy version
    sv = eod.get("strategy_version_report") or {}
    if sv:
        lines.append("## Strategy Version")
        lines.append(f"- Current version: {sv.get('current_version', 'v1')}")
        lines.append(f"- Pending suggestions: {sv.get('pending_suggestions', 0)}")
        lines.append(f"- Note: {sv.get('note', '')}")
        lines.append("")

    # Replay summary
    replay = eod.get("replay_summary") or {}
    if replay:
        lines.append("## Replay Summary (Research Only)")
        lines.append(f"- Strategy version: {replay.get('strategy_version', 'v1')}")
        lines.append(f"- Total rows: {replay.get('total_rows', 0)} | Triggered: {replay.get('total_triggered', 0)} | Conclusive: {replay.get('total_conclusive', 0)} | Pending future data: {replay.get('total_insufficient_future_data', 0)}")
        for entry in replay.get("setups") or []:
            rate_str = f"{entry['target_rate']:.0%}" if entry.get("target_rate") is not None else "n/a"
            lines.append(f"- {entry['setup']}: triggered={entry['triggered']} target={entry['target_hits']} stop={entry['stop_hits']} partial={entry['partial_moves']} pending={entry['insufficient_future_data']} target_rate={rate_str}")
        for note in replay.get("notes") or []:
            lines.append(f"- Note: {note}")
        lines.append("")

    scorecard = eod.get("signal_scorecard") or {}
    if scorecard.get("signals"):
        lines.append("## Signal Scorecard")
        lines.append(f"- Note: {scorecard.get('note', '')}")
        for signal in scorecard.get("signals") or []:
            lines.append(f"### {signal.get('signal_label', signal.get('signal_key', 'Signal'))}")
            for row in signal.get("counts") or []:
                lines.append(
                    "- "
                    f"{row.get('signal_value', 'unknown')}: "
                    f"total={row.get('total_rows', 0)} "
                    f"triggered={row.get('triggered_rows', 0)} "
                    f"active={row.get('active_rows', 0)} "
                    f"conclusive={row.get('conclusive_rows', 0)} "
                    f"target={row.get('target_hits', 0)} "
                    f"stop={row.get('stop_hits', 0)} "
                    f"partial={row.get('partial_moves', 0)} "
                    f"pending={row.get('insufficient_future_data', 0)}"
                )
        lines.append("")

    lines.append("---")
    lines.append("*Generated by after-market-review. Research only. No trade recommendations.*")
    return "\n".join(lines)


_DECISIONS_FILENAME = "suggestion_decisions.json"
_VALID_DECISION_STATUSES = {"approved", "rejected", "needs_review", "applied_later"}


def _suggestion_key(suggestion: str, strategy_version: str) -> str:
    """Stable 12-char hex key for a (suggestion, strategy_version) pair."""
    raw = f"{strategy_version}:{suggestion}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _load_suggestion_decisions(output_dir: str) -> dict[str, dict[str, Any]]:
    """Return decisions dict keyed by suggestion_key, or empty dict if file missing."""
    path = Path(output_dir) / _DECISIONS_FILENAME
    if not path.exists():
        return {}
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
        return {r["suggestion_key"]: r for r in records if "suggestion_key" in r}
    except (json.JSONDecodeError, TypeError):
        return {}


def _save_suggestion_decision(output_dir: str, record: dict[str, Any]) -> None:
    """Upsert a decision record into the global decisions file."""
    path = Path(output_dir) / _DECISIONS_FILENAME
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict[str, Any]] = {}
    if path.exists():
        try:
            for r in json.loads(path.read_text(encoding="utf-8")):
                if "suggestion_key" in r:
                    existing[r["suggestion_key"]] = r
        except (json.JSONDecodeError, TypeError):
            pass
    existing[record["suggestion_key"]] = record
    path.write_text(json.dumps(list(existing.values()), indent=2, default=str), encoding="utf-8")


def run_record_suggestion_decision(args: argparse.Namespace) -> dict[str, Any]:
    """Record an approval decision for a pending rule suggestion. Does not apply it."""
    report_date = getattr(args, "date", None) or new_york_market_date()
    output_dir = getattr(args, "output_dir", "reports")
    idx = args.index  # 1-based
    status = args.status
    note = getattr(args, "note", "") or ""

    pkg_path = Path(output_dir) / report_date / "approval_package.json"
    if not pkg_path.exists():
        print(f"No approval package found for {report_date} at {pkg_path}")
        print("Run after-market-review first to generate the approval package.")
        return {"error": "approval_package_not_found", "path": str(pkg_path)}

    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    suggestions = pkg.get("suggestions") or []
    if idx < 1 or idx > len(suggestions):
        print(f"Index {idx} is out of range — package has {len(suggestions)} suggestion(s).")
        return {"error": "index_out_of_range", "count": len(suggestions)}

    s = suggestions[idx - 1]
    key = _suggestion_key(s["suggestion"], s.get("strategy_version", "v1"))

    record = {
        "suggestion_key": key,
        "suggestion": s["suggestion"],
        "reason": s.get("reason", ""),
        "confidence": s.get("confidence", "low"),
        "strategy_version": s.get("strategy_version", "v1"),
        "status": status,
        "decided_at": datetime.now(tz=ZoneInfo("America/New_York")).isoformat(),
        "note": note,
        "date": report_date,
        "not_applied": True,
    }
    _save_suggestion_decision(output_dir, record)

    print(f"Decision recorded: [{status.upper()}] {s['suggestion']}")
    if note:
        print(f"  Note: {note}")
    print("  Approved does not mean applied. No scoring, trigger, or trading behavior has changed.")

    return {"suggestion_key": key, "status": status, "suggestion": s["suggestion"], "not_applied": True}


# --------------------------------------------------------------------------- #
# Divergence calibration (research-only; two-key human gate)                   #
# --------------------------------------------------------------------------- #
def _cal_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def _ny_market_date(ts: Any) -> str:
    """Convert an ISO snapshot timestamp to its America/New_York calendar date (YYYY-MM-DD)."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except (ValueError, TypeError):
        # Unparseable timestamp -> the raw slice may be a wrong (UTC) join key; warn so a
        # systematic drop (e.g. a schema/format change) is visible rather than silent.
        print(f"  [calibration] WARNING: could not parse snapshot_time {ts!r} as ISO; join may be off.")
        return str(ts)[:10]


def _load_pick_records(outcomes_path: str, repo: ScannerRepository) -> tuple[list[PickRecord], int]:
    """Join resolved outcomes with snapshot sub-scores into PickRecords.

    Returns ``(picks, dropped)``. ``dropped`` counts resolved outcomes with no matching
    snapshot sub-score row (e.g. outcomes predating sub-score persistence).
    """
    path = Path(outcomes_path)
    if not path.exists():
        print(f"  [calibration] outcomes file not found: {path} — no picks to calibrate on.")
        return [], 0
    try:
        outcomes = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # A corrupt outcomes file must NOT masquerade as "no data yet" — surface it loudly.
        print(f"  [calibration] WARNING: could not read outcomes file {path}: {exc}")
        return [], 0

    sub = repo.list_snapshot_subscores()
    sub_map: dict[tuple[str, str], dict[str, Any]] = {}
    if not sub.empty:
        for row in sub.to_dict("records"):
            key = (str(row.get("symbol") or "").upper(), _ny_market_date(row.get("snapshot_time")))
            # First row wins; the query's ORDER BY snapshot_time DESC means the most-recent
            # snapshot for a (symbol, date) is encountered first. Do not drop the ORDER BY.
            sub_map.setdefault(key, row)

    picks: list[PickRecord] = []
    dropped = 0
    for o in outcomes or []:
        sym = str(o.get("symbol") or "").upper()
        date = str(o.get("pick_date") or "")
        row = sub_map.get((sym, date))
        if not sym or not date or row is None:
            dropped += 1
            continue
        picks.append(
            PickRecord(
                symbol=sym,
                pick_date=date,
                result=o.get("result"),
                return_pct=_cal_float(o.get("return_pct")),
                setup_category=str(row.get("setup_category") or ""),
                score_band=score_bucket(_cal_float(row.get("total_score")) or 0.0),
                trend_score=float(row.get("trend_score") or 0.0),
                momentum_score=float(row.get("momentum_score") or 0.0),
                volume_score=float(row.get("volume_score") or 0.0),
                risk_score=float(row.get("risk_score") or 0.0),
                setup_quality_score=float(row.get("setup_quality_score") or 0.0),
            )
        )
    return picks, dropped


def _build_weight_proposals(args: argparse.Namespace, strategy_version: str) -> list[dict[str, Any]]:
    """Run divergence calibration; return gate-ready weight-proposal suggestion dicts."""
    settings = load_scanner_settings(args.config)
    repo = ScannerRepository(settings.database_path)
    outcomes_path = os.environ.get("TONY_OUTCOMES_FILE") or "reports/tony_stocks_outcomes.json"
    picks, dropped = _load_pick_records(outcomes_path, repo)
    ledger_path = teaching_log_path()
    try:
        ledger = (
            json.loads(ledger_path.read_text(encoding="utf-8"))
            if ledger_path.exists()
            else {"records": []}
        )
    except (json.JSONDecodeError, OSError) as exc:
        # A corrupt teaching ledger silently yields zero divergence evidence (no proposals
        # forever) — surface it so the operator knows the calibrator is starved, not quiet.
        print(f"  [calibration] WARNING: could not read teaching ledger {ledger_path}: {exc}")
        ledger = {"records": []}
    weights = asdict(load_scoring_config(settings.scoring_config_path).weights)
    report = build_divergence_calibration(picks, ledger, weights, strategy_version=strategy_version)
    print(f"  Calibration: {report.headline} (picks={len(picks)}, dropped={dropped})")
    if dropped > 0 and not picks:
        print(
            f"  [calibration] WARNING: all {dropped} resolved outcome(s) dropped at the "
            "sub-score join — check snapshot coverage or snapshot_time format."
        )

    suggestions: list[dict[str, Any]] = []
    for p in report.proposals:
        d = p.to_dict()
        d["reason"] = (
            f"net_override {p.divergence_evidence['net_override']:+d} on "
            f"{p.cohort_dimension}='{p.cohort}'; separation "
            f"{p.attribution_evidence['separation']} (n={p.attribution_evidence['n']})"
        )
        suggestions.append(d)
    return suggestions


def _strategy_versions_path(output_dir: str) -> Path:
    return Path(output_dir) / "strategy_versions.json"


def _load_strategy_versions(output_dir: str) -> list[dict[str, Any]]:
    path = _strategy_versions_path(output_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # This is the live-write path; losing ledger continuity here resets version lineage.
        print(f"  [calibration] WARNING: strategy_versions.json unreadable ({path}): {exc}")
        return []
    if not isinstance(data, list):
        print(f"  [calibration] WARNING: {path} is valid JSON but not a list ({type(data).__name__}); treating as empty.")
        return []
    return data


def _next_strategy_version(ledger: list[dict[str, Any]]) -> str:
    nums = [
        int(str(e.get("version") or "")[1:])
        for e in ledger
        if str(e.get("version") or "").startswith("v") and str(e.get("version") or "")[1:].isdigit()
    ]
    return f"v{(max(nums) if nums else 1) + 1}"


_WEIGHT_KEY_SET = {
    "trend_weight",
    "momentum_weight",
    "volume_weight",
    "risk_weight",
    "setup_quality_weight",
}


def _validate_weight_set(weights: dict[str, Any]) -> str | None:
    """Return an error string if ``weights`` is unsafe to write to live config, else None.

    The pure calibration core already guarantees valid weights, but activation reads the
    payload from JSON on disk (the approval package), so this is the trust-boundary check
    that prevents a malformed or hand-edited package from corrupting the scoring weights.
    """
    if set(weights) != _WEIGHT_KEY_SET:
        return f"unexpected weight keys: {sorted(weights)} (expected {sorted(_WEIGHT_KEY_SET)})"
    try:
        vals = [float(v) for v in weights.values()]
    except (TypeError, ValueError):
        return "non-numeric weight value"
    if any(v < 0.05 - 1e-9 or v > 0.50 + 1e-9 for v in vals):
        return "a weight is outside the allowed [0.05, 0.50] range"
    if abs(sum(vals) - 1.0) > 1e-6:
        return f"weights sum to {sum(vals):.4f}, not 1.0"
    return None


def _write_scoring_weights(scoring_path: Path, weights: dict[str, float]) -> None:
    """Write only the ``weights:`` block of scoring_config.yaml, preserving everything else.

    Caller MUST validate ``weights`` with ``_validate_weight_set`` first; this raises on an
    invalid set as a defense-in-depth guard so a bad payload is never partially written.
    """
    import yaml

    err = _validate_weight_set(weights)
    if err:
        raise ValueError(f"refusing to write invalid scoring weights: {err}")
    raw: dict[str, Any] = {}
    if scoring_path.exists():
        raw = yaml.safe_load(scoring_path.read_text(encoding="utf-8")) or {}
    else:
        print(f"  [calibration] WARNING: {scoring_path} did not exist; writing a weights-only config.")
    raw["weights"] = {k: float(v) for k, v in weights.items()}
    scoring_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def run_activate_strategy_version(args: argparse.Namespace) -> dict[str, Any]:
    """Key 2 — the SOLE path that writes live scanner weights. Refuses without an approved proposal."""
    import yaml

    output_dir = getattr(args, "output_dir", "reports")
    config_dir = getattr(args, "config_dir", "config")
    report_date = getattr(args, "date", None) or new_york_market_date()
    key = getattr(args, "key", None)
    revert = bool(getattr(args, "revert", False))
    scoring_path = Path(config_dir) / "scoring_config.yaml"
    ledger = _load_strategy_versions(output_dir)

    if revert:
        if not ledger:
            print("Nothing to revert — no strategy version has been activated.")
            return {"error": "nothing_to_revert"}
        tail = ledger[-1]
        prev_w = tail.get("previous_weights") or {}
        if not prev_w:
            return {"error": "no_previous_weights"}
        err = _validate_weight_set(prev_w)
        if err:
            print(f"Refusing to revert — recorded predecessor weights are invalid: {err}")
            return {"error": "invalid_weight_payload", "detail": err}
        _write_scoring_weights(scoring_path, prev_w)
        entry = {
            "version": _next_strategy_version(ledger),
            "activated_at": datetime.now(tz=ZoneInfo("America/New_York")).isoformat(),
            "weights": prev_w,
            "previous_weights": tail.get("weights"),
            "predecessor": tail.get("version"),
            "proposal_key": None,
            "rationale": f"Revert of {tail.get('version')}",
        }
        ledger.append(entry)
        _strategy_versions_path(output_dir).write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        print(f"Reverted live weights to the predecessor of {tail.get('version')}.")
        return {"version": entry["version"], "reverted": True, "weights": prev_w}

    decisions = _load_suggestion_decisions(output_dir)
    approved = [d for d in decisions.values() if d.get("status") == "approved"]
    candidates: dict[str, dict[str, Any]] = {}
    for d in approved:
        pkg_path = Path(output_dir) / (d.get("date") or report_date) / "approval_package.json"
        if not pkg_path.exists():
            continue
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for s in pkg.get("suggestions") or []:
            if s.get("kind") != "weight_calibration" or not s.get("new_weights"):
                continue
            skey = _suggestion_key(s["suggestion"], s.get("strategy_version", "v1"))
            if skey == d.get("suggestion_key"):
                candidates[skey] = s

    if not candidates:
        print("No approved weight-calibration proposal found.")
        print("Approve one first: record-suggestion-decision --index N --status approved")
        return {"error": "no_approved_calibration"}
    if key:
        candidates = {k: v for k, v in candidates.items() if k == key}
        if not candidates:
            return {"error": "key_not_found", "key": key}
    if len(candidates) > 1:
        print("Multiple approved calibrations — pass --key to choose one:")
        for k in candidates:
            print(f"  {k}")
        return {"error": "ambiguous", "keys": list(candidates)}

    chosen_key, suggestion = next(iter(candidates.items()))
    try:
        new_w = {k: float(v) for k, v in suggestion["new_weights"].items()}
    except (TypeError, ValueError, AttributeError):
        print("Approved proposal has a malformed new_weights payload — refusing to activate.")
        return {"error": "invalid_weight_payload", "detail": "new_weights not a numeric mapping"}
    err = _validate_weight_set(new_w)
    if err:
        print(f"Approved proposal's weights are invalid — refusing to activate: {err}")
        return {"error": "invalid_weight_payload", "detail": err}

    if ledger and ledger[-1].get("weights") == new_w and ledger[-1].get("proposal_key") == chosen_key:
        print(f"Already active: {ledger[-1]['version']}. No change.")
        return {"version": ledger[-1]["version"], "noop": True}

    old_w = asdict(load_scoring_config(scoring_path).weights)
    predecessor = ledger[-1]["version"] if ledger else "v1"
    version = _next_strategy_version(ledger)

    _write_scoring_weights(scoring_path, new_w)
    versions_dir = Path(config_dir) / "strategy_versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    provenance = {
        "version": version,
        "predecessor": predecessor,
        "weights": new_w,
        "previous_weights": old_w,
        "proposal_key": chosen_key,
        "target_component": suggestion.get("target_component"),
        "cohort": suggestion.get("cohort"),
        "rationale": suggestion.get("rationale") or suggestion.get("suggestion"),
        "attribution_evidence": suggestion.get("attribution_evidence"),
        "divergence_evidence": suggestion.get("divergence_evidence"),
    }
    (versions_dir / f"{version}.yaml").write_text(yaml.safe_dump(provenance, sort_keys=False), encoding="utf-8")
    entry = {
        "version": version,
        "activated_at": datetime.now(tz=ZoneInfo("America/New_York")).isoformat(),
        "weights": new_w,
        "previous_weights": old_w,
        "predecessor": predecessor,
        "proposal_key": chosen_key,
        "rationale": provenance["rationale"],
    }
    ledger.append(entry)
    _strategy_versions_path(output_dir).write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"Activated {version} (was {predecessor}). The next scan uses the new weights.")
    for k in new_w:
        print(f"  {k}: {old_w.get(k)} -> {new_w[k]}")
    return {"version": version, "weights": new_w, "predecessor": predecessor}


def _build_approval_package(
    report_date: str,
    suggestions: list[dict[str, Any]],
    strategy_version: str,
    decisions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the research-only approval package from pending rule suggestions.

    If prior decisions are provided, each suggestion's status is updated to reflect
    the recorded decision. Approved suggestions remain not applied.
    """
    enriched = []
    for s in suggestions:
        entry = dict(s)
        if decisions:
            key = _suggestion_key(entry["suggestion"], entry.get("strategy_version", "v1"))
            if key in decisions:
                dec = decisions[key]
                entry["status"] = dec["status"]
                entry["decided_at"] = dec.get("decided_at")
                entry["decision_note"] = dec.get("note", "")
                entry["not_applied"] = True
        enriched.append(entry)

    pending = [s for s in enriched if s.get("status") == "needs_review"]
    decided = [s for s in enriched if s.get("status") != "needs_review"]
    return {
        "report_date": report_date,
        "strategy_version": strategy_version,
        "pending_count": len(pending),
        "decided_count": len(decided),
        "suggestions": enriched,
        "not_applied_note": (
            "These suggestions have not been applied. "
            "Approved does not mean applied. "
            "No scoring, trigger, or trading behavior has changed."
        ),
        "research_only": True,
    }


def _build_approval_package_markdown(report_date: str, package: dict[str, Any]) -> str:
    """Build a markdown approval package from the approval dict."""
    lines: list[str] = []
    lines.append(f"# Approval Package — {report_date}")
    lines.append("")
    lines.append(f"**Strategy version:** {package['strategy_version']}  ")
    lines.append(f"**Pending suggestions:** {package['pending_count']}  ")
    lines.append("")
    lines.append(f"> {package['not_applied_note']}")
    lines.append("")

    if not package["suggestions"]:
        lines.append("No approval items today.")
    else:
        lines.append("## Pending Suggestions (needs_review)")
        lines.append("")
        for i, s in enumerate(package["suggestions"], 1):
            conf = str(s.get("confidence", "")).upper()
            lines.append(f"### {i}. [{conf}] {s.get('suggestion', '')}")
            lines.append(f"- **Reason:** {s.get('reason', '')}")
            lines.append(f"- **Confidence:** {s.get('confidence', 'low')}")
            lines.append(f"- **Status:** {s.get('status', 'needs_review')}")
            lines.append(f"- **Strategy version:** {s.get('strategy_version', 'v1')}")
            lines.append("")

    lines.append("---")
    lines.append("*Research only. Not applied. No scoring, trigger, or trading behavior changed.*")
    return "\n".join(lines)


def _next_proposed_version(current: str) -> str:
    """Return the next minor version label: 'v1' → 'v1.1', 'v1.2' → 'v1.3'."""
    core = current.lstrip("v")
    parts = core.split(".")
    if len(parts) == 1:
        return f"v{parts[0]}.1"
    minor = int(parts[-1]) + 1
    return f"v{'.'.join(parts[:-1])}.{minor}"


def _build_strategy_proposal(
    report_date: str,
    decisions: dict[str, dict[str, Any]],
    current_version: str,
) -> dict[str, Any]:
    """Build a research-only proposed strategy version from approved suggestions.

    Does not modify config, scoring, or any live code. Approved does not mean applied.
    """
    approved = [
        d for d in decisions.values()
        if d.get("status") == "approved"
    ]
    proposed_version = _next_proposed_version(current_version) if approved else current_version
    return {
        "report_date": report_date,
        "current_version": current_version,
        "proposed_version": proposed_version,
        "approved_count": len(approved),
        "approved_suggestions": approved,
        "not_applied_note": (
            "This proposal has not been applied. "
            "Approved does not mean applied. "
            "No config, scoring, trigger, or trading behavior has changed."
        ),
        "research_only": True,
    }


def _build_strategy_proposal_markdown(proposal: dict[str, Any]) -> str:
    """Build a markdown strategy proposal from the proposal dict."""
    report_date = proposal["report_date"]
    lines: list[str] = []
    lines.append(f"# Strategy Proposal — {report_date}")
    lines.append("")
    lines.append(f"**Current version:** {proposal['current_version']}  ")
    lines.append(f"**Proposed version:** {proposal['proposed_version']}  ")
    lines.append(f"**Approved suggestions:** {proposal['approved_count']}  ")
    lines.append("")
    lines.append(f"> {proposal['not_applied_note']}")
    lines.append("")

    if not proposal["approved_suggestions"]:
        lines.append("No strategy proposal today.")
    else:
        lines.append("## Approved Suggestions (not applied)")
        lines.append("")
        for i, s in enumerate(proposal["approved_suggestions"], 1):
            conf = str(s.get("confidence", "")).upper()
            lines.append(f"### {i}. [{conf}] {s.get('suggestion', '')}")
            lines.append(f"- **Reason:** {s.get('reason', '')}")
            lines.append(f"- **Source version:** {s.get('strategy_version', 'v1')}")
            lines.append(f"- **Proposed in:** {proposal['proposed_version']}")
            lines.append(f"- **Status:** {s.get('status', 'approved')}")
            if s.get("decision_note") or s.get("note"):
                lines.append(f"- **Note:** {s.get('decision_note') or s.get('note', '')}")
            lines.append(f"- **Decided at:** {s.get('decided_at', 'unknown')}")
            lines.append("")

    lines.append("---")
    lines.append("*Research only. Not applied. No config, scoring, trigger, or trading behavior changed.*")
    return "\n".join(lines)


_MIN_CONCLUSIVE_FOR_PROPOSAL_VALIDATION = 3


def _build_proposal_replay(
    report_date: str,
    proposal: dict[str, Any],
    baseline_replay: dict[str, Any],
) -> dict[str, Any]:
    """Compare current baseline replay against an approved strategy proposal.

    Research-only. Does not change scoring, trigger rules, or trading behavior.
    Approved does not mean applied.
    """
    current_version = proposal.get("current_version", CURRENT_STRATEGY_VERSION)
    proposed_version = proposal.get("proposed_version", current_version)
    approved = proposal.get("approved_suggestions") or []
    total_conclusive = int(baseline_replay.get("total_conclusive", 0) or 0)

    not_applied_note = (
        "This replay has not been applied. "
        "Approved does not mean applied. "
        "No config, scoring, trigger, or trading behavior has changed."
    )

    if not approved:
        return {
            "report_date": report_date,
            "current_version": current_version,
            "proposed_version": proposed_version,
            "validated": False,
            "validation_status": "no_approved_suggestions",
            "baseline_replay": baseline_replay,
            "approved_suggestions": [],
            "notes": [
                "No approved suggestions. No proposal to replay.",
                "This is a research-only replay. It does not change scoring, trigger rules, or trading behavior.",
            ],
            "not_applied_note": not_applied_note,
            "research_only": True,
        }

    if total_conclusive == 0:
        return {
            "report_date": report_date,
            "current_version": current_version,
            "proposed_version": proposed_version,
            "validated": False,
            "validation_status": "insufficient_data",
            "baseline_replay": baseline_replay,
            "approved_suggestions": approved,
            "notes": [
                "Proposal cannot be validated yet. No conclusive outcome data available.",
                "Collect more real-data outcomes before evaluating this proposal.",
                "This is a research-only replay. It does not change scoring, trigger rules, or trading behavior.",
            ],
            "not_applied_note": not_applied_note,
            "research_only": True,
        }

    validated = total_conclusive >= _MIN_CONCLUSIVE_FOR_PROPOSAL_VALIDATION
    validation_status = "validated" if validated else "preliminary"

    suggestion_context: list[dict[str, Any]] = []
    for s in approved:
        suggestion_context.append({
            "suggestion": s.get("suggestion", ""),
            "reason": s.get("reason", ""),
            "confidence": s.get("confidence", ""),
            "strategy_version": s.get("strategy_version", "v1"),
            "baseline_total_conclusive": total_conclusive,
            "baseline_setups": baseline_replay.get("setups", []),
            "note": "Replay is research-only. Scoring and trigger rules are unchanged.",
        })

    notes = [
        "This replay compares the current strategy baseline against the approved proposal.",
        "No scoring or trigger rules have changed.",
        f"Baseline conclusive rows: {total_conclusive}.",
        "This is a research-only replay. It does not change scoring, trigger rules, or trading behavior.",
    ]
    if not validated:
        notes.append(
            f"Only {total_conclusive} conclusive row(s) — patterns are preliminary. "
            f"At least {_MIN_CONCLUSIVE_FOR_PROPOSAL_VALIDATION} are needed for a meaningful comparison."
        )

    return {
        "report_date": report_date,
        "current_version": current_version,
        "proposed_version": proposed_version,
        "validated": validated,
        "validation_status": validation_status,
        "baseline_replay": baseline_replay,
        "approved_suggestions": suggestion_context,
        "notes": notes,
        "not_applied_note": not_applied_note,
        "research_only": True,
    }


def _build_proposal_replay_markdown(replay: dict[str, Any]) -> str:
    """Build markdown for the proposal replay report."""
    report_date = replay["report_date"]
    lines: list[str] = []
    lines.append(f"# Proposal Replay — {report_date}")
    lines.append("")
    lines.append(f"**Current version:** {replay['current_version']}  ")
    lines.append(f"**Proposed version:** {replay['proposed_version']}  ")
    lines.append(f"**Validation status:** {replay['validation_status']}  ")
    lines.append("")
    lines.append(f"> {replay['not_applied_note']}")
    lines.append("")

    for note in replay.get("notes", []):
        lines.append(f"- {note}")
    lines.append("")

    approved = replay.get("approved_suggestions") or []
    if not approved:
        lines.append("No approved suggestions. No proposal to replay.")
    else:
        baseline = replay.get("baseline_replay") or {}
        lines.append("## Baseline Replay (Current Version)")
        lines.append("")
        lines.append(f"- Total rows: {baseline.get('total_rows', 0)}")
        lines.append(f"- Total triggered: {baseline.get('total_triggered', 0)}")
        lines.append(f"- Conclusive rows: {baseline.get('total_conclusive', 0)}")
        lines.append(f"- Pending future data: {baseline.get('total_insufficient_future_data', 0)}")
        lines.append("")

        setups = baseline.get("setups") or []
        if setups:
            lines.append("### Setup Rates")
            lines.append("")
            for s in setups:
                target_rate = s.get("target_rate")
                stop_rate = s.get("stop_rate")
                t_str = f"{target_rate:.1%}" if target_rate is not None else "N/A"
                s_str = f"{stop_rate:.1%}" if stop_rate is not None else "N/A"
                lines.append(
                    f"- **{s['setup']}**: {s['conclusive_rows']} conclusive "
                    f"| target {t_str} | stop {s_str}"
                )
            lines.append("")

        lines.append("## Approved Suggestions (not applied)")
        lines.append("")
        for i, s in enumerate(approved, 1):
            conf = str(s.get("confidence", "")).upper()
            lines.append(f"### {i}. [{conf}] {s.get('suggestion', '')}")
            lines.append(f"- **Reason:** {s.get('reason', '')}")
            lines.append(f"- **Source version:** {s.get('strategy_version', 'v1')}")
            lines.append(f"- **Note:** {s.get('note', '')}")
            lines.append("")

    lines.append("---")
    lines.append("*Research only. Not applied. No config, scoring, trigger, or trading behavior changed.*")
    return "\n".join(lines)


def _is_within_regular_market_hours(now: datetime | None = None) -> bool:
    """Return True if the current America/New_York time is a weekday inside 9:30–16:00 ET.

    No holiday calendar is applied; weekends are treated as outside market hours.
    """
    et_now = now if now is not None else datetime.now(tz=ZoneInfo("America/New_York"))
    if et_now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = et_now.time()
    return datetime_time(9, 30) <= t <= datetime_time(16, 0)


def run_after_market_review(args: argparse.Namespace) -> dict[str, Any]:
    """Run after-market review: update snapshots, EOD report, real-only analytics, save reports."""
    report_date = getattr(args, "date", None) or new_york_market_date()
    output_base = Path(getattr(args, "output_dir", "reports")) / report_date
    output_base.mkdir(parents=True, exist_ok=True)

    print(f"After-market review — {report_date} {MARKET_TIMEZONE_LABEL}")
    print("Research only: no scoring changes, no trading, no suggestions auto-applied.")

    # 1. Update snapshots — guard against stale intraday refresh outside market hours
    skip_update = getattr(args, "skip_update_snapshots", False)
    force_update = getattr(args, "force_update_snapshots", False)
    in_market_hours = _is_within_regular_market_hours()

    if skip_update:
        print("\nSkipping update-snapshots (--skip-update-snapshots).")
        did_update = False
    elif force_update:
        print("\nUpdating open snapshots (--force-update-snapshots)...")
        run_update_snapshots(SimpleNamespace(config=args.config, limit=500))
        did_update = True
    elif not in_market_hours:
        print("\nOutside market hours; skipping live snapshot refresh. Using stored close/tracking data.")
        did_update = False
    else:
        print("\nUpdating open snapshots...")
        run_update_snapshots(SimpleNamespace(config=args.config, limit=500))
        did_update = True

    # 2. EOD report
    print("\n--- EOD Report ---")
    eod_args = SimpleNamespace(config=args.config, date=report_date)
    eod_result = run_eod_report(eod_args)

    # 3. Real-only outcome analytics (date-scoped)
    print("\n--- Outcome Analytics (real-only) ---")
    analytics_args = SimpleNamespace(
        config=args.config,
        date=report_date,
        today=False,
        include_seeded=False,
        days=None,
        min_score=None,
        real_only=True,
        include_demo=False,
        include_legacy=False,
        exclude_demo=False,
        provider=None,
        group_by=None,
    )
    analytics_result = run_outcome_analytics(analytics_args)

    # 4. Save core report files
    eod_json_path = output_base / "eod_report.json"
    eod_md_path = output_base / "eod_report.md"
    analytics_json_path = output_base / "outcome_analytics.json"

    eod_json_path.write_text(json.dumps(eod_result, indent=2, default=str), encoding="utf-8")
    analytics_json_path.write_text(json.dumps(analytics_result, indent=2, default=str), encoding="utf-8")
    eod_md_path.write_text(_build_eod_report_markdown(report_date, eod_result), encoding="utf-8")

    # 5. Build and save approval package (load prior decisions if available)
    sr = eod_result.get("tony_self_review") or {}
    suggestions = sr.get("rule_suggestions") or []
    sv = (eod_result.get("strategy_version_report") or {}).get("current_version", CURRENT_STRATEGY_VERSION)

    # Divergence calibration — append confidence-tagged weight proposals to the gate.
    # Wrapped defensively: calibration is research-only and must never break the daily review.
    print("\n--- Divergence Calibration (research only) ---")
    try:
        weight_proposals = _build_weight_proposals(args, sv)
    except Exception as exc:  # noqa: BLE001 - isolate the review from any calibration fault
        import traceback

        weight_proposals = []
        # Non-breaking by design, but keep the stack so a permanently-broken calibrator is
        # diagnosable rather than a silent one-line "skipped".
        print(f"  Divergence calibration skipped after error: {exc}\n{traceback.format_exc()}")
    if weight_proposals:
        suggestions = list(suggestions) + weight_proposals

    decisions = _load_suggestion_decisions(getattr(args, "output_dir", "reports"))
    approval = _build_approval_package(report_date, suggestions, sv, decisions=decisions)

    approval_json_path = output_base / "approval_package.json"
    approval_md_path = output_base / "approval_package.md"
    approval_json_path.write_text(json.dumps(approval, indent=2, default=str), encoding="utf-8")
    approval_md_path.write_text(_build_approval_package_markdown(report_date, approval), encoding="utf-8")

    print("\nApproval package (research only — not applied):")
    print(f"  Strategy version: {approval['strategy_version']}")
    print(f"  Pending suggestions: {approval['pending_count']}")
    if approval["suggestions"]:
        for s in approval["suggestions"]:
            print(f"  - [{s['confidence'].upper()}] {s['suggestion']}")
    else:
        print("  No approval items today.")

    # 6. Build and save strategy proposal from approved decisions
    proposal = _build_strategy_proposal(report_date, decisions, sv)
    proposal_json_path = output_base / "strategy_proposal.json"
    proposal_md_path = output_base / "strategy_proposal.md"
    proposal_json_path.write_text(json.dumps(proposal, indent=2, default=str), encoding="utf-8")
    proposal_md_path.write_text(_build_strategy_proposal_markdown(proposal), encoding="utf-8")

    print("\nStrategy proposal (research only — not applied):")
    print(f"  Current version: {proposal['current_version']}")
    print(f"  Proposed version: {proposal['proposed_version']}")
    print(f"  Approved suggestions: {proposal['approved_count']}")
    if not proposal["approved_suggestions"]:
        print("  No strategy proposal today.")

    # 7. Build and save proposal replay — compares baseline vs approved proposal
    baseline_replay = analytics_result.get("replay_summary") or {}
    proposal_replay = _build_proposal_replay(report_date, proposal, baseline_replay)
    replay_json_path = output_base / "proposal_replay.json"
    replay_md_path = output_base / "proposal_replay.md"
    replay_json_path.write_text(json.dumps(proposal_replay, indent=2, default=str), encoding="utf-8")
    replay_md_path.write_text(_build_proposal_replay_markdown(proposal_replay), encoding="utf-8")

    print("\nProposal replay (research only — not applied):")
    print(f"  Validation status: {proposal_replay['validation_status']}")
    print(f"  Baseline conclusive rows: {baseline_replay.get('total_conclusive', 0)}")

    created = [
        str(eod_json_path), str(eod_md_path), str(analytics_json_path),
        str(approval_json_path), str(approval_md_path),
        str(proposal_json_path), str(proposal_md_path),
        str(replay_json_path), str(replay_md_path),
    ]

    # 8. Vault export (Obsidian memory layer)
    print("\n--- Vault Export ---")
    vault_result = _run_vault_export(report_date, eod_result, args.config)
    if vault_result.get("skipped"):
        print(f"Vault export skipped: {vault_result.get('reason')}")
    else:
        print(f"Vault snapshots: {vault_result['snapshots_processed']} | Files: {len(vault_result['files_written'])}")
        created.extend(vault_result["files_written"])

    print("\nAfter-market review complete.")
    print(f"Report date: {report_date} {MARKET_TIMEZONE_LABEL}")
    print("Reports saved:")
    for path in created:
        print(f"  {path}")

    return {
        "report_date": report_date,
        "files_created": created,
        "eod_report": eod_result,
        "outcome_analytics": analytics_result,
        "approval_package": approval,
        "strategy_proposal": proposal,
        "proposal_replay": proposal_replay,
        "market_hours_active": in_market_hours,
        "snapshot_refresh_ran": did_update,
    }


def run_data_check(args: argparse.Namespace) -> None:
    """Test the configured market data provider for one or more symbols. Does not scan or trade."""
    settings = load_scanner_settings(args.config)
    effective_provider = resolve_effective_provider(settings)
    market_data_cfg = settings.market_data or {}
    alpaca_cfg = market_data_cfg.get("alpaca") or {}
    real_enabled = bool(market_data_cfg.get("real_provider_enabled", False))
    lookback_days = getattr(args, "lookback_days", 5)
    requested_timeframe = getattr(args, "timeframe", None) or settings.timeframe

    # Resolve symbols: --symbols takes precedence over --symbol
    raw_symbols_arg = getattr(args, "symbols", "")
    if raw_symbols_arg.strip():
        symbols = [s.strip().upper() for s in raw_symbols_arg.split(",") if s.strip()]
    else:
        symbols = [args.symbol.upper().strip()]

    print("Data provider check")
    print("Does not scan, trade, or place orders.")
    print(f"Config:              {args.config}")
    print(f"Configured provider: {settings.provider}")
    print(f"Effective provider:  {effective_provider} (real_provider_enabled={real_enabled})")
    print(f"Requested timeframe: {requested_timeframe}")
    print(f"Symbols:             {', '.join(symbols)}")

    if effective_provider == "alpaca_iex":
        feed = str(alpaca_cfg.get("feed", "iex"))
        configured_timeframe = str(alpaca_cfg.get("timeframe", "1Day"))
        import os as _os
        keys_present = bool(_os.getenv("ALPACA_API_KEY")) and bool(_os.getenv("ALPACA_SECRET_KEY"))
        print(f"Feed:                {feed}")
        print(f"Configured timeframe:{configured_timeframe}")
        print(f"Keys present:        {keys_present}")
        print("NOTE: Alpaca IEX is a single-exchange feed. It may differ from consolidated SIP data.")

    try:
        metadata_by_symbol = load_universe_metadata(settings.universe_config_path)
        profiles_by_symbol = {
            sym: meta.demo_profile
            for sym, meta in metadata_by_symbol.items()
            if meta.demo_profile
        }
        provider = build_market_data_provider(
            effective_provider,
            settings.cache_dir,
            profiles_by_symbol=profiles_by_symbol,
            market_data_config=settings.market_data,
        )
    except EnvironmentError as exc:
        print(f"\nConfiguration error: {exc}")
        return

    any_success = False
    any_fallback = False
    for symbol in symbols:
        print(f"\n--- {symbol} ---")
        try:
            data = provider.fetch_ohlcv(symbol, lookback_days, requested_timeframe)
        except EnvironmentError as exc:
            print(f"  Error: {exc}")
            continue
        except Exception as exc:
            print(f"  Fetch failed: {exc}")
            continue

        if data.empty:
            print("  No bars returned. Symbol may not be in the data set or date range returned nothing.")
            continue

        any_success = True
        latest_ts = data.index[-1]
        latest_close = float(data["close"].iloc[-1])
        latest_volume = int(data["volume"].iloc[-1])
        print(f"  Bars returned: {len(data)}")
        print(f"  Latest bar:    {latest_ts}")
        print(f"  Close:         {latest_close:.4f}")
        print(f"  Volume:        {latest_volume:,}")
        if str(requested_timeframe).lower() not in {"daily", "1day"}:
            features = calculate_intraday_features(symbol, data, timeframe=str(requested_timeframe))
            print(f"  Intraday read: {features.status}")
            print(f"  VWAP:          {features.vwap if features.vwap is not None else 'n/a'}")
            print(f"  Above VWAP:    {features.price_above_vwap}")
            print(
                "  Day change:    "
                f"{features.intraday_change_percent if features.intraday_change_percent is not None else 'n/a'}"
            )
            print(f"  Opening range: {features.opening_range_high} / {features.opening_range_low}")

        if isinstance(provider, AlpacaIEXProvider) and symbol in provider.fallback_symbols:
            print(f"  WARNING: {symbol} used demo fallback. Check Alpaca key and connectivity.")
            any_fallback = True
        else:
            print(f"  Provider responded successfully.")

    if isinstance(provider, AlpacaIEXProvider) and any_fallback:
        print("\nFallback occurred for one or more symbols. Verify Alpaca API keys in .env and connectivity.")
    elif any_success:
        print(f"\nCheck complete. Provider: {provider.name}")


def run_provider_health(args: argparse.Namespace) -> ProviderHealth:
    """Run a provider health check. Does not scan, trade, or place orders."""
    settings = load_scanner_settings(args.config)
    effective_provider = resolve_effective_provider(settings)
    market_data_cfg = settings.market_data or {}
    real_enabled = bool(market_data_cfg.get("real_provider_enabled", False))
    lookback_days = getattr(args, "lookback_days", 5)

    raw_symbols = getattr(args, "symbols", "")
    test_symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()] if raw_symbols.strip() else None

    metadata_by_symbol = load_universe_metadata(settings.universe_config_path)
    profiles_by_symbol = {
        sym: meta.demo_profile
        for sym, meta in metadata_by_symbol.items()
        if meta.demo_profile
    }

    print("Provider health check")
    print("Does not scan, trade, or place orders.")
    print(f"Config:              {args.config}")
    print(f"Configured provider: {settings.provider}")
    print(f"Effective provider:  {effective_provider} (real_provider_enabled={real_enabled})")

    health = check_provider_health(
        effective_provider=effective_provider,
        configured_provider=settings.provider,
        market_data_config=settings.market_data,
        test_symbols=test_symbols,
        lookback_days=lookback_days,
        profiles_by_symbol=profiles_by_symbol,
    )

    print(f"\nHealth check result: {'PASSED' if health.passed else 'FAILED'}")
    print(f"Keys present:        {health.keys_present}")
    print(f"Feed:                {health.feed}")
    print(f"Timeframe:           {health.timeframe}")
    print(f"Fallback provider:   {health.fallback_provider}")
    print(f"Symbols requested:   {health.symbols_requested}")
    print(f"Symbols with data:   {health.symbols_with_data}")
    print(f"Symbols fallback:    {health.symbols_fallback}")
    print(f"Symbols stale:       {health.symbols_stale}")
    print(f"Using fallback:      {health.using_fallback}")
    if health.latest_bar_time:
        print(f"Latest bar time:     {health.latest_bar_time}")
    if health.provider_errors:
        print("Errors:")
        for err in health.provider_errors:
            print(f"  {err}")
    if effective_provider == "alpaca_iex":
        print("NOTE: Alpaca IEX is a single-exchange feed. It may differ from consolidated SIP data.")

    if getattr(args, "record_event", False):
        repo = ScannerRepository(settings.database_path)
        tony = TonyStocksService(repo, settings.tony_stocks)
        tony.start_cycle()
        configure_logging(settings.log_dir)
        health_dict = health.to_dict()
        if health.passed:
            tony.record_provider_health_passed(health_dict)
        else:
            tony.record_provider_health_failed(health_dict)
        print("\nHealth check event recorded.")

    return health


def _fetch_intraday_features_for_tony(
    settings: Any,
    provider: Any,
    symbols: list[str],
) -> tuple[dict[str, IntradayFeatures], dict[str, Any]]:
    """Fetch optional intraday bars for Tony analysis without changing scoring."""
    from collections import Counter

    intraday_cfg = settings.intraday or {}
    timeframe = str(intraday_cfg.get("timeframe", "5Min"))
    allow_demo_fallback = bool(intraday_cfg.get("allow_demo_fallback", False))
    require_real = bool(intraday_cfg.get("require_real_provider", True))
    base_summary = {
        "enabled": bool(intraday_cfg.get("enabled", False)),
        "timeframe": timeframe,
        "use_for_tony_analysis": bool(intraday_cfg.get("use_for_tony_analysis", True)),
        "use_for_scoring": bool(intraday_cfg.get("use_for_scoring", False)),
        "allow_demo_fallback": allow_demo_fallback,
        "require_real_provider": require_real,
        "intraday_provider": "none",
        "symbols_requested": 0,
        "symbols_with_intraday": 0,
        "real_intraday_count": 0,
        "missing_count": 0,
        "intraday_fallback_count": 0,
        "intraday_stale_count": 0,
        "intraday_fallback_symbols": [],
        "intraday_stale_symbols": [],
        "above_vwap_count": 0,
        "below_vwap_count": 0,
        "opening_range_breakout_count": 0,
        "opening_range_breakdown_count": 0,
        "sample_reads": [],
    }
    if not intraday_cfg.get("enabled", False) or not intraday_cfg.get("use_for_tony_analysis", True):
        return {}, {}
    lookback_days = int(intraday_cfg.get("lookback_days", 5))
    max_symbols = int(intraday_cfg.get("max_symbols_per_cycle", len(symbols)) or len(symbols))
    selected = [symbol.upper() for symbol in symbols[:max_symbols]]
    base_summary["symbols_requested"] = len(selected)
    if not selected:
        return {}, base_summary
    if require_real and not isinstance(provider, AlpacaIEXProvider):
        # Real provider required but not available — mark all as missing, do not use demo
        base_summary["intraday_provider"] = "skipped_require_real"
        missing = {
            symbol: IntradayFeatures(symbol=symbol, timeframe=timeframe, data_available=False, status="intraday_data_missing")
            for symbol in selected
        }
        return missing, _build_intraday_summary(timeframe, selected, missing, base_summary=base_summary)
    bars_by_symbol: dict[str, Any] = {}
    fallback_before: Counter[str] = Counter()
    stale_before: Counter[str] = Counter()
    if isinstance(provider, AlpacaIEXProvider):
        fallback_before = Counter(provider.fallback_symbols)
        stale_before = Counter(provider.stale_symbols)
    try:
        if isinstance(provider, AlpacaIEXProvider) and provider.batch_requests_enabled and len(selected) > 1:
            bars_by_symbol = provider.fetch_ohlcv_batch(selected, lookback_days, timeframe)
            base_summary["intraday_provider"] = "alpaca_iex"
        else:
            bars_by_symbol = {
                symbol: provider.fetch_ohlcv(symbol, lookback_days, timeframe)
                for symbol in selected
            }
            base_summary["intraday_provider"] = provider.name
    except Exception as exc:
        LOGGER.warning("Intraday feature fetch failed: %s", exc)
        if not allow_demo_fallback:
            base_summary["intraday_provider"] = "none_fetch_failed"
            missing = {
                symbol: IntradayFeatures(symbol=symbol, timeframe=timeframe, data_available=False, status="intraday_data_missing")
                for symbol in selected
            }
            summary = _build_intraday_summary(timeframe, selected, missing, base_summary=base_summary)
            return missing, summary
        base_summary["intraday_provider"] = "demo_generated_fallback"
        demo_provider = build_market_data_provider(
            "demo_generated",
            settings.cache_dir,
            profiles_by_symbol=None,
            market_data_config=settings.market_data,
        )
        bars_by_symbol = {
            symbol: demo_provider.fetch_ohlcv(symbol, lookback_days, timeframe)
            for symbol in selected
        }
    intraday_fallback_symbols: set[str] = set()
    intraday_stale_symbols: set[str] = set()
    if isinstance(provider, AlpacaIEXProvider):
        fallback_after = Counter(provider.fallback_symbols)
        stale_after = Counter(provider.stale_symbols)
        for symbol in selected:
            if fallback_after[symbol] > fallback_before[symbol]:
                intraday_fallback_symbols.add(symbol)
            if stale_after[symbol] > stale_before[symbol]:
                intraday_stale_symbols.add(symbol)
    elif base_summary.get("intraday_provider") == "demo_generated_fallback":
        intraday_fallback_symbols = set(selected)

    features = {
        symbol: calculate_intraday_features(symbol, bars_by_symbol.get(symbol), timeframe=timeframe)
        for symbol in selected
    }
    if not allow_demo_fallback:
        for symbol in intraday_fallback_symbols:
            features[symbol] = IntradayFeatures(
                symbol=symbol,
                timeframe=timeframe,
                data_available=False,
                status="intraday_data_missing",
            )
    summary = _build_intraday_summary(
        timeframe=timeframe,
        requested_symbols=selected,
        features_by_symbol=features,
        fallback_count=len(intraday_fallback_symbols),
        stale_count=len(intraday_stale_symbols),
        base_summary=base_summary,
    )
    summary["intraday_fallback_symbols"] = sorted(intraday_fallback_symbols)
    summary["intraday_stale_symbols"] = sorted(intraday_stale_symbols)
    return features, summary


def _build_intraday_summary(
    timeframe: str,
    requested_symbols: list[str],
    features_by_symbol: dict[str, IntradayFeatures],
    fallback_count: int = 0,
    stale_count: int = 0,
    base_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize intraday reads for console, Tony events, and dashboard."""
    summary = dict(base_summary or {})
    summary.update(
        {
            "timeframe": timeframe,
            "symbols_requested": len(requested_symbols),
            "intraday_fallback_count": int(fallback_count),
        }
    )
    reads: list[dict[str, Any]] = []
    with_data = 0
    above_vwap = 0
    below_vwap = 0
    or_breakout = 0
    or_breakdown = 0
    for symbol in requested_symbols:
        features = features_by_symbol.get(symbol)
        if features is None or not features.data_available:
            reads.append({"symbol": symbol, "read": "intraday_data_missing", "status": "intraday_data_missing"})
            continue
        with_data += 1
        if features.price_above_vwap is True:
            above_vwap += 1
        elif features.price_above_vwap is False:
            below_vwap += 1
        if features.opening_range_breakout_candidate:
            or_breakout += 1
        if features.opening_range_breakdown_warning:
            or_breakdown += 1
        reads.append(
            {
                "symbol": symbol,
                "read": _tony_intraday_label_from_features(features),
                "status": features.status,
                "above_vwap": features.price_above_vwap,
                "opening_range_status": _opening_range_status_from_features(features),
            }
        )
    summary.update(
        {
            "symbols_with_intraday": with_data,
            "real_intraday_count": with_data,
            "missing_count": max(0, len(requested_symbols) - with_data),
            "intraday_stale_count": stale_count,
            "above_vwap_count": above_vwap,
            "below_vwap_count": below_vwap,
            "opening_range_breakout_count": or_breakout,
            "opening_range_breakdown_count": or_breakdown,
            "sample_reads": reads[:5],
        }
    )
    return summary


def _opening_range_status_from_features(features: IntradayFeatures) -> str:
    if features.opening_range_breakout_candidate:
        return "opening_range_breakout_watch"
    if features.opening_range_breakdown_warning:
        return "opening_range_breakdown_warning"
    return features.status


def _print_intraday_summary(summary: dict[str, Any], prefix: str = "") -> None:
    """Print compact intraday scan/watch statistics."""
    provider_used = summary.get("intraday_provider", "unknown")
    allow_fallback = summary.get("allow_demo_fallback", False)
    print(
        f"{prefix}Intraday summary: provider={provider_used} allow_demo_fallback={allow_fallback} "
        f"requested={summary.get('symbols_requested', 0)} "
        f"real_intraday={summary.get('real_intraday_count', summary.get('symbols_with_intraday', 0))} "
        f"missing={summary.get('missing_count', 0)} "
        f"fallback={summary.get('intraday_fallback_count', 0)} "
        f"stale={summary.get('intraday_stale_count', 0)} "
        f"above_vwap={summary.get('above_vwap_count', 0)} "
        f"below_vwap={summary.get('below_vwap_count', 0)} "
        f"or_breakout={summary.get('opening_range_breakout_count', 0)} "
        f"or_breakdown={summary.get('opening_range_breakdown_count', 0)}"
    )
    sample_reads = summary.get("sample_reads") or []
    if sample_reads:
        sample_text = ", ".join(f"{item.get('symbol')}: {item.get('read')}" for item in sample_reads)
        print(f"{prefix}Sample intraday reads: {sample_text}")


def _intraday_snapshot_fields(features: IntradayFeatures | None) -> dict[str, Any]:
    if features is None:
        return {}
    if not features.data_available:
        return {
            "intraday_read": "intraday_data_missing",
            "intraday_timeframe": features.timeframe,
            "intraday_opening_range_status": features.status,
        }
    opening_range_status = "opening_range_breakout_watch" if features.opening_range_breakout_candidate else (
        "opening_range_breakdown_warning" if features.opening_range_breakdown_warning else features.status
    )
    return {
        "intraday_read": _tony_intraday_label_from_features(features),
        "intraday_timeframe": features.timeframe,
        "intraday_close": features.latest_close,
        "intraday_vwap": features.vwap,
        "intraday_above_vwap": features.price_above_vwap,
        "intraday_day_change_percent": features.intraday_change_percent,
        "intraday_relative_volume": features.intraday_relative_volume,
        "intraday_opening_range_status": opening_range_status,
    }


def _tony_intraday_label_from_features(features: IntradayFeatures) -> str:
    if not features.data_available:
        return "intraday_data_missing"
    if features.opening_range_breakdown_warning:
        return "opening_range_breakdown_warning"
    if features.price_above_vwap is False or features.vwap_loss_warning:
        return "below_vwap"
    if features.opening_range_breakout_candidate:
        return "opening_range_breakout_watch"
    if features.distance_from_high_percent is not None and features.distance_from_high_percent >= -0.01:
        return "near_high_of_day"
    if features.distance_from_high_percent is not None and features.distance_from_high_percent <= -0.03:
        return "fading_from_high"
    if features.price_above_vwap:
        return "above_vwap"
    return features.trend_since_open


def _snapshot_data_source_fields(provider_name: str, real_only: bool) -> dict[str, Any]:
    """Metadata persisted on candidate snapshots for analytics filtering."""
    if "alpaca_iex" in provider_name:
        data_source = "real_alpaca"
        used_demo = False
    elif provider_name == "recorded_real_fixture":
        data_source = "recorded_real_fixture"
        used_demo = False
    else:
        data_source = "demo_generated"
        used_demo = True
    return {
        "data_source": data_source,
        "data_source_provider": provider_name,
        "used_demo_data": used_demo,
        "used_fallback_data": False,
        "real_data_only_run": real_only,
        "missing_real_data_reason": None,
    }


def _emit_tony_outcomes(
    repo: "ScannerRepository",
    eod_date: str,
    *,
    days: int = 120,
) -> tuple[Path, int]:
    """Assemble real resolved outcomes and write tony_stocks_outcomes.json.

    Reads the real-only resolved snapshot history, builds per-episode outcome
    records, and writes the Command Center outcomes file. Returns (path, count).
    Research only: no scoring, trigger, or trading changes.
    """
    df = repo.list_snapshots_for_analytics(days=days)
    if df is None or df.empty:
        records: list[dict[str, Any]] = []
    else:
        prepared = OutcomeAnalytics(df, real_only=True).prepared()
        raw_records = build_resolved_outcome_records(prepared)
        records = build_tony_outcomes(raw_records, eod_date=eod_date)
    path = write_tony_outcomes(records)
    return path, len(records)


def run_emit_outcomes(args: argparse.Namespace) -> dict[str, Any]:
    """Standalone backfill: write tony_stocks_outcomes.json from the live DB.

    Research only: reads resolved snapshot history, writes JSON for the Command
    Center. No scoring, trigger, or trading changes.
    """
    report_date = getattr(args, "date", None) or new_york_market_date()
    print(f"Emit Tony outcomes — {report_date} {MARKET_TIMEZONE_LABEL}")
    print("Research only: reads resolved snapshots, writes tony_stocks_outcomes.json. No trading.")
    try:
        settings = load_scanner_settings(args.config)
    except (FileNotFoundError, OSError) as exc:
        print(f"Config not loadable: {exc}")
        return {"skipped": True, "reason": str(exc)}
    repo = ScannerRepository(settings.database_path)
    days = int(getattr(args, "days", None) or 120)
    path, count = _emit_tony_outcomes(repo, report_date, days=days)
    print(f"Resolved outcomes emitted: {count}")
    print(f"Outcomes file: {path}")
    return {"outcomes_file": str(path), "count": count}


def _funnel_eval_signals_from_snapshots(snapshots: Any) -> dict[str, dict[str, Any]]:
    """Best-effort per-symbol funnel signals from the EARLIEST snapshot per symbol
    (closest to pick time). Only price + dollar-volume are reliably stored; the
    recommendation/earnings/relative-strength signals are not persisted historically,
    so those stages report ``insufficient_data`` rather than guessing.
    """
    if snapshots is None or getattr(snapshots, "empty", True) or "symbol" not in snapshots.columns:
        return {}
    df = snapshots
    if "snapshot_time" in df.columns:
        df = df.sort_values("snapshot_time")
    price_cols = [c for c in ("snapshot_price", "latest_close", "close", "entry") if c in df.columns]
    dv_cols = [c for c in ("dollar_volume", "dollar_volume_20") if c in df.columns]
    out: dict[str, dict[str, Any]] = {}
    for symbol, grp in df.groupby("symbol", sort=False):
        first = grp.iloc[0]
        price = next((float(first[c]) for c in price_cols if pd.notna(first.get(c))), None)
        dv = next((float(first[c]) for c in dv_cols if pd.notna(first.get(c))), None)
        out[str(symbol).upper()] = {"price": price, "dollar_volume": dv}
    return out


def _compute_funnel_eval_report(settings: Any, *, days: int, min_sample: int):
    """Pure-ish compute step shared by the ``funnel-eval`` CLI and the nightly learner.

    Reads stored outcomes + snapshot-derived signals and evaluates every funnel stage.
    Returns ``(report, outcomes_path, n_outcomes, n_picks)``. No printing, no file writes.
    """
    from trading_bot.analytics.funnel_eval import (  # noqa: PLC0415
        build_evaluated_picks,
        evaluate_funnel_stages,
    )
    from trading_bot.data.research_funnel import FunnelStageConfig  # noqa: PLC0415

    repo = ScannerRepository(settings.database_path)
    outcomes_path = os.environ.get("TONY_OUTCOMES_FILE") or "reports/tony_stocks_outcomes.json"
    try:
        outcomes = json.loads(Path(outcomes_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        outcomes = []
    if not isinstance(outcomes, list):
        outcomes = []

    snapshots = repo.list_snapshots_for_analytics(days=days)
    signals = _funnel_eval_signals_from_snapshots(snapshots)
    picks = build_evaluated_picks(outcomes, signals)

    cfg = FunnelStageConfig.from_dict(settings.research_funnel or {})
    report = evaluate_funnel_stages(picks, cfg, min_sample=min_sample)
    return report, outcomes_path, len(outcomes), len(picks)


def _refresh_funnel_eval_for_learning(reports: Path, config_path: str, *, days: int,
                                      min_sample: int) -> bool:
    """Produce/refresh ``<reports>/funnel_eval.json`` so the nightly learner can consume
    it. Fail-quiet: any error (bad config, DB, I/O) is swallowed so ``learn`` still
    completes. Returns True if the file was written. Read-only on trading surfaces.
    """
    try:
        settings = load_scanner_settings(config_path)
        report, _path, _n, _picks = _compute_funnel_eval_report(
            settings, days=days, min_sample=min_sample)
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "funnel_eval.json").write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        return True
    except Exception as exc:  # pragma: no cover - defensive, must never break learning
        print(f"[learn] funnel-eval refresh skipped: {exc}")
        return False


def run_funnel_eval(args: argparse.Namespace) -> dict[str, Any]:
    """Research-only funnel evaluation: per funnel stage, does the screen separate
    winning picks from losing ones in the stored outcome history? No trading, no
    scoring changes, no profitability claim.
    """
    print("Funnel evaluation - research only. Measures stage selectivity over stored outcomes; no edge claim.")
    settings = load_scanner_settings(args.config)

    days = int(getattr(args, "days", None) or 120)
    min_sample = int(getattr(args, "min_sample", None) or 5)
    report, outcomes_path, n_outcomes, n_picks = _compute_funnel_eval_report(
        settings, days=days, min_sample=min_sample)

    print(f"Outcomes file: {outcomes_path} ({n_outcomes} records -> {n_picks} evaluable picks)")
    print(f"Signals: price/dollar-volume from snapshots; recommendation/earnings/RS not persisted historically.")
    print(f"{'Stage':<26}{'kept (win%)':<16}{'dropped (win%)':<18}{'d win%':<10}{'verdict'}")
    print("-" * 86)
    for st in report.stages:
        kept = f"{st.kept_n} ({st.kept_win_rate*100:.0f}%)" if st.kept_win_rate is not None else f"{st.kept_n} (-)"
        drop = f"{st.dropped_n} ({st.dropped_win_rate*100:.0f}%)" if st.dropped_win_rate is not None else f"{st.dropped_n} (-)"
        delta = f"{st.win_rate_delta*100:+.0f}" if st.win_rate_delta is not None else "-"
        print(f"{st.stage:<26}{kept:<16}{drop:<18}{delta:<10}{st.verdict}")

    if getattr(args, "save_report", False):
        report_date = new_york_market_date()
        out_dir = Path(getattr(args, "output_dir", "reports")) / report_date
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "funnel_eval.json"
        out_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"Saved: {out_path}")

    return report.to_dict()


def _load_json_list(path: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def run_tony_divergence(args: argparse.Namespace) -> dict[str, Any]:
    """Build + persist the Tony teaching/divergence ledger: grade Tony's verdicts
    against the bot's resolved outcomes. Research only — pure separation stays; nothing
    here ever touches the bot's paper book.
    """
    from trading_bot.analytics.tony_divergence import (  # noqa: PLC0415
        build_tony_divergence,
        write_divergence_ledger,
    )

    print("Tony divergence - research only. Grades Tony's verdicts vs the bot's outcomes; never trades.")
    verdicts_path = os.environ.get("TONY_VERDICTS_FILE") or "reports/tony_stocks_verdicts.json"
    outcomes_path = os.environ.get("TONY_OUTCOMES_FILE") or "reports/tony_stocks_outcomes.json"
    verdicts = _load_json_list(verdicts_path)
    outcomes = _load_json_list(outcomes_path)

    ledger = build_tony_divergence(verdicts, outcomes)
    out = write_divergence_ledger(ledger)
    tallies = ledger.tallies

    print(f"Verdicts: {len(verdicts)} | Outcomes: {len(outcomes)} | Graded records: {len(ledger.records)}")
    print(
        f"agreed_right={tallies['agreed_right']} agreed_wrong={tallies['agreed_wrong']} "
        f"cc_overrode_saved={tallies['cc_overrode_saved']} cc_overrode_missed={tallies['cc_overrode_missed']} "
        f"pending={tallies['pending']}"
    )
    divergences = [r for r in ledger.records if r.classification.startswith("cc_overrode")]
    if divergences:
        print("Recent divergences (Tony vs bot, who was right):")
        for r in divergences[:15]:
            who = "tony" if r.classification == "cc_overrode_saved" else "bot"
            ret = f"{r.return_pct:+.1f}%" if r.return_pct is not None else "-"
            print(f"  {r.symbol} {r.pick_date}: tony={r.verdict} -> {who} right ({ret}) :: {r.tony_reasoning[:70]}")
    print(f"Teaching ledger: {out}")
    return ledger.to_dict()


def run_learn(args: argparse.Namespace) -> int:
    """Nightly self-learning pass. Reads resolved outcomes + teaching ledger + funnel
    eval, grades them across dimensions, evolves the running knowledge base, narrates
    the lessons (Claude, falling back to deterministic templates), and writes four
    sinks: the dated vault note, the living _knowledge.md, the dashboard insights, and
    the Command Center bridge brief. READ-ONLY on all trading surfaces; fail-quiet per
    step so a 1:30am scheduled run always exits 0. See design spec
    docs/superpowers/specs/2026-06-04-nightly-self-learning-design.md.
    """
    from datetime import date as _date  # noqa: PLC0415

    from trading_bot.analytics.nightly_learning import build_nightly_facts  # noqa: PLC0415
    from trading_bot.analytics.learning_knowledge import (  # noqa: PLC0415
        knowledge_from_dict,
        update_knowledge,
    )
    from trading_bot.analytics.learning_narrator import narrate  # noqa: PLC0415
    from trading_bot.analytics.llm_clients import (  # noqa: PLC0415
        make_llm_client,
        model_for,
        resolve_provider,
    )
    from trading_bot.vault.learning_writer import (  # noqa: PLC0415
        write_learning_note,
        write_knowledge_page,
        write_cc_learning_bridge,
    )
    from trading_bot.agent_bridge import record_agent_insights_batch  # noqa: PLC0415

    settings = load_scanner_settings(args.config)
    lcfg = getattr(settings, "learning", None) or {}
    vault_cfg = getattr(settings, "vault", None) or {}
    as_of = args.date or str(_date.today())
    reports = Path(args.reports_dir)
    vault_dir = args.vault_dir or vault_cfg.get("vault_dir", "vault")
    cc_dir = args.command_center_dir or vault_cfg.get("command_center_dir")
    use_llm = (not args.no_llm) and bool(lcfg.get("use_llm", True))
    min_sample = args.min_sample if getattr(args, "min_sample", None) is not None else int(lcfg.get("min_sample", 5))
    history_cap = int(lcfg.get("knowledge_history_cap", 30))
    provider = resolve_provider(lcfg.get("provider")) if use_llm else "none"
    model = model_for(provider, lcfg)

    print("Nightly learning - research only. Read-only on trading; never edits config/risk.")

    def _read_json(name: str, default: Any) -> Any:
        try:
            return json.loads((reports / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    # Self-contained nightly: produce/refresh reports/funnel_eval.json before building
    # facts so the funnel evaluation always feeds the learner. Fail-quiet — a bad
    # funnel-eval never stops the learning run (read-only on trading surfaces).
    _refresh_funnel_eval_for_learning(
        reports, args.config, days=int(getattr(args, "days", None) or 120),
        min_sample=min_sample)

    outcomes = _read_json("tony_stocks_outcomes.json", [])
    teaching = _read_json("tony_teaching_log.json", None)
    funnel = _read_json("funnel_eval.json", None)
    prior_kb = knowledge_from_dict(_read_json("learning_knowledge.json", None))
    try:
        notes = sorted((Path(vault_dir) / "learning").glob("20*.md"))
        prior_note = notes[-1].read_text(encoding="utf-8") if notes else None
    except OSError:
        prior_note = None

    facts = build_nightly_facts(outcomes, teaching, funnel, None,
                                as_of=as_of, min_sample=min_sample)
    kb = update_knowledge(prior_kb, facts, history_cap=history_cap)

    client = make_llm_client(provider) if use_llm and provider != "none" else None
    narration = narrate(facts, kb, prior_note, client=client, use_llm=use_llm, model=model)

    bridge_expected = bool(cc_dir and not args.no_bridge and lcfg.get("bridge_to_cc", True))

    failures: list[str] = []
    for label, fn in (
        ("vault note", lambda: write_learning_note(vault_dir, facts, narration)),
        ("knowledge page", lambda: write_knowledge_page(vault_dir, kb)),
        ("knowledge json", lambda: _write_knowledge_json(reports, kb)),
        ("dashboard insights", lambda: record_agent_insights_batch(
            narration.insights, on_date=as_of, path=reports / "agent_insights.json")),
    ):
        try:
            fn()
        except Exception as exc:  # keep the run alive, but record the failure loudly
            failures.append(label)
            LOGGER.warning("[learn] sink FAILED (%s) for %s: %s", label, as_of, exc)
            print(f"[learn] sink error ({label}): {exc}")

    if bridge_expected:
        try:
            write_cc_learning_bridge(cc_dir, facts, kb, narration)
        except Exception as exc:
            failures.append("cc bridge")
            LOGGER.warning("[learn] sink FAILED (cc bridge) for %s: %s", as_of, exc)
            print(f"[learn] bridge error: {exc}")

    # Freshness self-check — the loop's whole point is to FEED today's lessons back.
    # A fail-quiet sink, or the disk-idempotent CC-bridge skip leaving nothing, must
    # not pass silently. Verify each dated feedback file actually landed for as_of;
    # a missing/empty one means the loop is degraded and gets surfaced loudly below.
    for label in _verify_learning_sinks(vault_dir, reports, cc_dir, as_of, bridge_expected):
        if label not in failures:
            failures.append(label)
        LOGGER.warning("[learn] freshness check FAILED: %s missing/empty for %s", label, as_of)
        print(f"[learn] STALE: {label} not written for {as_of}")

    llm_state = "fallback" if narration.template_fallback else f"on ({model})"
    status = "OK" if not failures else f"DEGRADED: {', '.join(failures)} failed"
    print(f"[learn] {as_of}: graded {facts.summary['trades']} trades, "
          f"{len(kb.items)} knowledge items, llm={llm_state} -- {status}")
    _write_learn_health(reports, as_of, failures)
    if failures:
        # Non-zero so the systemd oneshot is marked FAILED (visible in `systemctl --failed`)
        # instead of the loop silently rotting on stale learning.
        LOGGER.error("[learn] %s: feedback loop DEGRADED -- %d sink(s) failed: %s",
                     as_of, len(failures), ", ".join(failures))
        return 1
    return 0


def _write_knowledge_json(reports: Path, kb: Any) -> None:
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "learning_knowledge.json").write_text(
        json.dumps(kb.to_dict(), indent=2), encoding="utf-8")


def _verify_learning_sinks(vault_dir: str | Path, reports: Path, cc_dir: str | None,
                           as_of: str, bridge_expected: bool) -> list[str]:
    """Confirm each nightly feedback file actually landed for ``as_of`` (exists and is
    non-empty). Catches a fail-quiet sink, or the disk-idempotent CC-bridge skip that
    leaves nothing, so a degraded feedback loop never passes as success. Returns the
    labels of the missing/empty sinks (empty list == healthy)."""
    # Only files that MUST be (re)written every run. agent_insights.json is a cumulative
    # mailbox that can legitimately be empty, so it is tracked by the sink try/except
    # (a raise is caught) but not freshness-checked here.
    learning = Path(vault_dir) / "learning"
    checks: list[tuple[str, Path]] = [
        ("vault note", learning / f"{as_of}.md"),
        ("knowledge page", learning / "_knowledge.md"),
        ("knowledge json", reports / "learning_knowledge.json"),
    ]
    if bridge_expected and cc_dir:
        checks.append(("cc bridge",
                       Path(cc_dir) / "bridge" / "tony-stocks" / "learning" / f"{as_of}.md"))
    missing: list[str] = []
    for label, path in checks:
        try:
            if not path.exists() or path.stat().st_size == 0:
                missing.append(label)
        except OSError:
            missing.append(label)
    return missing


def _write_learn_health(reports: Path, as_of: str, failures: list[str]) -> None:
    """Machine-readable health marker (``reports/learning_health.json``) so the dashboard
    and the next run can see whether the nightly feedback loop was fully delivered.
    Best-effort: never raises (a health-write failure must not break the run)."""
    from datetime import datetime, timezone  # noqa: PLC0415
    try:
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "learning_health.json").write_text(json.dumps({
            "as_of": as_of,
            "ok": not failures,
            "failed_sinks": failures,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2), encoding="utf-8")
    except Exception as exc:  # never let the health marker break the run
        LOGGER.warning("[learn] could not write learning_health.json: %s", exc)


# ---------------------------------------------------------------------------
# Off-hours research engine — CLI helpers + guards
# ---------------------------------------------------------------------------

# Stop file path (mirrors run_watch pattern; patchable in tests)
_OFF_HOURS_STOP_FILE = Path("data/STOP_OFF_HOURS")

# Idempotency state file (persists across restarts; mirrors _emit_due_bridges style)
_OFF_HOURS_STATE_FILE = Path("data/off_hours_prep_state.json")


def _now_et() -> datetime:
    """Return current datetime in America/New_York. Extracted for easy monkeypatching in tests."""
    return datetime.now(tz=ZoneInfo("America/New_York"))


def _off_hours_prep_already_run(et_date: str, phase: str) -> bool:
    """Return True if this <et_date>:<phase> key has already been run (disk-idempotent).

    Mirrors _emit_due_bridges idempotency: keyed by '<date>:<phase>' in a JSON set.
    """
    state_file = _OFF_HOURS_STATE_FILE
    if not state_file.is_absolute():
        state_file = Path.cwd() / state_file
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        already_run: set[str] = set(data.get("run_keys", []))
    except (OSError, ValueError, KeyError):
        already_run = set()
    return f"{et_date}:{phase}" in already_run


def _mark_off_hours_prep_run(et_date: str, phase: str) -> None:
    """Persist the <et_date>:<phase> key so subsequent watch cycles skip the prep."""
    state_file = _OFF_HOURS_STATE_FILE
    if not state_file.is_absolute():
        state_file = Path.cwd() / state_file
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        run_keys: list[str] = data.get("run_keys", [])
    except (OSError, ValueError):
        run_keys = []
    key = f"{et_date}:{phase}"
    if key not in run_keys:
        run_keys.append(key)
    # Trim to last 500 entries to prevent unbounded growth
    run_keys = run_keys[-500:]
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({"run_keys": run_keys}, indent=2), encoding="utf-8")
    except OSError:
        pass  # state file write failure is non-fatal


def run_off_hours_prep(args: argparse.Namespace) -> dict[str, Any]:
    """Off-hours research prep: scan → enrich → build morning watchlist → write sinks.

    READ-ONLY on all trading surfaces. Zero execution path: no orders are placed
    off-hours. Fail-quiet per sink (exit 0). Mirrors run_learn for its
    error-collection pattern.

    Returns a summary dict with keys: phase, et_date, shortlist_size, sinks_written,
    errors.
    """
    from trading_bot.analytics.off_hours_window import Phase, current_phase  # noqa: PLC0415
    from trading_bot.analytics.catalyst_enrichment import build_catalyst_tags, CatalystTags  # noqa: PLC0415
    from trading_bot.analytics.morning_prep import build_morning_prep  # noqa: PLC0415
    from trading_bot.vault.morning_prep_writer import (  # noqa: PLC0415
        write_morning_prep_report,
        write_morning_prep_note,
        write_morning_prep_bridge,
    )
    from trading_bot.data.premarket_provider import NullPreMarketProvider  # noqa: PLC0415
    from datetime import date as _date  # noqa: PLC0415

    errors: list[str] = []
    sinks_written: list[str] = []

    # --- 1. Clock / phase ---
    now_et = _now_et()
    et_date = now_et.strftime("%Y-%m-%d")

    phase_override = getattr(args, "phase", None)
    if phase_override:
        phase_str = str(phase_override)
    else:
        phase_str = current_phase(now_et).value

    # --- 2. Settings + dirs ---
    settings = load_scanner_settings(args.config)
    off_cfg = getattr(settings, "off_hours", None) or {}
    vault_cfg = getattr(settings, "vault", None) or {}

    shortlist_size = int(off_cfg.get("shortlist_size", 20))
    blackout_days = int(off_cfg.get("earnings_blackout_days", 5))
    enrich_budget = int(off_cfg.get("enrich_budget", 25))

    reports_dir_str = getattr(args, "reports_dir", None) or "reports"
    vault_dir_str = (getattr(args, "vault_dir", None)
                     or vault_cfg.get("vault_dir", "vault"))
    cc_dir_str = (getattr(args, "command_center_dir", None)
                  or vault_cfg.get("command_center_dir") or None)

    reports_dir = Path(reports_dir_str)

    # --- 3. Scan: load recent scored rows from DB (no new scan needed for off-hours) ---
    scored_rows: list[dict[str, Any]] = []
    try:
        repo = ScannerRepository(settings.database_path)
        df = repo.list_candidate_snapshots(limit=500)
        if not df.empty:
            for _, row in df.iterrows():
                scored_rows.append({
                    "symbol": row.get("symbol", ""),
                    # candidate_snapshots uses: total_score, setup_category,
                    # planned_entry_price, stop, target
                    # Remap to the contract names expected by build_morning_prep:
                    # total_score -> total_score (already correct)
                    # setup_category -> setup_category (already correct)
                    # planned_entry_price -> planned_entry_price (already correct)
                    # stop -> stop_price
                    # target -> target_price
                    "total_score": row.get("total_score"),
                    "setup_category": row.get("setup_category", ""),
                    "planned_entry_price": row.get("planned_entry_price"),
                    "stop_price": row.get("stop"),
                    "target_price": row.get("target"),
                })
    except Exception as exc:
        errors.append(f"scan/db: {exc}")

    # --- 4. Catalyst enrichment (budgeted; degrade to empty tags in demo mode) ---
    catalyst_tags: dict[str, CatalystTags] = {}
    if enrich_budget > 0 and scored_rows:
        try:
            # Use research_providers if keys available; degrade gracefully if not
            from trading_bot.data.research_providers import FmpProvider, FinnhubProvider  # noqa: PLC0415
            fmp = FmpProvider(api_key=os.getenv("FMP_API_KEY", ""))
            finnhub = FinnhubProvider(api_key=os.getenv("FINNHUB_API_KEY", ""))

            today = now_et.date()
            # One bulk earnings calendar call if FMP available
            earnings_map: dict[str, _date] = {}
            if fmp.available:
                try:
                    from datetime import timedelta as _td  # noqa: PLC0415
                    earnings_map = fmp.earnings_calendar(today, today + _td(days=30))
                except Exception:
                    pass

            top_symbols = [r["symbol"] for r in scored_rows[:enrich_budget] if r.get("symbol")]
            for sym in top_symbols:
                try:
                    rec = None
                    if finnhub.available:
                        rec_score = finnhub.recommendation(sym)
                        if rec_score is not None:
                            rec = {"buy": max(0, int(rec_score * 10)), "sell": 0,
                                   "strongBuy": 0, "strongSell": 0}
                    catalyst_tags[sym] = build_catalyst_tags(
                        sym,
                        earnings_date=earnings_map.get(sym),
                        today=today,
                        blackout_days=blackout_days,
                        recommendation_now=rec,
                    )
                except Exception as sym_exc:
                    # Per-symbol failure: degrade to empty tag for that symbol.
                    # Fail-quiet but leave a debug breadcrumb for diagnosis.
                    LOGGER.debug("catalyst enrichment failed for %s: %s", sym, sym_exc)
                    catalyst_tags[sym] = build_catalyst_tags(sym, today=today)
        except Exception as exc:
            errors.append(f"catalyst_enrichment: {exc}")

    # --- 5. OVERNIGHT phase: optional run_learn equivalent (each wrapped, fail-quiet) ---
    learning_facts: dict | None = None
    if phase_str == Phase.OVERNIGHT.value:
        # Refresh funnel_eval (reuse existing helper). The helper is self-contained
        # and fail-quiet (never raises; returns False on failure), so we inspect its
        # return value rather than wrapping it in a try/except that could never fire.
        if not _refresh_funnel_eval_for_learning(
                reports_dir, args.config, days=120, min_sample=5):
            errors.append("funnel_eval_refresh: failed (see logs)")

        # Load existing learning facts from reports (if available)
        try:
            facts_path = reports_dir / "learning_knowledge.json"
            learning_facts = json.loads(facts_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            learning_facts = None

    # --- 6. Optional narrative (from learning_narrator if API key available) ---
    narrative: str | None = None
    try:
        from trading_bot.analytics.learning_narrator import narrate  # noqa: PLC0415
        from trading_bot.analytics.llm_clients import (  # noqa: PLC0415
            make_llm_client, model_for, resolve_provider,
        )
        from trading_bot.analytics.learning_knowledge import knowledge_from_dict  # noqa: PLC0415

        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY"):
            _lcfg = getattr(settings, "learning", None) or {}
            _provider = resolve_provider(_lcfg.get("provider"))
            _model = model_for(_provider, _lcfg)
            _client = make_llm_client(_provider) if _provider != "none" else None
            if _client is not None:
                _kb = knowledge_from_dict(None)
                narration = narrate({}, _kb, None,  # type: ignore[arg-type]
                                    client=_client, use_llm=True, model=_model)
                if narration and not narration.template_fallback:
                    narrative = str(narration)
    except Exception as exc:
        errors.append(f"narrative: {exc}")

    # --- 7. Premarket provider (null by default; wiring exists for future real providers) ---
    _pm_provider_name = off_cfg.get("premarket_provider", "null")
    _pm_provider = NullPreMarketProvider()  # noqa: F841  — seam exists; premarket=None to assembler

    # --- 8. Build the morning prep package ---
    try:
        prep = build_morning_prep(
            scored_rows=scored_rows,
            catalyst_tags=catalyst_tags,
            learning_facts=learning_facts,
            now_et=now_et,
            phase=phase_str,
            shortlist_size=shortlist_size,
        )
    except Exception as exc:
        errors.append(f"build_morning_prep: {exc}")
        # Return minimal summary even if the assembler fails
        return {
            "phase": phase_str,
            "et_date": et_date,
            "shortlist_size": shortlist_size,
            "sinks_written": sinks_written,
            "errors": errors,
        }

    # --- 9. Write all four sinks, each in its own try/except (fail-quiet) ---
    for label, fn in (
        ("report (json+md)", lambda: write_morning_prep_report(
            prep, reports_dir=reports_dir)),
        ("vault note", lambda: write_morning_prep_note(
            prep, vault_dir=vault_dir_str, narrative=narrative)),
        ("cc bridge", lambda: write_morning_prep_bridge(
            prep, command_center_dir=cc_dir_str, narrative=narrative)),
    ):
        try:
            path = fn()
            # write_morning_prep_bridge returns None when no CC dir is configured.
            if path is not None:
                sinks_written.append(str(path))
        except Exception as exc:
            errors.append(f"sink({label}): {exc}")
            print(f"[off-hours-prep] sink error ({label}): {exc}")

    print(
        f"[off-hours-prep] {et_date} phase={phase_str}: "
        f"{len(prep.shortlist)} candidates, "
        f"{len(sinks_written)} sinks written, "
        f"{len(errors)} error(s)"
    )
    return {
        "phase": phase_str,
        "et_date": et_date,
        "shortlist_size": shortlist_size,
        "sinks_written": sinks_written,
        "errors": errors,
    }


def run_off_hours_watch(args: argparse.Namespace) -> dict[str, Any]:
    """Inverse watch loop: runs off-hours prep once per ET date+phase; skips during
    market hours. Honors a stop file and --max-cycles for clean termination.

    ZERO execution path: no paper trades, no order submission, no live trading.
    All prep runs are read-only research only.
    """
    from trading_bot.analytics.off_hours_window import Phase, current_phase  # noqa: PLC0415

    settings = load_scanner_settings(args.config)
    off_cfg = getattr(settings, "off_hours", None) or {}

    cadence_override = getattr(args, "cadence_minutes", None)
    cadence_minutes = float(cadence_override or off_cfg.get("cadence_minutes", 30))
    cadence_seconds = max(0, int(cadence_minutes * 60))

    max_cycles_val = getattr(args, "max_cycles", None)
    max_cycles: int | None = int(max_cycles_val) if max_cycles_val is not None else None

    stop_file = _OFF_HOURS_STOP_FILE
    if not stop_file.is_absolute():
        stop_file = Path.cwd() / stop_file

    print("Off-Hours Watch Mode — research only. No paper trades, no order submission, no live trading.")
    print(f"Config: {args.config}")
    print(f"Cadence: {cadence_minutes:g} minutes")
    print(f"Max cycles: {max_cycles if max_cycles is not None else 'unlimited'}")
    print(f"Stop file: {stop_file}")

    cycle = 0
    prep_args = SimpleNamespace(
        config=args.config,
        phase=None,
        reports_dir=None,
        vault_dir=None,
        command_center_dir=None,
    )

    stopped_by = "unknown"
    while True:
        # --- Stop file check (mirror run_watch) ---
        if stop_file.exists():
            print(f"[off-hours-watch] stop file detected ({stop_file}); exiting.")
            stopped_by = "stop_file"
            break

        # --- Max-cycles check ---
        if max_cycles is not None and cycle >= max_cycles:
            stopped_by = "max_cycles"
            break

        now_et = _now_et()
        et_date = now_et.strftime("%Y-%m-%d")
        phase = current_phase(now_et)

        if phase == Phase.MARKET_HOURS:
            # Market hours: NO prep — just sleep and continue
            LOGGER.debug("off-hours-watch: MARKET_HOURS — skipping prep this tick")
            cycle += 1
            if cadence_seconds > 0 and (max_cycles is None or cycle < max_cycles):
                time.sleep(cadence_seconds)
            continue

        phase_str = phase.value

        # --- Idempotency: only run prep once per <et_date>:<phase> ---
        if _off_hours_prep_already_run(et_date, phase_str):
            cycle += 1
            if cadence_seconds > 0 and (max_cycles is None or cycle < max_cycles):
                time.sleep(cadence_seconds)
            continue

        # --- Run the prep ---
        try:
            prep_args.phase = phase_str
            run_off_hours_prep(prep_args)
            _mark_off_hours_prep_run(et_date, phase_str)
        except Exception as exc:  # pragma: no cover - run_off_hours_prep is itself fail-quiet
            LOGGER.warning("off-hours-watch: prep error (phase=%s): %s", phase_str, exc)

        cycle += 1
        if cadence_seconds > 0 and (max_cycles is None or cycle < max_cycles):
            time.sleep(cadence_seconds)

    return {"cycles_completed": cycle, "stopped_by": stopped_by}


def run_paper_status(args: argparse.Namespace) -> dict[str, Any]:
    """Print paper-trading account/positions status. Read-only."""
    from trading_bot.execution import load_paper_trading_config  # noqa: PLC0415

    settings = load_scanner_settings(args.config)
    cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
    repo = ScannerRepository(settings.database_path)
    print(f"Paper trading: {'ENABLED' if cfg.enabled else 'disabled'} (account '{cfg.account_label}')")
    if cfg.disabled_reason:
        print(f"  reason: {cfg.disabled_reason}")
    open_rows = repo.list_open_paper_positions(account_label=cfg.account_label)
    closed_rows = [r for r in repo.list_paper_positions(account_label=cfg.account_label) if r["status"] == "closed"]
    print(f"Open positions: {len(open_rows)}")
    for r in open_rows:
        print(f"  {r['symbol']}: qty={r['qty']} entry={r['entry_price']} stop={r['stop']} target={r['target']}")
    target_hits = sum(1 for r in closed_rows if r.get("result") == "target_hit")
    stop_hits = sum(1 for r in closed_rows if r.get("result") == "stop_hit")
    realized = sum(float(r["realized_pl"]) for r in closed_rows if r.get("realized_pl") is not None)
    print(f"Closed: {len(closed_rows)} (target_hits={target_hits} stop_hits={stop_hits}) realized P/L ${realized:,.2f}")
    return {"enabled": cfg.enabled, "open": len(open_rows), "closed": len(closed_rows), "realized_pl": realized}


def run_paper_flatten(args: argparse.Namespace) -> dict[str, Any]:
    """Kill switch: close all open paper positions at the broker and in the ledger."""
    from trading_bot.execution import build_alpaca_paper_broker, load_paper_trading_config  # noqa: PLC0415

    settings = load_scanner_settings(args.config)
    cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
    repo = ScannerRepository(settings.database_path)
    open_rows = repo.list_open_paper_positions(account_label=cfg.account_label)
    if not open_rows:
        print("No open paper positions to flatten.")
        return {"flattened": 0}
    try:
        broker = build_alpaca_paper_broker(cfg)
    except Exception as exc:
        print(f"Could not build broker to flatten ({exc}).")
        return {"flattened": 0, "error": str(exc)}
    from trading_bot.execution.paper_engine import _latest_close_records, _realized_pl  # noqa: PLC0415

    flattened = 0
    for r in open_rows:
        sym = str(r["symbol"]).upper()
        try:
            if broker.close_position(sym) is None:
                # Live broker returns None on any close failure. Closing the repo row
                # anyway would leave a REAL open position with nothing tracking it.
                print(f"  failed to flatten {sym}: broker refused the close; row left open (re-run to retry)")
                continue
            record = _latest_close_records(broker).get(sym, {})
            realized = record.get("realized_pl")
            if realized is None:  # live broker reports no P&L — compute from entry + exit fill
                realized = _realized_pl(r, record.get("exit"))
            repo.close_paper_position(
                sym, account_label=cfg.account_label, result="closed",
                exit_price=record.get("exit"), realized_pl=realized,
                closed_at=utc_now_iso(),
            )
            flattened += 1
            print(f"  flattened {sym}")
        except Exception as exc:
            print(f"  failed to flatten {sym}: {exc}")
    print(f"Flattened {flattened} position(s).")
    return {"flattened": flattened}


def run_paper_reprotect(args: argparse.Namespace) -> dict[str, Any]:
    """Re-attach GTC stop/target (OCO) protection to open paper positions.

    For positions held at the broker that lack a live protective sell order (e.g.
    their original day-TIF bracket legs expired at a prior close), submit a GTC OCO
    using the position's stored stop/target. Idempotent: skips any symbol that
    already has an open protective sell order, so re-running never double-protects.
    """
    from trading_bot.execution import build_alpaca_paper_broker, load_paper_trading_config  # noqa: PLC0415

    settings = load_scanner_settings(args.config)
    cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
    repo = ScannerRepository(settings.database_path)
    open_rows = repo.list_open_paper_positions(account_label=cfg.account_label)
    if not open_rows:
        print("No open paper positions to protect.")
        return {"protected": 0, "skipped": 0}
    try:
        broker = build_alpaca_paper_broker(cfg)
    except Exception as exc:
        print(f"Could not build broker ({exc}).")
        return {"protected": 0, "skipped": 0, "error": str(exc)}

    held = {p.symbol.upper() for p in broker.list_positions()}
    already = broker.open_protective_symbols()
    tif = cfg.time_in_force if cfg.time_in_force == "gtc" else "gtc"  # protection must persist
    protected = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    for r in open_rows:
        sym = str(r["symbol"]).upper()
        if sym not in held:
            print(f"  skip {sym}: not held at broker"); skipped += 1; continue
        if sym in already:
            print(f"  skip {sym}: already has an open protective order"); skipped += 1; continue
        stop, target, qty = r.get("stop"), r.get("target"), r.get("qty")
        if stop is None or target is None or not qty:
            print(f"  skip {sym}: missing stop/target/qty"); skipped += 1; continue
        try:
            order = broker.submit_protection(
                symbol=sym, qty=int(qty), stop=float(stop), target=float(target), time_in_force=tif,
            )
            protected += 1
            results.append({"symbol": sym, "order_id": order.order_id, "stop": float(stop), "target": float(target)})
            print(f"  protected {sym}: qty={qty} stop={stop} target={target} (order {order.order_id})")
        except Exception as exc:
            print(f"  FAILED {sym}: {exc}")
            results.append({"symbol": sym, "error": str(exc)})
    print(f"Re-protected {protected} position(s); skipped {skipped}.")
    return {"protected": protected, "skipped": skipped, "results": results}


def run_paper_check(args: argparse.Namespace) -> dict[str, Any]:
    """Verify the bot's Alpaca PAPER account connects (and optionally can send a trade).

    Read-only by default (account snapshot). With --test-order SYMBOL it submits a
    1-share bracket then immediately flattens it, proving trade submission works.
    """
    from trading_bot.execution import build_alpaca_paper_broker, load_paper_trading_config  # noqa: PLC0415

    settings = load_scanner_settings(args.config)
    cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
    print(f"Paper base URL: {cfg.base_url} | account label: '{cfg.account_label}'")
    print("(uses ALPACA_PAPER_API_KEY/SECRET if set, else ALPACA_API_KEY/SECRET)")
    try:
        broker = build_alpaca_paper_broker(cfg)
        account = broker.account()
    except Exception as exc:
        print(f"FAILED to connect to Alpaca paper account: {exc}")
        return {"ok": False, "error": str(exc)}
    print(
        f"Account OK — number {account.account_number or '(n/a)'} | "
        f"equity ${account.equity:,.2f}, cash ${account.cash:,.2f}, "
        f"buying power ${account.buying_power:,.2f}"
    )
    print("  (compare this account number to the Command Center's Tony account — they MUST differ)")
    result: dict[str, Any] = {"ok": True, "equity": account.equity, "account_number": account.account_number}

    symbol = getattr(args, "test_order", None)
    if symbol:
        try:
            df = load_yfinance(symbol)
            close_col = "Close" if "Close" in df.columns else "close"
            price = float(df[close_col].iloc[-1])
            entry, stop, target = round(price, 2), round(price * 0.95, 2), round(price * 1.05, 2)
            print(f"Submitting TEST bracket: 1 {symbol.upper()} ~{entry} (stop {stop} / target {target})")
            order = broker.submit_bracket(
                symbol=symbol, qty=1, entry=entry, stop=stop, target=target,
                time_in_force=cfg.time_in_force,
            )
            print(f"  submitted: id={order.order_id} status={order.status}")
            position = broker.get_position(symbol)
            if position is not None:
                broker.close_position(symbol)
                print("  filled — test position flattened.")
            else:
                print("  queued (market closed / not yet filled) — left as proof it reached the account.")
            result["test_order_id"] = order.order_id
        except Exception as exc:
            print(f"  TEST ORDER failed: {exc}")
            result["test_order_error"] = str(exc)
    return result


def _emit_due_bridges(
    config_path: str,
    now_et: datetime,
    emitted_slots: set[str],
) -> set[str]:
    """Emit any intraday/EOD bridges due at the current US Eastern time. Idempotent.

    Checkpoints (America/New_York, inside the 9:30-16:00 ET session): 10:30, 13:00,
    15:30, and the 16:00 EOD. Disk-idempotent so a watch restart never re-drops a
    slot. Failures are logged and never break the watch loop.
    """
    from trading_bot.vault import due_bridge_slots  # noqa: PLC0415

    due = due_bridge_slots(now_et, emitted_slots)
    if not due:
        return emitted_slots
    try:
        settings = load_scanner_settings(config_path)
    except (FileNotFoundError, OSError, ValueError):
        return emitted_slots
    vault_cfg = settings.vault or {}
    if not vault_cfg.get("enabled", False) or not vault_cfg.get("bridge_enabled", False):
        emitted_slots.update(due)  # nothing to write; don't retry every cycle
        return emitted_slots
    cc_dir = vault_cfg.get("command_center_dir", "")
    date = now_et.strftime("%Y-%m-%d")
    for slot in due:
        is_intraday = slot != "eod"
        fname = f"{date}T{slot}.md" if is_intraday else f"{date}.md"
        bridge_file = Path(cc_dir) / "bridge" / "tony-stocks" / fname if cc_dir else None
        if bridge_file is not None and bridge_file.exists():
            emitted_slots.add(slot)  # already on disk (e.g. after a restart)
            continue
        try:
            eod_result = run_eod_report(SimpleNamespace(config=config_path, date=date))
            _run_vault_export(date, eod_result, config_path, slot=slot)
            emitted_slots.add(slot)
            print(f"Bridge emitted for slot {slot} ({date} ET)")
            LOGGER.info("Intraday bridge emitted: slot=%s date=%s", slot, date)
        except Exception as exc:  # never break the watch loop on a bridge failure
            LOGGER.warning("Bridge emit for slot %s failed: %s", slot, exc)
    return emitted_slots


def _run_vault_export(
    date: str,
    eod_result: dict[str, Any],
    config_path: str,
    slot: str | None = None,
) -> dict[str, Any]:
    """Load active snapshots from DB, compute days_active, write vault + bridge files.

    ``slot`` controls bridge cadence (see write_bridge_export). For an intraday slot
    only the bridge + outcomes are written (the repo vault daily note / ticker pages
    / index stay an EOD artifact); the canonical EOD run writes everything.
    """
    is_intraday = bool(slot) and slot != "eod"
    try:
        settings = load_scanner_settings(config_path)
    except (FileNotFoundError, OSError) as exc:
        return {"skipped": True, "reason": f"config not loadable: {exc}"}
    vault_cfg = settings.vault or {}
    if not vault_cfg.get("enabled", False):
        return {"skipped": True, "reason": "vault.enabled is false in config"}

    vault_dir = vault_cfg.get("vault_dir", "vault")
    command_center_dir = vault_cfg.get("command_center_dir", "")
    bridge_enabled = vault_cfg.get("bridge_enabled", False)

    repo = ScannerRepository(settings.database_path)
    df = repo.list_snapshots_for_analytics(days=60)

    snapshots: list[dict[str, Any]] = []
    try:
        open_pos_syms = {str(p["symbol"]).upper() for p in repo.list_open_paper_positions()}
    except Exception:
        open_pos_syms = set()
    active_count = len(open_pos_syms)  # the live paper book = carry-over positions
    if not df.empty:
        df["_date"] = pd.to_datetime(df["snapshot_time"], utc=True).dt.date
        days_active_map: dict[str, int] = df.groupby("symbol")["_date"].nunique().to_dict()
        latest = df.sort_values("snapshot_time", ascending=False).drop_duplicates(subset=["symbol"])
        try:
            anchor = pd.to_datetime(date).date()
        except Exception:
            anchor = None

        def _live(value: Any) -> Any:
            return None if value is None or (isinstance(value, float) and pd.isna(value)) else value

        for _, row in latest.iterrows():
            sym = str(row.get("symbol", ""))
            row_date = row.get("_date")
            # Only hand the CC symbols seen in the last few days, so prices/levels match
            # the live feed — not 60-day-stale rows that trip Tony's data-integrity check.
            if anchor is not None and row_date is not None and (anchor - row_date).days > 3:
                continue
            entry_status = str(row.get("entry_status") or "").lower()
            triggered = (
                sym.upper() in open_pos_syms
                or entry_status == "triggered"
                or bool(_live(row.get("entry_triggered")))
            )
            # Live price first (intraday-refreshed); daily close only as a last resort.
            latest_close = (
                _live(row.get("current_price"))
                or _live(row.get("intraday_close"))
                or _live(row.get("close"))
            )
            snapshots.append({
                "symbol": sym,
                "score": row.get("total_score"),
                "setup_category": row.get("setup_category", ""),
                "status": "active" if triggered else (row.get("outcome_label") or ""),
                "days_active": days_active_map.get(sym, 1),
                "latest_close": latest_close,
                "target_price": row.get("target"),
                "stop_price": row.get("stop"),
            })

    # Reflect the live book in the bridge's "Active carry-over" line.
    _tos = eod_result.get("terminal_outcome_summary")
    if isinstance(_tos, dict):
        _tos["active_count"] = active_count
    else:
        eod_result["terminal_outcome_summary"] = {"active_count": active_count}

    files_written: list[str] = []

    if not is_intraday:
        daily_path = write_daily_note(date, eod_result, vault_dir, snapshots=snapshots)
        files_written.append(str(daily_path))

        for snap in snapshots:
            ticker_path = upsert_ticker_page(date, snap, vault_dir)
            files_written.append(str(ticker_path))

        index_path = update_vault_index(date, snapshots, vault_dir)
        files_written.append(str(index_path))

    if bridge_enabled and command_center_dir:
        bridge_path = write_bridge_export(date, eod_result, command_center_dir, snapshots=snapshots, slot=slot)
        files_written.append(str(bridge_path))

    if bridge_enabled:
        # Emit resolved outcomes so the Command Center can grade Tony's verdicts.
        # Sourced from the real-only resolved snapshot history; path defaults to
        # reports/tony_stocks_outcomes.json (honors TONY_OUTCOMES_FILE) and is
        # independent of command_center_dir.
        outcomes_path, outcomes_count = _emit_tony_outcomes(repo, date)
        files_written.append(str(outcomes_path))

    return {
        "vault_dir": str(vault_dir),
        "bridge_enabled": bridge_enabled,
        "snapshots_processed": len(snapshots),
        "files_written": files_written,
    }


def run_export_to_vault(args: argparse.Namespace) -> dict[str, Any]:
    """Export latest EOD data to Obsidian vault and bridge. Research only."""
    report_date = getattr(args, "date", None) or new_york_market_date()
    print(f"Vault export — {report_date} {MARKET_TIMEZONE_LABEL}")
    print("Research only: reads DB, writes markdown. No scoring or trading changes.")

    slot = getattr(args, "slot", None)
    eod_args = SimpleNamespace(config=args.config, date=report_date)
    eod_result = run_eod_report(eod_args)

    result = _run_vault_export(report_date, eod_result, args.config, slot=slot)
    if result.get("skipped"):
        print(f"Vault export skipped: {result.get('reason')}")
        return result

    print(f"Vault: {result['vault_dir']}")
    print(f"Snapshots processed: {result['snapshots_processed']}")
    print(f"Files written: {len(result['files_written'])}")
    if result.get("bridge_enabled"):
        print("Bridge export: enabled")
    return result


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "backtest":
        run_backtest(args)
    elif args.command == "scan":
        run_scan(args)
    elif args.command == "snapshot":
        args.save_snapshots = True
        run_scan(args)
    elif args.command == "update-snapshots":
        run_update_snapshots(args)
    elif args.command == "seed-demo-snapshots":
        run_seed_demo_snapshots(args)
    elif args.command == "watch":
        run_watch(args)
    elif args.command == "tony-events":
        run_tony_events(args)
    elif args.command == "outcome-analytics":
        run_outcome_analytics(args)
    elif args.command == "backtest-review":
        run_backtest_review(args)
    elif args.command == "eod-report":
        run_eod_report(args)
    elif args.command == "after-market-review":
        run_after_market_review(args)
    elif args.command == "record-suggestion-decision":
        run_record_suggestion_decision(args)
    elif args.command == "activate-strategy-version":
        run_activate_strategy_version(args)
    elif args.command == "data-check":
        run_data_check(args)
    elif args.command == "provider-health":
        run_provider_health(args)
    elif args.command == "export-to-vault":
        run_export_to_vault(args)
    elif args.command == "emit-outcomes":
        run_emit_outcomes(args)
    elif args.command == "funnel-eval":
        run_funnel_eval(args)
    elif args.command == "tony-divergence":
        run_tony_divergence(args)
    elif args.command == "learn":
        run_learn(args)
    elif args.command == "off-hours-prep":
        run_off_hours_prep(args)
    elif args.command == "off-hours-watch":
        run_off_hours_watch(args)
    elif args.command == "paper-status":
        run_paper_status(args)
    elif args.command == "paper-flatten":
        run_paper_flatten(args)
    elif args.command == "paper-check":
        run_paper_check(args)
    elif args.command == "paper-reprotect":
        run_paper_reprotect(args)
    else:
        parser.error(f"Unknown command: {args.command}")


def _print_entry_trigger_planned_summary(entry_plans: dict[str, dict[str, Any]]) -> None:
    """Print research-only planned intraday trigger summary at snapshot creation."""
    with_planned = sum(1 for plan in entry_plans.values() if plan.get("planned_entry_price") not in (None, ""))
    pending = sum(1 for plan in entry_plans.values() if plan.get("entry_status") == "pending")
    missing = sum(1 for plan in entry_plans.values() if plan.get("entry_status") == "missing_real_data")
    no_trigger = sum(1 for plan in entry_plans.values() if plan.get("entry_status") == "no_intraday_trigger")
    print(
        f"Entry trigger plans: planned={with_planned} pending={pending} "
        f"missing_real_data={missing} no_intraday_trigger={no_trigger}"
    )
    samples = [
        (symbol, plan)
        for symbol, plan in entry_plans.items()
        if plan.get("planned_entry_price") not in (None, "")
    ][:5]
    for symbol, plan in samples:
        print(
            f"  {symbol}: snapshot={plan.get('snapshot_price')} "
            f"planned={plan.get('planned_entry_price')} rule={plan.get('planned_entry_rule')}"
        )


def _print_snapshot_summary(results: list[object], snapshot_count: int) -> None:
    """Print a concise candidate snapshot summary."""
    primary_count = sum(1 for result in results if getattr(result, "universe_role", "") == "primary_candidate")
    speculative_count = sum(1 for result in results if getattr(result, "universe_role", "") == "speculative_candidate")
    reference_count = sum(1 for result in results if getattr(result, "universe_role", "") in {"benchmark", "reference"})
    warnings_count = sum(len(getattr(result, "warnings", [])) for result in results)
    categories: dict[str, int] = {}
    for result in results:
        category = getattr(result, "setup_category", "Uncategorized")
        categories[category] = categories.get(category, 0) + 1
    top_categories = ", ".join(f"{category}: {count}" for category, count in sorted(categories.items(), key=lambda item: (-item[1], item[0]))[:5])
    print("\nCandidate snapshots:")
    print(f"Snapshots created: {snapshot_count}")
    print(f"Primary candidates scored: {primary_count}")
    print(f"Speculative candidates scored: {speculative_count}")
    print(f"Benchmark/reference symbols scored: {reference_count}")
    print(f"Warnings across scored symbols: {warnings_count}")
    print(f"Top setup categories: {top_categories}")


def _log_pre_screen_result(result: PreScreenResult) -> None:
    """Print a one-line pre-screener summary to stdout and log detail."""
    if result.fallback_used:
        print(
            f"Pre-screener: filtered pool too small ({result.filtered_count}); "
            f"using full list ({result.original_count} symbols)."
        )
    else:
        print(
            f"Pre-screener: {result.original_count} -> {result.symbols.__len__()} symbols "
            f"(screened_out={result.screened_out_count} no_cache_data={result.no_cache_data_count})"
        )
        if result.screened_out_count > 0:
            reasons_str = ", ".join(
                f"{k}={v}" for k, v in result.reasons.items() if v > 0
            )
            if reasons_str:
                print(f"  Screened-out reasons: {reasons_str}")


def _resolve_watch_max_cycles(args: argparse.Namespace, watch_config: dict[str, Any]) -> int | None:
    if getattr(args, "once", False):
        return 1
    if getattr(args, "max_cycles", None) is not None:
        return int(args.max_cycles)
    configured = watch_config.get("max_cycles")
    if configured in (None, ""):
        return None
    return int(configured)


def _within_watch_window(watch_config: dict[str, Any], timezone_name: str) -> bool:
    now = datetime.now(ZoneInfo(timezone_name)).time()
    start = _parse_watch_time(str(watch_config.get("start_time", "09:35")))
    end = _parse_watch_time(str(watch_config.get("end_time", "16:10")))
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def _parse_watch_time(value: str) -> datetime_time:
    return datetime_time.fromisoformat(value)


def _sleep_until_next_cycle(interval_seconds: int, stop_file: Path) -> bool:
    if interval_seconds <= 0:
        return not stop_file.exists()
    remaining = interval_seconds
    while remaining > 0:
        if stop_file.exists():
            return False
        sleep_for = min(1, remaining)
        time.sleep(sleep_for)
        remaining -= sleep_for
    return not stop_file.exists()


def _print_dataframe(data: pd.DataFrame) -> None:
    if data.empty:
        print("No rows.")
        return
    print(data.fillna("N/A").to_string(index=False))


def _events_on_date(events: pd.DataFrame, date_value: str) -> list[dict[str, Any]]:
    if events.empty or "created_at" not in events.columns:
        return []
    mask = market_date_mask(events["created_at"], date_value)
    return events[mask].to_dict("records")


def _watch_run_summary_for_date(
    repo: Any, report_date: str
) -> tuple[dict[str, Any] | None, int]:
    """Return (latest watch run on report_date, total cycles_completed on report_date).

    Falls back to the globally latest watch run only when no run matches the date,
    so that eod-report --date never inherits watch cycles from a different day.
    """
    runs = repo.recent_watch_runs(limit=200)
    on_date = [
        r for r in runs
        if r.get("started_at") and market_date_mask(
            pd.Series([r["started_at"]]), report_date
        ).iloc[0]
    ]
    if on_date:
        latest = on_date[0]
        total_cycles = sum(int(r.get("cycles_completed", 0) or 0) for r in on_date)
        return latest, total_cycles
    return None, 0


def latest_event_of_type_records(events: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    for row in events:
        if row.get("event_type") == event_type:
            return row
    return None


def all_event_records_of_type(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [row for row in events if row.get("event_type") == event_type]


def _payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    try:
        parsed = json.loads(str(row.get("payload_json") or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def repeated_fallback_symbols(events: list[dict[str, Any]]) -> list[str]:
    counts: Counter[str] = Counter()
    for row in events:
        payload = _payload(row)
        candidates = (
            payload.get("missing_real_data_symbols")
            or payload.get("fallback_symbols")
            or payload.get("intraday_fallback_symbols")
            or payload.get("intraday_missing_symbols")
            or payload.get("symbols_fallback")
            or []
        )
        if isinstance(candidates, str):
            candidates = [candidates]
        for symbol in candidates:
            text = str(symbol).upper().strip()
            if text:
                counts[text] += 1
    if not counts:
        return []
    max_count = max(counts.values())
    if max_count > 1:
        counts = Counter({symbol: count for symbol, count in counts.items() if count > 1})
    return [symbol for symbol, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _top_event_symbols(events: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in events:
        symbol = str(row.get("symbol") or "").upper().strip()
        if symbol and symbol != "NAN":
            counts[symbol] += 1
        payload = _payload(row)
        payload_symbol = str(payload.get("symbol") or "").upper().strip()
        if payload_symbol and payload_symbol != "NAN":
            counts[payload_symbol] += 1
    return counts


def _top_hypotheses(events: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in events:
        if row.get("event_type") != "analyst_candidate_hypothesis":
            continue
        payload = _payload(row)
        label = str(payload.get("setup_read") or payload.get("priority_label") or row.get("title") or "unknown")
        counts[label] += 1
    return counts


def _format_counter(counts: Counter[str], limit: int = 5) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}: {value}" for key, value in counts.most_common(limit))


def _format_count_dict(counts: dict[str, Any], limit: int = 8) -> str:
    if not counts:
        return "none"
    pairs = sorted(((str(key), int(value)) for key, value in counts.items()), key=lambda item: (-item[1], item[0]))
    parts = [f"{key}: {value}" for key, value in pairs[:limit]]
    if len(pairs) > limit:
        parts.append(f"+{len(pairs) - limit} more")
    return ", ".join(parts)


def _build_scan_coverage_summary(
    report_date: str,
    repo: ScannerRepository,
    settings: Any,
    today_events: list[dict[str, Any]],
) -> dict[str, Any]:
    configured_universe_size = _configured_universe_size(settings)
    scan_completed_events = all_event_records_of_type(today_events, "scan_completed")
    scan_payloads = []
    for row in scan_completed_events:
        payload = _payload(row)
        if payload:
            scan_payloads.append(payload)
    latest_scan = scan_payloads[0] if scan_payloads else {}

    selected_loaded = _int_or_none(latest_scan.get("symbols_loaded"))
    scored_symbols = _int_or_none(latest_scan.get("symbols_scored"))
    skipped_symbols = _int_or_none(latest_scan.get("symbols_skipped"))
    missing_real_data_count = _int_or_none(latest_scan.get("missing_real_data_count"))
    if missing_real_data_count is None:
        missing_real_data_count = len(latest_scan.get("missing_real_data_symbols") or [])
    quarantined_symbols = [str(symbol).upper() for symbol in (latest_scan.get("quarantined_symbols") or []) if str(symbol).strip()]
    quarantined_count = _int_or_none(latest_scan.get("quarantined_count"))
    if quarantined_count is None:
        quarantined_count = len(quarantined_symbols)
    real_data_symbols = _int_or_none(latest_scan.get("real_data_symbols"))
    if real_data_symbols is None and selected_loaded is not None:
        real_data_symbols = max(0, selected_loaded - int(missing_real_data_count or 0))
    not_scored_count = None
    if selected_loaded is not None and scored_symbols is not None:
        not_scored_count = max(0, selected_loaded - scored_symbols)

    selected_symbol_set: set[str] = set()
    selected_symbols_available = False
    scored_symbol_set: set[str] = set()
    scored_symbols_available = False
    aggregated_skip_reasons: Counter[str] = Counter()
    skip_payload_available = False
    total_not_scored_across_runs = 0

    for payload in scan_payloads:
        loaded = _int_or_none(payload.get("symbols_loaded"))
        scored = _int_or_none(payload.get("symbols_scored"))
        if loaded is not None and scored is not None:
            total_not_scored_across_runs += max(0, loaded - scored)

        selected_symbols = [str(symbol).upper() for symbol in (payload.get("selected_symbols") or []) if str(symbol).strip()]
        if selected_symbols:
            selected_symbols_available = True
            selected_symbol_set.update(selected_symbols)

        scored_list = [str(symbol).upper() for symbol in (payload.get("scored_symbols") or []) if str(symbol).strip()]
        if scored_list:
            scored_symbols_available = True
            scored_symbol_set.update(scored_list)

        skip_counts = payload.get("skip_reason_counts") or {}
        if isinstance(skip_counts, dict) and skip_counts:
            skip_payload_available = True
            for key in SCAN_SKIP_REASON_KEYS:
                aggregated_skip_reasons[key] += int(skip_counts.get(key, 0) or 0)
            # Backward compat: fold old not_enough_data counts into not_enough_bars only
            # when not_enough_bars was not already set in this payload (avoids double-count).
            if not skip_counts.get("not_enough_bars"):
                aggregated_skip_reasons["not_enough_bars"] += int(skip_counts.get("not_enough_data", 0) or 0)

    scan_runs = repo.list_scan_runs(limit=500)
    run_ids_today = [
        int(run["id"])
        for run in scan_runs
        if run.get("created_at")
        and bool(market_date_mask(pd.Series([run["created_at"]]), report_date).iloc[0])
    ]
    scan_results_today = repo.list_scan_results_for_run_ids(run_ids_today)
    if not scored_symbols_available and not scan_results_today.empty and "symbol" in scan_results_today.columns:
        scored_symbol_set.update(
            str(symbol).upper()
            for symbol in scan_results_today["symbol"].dropna().tolist()
            if str(symbol).strip()
        )
        scored_symbols_available = bool(scored_symbol_set)

    unique_symbols_scanned_today = len(selected_symbol_set) if selected_symbols_available else None
    unique_symbols_scored_today = len(scored_symbol_set) if scored_symbols_available else None
    percent_universe_covered_today = None
    if configured_universe_size and unique_symbols_scanned_today is not None:
        percent_universe_covered_today = round((unique_symbols_scanned_today / configured_universe_size) * 100, 2)

    batch_payload = _payload(latest_event_of_type_records(today_events, "batch_fetch_summary"))
    api_requests = _int_or_none(latest_scan.get("api_requests_used"))
    if api_requests is None:
        api_requests = _int_or_none(batch_payload.get("api_requests"))
    batch_requests = _int_or_none(latest_scan.get("batch_requests_used"))
    if batch_requests is None:
        batch_requests = _int_or_none(batch_payload.get("batch_requests"))

    rotation_events = all_event_records_of_type(today_events, "universe_rotation_summary")
    rotation_payloads = []
    for row in rotation_events:
        payload = _payload(row)
        if payload:
            rotation_payloads.append(payload)
    latest_rotation = rotation_payloads[0] if rotation_payloads else {}
    rotation_bucket_summary = None
    if latest_rotation:
        bucket_ids = sorted(
            {
                int(payload.get("bucket_id"))
                for payload in rotation_payloads
                if payload.get("bucket_id") not in (None, "")
            }
        )
        rotation_bucket_summary = {
            "bucket_ids_today": bucket_ids,
            "latest_bucket_id": _int_or_none(latest_rotation.get("bucket_id")),
            "latest_total": _int_or_none(latest_rotation.get("total")),
            "latest_core_count": _int_or_none(latest_rotation.get("core_count")),
            "latest_open_snapshot_count": _int_or_none(latest_rotation.get("open_snapshot_count")),
            "latest_previous_candidate_count": _int_or_none(latest_rotation.get("previous_candidate_count")),
            "latest_discovery_count": _int_or_none(latest_rotation.get("discovery_count")),
        }

    if not skip_payload_available:
        aggregated_skip_reasons["missing_real_data"] = int(missing_real_data_count or 0)
        aggregated_skip_reasons["quarantined"] = int(quarantined_count or 0)
    aggregated_skip_reasons["missing_real_data"] = max(
        int(aggregated_skip_reasons.get("missing_real_data", 0)),
        int(missing_real_data_count or 0),
    )
    aggregated_skip_reasons["quarantined"] = max(
        int(aggregated_skip_reasons.get("quarantined", 0)),
        int(quarantined_count or 0),
    )
    known_skip_total = sum(
        int(aggregated_skip_reasons.get(key, 0))
        for key in SCAN_SKIP_REASON_KEYS
        if key != "other_unknown"
    )
    aggregated_skip_reasons["other_unknown"] = max(
        int(aggregated_skip_reasons.get("other_unknown", 0)),
        max(0, total_not_scored_across_runs - known_skip_total),
    )
    skip_reason_counts = {
        key: int(aggregated_skip_reasons.get(key, 0))
        for key in SCAN_SKIP_REASON_KEYS
    }

    notes = [
        "Active/core/prior/open-snapshot symbols may repeat across cycles, so daily unique coverage will be lower than raw cycle totals.",
        "The discovery bucket should rotate across cycles; this report only measures coverage and does not change rotation behavior.",
        "A larger universe needs a screener funnel before scanning thousands of stocks end to end.",
    ]

    rotation_diagnostics = build_rotation_diagnostics(
        scan_results_today,
        configured_universe_size=configured_universe_size,
        rotation_bucket_summary=rotation_bucket_summary,
    )

    return {
        "configured_universe_size": configured_universe_size,
        "symbols_selected_loaded": selected_loaded,
        "real_data_symbols": real_data_symbols,
        "symbols_scored": scored_symbols,
        "not_scored_count": not_scored_count,
        "symbols_skipped": skipped_symbols,
        "missing_real_data_count": int(missing_real_data_count or 0),
        "missing_real_data_symbols": [str(symbol).upper() for symbol in (latest_scan.get("missing_real_data_symbols") or []) if str(symbol).strip()],
        "quarantined_count": int(quarantined_count or 0),
        "quarantined_symbols": quarantined_symbols,
        "unique_symbols_scanned_today": unique_symbols_scanned_today,
        "unique_symbols_scored_today": unique_symbols_scored_today,
        "percent_universe_covered_today": percent_universe_covered_today,
        "api_requests": api_requests,
        "batch_requests": batch_requests,
        "rotation_bucket_summary": rotation_bucket_summary,
        "skip_reason_counts": skip_reason_counts,
        "rotation_diagnostics": rotation_diagnostics,
        "notes": notes,
    }


def _configured_universe_size(settings: Any) -> int | None:
    config_path = getattr(settings, "universe_config_path", None)
    if not config_path:
        return None
    try:
        return len(load_universe(config_path))
    except Exception:
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _warning_counts(prepared: pd.DataFrame) -> pd.DataFrame:
    if prepared.empty or "warnings_json" not in prepared.columns:
        return pd.DataFrame(columns=["warning_type", "count"])
    counts: Counter[str] = Counter()
    for raw in prepared["warnings_json"].tolist():
        try:
            warnings = json.loads(str(raw or "[]"))
        except json.JSONDecodeError:
            warnings = []
        if not warnings:
            warnings = ["No warning"]
        for warning in warnings:
            counts[str(warning)] += 1
    return pd.DataFrame(
        [{"warning_type": key, "count": value} for key, value in counts.most_common()]
    )


def _is_heartbeat_stale(
    last_heartbeat_at: str | None,
    stale_minutes: int = 10,
    *,
    now: datetime | None = None,
) -> bool:
    if not last_heartbeat_at:
        return False
    try:
        ts = datetime.fromisoformat(str(last_heartbeat_at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ref = now if now is not None else datetime.now(timezone.utc)
        return (ref - ts).total_seconds() / 60 > stale_minutes
    except Exception:
        return False


_TERMINAL_OUTCOME_LABELS = {"target_hit", "stop_hit", "partial_move", "failed_setup", "expired_no_trigger"}


def _summarize_product_reconciliation(snapshots: pd.DataFrame) -> dict[str, int]:
    """Lightweight raw-vs-product reconciliation used by EOD reporting.

    The Streamlit-era helpers that did per-row hidden/incomplete accounting were
    removed with the dashboard. This version returns the same 15-key dict shape
    using only columns directly available on the prepared DataFrame, so callers
    and markdown output keep working unchanged.
    """
    empty = {
        "raw_snapshot_rows": 0,
        "raw_triggered_entry_rows": 0,
        "product_eligible_rows": 0,
        "product_visible_symbols": 0,
        "deduped_active_positions": 0,
        "deduped_waiting_picks": 0,
        "deduped_closed_results": 0,
        "target_hits": 0,
        "stop_hits": 0,
        "partial_moves": 0,
        "pending_triggers": 0,
        "expired_no_trigger": 0,
        "insufficient_data": 0,
        "incomplete_rows_hidden_from_product_views": 0,
        "history_rows_hidden_from_product_views": 0,
    }
    if snapshots is None or snapshots.empty:
        return empty

    df = snapshots
    out = dict(empty)
    out["raw_snapshot_rows"] = int(len(df))
    if "entry_triggered" in df.columns:
        out["raw_triggered_entry_rows"] = int(
            df["entry_triggered"].fillna(0).astype(int).sum()
        )
    out["product_eligible_rows"] = out["raw_snapshot_rows"]

    symbol_col = "symbol" if "symbol" in df.columns else None
    if symbol_col:
        out["product_visible_symbols"] = int(df[symbol_col].dropna().nunique())

    if "tracking_status" in df.columns and symbol_col:
        active_mask = df["tracking_status"].astype(str).str.lower() == "active"
        out["deduped_active_positions"] = int(df.loc[active_mask, symbol_col].dropna().nunique())

    if "entry_status" in df.columns:
        pending_mask = df["entry_status"].astype(str).str.lower() == "pending"
        out["pending_triggers"] = int(pending_mask.sum())
        if symbol_col:
            out["deduped_waiting_picks"] = int(df.loc[pending_mask, symbol_col].dropna().nunique())

    if "outcome_label" in df.columns:
        labels = df["outcome_label"].astype(str).str.lower()
        out["target_hits"] = int((labels == "target_hit").sum())
        out["stop_hits"] = int((labels == "stop_hit").sum())
        out["partial_moves"] = int((labels == "partial_move").sum())
        out["expired_no_trigger"] = int((labels == "expired_no_trigger").sum())
        out["insufficient_data"] = int((labels == "insufficient_future_data").sum())
        if symbol_col:
            closed_mask = labels.isin(_TERMINAL_OUTCOME_LABELS)
            out["deduped_closed_results"] = int(df.loc[closed_mask, symbol_col].dropna().nunique())

    return out


def _outcome_counts(prepared: pd.DataFrame) -> pd.DataFrame:
    if prepared.empty or "outcome_label" not in prepared.columns:
        return pd.DataFrame(columns=["outcome_label", "count"])
    return (
        prepared["outcome_label"]
        .fillna("unreviewed")
        .value_counts()
        .rename_axis("outcome_label")
        .reset_index(name="count")
    )


def _best_target_hit_group(table: pd.DataFrame | None) -> str:
    if table is None or table.empty or "target_hit_rate" not in table.columns:
        return "none"
    sorted_table = table.sort_values(["target_hit_rate", "total_snapshots"], ascending=[False, False])
    row = sorted_table.iloc[0]
    if float(row.get("target_hit_rate", 0) or 0) <= 0:
        return "none"
    return str(row.iloc[0])


def _print_scan_coverage_summary(coverage: dict[str, Any], header: str = "\nScan coverage and funnel:") -> None:
    print(header)
    print(f"Configured universe size: {coverage.get('configured_universe_size', 'unknown') if coverage.get('configured_universe_size') is not None else 'unknown'}")
    print(f"Symbols selected/loaded: {coverage.get('symbols_selected_loaded', 'unknown') if coverage.get('symbols_selected_loaded') is not None else 'unknown'}")
    print(f"Real-data symbols: {coverage.get('real_data_symbols', 'unknown') if coverage.get('real_data_symbols') is not None else 'unknown'}")
    print(f"Scored symbols: {coverage.get('symbols_scored', 'unknown') if coverage.get('symbols_scored') is not None else 'unknown'}")
    print(f"Not scored: {coverage.get('not_scored_count', 'unknown') if coverage.get('not_scored_count') is not None else 'unknown'}")
    print(f"Skipped symbols: {coverage.get('symbols_skipped', 'unknown') if coverage.get('symbols_skipped') is not None else 'unknown'}")
    print(
        f"Missing real-data symbols: {coverage.get('missing_real_data_count', 0)}"
        + (
            f" ({', '.join(coverage.get('missing_real_data_symbols') or [])})"
            if coverage.get("missing_real_data_symbols")
            else ""
        )
    )
    print(
        f"Quarantined symbols: {coverage.get('quarantined_count', 0)}"
        + (
            f" ({', '.join(coverage.get('quarantined_symbols') or [])})"
            if coverage.get("quarantined_symbols")
            else ""
        )
    )
    unique_scanned_today = coverage.get("unique_symbols_scanned_today")
    unique_scored_today = coverage.get("unique_symbols_scored_today")
    print(f"Unique symbols with bar data today (all symbols that returned OHLCV bars across all scan cycles): {unique_scanned_today if unique_scanned_today is not None else 'unknown'}")
    print(f"Unique symbols fully scored today: {unique_scored_today if unique_scored_today is not None else 'unknown'}")
    pct = coverage.get("percent_universe_covered_today")
    print(f"Percent of universe covered today: {f'{pct:.2f}%' if pct is not None else 'unavailable'}")
    print(
        "Note: 'bar data' count above includes every symbol that returned OHLCV bars in any scan cycle today. "
        "The rotation diagnostics section below counts only symbols tracked via discovery-rotation metadata — "
        "a subset. The difference between these two counts is expected."
    )
    print(f"API requests: {coverage.get('api_requests', 'unknown') if coverage.get('api_requests') is not None else 'unknown'}")
    print(f"Batch requests: {coverage.get('batch_requests', 'unknown') if coverage.get('batch_requests') is not None else 'unknown'}")
    rotation = coverage.get("rotation_bucket_summary") or {}
    if rotation:
        bucket_ids = rotation.get("bucket_ids_today") or []
        print(
            "Rotation bucket summary: "
            f"latest_bucket={rotation.get('latest_bucket_id', 'unknown')} "
            f"total={rotation.get('latest_total', 'unknown')} "
            f"core={rotation.get('latest_core_count', 'unknown')} "
            f"open={rotation.get('latest_open_snapshot_count', 'unknown')} "
            f"prior={rotation.get('latest_previous_candidate_count', 'unknown')} "
            f"discovery={rotation.get('latest_discovery_count', 'unknown')} "
            f"bucket_ids_today={', '.join(str(item) for item in bucket_ids) if bucket_ids else 'unknown'}"
        )
    else:
        print("Rotation bucket summary: unavailable")
    skip_counts = coverage.get("skip_reason_counts") or {}
    print("Skip / not-scored reasons (best available):")
    for key, label in _SKIP_REASON_LABELS.items():
        count = int(skip_counts.get(key, 0) or 0)
        if count or key not in ("not_enough_data", "duplicate_tracked"):
            print(f"  {label}: {count}")
    print("Notes:")
    for note in coverage.get("notes") or []:
        print(f"  - {note}")
    diag = coverage.get("rotation_diagnostics") or {}
    if diag:
        _print_rotation_diagnostics(diag)


def _print_rotation_diagnostics(diag: dict[str, Any], header: str = "\nDiscovery rotation diagnostics:") -> None:
    print(header)
    note = str(diag.get("note") or "").strip()
    if note:
        print(f"  Note: {note}")
    unique = diag.get("unique_symbols_scanned")
    total = diag.get("total_scan_appearances")
    repeats = diag.get("repeat_scan_count")
    pct = diag.get("percent_universe_touched")
    fresh = diag.get("estimated_fresh_discovery")
    print(f"  Unique symbols in rotation tracking (discovery-rotation-selected symbols — subset of total bar-data symbols): {unique if unique is not None else 'unavailable'}")
    print(f"  Total scan appearances: {total if total is not None else 'unavailable'}")
    print(f"  Symbols with repeat scans: {repeats if repeats is not None else 'unavailable'}")
    print(f"  Estimated fresh discovery symbols: {fresh if fresh is not None else 'unavailable'}")
    print(f"  Percent of configured universe touched: {f'{pct:.1f}%' if pct is not None else 'unavailable'}")
    top = diag.get("top_repeated_symbols") or []
    if top:
        print("  Top repeated symbols (by scan count):")
        for item in top:
            label = f" [{item['repeat_label']}]" if item.get("repeat_label") else ""
            role = f" ({item['universe_role']})" if item.get("universe_role") else ""
            print(f"    {item['symbol']}: {item['scan_count']} scans{role}{label}")
    ac = diag.get("active_core_repeats") or []
    if ac:
        print(f"  Active/core expected repeats: {', '.join(r['symbol'] for r in ac)}")
    else:
        print("  Active/core expected repeats: none identified")


def _print_signal_scorecard(scorecard: dict[str, Any], header: str = "\nSignal scorecard:") -> None:
    signals = scorecard.get("signals") or []
    print(header)
    if not signals:
        print("No signal scorecard rows.")
        return
    note = str(scorecard.get("note") or "").strip()
    if note:
        print(f"  {note}")
    for signal in signals:
        print(f"\n  {signal.get('signal_label', signal.get('signal_key', 'Signal'))}:")
        counts = signal.get("counts") or []
        if not counts:
            print("    No rows.")
            continue
        table = pd.DataFrame(counts)
        _print_dataframe(table)


if __name__ == "__main__":
    main()
