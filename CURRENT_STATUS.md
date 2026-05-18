# Trading Bot Project - Current Status

_Last updated: 2026-05-18_

## Overall status

**V13** — Tony Hypothesis-to-Outcome Tracking. Tony analyst reads (priority label, recommended action, setup/risk/volume/market-context/data-quality reads, hypothesis, reasons, concerns) stored with candidate snapshots at creation time. Outcome analytics groups by any Tony field. Dashboard Tony Learning panel (early tracking language, no profitability claims). `TONY_ANALYSIS_VERSION = "v1"` on every attached read. 321 tests pass, 0 errors.

**V12** — Workday Watch Mode + Run Controls. Watch run lifecycle tracked in SQLite (`watch_runs` table). Heartbeat updates every cycle; dashboard detects and displays stale/running/stopped/error states. Market-hours guard (9:30–16:00 ET) with spam-prevention flag. Tony events for all watch lifecycle transitions. 282 tests pass, 0 errors.

**V11** — Dashboard Command Center UX. "Command Center" tab is the first/default tab showing Tony status, provider, scan age, symbols, API requests, fallback, snapshots today, analyst hypotheses, warnings, market context, Watch Health panel, Data Quality panel, Outcome Snapshot panel. 230 tests pass, 0 errors.

**V10** — Tony Stocks Analyst Engine. Deterministic analyst reads (setup, volume, risk, data quality, outcome context, priority) for every scan cycle. Five priority labels, five allowed recommended actions (no buy/sell). Dashboard Analyst Reads expander. 180 tests pass, 0 errors.

**V9.5** — Universe expanded to 171 symbols across 14 sectors/themes. Batch fetching (multi-symbol Alpaca endpoint) retrieves all symbols in 1–2 HTTP requests. Universe rotation selects core benchmarks + open snapshots + previous high-priority candidates + rotating discovery pool (round-robin) up to 175 symbols per 5-minute watch cycle. 121 tests pass, 0 errors.

V8 Alpaca IEX Market Data Provider Foundation: real-market-data adapter for Alpaca IEX historical bars. Provider disabled by default (demo_generated is still active). When enabled, reads US equity bars and falls back to demo data if Alpaca is unreachable. Tony Stocks creates internal events for fallback and stale-data conditions. No broker execution, no trading, no order placement.

V7 Outcome Analytics has been added on top of the swing/day-trade scanner. The project can now summarize candidate snapshot outcomes by setup category, universe role, score bucket, warning type, tags, and seeded-demo status. Tony Stocks remains a watcher/analyst event layer only; it does not paper trade, execute broker orders, or place live trades.

## Implemented

- Config-driven scanner setup in `config/default_config.yaml`.
- Starter stock universe with tags in `config/universe_config.yaml`.
- Mid/small-cap focused swing research universe in `config/universe_swing_research_config.yaml`.
- Swing scoring mode, weights, thresholds, and ETF/mega-cap penalties in `config/scoring_config.yaml`.
- Provider-adapter market data layer with deterministic `demo_generated` provider and HTTP provider placeholder.
- Technical indicator package for SMA, EMA, RSI, ATR, rolling volatility, returns, relative volume, dollar volume, and rolling highs/lows.
- 0-100 scoring engine with trend, momentum, volume/liquidity, risk, and setup-quality scores.
- Swing setup categories: Breakout Watch, Pullback Watch, Momentum Continuation, Overextended / Wait, Weak / Avoid, and ETF / Benchmark Reference.
- Clear reasons and warnings, including ETF/reference, mega-cap, overextended, low-liquidity, wide-ATR, flat-action, and demo-data warnings.
- SQLite tables for `scan_runs`, `scan_results`, `manual_picks`, and `paper_trades`, with additive fields for `setup_category` and `tags_json`.
- Additive scan result fields for universe role, symbol metadata, relative volume, ATR percent, 10-day return, demo profile, notes, and candidate summary.
- CLI scanner command: `python -m trading_bot.cli scan --config config/default_config.yaml`.
- CSV export to `outputs/latest_scan_results.csv`.
- Streamlit dashboard with overview metrics, swing filters, ranked table, stock detail, manual picks, paper journal, performance sections, and basic charts.
- Dashboard sections for Primary Swing Candidates, Benchmarks / Market Context, Mega-Cap References, Avoid / Weak / Overextended, and Speculative Watchlist.
- Candidate snapshot configuration in `config/default_config.yaml`.
- SQLite `candidate_snapshots` table for saving scan-time signal snapshots without creating trades.
- Repository methods for creating, listing, filtering, updating, and counting candidate snapshots.
- CLI snapshot command: `python -m trading_bot.cli snapshot --config config/default_config.yaml`.
- Optional scanner flag: `python -m trading_bot.cli scan --config config/default_config.yaml --save-snapshots`.
- Dashboard Candidate Snapshots section with summary metrics, category/role charts, filters, top candidate table, and selected snapshot detail.
- Central long trade-plan validation for entry, stop, target, and risk/reward.
- Additive `trade_plan_valid` and `trade_plan_status` fields in scan results and candidate snapshots.
- Candidate snapshots exclude invalid trade plans by default.
- Snapshot follow-up calculation for highest/lowest price seen, return windows, entry trigger state, and outcome labels.
- CLI command: `python -m trading_bot.cli update-snapshots --config config/default_config.yaml`.
- PowerShell helper: `scripts/run_snapshot_update.ps1`.
- Demo-only historical snapshot seed command: `python -m trading_bot.cli seed-demo-snapshots --config config/default_config.yaml`.
- PowerShell helper: `scripts/run_seed_demo_snapshots.ps1`.
- Seeded demo snapshots are labeled in notes and use the normal follow-up calculator for outcomes.
- Scheduled Watch Mode command: `python -m trading_bot.cli watch --config config/default_config.yaml`.
- One-cycle watch test mode: `python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1`.
- PowerShell helper: `scripts/run_watch_mode.ps1`.
- Watch mode supports configurable intervals, max cycles, market-hours guard (9:30–16:00 ET, no holiday calendar), Ctrl+C shutdown, and a stop file at `data/STOP_WATCH_MODE`.
- Watch run lifecycle tracked in `watch_runs` SQLite table: `create_watch_run()`, `update_watch_run_heartbeat()`, `update_watch_run_stopped()`, `update_watch_run_error()`, `latest_watch_run()`.
- Heartbeat staleness detection: `is_heartbeat_stale()` helper used by both CLI (startup stale detection) and dashboard.
- Dashboard Command Center shows live watch status: running/stale/stopped/error, heartbeat age, cycles completed, latest scan run ID, symbols scored, API requests used.
- Stop file path printed at watch startup; Tony lifecycle events for `watch_run_started`, `watch_run_stopped`, `watch_run_error`, `watch_heartbeat_stale`, `watch_waiting_for_market_open`.
- Dashboard overview includes a compact watch-status readout based on latest scan and candidate snapshot data.
- Tony Stocks configuration in `config/default_config.yaml`.
- SQLite `tony_events` table for internal watcher/analyst events.
- Deterministic Tony event service in `src/trading_bot/tony/events.py`; no LLM calls or external notifications.
- CLI command: `python -m trading_bot.cli tony-events --config config/default_config.yaml --limit 20`.
- Tony events are created for scan start/completion, snapshots created/updated, high-score candidates, warning summaries, outcome updates, and watch-cycle completion.
- Dashboard Tony Stocks tab with filters, status cards, event table, and payload detail.
- Outcome analytics service in `src/trading_bot/analytics/outcomes.py`.
- CLI command: `python -m trading_bot.cli outcome-analytics --config config/default_config.yaml`.
- Outcome analytics exclude seeded demo fixture rows by default and can include them with `--include-seeded`.
- Dashboard Outcome Analytics tab with setup-category, score-bucket, universe-role, outcome-label, and warning-type summaries.
- Tony event integration for outcome analytics runs.
- PowerShell helper scripts for tests, scanner, and dashboard.
- Alpaca IEX market data provider adapter in `src/trading_bot/data/market_data.py` (disabled by default).
- `market_data:` config block in `config/default_config.yaml` with Alpaca settings (feed, timeframe, max_symbols_per_scan, fail_safe_to_demo, stale_data_minutes).
- CLI command: `python -m trading_bot.cli data-check --config config/default_config.yaml --symbol PLTR`.
- Data-check prints active provider, feed, timeframe, latest bar timestamp, close, and volume. Works in demo mode without keys.
- Alpaca per-scan symbol cap applied automatically from `market_data.alpaca.max_symbols_per_scan` (default: 30).
- Tony events for `data_provider_fallback` and `stale_data_warning` when using Alpaca IEX.
- Dashboard Data Provider Status section in Overview tab showing active provider, feed, timeframe, and Alpaca IEX disclaimer.
- `ALPACA_DATA_FEED=iex` added to `.env.example`.
- 16 new Alpaca provider tests in `tests/test_alpaca_provider.py`; all mocked, no real API calls.

**Alpaca IEX notice (in all relevant docs):** Alpaca IEX is a single-exchange feed and may differ from consolidated SIP market tape. It is for testing the real-data pipeline only. Do not use as sole basis for execution decisions. No orders are placed.

## Confirmed in this environment

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` passed.
- `python -m compileall src` passed through the test script.
- `pytest` passed with 51 tests.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1` ran successfully and wrote `data/trading_bot.db`, `outputs/latest_scan_results.csv`, and `logs/trading_bot.log`.
- `python -m trading_bot.cli snapshot --config config/default_config.yaml` ran successfully. The latest run created 0 new snapshots because the configured dedupe window suppressed same-hour duplicates.
- `python -m trading_bot.cli update-snapshots --config config/default_config.yaml` ran successfully and updated 17 open/watch snapshots.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_snapshot_update.ps1` ran successfully.
- `python -m trading_bot.cli seed-demo-snapshots --config config/default_config.yaml` ran successfully and deduped existing demo rows by default.
- `python -m trading_bot.cli seed-demo-snapshots --config config/default_config.yaml --force` was used once locally to refresh demo fixture rows after the lookback alignment fix.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_seed_demo_snapshots.ps1` ran successfully and skipped duplicate demo rows by default.
- `python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1` ran successfully.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_watch_mode.ps1 -MaxCycles 1` ran successfully.
- `python -m trading_bot.cli tony-events --config config/default_config.yaml --limit 20` ran successfully.
- `python -m trading_bot.cli outcome-analytics --config config/default_config.yaml` ran successfully with seeded demo rows excluded by default.
- `python -m trading_bot.cli outcome-analytics --config config/default_config.yaml --include-seeded` ran successfully and clearly labeled seeded demo fixtures as not evidence of real market edge.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1` started Streamlit and reported `http://localhost:8501`.
- Demo snapshot outcomes now include `target_hit`, `stop_hit`, `partial_move`, `failed_setup`, `entry_not_triggered`, `expired_no_trigger`, and `insufficient_future_data` examples.
- Programmatic CSV validation confirmed eligible non-reference/non-avoid rows have `stop < entry`, `target > entry`, positive risk/reward, and valid trade-plan flags.

## Confirmed in V13

- `pytest tests/test_v13_tony_learning.py -v` passed: **39 tests, 0 failures**.
- `pytest --tb=short -q` passed: **321 tests, 0 failures, 0 errors** (up from 282).
- `provider-health` PASSED.
- `watch --max-cycles 1` ran; Tony analyst events and `tony_learning_updated` confirmed in `tony-events`.
- `outcome-analytics` ran cleanly; `tony_learning_updated` event at top of tony-events log.

## Confirmed in V12

- `pytest --tb=short -q` passed: **282 tests, 0 failures, 0 errors** (up from 230).
- `pytest tests/test_watch_run.py -v` passed: **52 tests, 0 failures**.
- `run_scanner.ps1` ran: 52 symbols scored, DVN top at 96.88, scan run ID recorded.
- `watch --max-cycles 1` ran: `watch_run_stopped` event confirmed in `tony-events`.
- `provider-health` PASSED.

## Confirmed in V11

- `pytest --tb=short -q` passed: **230 tests, 0 failures, 0 errors** (up from 180).
- `pytest tests/test_dashboard_helpers.py -v` passed: **50 tests, 0 failures**.
- Command Center tab renders as first/default tab in dashboard.
- Analyst hypothesis cards render with priority icons and no buy/sell wording.

## Confirmed in V9.5

- `pytest` passed with 121 tests, 0 errors (15 new universe tests + 31 V9 scaling/batch tests + 75 prior).
- Universe config loads 171 symbols; duplicates removed; roles validated; benchmarks present.
- Batch limit fix: `_fetch_bars_batch` uses `limit=10000` — 39 symbols now fetch in 2 requests (vs 23 before).
- Windows pytest temp fix: `$env:LOCALAPPDATA\TradingBotTests\<session_id>` per-session dir, no project-dir file locks.
- `python -m compileall src` passed.
- No Alpaca API keys are required for any test or demo scan.

## Confirmed in V8

- `pytest` passed with 67 tests (16 new Alpaca provider tests + 51 existing).
- `python -m compileall src` passed.
- Scanner still runs correctly with demo_generated provider.
- `python -m trading_bot.cli data-check --config config/default_config.yaml --symbol PLTR` ran in demo mode and printed bar data.
- Dashboard syntax verified clean.
- No Alpaca API keys are required for any existing test or demo scan.

## Git notes

- `git status --short` and `git diff --check` run in this shell, but Git prints a permission warning for `C:\Users\alexa/.config/git/ignore`.
- Git also reports CRLF normalization warnings for edited files.

## Not implemented

- Live trading.
- Broker execution.
- Alpaca broker/trading endpoints (only data API is wired).
- External Tony notifications such as email, SMS, Discord, or Telegram.
- Margin, leverage, short selling, or options logic.
- Advanced backtesting and automatic paper-trade creation.
- Intraday (5Min/15Min) scanning logic (provider supports it; scanner still uses daily bars).

## Next recommended work

1. Run `run_dashboard.ps1` and verify the Tony Learning panel renders in the Command Center (expander at the bottom).
2. Run `watch --max-cycles 5` with real Alpaca keys so real-data snapshots accumulate Tony analysis; then run `outcome-analytics` and verify Tony groupings appear in the panel.
3. Consider V14: add `watch_run_id` FK to `candidate_snapshots` so each snapshot can be correlated to a watch session.
4. Consider V14: add `tony_analysis_version` grouping to the CLI `--group-by` outcome table output so Tony v1 vs future v2 reads can be compared directly.
5. Add a holiday calendar to `is_within_us_eastern_market_hours()` if market-hours-only mode needs holiday awareness.
6. Initialize git and commit a known-good baseline.

**Universe symbols are curated for research/scanning and are not recommendations to buy or trade any security.**
