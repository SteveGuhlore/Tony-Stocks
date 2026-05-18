from __future__ import annotations

import argparse
import json
import logging
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from trading_bot.analytics import OutcomeAnalytics
from trading_bot.backtester import Backtester
from trading_bot.config import load_config
from trading_bot.data import load_csv, load_yfinance
from trading_bot.dashboard.helpers import is_heartbeat_stale
from trading_bot.data.market_data import (
    AlpacaIEXProvider,
    ProviderHealth,
    build_market_data_provider,
    check_provider_health,
)
from trading_bot.data.universe_rotation import RotationResult, WatchUniverseRotator
from trading_bot.data.universe import load_universe, load_universe_metadata, load_universe_tags
from trading_bot.intraday import IntradayFeatures, calculate_intraday_features
from trading_bot.logging_config import configure_logging
from trading_bot.risk import RiskManager
from trading_bot.scoring import ScoreEngine, load_scoring_config
from trading_bot.snapshots import (
    ENTRY_STATUS_MISSING_REAL_DATA,
    EntryTriggerSimulationResult,
    calculate_snapshot_followup,
    compute_planned_entry_at_snapshot,
    simulate_entry_trigger,
)
from trading_bot.snapshots.seeding import build_demo_seed_snapshots
from trading_bot.strategies import MovingAverageCrossoverStrategy
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.settings import load_scanner_settings, real_data_only_enabled, resolve_effective_provider
from trading_bot.tony import TonyStocksService
from trading_bot.tony.analysis import TONY_ANALYSIS_VERSION, MarketContext, analyze_candidates
from trading_bot.utils.time_utils import utc_now_iso


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

    outcome_analytics = subparsers.add_parser("outcome-analytics", help="Print candidate snapshot outcome analytics.")
    outcome_analytics.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config file.")
    outcome_analytics.add_argument("--include-seeded", action="store_true", help="Include demo seeded fixture rows.")
    outcome_analytics.add_argument("--days", type=int, default=None, help="Only include snapshots from the last N days.")
    outcome_analytics.add_argument("--real-only", action="store_true", help="Only include snapshots classified as real rows.")
    outcome_analytics.add_argument("--include-demo", action="store_true", help="Explicitly include old demo-generated rows.")
    outcome_analytics.add_argument("--include-legacy", action="store_true", help="Explicitly include legacy rows with unknown data source.")
    outcome_analytics.add_argument("--exclude-demo", action="store_true", help="Exclude snapshots classified as demo generated rows.")
    outcome_analytics.add_argument("--today", action="store_true", help="Only include snapshots created today in UTC.")
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
    eod_report.add_argument("--date", default=None, help="UTC date to review as YYYY-MM-DD. Defaults to today.")

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

    for symbol in symbols:
        data = ohlcv_by_symbol.get(symbol)
        if data is None or data.empty or len(data) < 60:
            LOGGER.warning("Skipping %s: not enough data", symbol)
            skipped_count += 1
            if real_only and "alpaca_iex" in provider.name:
                missing_real_data_symbols.add(symbol.upper())
            continue
        latest_close = float(data["close"].iloc[-1])
        avg_volume_20 = float(data["volume"].tail(20).mean())
        dollar_volume_20 = float((data["close"].tail(20) * data["volume"].tail(20)).mean())
        if not (settings.min_price <= latest_close <= settings.max_price):
            LOGGER.info("Skipping %s: latest close outside configured price bounds", symbol)
            skipped_count += 1
            continue
        if avg_volume_20 < settings.min_avg_volume or dollar_volume_20 < settings.min_dollar_volume:
            LOGGER.info("Skipping %s: liquidity below configured minimums", symbol)
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

    results.sort(key=lambda item: item.final_score, reverse=True)
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
    }
    if isinstance(provider, AlpacaIEXProvider):
        alpaca_cfg = (settings.market_data or {}).get("alpaca") or {}
        stale_minutes = int(alpaca_cfg.get("stale_data_minutes", 20))
        cycle_stats = provider.get_cycle_stats()
        scanned_count = len(symbols)
        missing_real_data_symbols.update(s.upper() for s in provider.missing_symbols)
        fallback_count = len(provider.fallback_symbols)
        missing_count = len(missing_real_data_symbols)
        real_data_count = max(0, len(market_data) - fallback_count)
        summary.update({
            "api_requests_used": cycle_stats.get("api_requests_used", 0),
            "batch_requests_used": cycle_stats.get("batch_requests_used", 0),
            "rate_limit_warnings": cycle_stats.get("rate_limit_warnings", 0),
            "batch_mode": cycle_stats.get("batch_mode", False),
            "fallback_count": fallback_count,
            "missing_real_data_count": missing_count,
            "missing_real_data_symbols": sorted(missing_real_data_symbols),
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
        from collections import Counter
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

    for snapshot in snapshots.to_dict("records"):
        checked += 1
        try:
            working = dict(snapshot)
            if entry_trigger_cfg.get("enabled", True):
                intraday_bars = None
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

            data = provider.fetch_ohlcv(str(snapshot["symbol"]), max(settings.lookback_days, 140, expire_after + 40), settings.timeframe)
            result = calculate_snapshot_followup(
                snapshot=working,
                ohlcv=data,
                same_bar_target_stop_policy=same_bar_policy,
                expire_after_trading_days=expire_after,
            )
            repo.update_candidate_snapshot_followup(int(snapshot["id"]), **result.to_update_fields())
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
    if rotation_cfg.get("enabled", False):
        universe_symbols = load_universe(settings.universe_config_path)
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
            if is_heartbeat_stale(prev_hb, stale_heartbeat_minutes):
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
    try:
        while max_cycles is None or cycles_completed < max_cycles:
            if stop_file.exists():
                stopped_by = "stop_file"
                print(f"Stop file found. Exiting cleanly: {stop_file}")
                LOGGER.info("Stop file detected: %s", stop_file)
                break

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
    analytics = OutcomeAnalytics(
        snapshots,
        include_seeded_demo=args.include_seeded,
        real_only=True if getattr(args, "real_only", False) else not (getattr(args, "include_demo", False) or getattr(args, "include_legacy", False)),
        include_demo=bool(getattr(args, "include_demo", False)),
        include_legacy=bool(getattr(args, "include_legacy", False)),
        exclude_demo=bool(getattr(args, "exclude_demo", False)),
        today=bool(getattr(args, "today", False)),
        provider=getattr(args, "provider", None),
    )
    prepared = analytics.prepared()
    exclusions = analytics.exclusion_counts()
    groups = args.group_by or ["setup_category", "score_bucket", "universe_role", "outcome_label", "warning_type"]

    print("Outcome analytics")
    print("Research only: analytics evaluate scanner output; they do not create trades or prove an edge.")
    if not getattr(args, "include_demo", False) and not getattr(args, "include_legacy", False):
        print("Real-data rows only. Demo and legacy rows excluded.")
    print(f"Seeded demo rows included: {bool(args.include_seeded)}")
    print(f"Real-only filter: {analytics.real_only}")
    print(f"Include demo rows: {bool(getattr(args, 'include_demo', False))}")
    print(f"Include legacy rows: {bool(getattr(args, 'include_legacy', False))}")
    print(f"Exclude demo filter: {bool(getattr(args, 'exclude_demo', False))}")
    print(f"Today filter: {bool(getattr(args, 'today', False))}")
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
    print("\nOutcome counts:")
    _print_dataframe(outcome_counts)

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
        )


def run_eod_report(args: argparse.Namespace) -> dict[str, Any]:
    """Print a research-only end-of-day data quality report."""
    settings = load_scanner_settings(args.config)
    repo = ScannerRepository(settings.database_path)
    report_date = getattr(args, "date", None) or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    events = repo.list_tony_events(limit=1000)
    today_events = _events_on_date(events, report_date)
    watch_run = repo.latest_watch_run()
    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True, limit=10000)
    analytics = OutcomeAnalytics(snapshots, include_seeded_demo=True, real_only=True)
    prepared = analytics.prepared()
    exclusions = analytics.exclusion_counts()
    if not prepared.empty:
        prepared = prepared[prepared["snapshot_time"].astype(str).str.slice(0, 10).eq(report_date)].copy()
    outcome_counts = _outcome_counts(prepared)
    warning_counts = _warning_counts(prepared)

    latest_watch_status = str(watch_run.get("status", "none")) if watch_run else "none"
    cycles_completed = int(watch_run.get("cycles_completed", 0) or 0) if watch_run else 0
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
    real_symbols_scanned = symbols_scanned
    if isinstance(symbols_scanned, int):
        real_symbols_scanned = max(0, symbols_scanned - len(fallback_symbols))
    top_symbols = _top_event_symbols(today_events)
    top_hypotheses = _top_hypotheses(today_events)

    created_today = len(prepared)
    updated_today = int(prepared["last_checked_at"].fillna("").astype(str).str.slice(0, 10).eq(report_date).sum()) if not prepared.empty and "last_checked_at" in prepared else 0

    print("End-of-day market data review")
    print("Research only: no trade recommendations, no broker execution, no paper trades, no live trades.")
    print("Tony has no proven edge from this report; it is data-quality review only.")
    print(f"Date reviewed: {report_date}")
    print(f"Watch cycles completed today: {cycles_completed}")
    print(f"Latest watch status: {latest_watch_status}")
    print(f"Provider used: {provider_used}")
    print(f"Symbols scanned: {symbols_scanned if symbols_scanned is not None else 'unknown'}")
    print(f"API requests: {api_requests if api_requests is not None else 'unknown'}")
    print(f"Real symbols scanned: {real_symbols_scanned if real_symbols_scanned is not None else 'unknown'}")
    print(f"Missing real-data symbols: {', '.join(fallback_symbols) if fallback_symbols else 'none'}")
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
    print(f"Top repeated high-priority symbols: {_format_counter(top_symbols)}")
    print(f"Top Tony hypotheses: {_format_counter(top_hypotheses)}")
    print("\nOutcome counts:")
    _print_dataframe(outcome_counts)
    print("\nWarning counts:")
    _print_dataframe(warning_counts)
    print("\nRepeated missing real-data symbols:")
    if fallback_symbols:
        for symbol in fallback_symbols:
            print(f"  {symbol}: missing real-data candidate. Quarantine or replace these symbols.")
    else:
        print("  none")
    print("\nData-quality notes:")
    print("  Active analytics review real-data rows only; demo, missing, and legacy rows are excluded by default.")
    print("  Alpaca IEX is a single-exchange feed and may differ from consolidated SIP data.")

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
        "real_intraday_count": int(intraday_payload.get("real_intraday_count", 0) or 0),
        "stale_intraday_count": int(intraday_payload.get("intraday_stale_count", 0) or 0),
        "snapshots_created_today": created_today,
        "snapshots_updated_today": updated_today,
        "real_only_snapshots_reviewed": len(prepared),
        "demo_rows_excluded": exclusions["demo_rows_excluded"],
        "legacy_unknown_rows_excluded": exclusions["legacy_unknown_rows_excluded"],
        "missing_real_data_rows_excluded": exclusions["missing_real_data_rows_excluded"],
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
    elif args.command == "eod-report":
        run_eod_report(args)
    elif args.command == "data-check":
        run_data_check(args)
    elif args.command == "provider-health":
        run_provider_health(args)
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
    print(data.to_string(index=False))


def _events_on_date(events: pd.DataFrame, date_value: str) -> list[dict[str, Any]]:
    if events.empty or "created_at" not in events.columns:
        return []
    rows = []
    for row in events.to_dict("records"):
        if str(row.get("created_at", "")).startswith(date_value):
            rows.append(row)
    return rows


def latest_event_of_type_records(events: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    for row in events:
        if row.get("event_type") == event_type:
            return row
    return None


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


if __name__ == "__main__":
    main()
