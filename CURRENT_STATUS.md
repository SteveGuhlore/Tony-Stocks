# Trading Bot Project - Current Status

_Last updated: 2026-05-19_

## Overall status

**V16** - Tony memory engine foundation. `eod-report` now builds a daily Tony memory summary from real-only outcome rows and stores the same summary in the existing Tony learning event payload for later review. The memory summary includes setup counts, triggered counts, active/closed counts, target/stop/partial counts, reassessment-label counts, preliminary best/worst setup notes, and data-quality notes explaining exclusions and raw-history preservation. This is research-only reporting memory; it does not change scoring, trigger rules, fixed active entries, broker behavior, or stored raw history.

**V16A** - Market-date fix for reporting and daily analytics. `eod-report`, `outcome-analytics --today`, and the daily Tony memory summary now default to the America/New_York market date instead of the UTC calendar date. Explicit `--date YYYY-MM-DD` still overrides `eod-report`, and report output now prints `Report date: YYYY-MM-DD America/New_York`. Stored timestamps remain UTC; only daily filtering/report semantics changed.

**V15.9** - Tony reassessment labels for active tracked setups. Active tracked research positions now get a deterministic reassessment label derived from stored tracking data only: `still_valid`, `weakening`, `invalidated`, or `needs_review`. The refresh step stores `reassessment_label`, a plain-English `reassessment_note`, and `last_reassessed_at`, and Tony’s tracked-setup summary event now includes reassessment counts. This is research-only status labeling on existing active tracking fields; it does not change scoring, trigger rules, fixed active entry anchoring, broker behavior, or stored history.

**V15.8C** - EOD data reconciliation. `eod-report` now prints a raw-vs-product reconciliation section showing raw snapshot rows, raw triggered entry rows, deduped active positions, deduped waiting picks, closed/current product-result counts, incomplete rows hidden from product views, history rows hidden by dedupe/current-state rules, and excluded demo/legacy/missing-real-data rows. Settings / System Health also shows a compact reconciliation summary. This confirms that dashboard dedupe/hiding changes visibility only; raw candidate snapshot history remains in `data/trading_bot.db`. V15.8C is reporting/aggregation only; it does not change scoring, trigger rules, broker behavior, or stored snapshot history.

**V15.8B** - Product Dashboard Semantics: Entry Triggers, Current Positions, Closing Price, Results Rehaul. Main product views now use clean product wording and state models: Tony Picks show `Entry trigger`, trigger distance, trigger explanation, and `Active entry: N/A`; Active Tracking shows fixed `Tracked from` / active entry, dynamic `Current price` vs `Closing price`, research P/L, and risk/reward from the active entry; Results now uses the same deduped symbol-level product rows with filters and actual stock cards instead of raw-count-only semantics. Home preview copy is reduced to one complete sentence per card, and product cards avoid `NaN`, `$nan`, `+nan%`, `unknown`, and raw missing placeholders. V15.8B is dashboard aggregation/rendering only; it does not change scoring, trigger rules, paper/live behavior, broker execution, or snapshots.

**V15.8A** - One Active Position Per Symbol + Planned vs Active Entry Cleanup. Main product views now build symbol-level Tony Picks and Active Tracking cards from deduped snapshot rows. Tony Picks show one card per symbol and hide symbols already actively tracked. Active Tracking keeps the first valid triggered research entry fixed per symbol, then overlays latest `current_price` / `research_unrealized_pl_pct` / reassessment fields from later rows for that symbol. Incomplete/demo/legacy/missing-real-data rows are hidden from Home, Tony Picks, Active Tracking, and Results still-active counts. V15.8A is dashboard aggregation only; it does not change scoring, trigger rules, paper/live behavior, or broker execution.

**V15.8** - Freeze Original Plan + Active Tracking Fields. Nullable snapshot columns store frozen `original_*` plan at trigger, live `current_price` / `research_unrealized_pl_pct`, `tracking_status`, and `time_active_minutes` refreshed during `update-snapshots` from real Alpaca 5Min bars only. Tony `tracked_setup_updated` event summarizes refresh. V15.8 adds research-only active tracking fields. It does not create paper trades or broker orders.

**V15.7E** - Home briefing card enrichment. Home Top 3 pick/tracking preview cards show compact pills + key levels (entry/target/stop or tracked/current/target/stop + P/L). Home status uses calm “not currently scanning” / “waiting for next session” copy; true errors only when meaningful. Missing live data on Home is count-only (no symbol list). UI only — no scoring/trigger/DB changes.

**V15.7D** - Active Tracking render hotfix + Home clarity. Restored missing `render_tracking_position_card` import (Active Tracking crash). Home status only shows error when watch run has a meaningful `latest_error_message`; after-hours/stale states use calm market-closed copy. Home missing-data line is count-only or max 4 symbols + “See Settings”. UI only — no scoring/trigger/DB changes.

**V15.7C** - Dashboard render fix + Home/Tony Picks separation. Theme HTML renders via `render_html()` → `st.markdown(..., unsafe_allow_html=True)`; stat grids are single complete fragments (no raw `<div class="tony-stat-tile">` text). Home is a short executive briefing (hero, status, 6 summary tiles, market one-liner, top 3 pick/tracking previews, review list). Tony Picks is the full watchlist with filters, sorting, and full signal cards. After-hours Tony status uses plain-English waiting copy. UI only — no scoring/trigger/DB changes.

**V15.7B** - Tony Stocks visual product polish. Gradient page theme, hero landing, signal/position/performance cards via `dashboard/theme.py`. UI only — no backend logic changes.

**V15.7A** - Dashboard crash fix + card polish. Safe JSON/NaN parsing for Tony Picks cards; no `$nan` in UI; sleeker HTML card styling. Does not change trading/scoring behavior.

**V15.7** - Trading-App Dashboard Shell. Main nav is five tabs: Home, Tony Picks, Active Tracking, Results, Settings / System Health. Card-style picks and tracking; plain-English Results; legacy developer tables moved under Settings. Uses existing snapshot data only (no new DB columns). V15.7 does not change trading/scoring behavior.

**V15.5** - Dashboard UI/UX Simplification. Command Center is a beginner-friendly 30-second home screen with Tony status, data safety, market read, top watches, entry trigger tracker, and end-of-day snapshot sections. V15.5 simplifies the dashboard for non-technical review. It does not change trading/scoring behavior.

**V15.2** - Symbol Quarantine for Missing Real Data. Config-driven, non-destructive quarantine excludes repeated no-bar symbols (HCP, SAMSF, SMAR, SQ) from real-data-only scan/watch without removing them from universe YAML.

**V15** - Intraday Entry Trigger Simulation (research-only). Candidate snapshots store `snapshot_price`, planned intraday trigger levels, and simulated `actual_entry_*` fields from real Alpaca 5Min bars after snapshot time. V15 adds research-only intraday trigger simulation. It does not create paper trades or broker orders.

**V14.7** - Real-Data-Only Enforcement. First live market-hours Tony run completed successfully; next focus is real-data-only analytics hygiene before intraday scoring. Active Tony watch/learning runs are real-data-only. Demo provider data is never allowed in watch, snapshots, Tony learning, analytics, paper trading, or live trading. Tests may use mocks or recorded real fixtures, but not synthetic demo market series. Outcome analytics now defaults to real-data rows only and excludes demo, missing-real-data, and legacy rows unless explicitly included for review.

**V14.5** - Intraday Watch Activation + Snapshot Verification. Watch/scan cycles now print intraday configuration and per-cycle summary stats, create a concise `intraday_analysis_summary` Tony event, and verify intraday reads attach to Tony hypotheses and candidate snapshots when enabled. Intraday reads are attached to Tony research hypotheses and snapshots, but do not affect scoring yet.

**V14** - Real Intraday Data Mode Foundation. Intraday config, 5Min Alpaca/demo fetch support, deterministic intraday feature extraction, VWAP/opening-range reads, Tony intraday labels, nullable snapshot fields, data-check timeframe support, and dashboard intraday read displays have been added. Intraday reads are research-only and are not entry automation.

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
- Daily Tony memory summary helper in `src/trading_bot/analytics/outcomes.py` built from real-only outcome rows.
- Outcome analytics exclude seeded demo fixture rows by default and can include them with `--include-seeded`.
- Outcome analytics can derive snapshot data-source classes (`real_alpaca`, `missing_real_data`, `recorded_real_fixture`, `legacy_unknown`, and old `demo_generated`) from snapshot metadata and legacy provider/warning/tag/note/Tony fields.
- Outcome analytics defaults to real-data rows only; CLI filters include `--real-only`, `--include-demo`, `--include-legacy`, `--today`, and `--provider alpaca_iex`.
- CLI command: `python -m trading_bot.cli eod-report --config config/default_config.yaml` for research-only market-day data-quality review.
- `eod-report` prints a Tony memory summary section and stores the same research-only summary through the existing Tony learning event path.
- Dashboard Outcome Analytics tab with setup-category, score-bucket, universe-role, outcome-label, and warning-type summaries.
- Dashboard Command Center includes a compact Market Day Review with real/demo/mixed rows, fallback symbols, snapshots today, real/stale intraday counts, and research-only warnings.
- Tony event integration for outcome analytics runs.
- PowerShell helper scripts for tests, scanner, and dashboard.
- Alpaca IEX market data provider adapter in `src/trading_bot/data/market_data.py` (disabled by default).
- `market_data:` config block in `config/default_config.yaml` with Alpaca settings (feed, timeframe, max_symbols_per_scan, fail_safe_to_demo, stale_data_minutes).
- `intraday:` config block in `config/default_config.yaml`; disabled for scoring by default and available for Tony research reads.
- CLI command: `python -m trading_bot.cli data-check --config config/default_config.yaml --symbol PLTR`.
- Data-check supports intraday timeframe checks, for example `--symbols PLTR,SOFI,HOOD --timeframe 5Min`.
- Watch mode prints intraday enabled/timeframe/Tony/scoring/fallback settings at startup.
- Scan/watch cycles print intraday symbols requested, symbols with data, missing count, fallback count, VWAP counts, opening-range counts, and sample reads.
- Tony creates one `intraday_analysis_summary` event per scan cycle when intraday reads are enabled.
- Command Center shows latest intraday summary event metrics.

## Confirmed in V14.5

- Focused V14.5 tests passed for intraday summary logic, Tony event creation, snapshot storage, and legacy snapshot compatibility.
- Full test stack passed: **331 tests, 0 failures, 0 errors**.
- Scanner passed and regenerated `outputs/latest_scan_results.csv`; local Alpaca HTTPS was blocked, so daily and intraday fetches fell back to demo.
- Watch startup printed intraday config and watch cycle output printed intraday requested/with-data/missing/fallback/VWAP/opening-range counts.
- `tony-events --limit 50` showed `intraday_analysis_summary`.
- Snapshot spot check confirmed new rows store `tony_intraday_read` and `intraday_timeframe` when intraday is enabled; in this environment they correctly show missing intraday data because real Alpaca fetch fell back and intraday fallback is disallowed.

## Confirmed in V14.7

- First live market-hours Tony run completed successfully.
- Latest market-hours watch events showed watch cycle 40 completed, Alpaca IEX returned real data for 167 symbols, 171 symbols fetched in 3 requests, 62/66 real Alpaca intraday reads, 0 stale intraday, and repeated fallback/no-bar symbols `HCP`, `SAMSF`, `SMAR`, and `SQ`.
- Outcome analytics root cause: demo warning rows were not current real-row warning carryover. The default analytics set mixed old demo/fallback snapshots with real rows; real-only analytics reviewed 77 `real_alpaca` snapshots and excluded the `Demo data only` warning rows.
- EOD report command prints watch status, provider, API request count, fallback symbols, intraday counts, snapshot counts, outcome/warning counts, and data-quality notes without trade recommendations.
- Tony remains research-only; no broker execution, paper trades, live trades, orders, options/Greeks logic, or LLM trade decisions were added.

## Confirmed in V14

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` passed: **329 tests, 0 failures, 0 errors**.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1` passed and regenerated `outputs/latest_scan_results.csv`.
- `provider-health` command ran but reported FAILED because outbound HTTPS to Alpaca was blocked in this environment; demo fallback returned data.
- `watch --max-cycles 1` passed, created 84 snapshots, updated 173 snapshots, and stopped cleanly.
- `data-check --symbols PLTR,SOFI,HOOD --timeframe 5Min` passed with demo fallback and printed intraday close, VWAP, above-VWAP status, day change, and opening range.
- Dashboard started at `http://localhost:8501`; Streamlit foreground process was stopped by command timeout after startup.
- Deterministic intraday feature helper in `src/trading_bot/intraday/features.py` for latest close, day range, volume, VWAP, and opening range.
- Candidate snapshots have nullable intraday fields for Tony intraday read, timeframe, close, VWAP, VWAP status, day-change percent, relative volume, and opening-range status.
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
- Intraday scoring automation. V14 stores optional research reads only; daily scoring remains the scanner default.

## Confirmed in V15.8

- Nullable V15.8 tracking columns on `candidate_snapshots` (additive migrations).
- `build_original_plan_freeze_updates()` sets `original_*` once when `entry_status=triggered`; never overwrites existing originals.
- `build_active_tracking_refresh_updates()` updates `current_price`, `research_unrealized_pl_pct`, `time_active_minutes`, and `tracking_status` from real Alpaca 5Min bars when provider is `alpaca_iex`.
- Tony `tracked_setup_updated` event after `update-snapshots` when tracked rows refresh.
- Dashboard Active Tracking + Home preview cards use frozen original entry and current research P/L fields.
- **480 tests passed.**

V15.8 adds research-only active tracking fields. It does not create paper trades or broker orders.

## Confirmed in V15.8A

- Main product tabs now use symbol-level helper aggregation instead of raw snapshot rows.
- Tony Picks show one card per symbol and exclude symbols already represented in Active Tracking.
- Active Tracking shows one card per symbol, anchored to the earliest valid triggered research entry for the current active position.
- Latest rows for the same symbol now refresh current price, research P/L, reassessment, and time-active fields without replacing the original tracked entry.
- Incomplete active-tracking rows with missing entry/target/stop/trigger time are hidden from Home, Tony Picks, and Active Tracking.
- Results `Still active` now aligns with valid deduped active-tracking symbols instead of raw historical rows.
- Main dashboard cards no longer surface `NaN`, `$nan`, `+nan%`, or `Not set yet` for active tracking.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` passed: **488 tests, 0 failures**.
- `eod-report` and `outcome-analytics --real-only --today` completed successfully after the change.
- `run_dashboard.ps1` started Streamlit at `http://localhost:8501`; startup verified in terminal. Full click-through/manual browser verification is still pending.

## Confirmed in V15.7B

- Product theme: purple/blue hero, stat tiles, rounded signal cards, emphasized Research P/L on tracking cards.
- Home hero: “Tony is watching the market.” with stat grid (status, picks, tracking, alerts, research P/L).
- Results uses performance stat cards + disclaimer banner.

## Confirmed in V15.7A

- Tony Picks no longer crashes when `tony_reasons_json` is NaN/float in SQLite rows.
- Display helpers: `format_money_or_missing`, `format_percent_or_missing`, `clean_text_or_default`.
- Home prefers Tony Picks with valid planned entry alerts; fresh active tracking only on Home.

## Confirmed in V15.7

- Dashboard main tabs: Home, Tony Picks, Active Tracking, Results, Settings / System Health.
- Tony Picks and Active Tracking use card UI from `candidate_snapshots` + Tony fields (no JSON on main tabs).
- Research P/L on open tracked setups is computed in helpers (`intraday_close` as provisional current price).
- Legacy Overview/Ranked Stocks/Snapshots/Outcome Analytics/Tony Events/etc. live under Settings → Legacy developer views.
- V15.5 Command Center preserved under Settings legacy tab.

## Confirmed in V15.5

- Command Center answers: Is Tony running? Real data? Anything broken? What is Tony watching? Entry alerts? What to review?
- Plain-English labels on Command Center (watchlist records, planned entry alerts, missing real data).
- Advanced technical tables moved into a collapsed expander; other tabs unchanged.
- Helper unit tests for status labels, trigger summaries, top-watch rows, and health/review bullets.

## Confirmed in V15.2

- `symbol_quarantine` config block in `config/default_config.yaml` quarantines HCP, SAMSF, SMAR, and SQ during `real_data_only` scan/watch.
- Quarantined symbols are excluded before Alpaca fetch, scoring, snapshots, and Tony candidate analysis.
- Symbols remain in `config/universe_swing_research_config.yaml` (non-destructive).
- `eod-report` and dashboard Market Day Review list configured quarantine vs event-detected missing symbols.
- Tony `symbol_quarantine_applied` event records exclusions per scan/watch cycle.
- 391 tests passed with clean teardown (V15.1 temp fix).

## Confirmed in V15

- Nullable snapshot fields: `snapshot_price`, `snapshot_bar_time`, `planned_entry_price`, `planned_entry_rule`, `planned_entry_buffer_pct`, `actual_entry_price`, `actual_entry_time`, `entry_status`, `entry_trigger_source`, `entry_trigger_timeframe`, `entry_trigger_notes`.
- Deterministic planned-entry rules for Breakout Watch, Momentum Continuation, and Pullback Watch in `src/trading_bot/snapshots/entry_triggers.py`.
- Trigger simulation during `update-snapshots` uses only real Alpaca 5Min bars strictly after snapshot time (no lookahead, no EOD-close entry).
- Outcome follow-up evaluates target/stop from `actual_entry_time` when `entry_status=triggered`.
- CLI prints planned/triggered/pending/expired/missing-real-data trigger counts; Tony `entry_trigger_summary` event added.
- Dashboard Candidate Snapshots and Command Center show trigger fields and compact metrics.
- Legacy snapshots without V15 fields still load; new scans show planned entry above snapshot price when intraday context exists.

## Next recommended work

1. Run `watch --max-cycles 1` during market hours and confirm `update-snapshots` marks same-day triggers from live 5Min bars.
2. Review `outcome-analytics --real-only --today --provider alpaca_iex` and `eod-report` after the next market-hours run before adding intraday scoring.
2. Quarantine, disable, or replace repeated fallback/no-bar symbols only after manual review; current repeated symbols are `HCP`, `SAMSF`, `SMAR`, and `SQ`.
3. Add `watch_run_id` FK to `candidate_snapshots` so each snapshot can be correlated to a watch session.
4. Add `tony_analysis_version` grouping to the CLI `--group-by` outcome table output so Tony v1 vs future v2 reads can be compared directly.
5. Decide whether intraday reads should become a scoring input after enough real-data snapshots exist.
5. Add a holiday calendar to `is_within_us_eastern_market_hours()` if market-hours-only mode needs holiday awareness.
6. Initialize git and commit a known-good baseline.

**Universe symbols are curated for research/scanning and are not recommendations to buy or trade any security.**
