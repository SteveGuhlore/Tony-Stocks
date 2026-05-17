from __future__ import annotations

import argparse
import logging
import time
from dataclasses import asdict
from datetime import datetime, time as datetime_time, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from trading_bot.backtester import Backtester
from trading_bot.config import load_config
from trading_bot.data import load_csv, load_yfinance
from trading_bot.data.market_data import build_market_data_provider
from trading_bot.data.universe import load_universe, load_universe_metadata, load_universe_tags
from trading_bot.logging_config import configure_logging
from trading_bot.risk import RiskManager
from trading_bot.scoring import ScoreEngine, load_scoring_config
from trading_bot.snapshots import calculate_snapshot_followup
from trading_bot.snapshots.seeding import build_demo_seed_snapshots
from trading_bot.strategies import MovingAverageCrossoverStrategy
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.settings import load_scanner_settings
from trading_bot.tony import TonyStocksService


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trading bot research CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest", help="Run a sample backtest.")
    source = backtest.add_mutually_exclusive_group(required=False)
    source.add_argument("--ticker", default=None, help="Ticker to download with yfinance, such as SPY.")
    source.add_argument("--csv", default=None, help="Path to local OHLCV CSV file.")
    backtest.add_argument("--period", default="1y", help="Download period for yfinance, such as 6mo, 1y, 5y.")
    backtest.add_argument("--config", default="configs/default_config.yaml", help="Path to YAML config file.")

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
    return parser


def run_backtest(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    ticker = args.ticker or "SPY"

    if args.csv:
        data = load_csv(args.csv)
    else:
        data = load_yfinance(ticker=ticker, period=args.period)

    strategy = MovingAverageCrossoverStrategy(
        fast_window=config.strategy.fast_window,
        slow_window=config.strategy.slow_window,
    )
    risk_manager = RiskManager(
        starting_cash=config.risk.starting_cash,
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
        starting_cash=config.backtest.starting_cash,
        fee_per_trade=config.backtest.fee_per_trade,
        slippage_fraction=config.backtest.slippage_fraction,
    )
    result = backtester.run(data)
    print(f"Data rows: {len(data)}")
    result.print_summary()


def run_scan(args: argparse.Namespace) -> dict[str, Any]:
    settings = load_scanner_settings(args.config)
    configure_logging(settings.log_dir)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)

    manual_symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
    symbols = load_universe(settings.universe_config_path, manual_symbols=manual_symbols)
    tags_by_symbol = load_universe_tags(settings.universe_config_path)
    metadata_by_symbol = load_universe_metadata(settings.universe_config_path)
    symbols = symbols[: settings.max_symbols]
    profiles_by_symbol = {
        symbol: metadata.demo_profile
        for symbol, metadata in metadata_by_symbol.items()
        if metadata.demo_profile
    }
    provider = build_market_data_provider(settings.provider, settings.cache_dir, profiles_by_symbol=profiles_by_symbol)
    scoring_config = load_scoring_config(settings.scoring_config_path)
    engine = ScoreEngine(scoring_config)
    repo = ScannerRepository(settings.database_path)
    tony = TonyStocksService(repo, settings.tony_stocks)
    tony.start_cycle()
    tony.record_scan_started(symbols_loaded=len(symbols), provider=provider.name)

    market_data: dict[str, object] = {}
    spy_data = None
    results = []

    for symbol in symbols:
        try:
            data = provider.fetch_ohlcv(symbol, settings.lookback_days, settings.timeframe)
            if data.empty or len(data) < 60:
                LOGGER.warning("Skipping %s: not enough data", symbol)
                continue
            latest_close = float(data["close"].iloc[-1])
            avg_volume_20 = float(data["volume"].tail(20).mean())
            dollar_volume_20 = float((data["close"].tail(20) * data["volume"].tail(20)).mean())
            if not (settings.min_price <= latest_close <= settings.max_price):
                LOGGER.info("Skipping %s: latest close outside configured price bounds", symbol)
                continue
            if avg_volume_20 < settings.min_avg_volume or dollar_volume_20 < settings.min_dollar_volume:
                LOGGER.info("Skipping %s: liquidity below configured minimums", symbol)
                continue
            market_data[symbol] = data
            if symbol == "SPY":
                spy_data = data
        except Exception as exc:
            LOGGER.warning("Skipping %s: %s", symbol, exc)

    if spy_data is None and "SPY" not in market_data:
        try:
            spy_data = provider.fetch_ohlcv("SPY", settings.lookback_days, settings.timeframe)
        except Exception:
            spy_data = None

    for symbol, data in market_data.items():
        try:
            results.append(
                engine.score(
                    symbol,
                    data,
                    spy_data=spy_data,
                    tags=tags_by_symbol.get(symbol, ()),
                    metadata=metadata_by_symbol.get(symbol),
                )
            )
        except Exception as exc:
            LOGGER.warning("Could not score %s: %s", symbol, exc)

    results.sort(key=lambda item: item.final_score, reverse=True)
    scan_run_id = repo.create_scan_run(
        universe_count=len(symbols),
        provider=provider.name,
        config_snapshot=asdict(settings),
    )
    repo.save_scan_results(scan_run_id, results)
    snapshot_ids = []
    if getattr(args, "save_snapshots", False):
        snapshot_ids = repo.create_candidate_snapshots(
            scan_run_id=scan_run_id,
            results=results,
            snapshot_config=settings.candidate_snapshots or {},
        )

    export_rows = [result.to_dict() for result in results]
    output_path = Path(settings.outputs_dir) / "latest_scan_results.csv"
    if export_rows:
        import pandas as pd

        pd.DataFrame(export_rows).to_csv(output_path, index=False)
    else:
        output_path.write_text("", encoding="utf-8")

    print(f"Scan run id: {scan_run_id}")
    print(f"Provider: {provider.name}")
    print(f"Symbols loaded: {len(symbols)}")
    print(f"Symbols scored: {len(results)}")
    print(f"CSV export: {output_path}")
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
    summary = {
        "scan_run_id": scan_run_id,
        "provider": provider.name,
        "symbols_loaded": len(symbols),
        "symbols_scored": len(results),
        "csv_path": str(output_path),
        "snapshots_created": len(snapshot_ids),
        "warnings_count": sum(len(result.warnings) for result in results),
    }
    tony.record_scan_completed(summary, results=results, snapshot_ids=snapshot_ids)
    return summary


def run_update_snapshots(args: argparse.Namespace) -> dict[str, Any]:
    """Update open candidate snapshots from configured OHLCV provider data."""
    settings = load_scanner_settings(args.config)
    configure_logging(settings.log_dir)
    metadata_by_symbol = load_universe_metadata(settings.universe_config_path)
    profiles_by_symbol = {
        symbol: metadata.demo_profile
        for symbol, metadata in metadata_by_symbol.items()
        if metadata.demo_profile
    }
    provider = build_market_data_provider(settings.provider, settings.cache_dir, profiles_by_symbol=profiles_by_symbol)
    repo = ScannerRepository(settings.database_path)
    tony = TonyStocksService(repo, settings.tony_stocks)
    tony.start_cycle()
    snapshots = repo.list_open_candidate_snapshots(limit=args.limit)
    followup_config = settings.snapshot_followup or {}
    same_bar_policy = str(followup_config.get("same_bar_target_stop_policy", "conservative_stop_first"))
    expire_after = int(followup_config.get("expire_after_trading_days", 20))

    checked = 0
    updated = 0
    outcomes: dict[str, int] = {}
    triggered_count = 0
    target_count = 0
    stop_count = 0
    insufficient_count = 0
    still_open_count = 0

    for snapshot in snapshots.to_dict("records"):
        checked += 1
        try:
            data = provider.fetch_ohlcv(str(snapshot["symbol"]), max(settings.lookback_days, 140, expire_after + 40), settings.timeframe)
            result = calculate_snapshot_followup(
                snapshot=snapshot,
                ohlcv=data,
                same_bar_target_stop_policy=same_bar_policy,
                expire_after_trading_days=expire_after,
            )
            repo.update_candidate_snapshot_followup(int(snapshot["id"]), **result.to_update_fields())
            updated += 1
            outcomes[result.outcome_label] = outcomes.get(result.outcome_label, 0) + 1
            if result.entry_triggered:
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
    print(f"Entry triggered: {triggered_count}")
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
        "target_hit": target_count,
        "stop_hit": stop_count,
        "insufficient_future_data": insufficient_count,
        "still_open": still_open_count,
        "outcomes": outcomes,
    }
    tony.record_snapshot_update(summary)
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
    provider = build_market_data_provider(settings.provider, settings.cache_dir, profiles_by_symbol=profiles_by_symbol)
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
    timezone_name = str(watch_config.get("timezone", "America/New_York"))
    stop_file = Path(str(watch_config.get("stop_file", "data/STOP_WATCH_MODE")))
    if not stop_file.is_absolute():
        stop_file = Path.cwd() / stop_file

    print("Scheduled Watch Mode")
    print("Research mode only: no paper trades, broker execution, or live trading.")
    print(f"Config: {args.config}")
    print(f"Interval minutes: {interval_minutes:g}")
    print(f"Snapshot update after scan: {run_updates}")
    print(f"Max cycles: {max_cycles if max_cycles is not None else 'unlimited'}")
    print(f"Market hours only: {market_hours_only}")
    print(f"Stop file: {stop_file}")
    LOGGER.info("Scheduled Watch Mode started. interval_minutes=%s max_cycles=%s", interval_minutes, max_cycles)

    cycles_completed = 0
    stopped_by = "max_cycles" if max_cycles == 0 else ""
    summaries: list[dict[str, Any]] = []
    try:
        while max_cycles is None or cycles_completed < max_cycles:
            if stop_file.exists():
                stopped_by = "stop_file"
                print(f"Stop file found. Exiting cleanly: {stop_file}")
                break

            if market_hours_only and not _within_watch_window(watch_config, timezone_name):
                now = datetime.now(ZoneInfo(timezone_name))
                print(f"Outside configured watch window at {now.isoformat()}; skipping cycle.")
                LOGGER.info("Watch cycle skipped outside configured market window.")
                if max_cycles is not None:
                    cycles_completed += 1
                if not _sleep_until_next_cycle(interval_seconds, stop_file):
                    stopped_by = "stop_file"
                    break
                continue

            cycle_number = cycles_completed + 1
            tony.start_cycle()
            cycle_started = datetime.now(ZoneInfo(timezone_name))
            print(f"\nWatch cycle {cycle_number} started at {cycle_started.isoformat()}")
            scan_summary = run_scan(SimpleNamespace(config=args.config, symbols="", save_snapshots=True))
            update_summary: dict[str, Any] | None = None
            if run_updates:
                update_summary = run_update_snapshots(SimpleNamespace(config=args.config, limit=500))
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
            if cycle_summary["next_run_time"]:
                print(f"Next run: {cycle_summary['next_run_time']}")
            tony.record_watch_cycle_completed(cycle_summary)

            if max_cycles is not None and cycles_completed >= max_cycles:
                stopped_by = "max_cycles"
                break
            if not _sleep_until_next_cycle(interval_seconds, stop_file):
                stopped_by = "stop_file"
                break
    except KeyboardInterrupt:
        stopped_by = "keyboard_interrupt"
        print("\nCtrl+C received. Scheduled Watch Mode stopped cleanly.")

    stopped_by = stopped_by or "completed"
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
    else:
        parser.error(f"Unknown command: {args.command}")


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


if __name__ == "__main__":
    main()
