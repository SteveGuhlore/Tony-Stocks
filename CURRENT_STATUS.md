# Trading Bot Project - Current Status

_Last updated: 2026-05-17_

## Overall status

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
- Watch mode supports configurable intervals, max cycles, simple market-hours window checks, Ctrl+C shutdown, and a stop file at `data/STOP_WATCH_MODE`.
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

1. Add Alpaca API keys to `.env` and set `real_provider_enabled: true` + `provider: alpaca_iex` under `market_data:` in `config/universe_swing_research_config.yaml`.
2. Run `python -m trading_bot.cli data-check --config config/universe_swing_research_config.yaml --symbol PLTR` with real keys.
3. Run `python -m trading_bot.cli watch --config config/universe_swing_research_config.yaml --max-cycles 1` to validate batch fetch at 171-symbol scale.
4. Run `python -m trading_bot.cli tony-events --limit 30` — look for `batch_fetch_summary`, `real_data_scan_scaled`, `universe_rotation_summary`.
5. If rate-limit warnings appear, reduce `max_symbols_per_cycle` or increase `request_sleep_seconds`.
6. Monitor rotation `bucket_id` across cycles to verify round-robin advances.
7. Initialize git and commit a known-good baseline.

**Universe symbols are curated for research/scanning and are not recommendations to buy or trade any security.**
