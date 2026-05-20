# Trading Bot Project - Testing Checklist

_Last updated: 2026-05-19_

Use this after every meaningful code change.

## Before coding

- Read `AGENTS.md`.
- Read `AGENT_STATE.md`.
- Run `git status --short` if git is initialized.
- Confirm no other agent has active edits.

## Environment checks

```powershell
python --version
pip --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Static sanity checks

```powershell
$env:PYTHONPATH = "src"
python -m compileall src
```

## Unit tests

Preferred on Windows (sets basetemp under `%LOCALAPPDATA%\TradingBotTests\pytest`):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

Direct pytest (also uses `%LOCALAPPDATA%\TradingBotTests\pytest` via `tests/conftest.py` when `--basetemp` is omitted):

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```

Avoid `--basetemp` inside the repo (for example `.pytest_tmp`). Project-local temp dirs are often locked on Windows and cause teardown `PermissionError` noise even when tests pass.

Required test areas:

- indicators,
- scoring engine,
- long trade-plan validation,
- snapshot follow-up outcome calculation,
- universe loader (including production universe size, roles, tags, benchmarks),
- database,
- risk manager,
- backtester,
- V9 scaling (batch fetch, rate limiter, universe rotation, request count audit),
- V11 dashboard helpers (event age, fallback detection, hypothesis counting, snapshot counting),
- V12 watch run state (table CRUD, heartbeat staleness, market-hours guard, watch status labels, no-broker behavior),
- V13 Tony hypothesis-to-outcome tracking (schema columns, Tony field storage, null-safe legacy compat, analysis version constant, outcome analytics grouping, learning event, no-broker guards).
- V14/V14.5 intraday data mode foundation (config parsing, 5Min fetch mocks, VWAP, opening range, insufficient data, Tony intraday labels, watch-mode summary, `intraday_analysis_summary` event, nullable snapshot fields, no order behavior).
- V14.7 real-data-only enforcement (snapshot data-source classification, default real-only analytics, `--include-demo`, today/provider filters, missing-real-data aggregation, EOD report structure, legacy row compatibility, no order behavior).
- V15 intraday entry trigger simulation (planned entry above snapshot price, trigger uses post-snapshot 5Min bars only, no lookahead, first-bar trigger time, pending/expired/missing-real-data statuses, legacy snapshot load, `entry_trigger_summary` event, no broker/order behavior).
- V15.1 Windows pytest temp cleanup (`run_tests.ps1` + `tests/conftest.py` use `%LOCALAPPDATA%\TradingBotTests`; no repo-local `.pytest_tmp` basetemp; clean pass/fail exit codes).
- V15.2 symbol quarantine (HCP/SAMSF/SMAR/SQ excluded from real-only scan, universe YAML unchanged, eod-report/dashboard listing, no broker/demo behavior).
- V15.5 dashboard Command Center UX (`tests/test_dashboard_helpers.py`: status labels, trigger summary, top-watch rows, missing/quarantined summaries; no Streamlit browser automation required).
- V15.8 active tracking fields (`tests/test_v15_8_active_tracking.py`: freeze once, current price/P/L, tracking_status map, legacy null-safe cards, no broker; `update-snapshots` refreshes tracking).
- V15.9 reassessment labels (`tests/test_v15_8_active_tracking.py`: `still_valid / weakening / invalidated / needs_review` assignment, fixed active entry remains unchanged, demo provider does not inject demo price refresh, reassessment updates do not delete snapshots; full-suite check required).
- V15.8C EOD reconciliation (`tests/test_outcome_analytics.py`: classified raw rows, raw-vs-product reconciliation counts, incomplete hidden rows, no deletion/mutation of snapshot history; manual: `eod-report` prints reconciliation proving product dedupe/hiding does not delete history).
- V15.8B dashboard product semantics (`tests/test_dashboard_helpers.py`: entry trigger survives dedupe, trigger distance/explanations, fixed active entry + latest current/closing price, risk/reward fallback, Results filters/cards/counts, no `NaN`/`unknown` product strings; `tests/test_dashboard_theme.py`: `Entry trigger` labels + preview semantics; manual: Home text readable, Tony Picks/Active Tracking/Results show clean product wording and no raw history).
- V15.8A dashboard symbol-level product views (`tests/test_dashboard_helpers.py`: duplicate Tony Picks collapse to one symbol, duplicate Active Tracking rows collapse to one card, first valid triggered entry stays fixed, latest current price overlays active card, incomplete tracking rows hidden, Home preview lists have no duplicate symbols, planned entry vs active entry fields stay distinct, Results still-active count aligns with deduped active cards; `tests/test_dashboard_theme.py`: planned/current/active metrics render on pick/tracking preview cards).
- V15.7E Home briefing card enrichment (`tests/test_dashboard_theme.py`: enriched preview HTML; `tests/test_dashboard_helpers.py`: preview model fields, count-only missing data, calm status; manual: Home cards informative but compact).
- V15.7D Active Tracking import + Home clarity (`tests/test_dashboard_theme.py`: import protection; `tests/test_dashboard_helpers.py`: status/missing-data summaries; manual: Active Tracking tab loads).
- V15.7C dashboard HTML render + Home briefing (`tests/test_dashboard_theme.py`: balanced stat grid, `render_html` unsafe markdown; `tests/test_dashboard_helpers.py`: home preview cap 3, status messages; manual: no raw `<div class="tony-stat-tile">` text on Home/Results).
- V15.7B visual theme (`dashboard/theme.py`; `tests/test_dashboard_theme.py` for `_TONY_APP_CSS`; manual Streamlit check).
- V15.7A dashboard NaN/JSON safety (`_parse_json_list`, display helpers, pick card with NaN reasons; 436 tests).
- V15.7 trading-app dashboard shell (`tests/test_dashboard_helpers.py`: pick phase, research P/L %, card models, results/system health summaries; no Streamlit browser automation required).

Hard rule: active Tony watch/learning runs are real-data-only. Demo provider data is never allowed in watch, snapshots, Tony learning, analytics, paper trading, or live trading. Tests may use mocks or recorded real fixtures, but not synthetic demo market series.

## Scanner smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli scan --config config/default_config.yaml
```

Expected:

- no crash,
- top ranked stocks print,
- `data/trading_bot.db` exists,
- `outputs/latest_scan_results.csv` exists,
- `logs/trading_bot.log` exists.
- active real-data-only config reports Alpaca no-bar symbols as missing real data,
- no demo fallback is used for active real runs,
- missing symbols are not scored or snapshotted.

## Candidate snapshot smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli snapshot --config config/default_config.yaml
```

Expected:

- no crash,
- scan results are still saved,
- candidate snapshot summary prints,
- `candidate_snapshots` table has open/watch rows,
- no paper trades are created.

## Candidate snapshot follow-up smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli update-snapshots --config config/default_config.yaml
```

Expected:

- no crash,
- open/watch snapshots are checked,
- follow-up fields are updated when future bars exist,
- prints planned triggers, triggered entries, pending, expired/no-trigger, and missing real-data trigger counts,
- intraday trigger simulation uses real Alpaca 5Min bars only when `real_data_only` is enabled,
- same-day daily demo snapshots may be labeled `insufficient_future_data`,
- no paper trades or orders are created.

## Demo snapshot seed smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli seed-demo-snapshots --config config/default_config.yaml
```

Expected:

- no crash,
- historical demo snapshots are created or skipped as duplicates,
- rows are clearly labeled as demo/testing snapshots,
- seeded rows are not treated as evidence of real market edge,
- no paper trades or orders are created.

## Scheduled Watch Mode smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1
```

Expected:

- no crash,
- one scan cycle runs,
- eligible candidate snapshots are created or skipped by dedupe cleanly,
- when `intraday.enabled: true`, watch startup prints intraday config and scan/watch output includes intraday summary counts,
- Tony events include `intraday_analysis_summary` when intraday reads are enabled,
- snapshot follow-up update runs if enabled,
- no paper trades or orders are created.

To run while the computer is on:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_watch_mode.ps1
```

To stop: press Ctrl+C in the PowerShell window, or create `data/STOP_WATCH_MODE`.

## Tony Stocks event smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli tony-events --config config/default_config.yaml --limit 20
```

Expected:

- no crash,
- recent Tony watcher/analyst events print,
- events are internal database records only,
- no external messages are sent,
- no paper trades or orders are created.

## Outcome analytics smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli outcome-analytics --config config/default_config.yaml
python -m trading_bot.cli outcome-analytics --config config/default_config.yaml --include-seeded
python -m trading_bot.cli outcome-analytics --config config/default_config.yaml --include-demo
python -m trading_bot.cli outcome-analytics --config config/default_config.yaml --real-only
python -m trading_bot.cli outcome-analytics --config config/default_config.yaml --real-only --today --provider alpaca_iex
```

Expected:

- no crash,
- seeded demo fixture rows, old demo rows, missing-real-data rows, and legacy rows are excluded by default,
- `--include-seeded` mode clearly labels seeded fixture results as not evidence of real market edge,
- `--include-demo` explicitly includes old demo rows for review,
- grouped setup category, score bucket, universe role, outcome label, and warning summaries print,
- no paper trades or orders are created.

## End-of-day market review smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli eod-report --config config/default_config.yaml
```

Expected:

- no crash,
- prints watch cycles, latest watch status, provider, real symbols scanned, API requests, missing real-data symbols, intraday real/stale/VWAP/opening-range counts, snapshots today, outcome counts, warning counts, and data-quality notes,
- repeated missing real-data symbols are reported for manual review only,
- no paper trades, broker orders, or live orders are created.

## Data-check smoke test (demo mode — no real keys needed)

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli data-check --config config/default_config.yaml --symbol PLTR
python -m trading_bot.cli data-check --config config/default_config.yaml --symbols PLTR,SOFI,HOOD --timeframe 5Min
```

Expected:

- no crash,
- prints active provider (demo_generated by default),
- prints latest bar timestamp, close, and volume,
- no scan, no trade, no order.
- with `--timeframe 5Min`, prints intraday read, VWAP, day-change, and opening-range values when bars are available.

To test with real Alpaca keys:
1. Copy `.env.example` to `.env` and fill in `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`.
2. Set `provider: alpaca_iex` in `config/default_config.yaml`.
3. Re-run the command above.
4. Check for "fallback" warning if keys are invalid or market is closed outside hours.

**Alpaca IEX notice:** IEX is a single-exchange feed; may differ from SIP consolidated tape. For research/scanning only — no orders are placed.

## Alpaca provider unit tests (mocked — no real API calls)

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_alpaca_provider.py -v
```

Expected:

- 16 tests pass,
- no real HTTP requests (all mocked),
- missing-key test raises EnvironmentError with helpful message,
- fallback-to-demo test produces demo data and records fallback_symbols,
- HTTP error test raises OSError without fallback when fail_safe_to_demo=False.

## V9 scaling tests (batch fetch, rate limiter, universe rotation)

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_v9_scaling.py tests/test_universe.py -v
```

Expected:

- 31 V9 scaling tests pass (batch normalization, rate limiter, rotation, request count audit).
- 20 universe tests pass (5 original + 15 V9.5 production universe tests).
- `test_batch_request_uses_high_limit` confirms `limit=10000` in batch HTTP params.
- `test_batch_of_n_symbols_counts_as_one_http_request` confirms 1 batch call for N symbols.
- Production universe tests confirm ≥150 symbols, valid roles, core benchmarks, discovery pool.
- No real HTTP requests — all mocked.
- No broker, order, or paper-trade behavior.

## V9 watch-mode validation (requires real Alpaca keys)

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli watch --config config/universe_swing_research_config.yaml --max-cycles 1
python -m trading_bot.cli tony-events --config config/universe_swing_research_config.yaml --limit 30
```

Expected (with real keys):

- Scan cycles over up to 175 symbols using rotation.
- `batch_fetch_summary` Tony event shows 175 symbols in 1–2 HTTP requests.
- `universe_rotation_summary` Tony event shows bucket_id, core/discovery/open-snapshot counts.
- No rate-limit warnings at default RPM=175 with buffer.
- No broker calls, no orders, no paper trades.

## Dashboard smoke test

```powershell
streamlit run src/trading_bot/dashboard/app.py
```

Expected:

- dashboard opens,
- latest scan overview is visible,
- ranked stocks table loads.

## Safety checks

- `live_trading_enabled` remains false.
- Alpaca adapter uses market data endpoints only — no broker/trading/order endpoints.
- No real API keys are committed.
- No broker order execution exists in V1 scanner.
- Every scored stock includes entry, stop, target, risk/reward, reasons, and warnings.
- Long setup trade levels must be validated before snapshots, paper trades, or outcome tracking can trust scanner output.
- Eligible buy-opportunity rows must have `stop < entry`, `target > entry`, and positive risk/reward.
- Candidate snapshots are saved as research records only and do not create paper trades or orders.
- Candidate snapshots exclude invalid trade plans by default.
- Snapshot follow-up updates must not create paper trades, broker orders, or live orders.
- Seeded demo snapshots are for dashboard/outcome tracker testing only and are not evidence of real market edge.
- Scheduled Watch Mode is scanning/snapshot collection only. It does not place paper trades or live trades.
- Tony Stocks is currently a watcher/analyst event layer only. It does not paper trade, execute broker orders, place live trades, or use an LLM for trade decisions.
- Outcome analytics are for model evaluation and research. Seeded demo fixture results are excluded by default and are not proof of strategy quality.
- Intraday reads are attached to Tony research hypotheses and snapshots when enabled, but do not affect scoring yet and are not entry automation.

## V12 watch run state tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_watch_run.py -v
```

Expected:

- 52 tests pass across 10 classes: `TestWatchRunTable`, `TestCreateWatchRun`, `TestUpdateWatchRunHeartbeat`, `TestUpdateWatchRunStopped`, `TestUpdateWatchRunError`, `TestLatestWatchRun`, `TestIsHeartbeatStale`, `TestIsWithinUsEasternMarketHours`, `TestWatchStatusLabel`, `TestNoBrokerBehavior`.
- All heartbeat/market-hours tests use injected `now` — no real-time clock dependency.
- No broker fields, no paper trades, no order placement in any watch run operation.

## V12 Workday watch mode smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1
python -m trading_bot.cli tony-events --config config/default_config.yaml --limit 10
```

Expected:

- Watch run created (`watch_run_started` Tony event).
- One scan cycle completes with heartbeat update.
- Watch run marked stopped (`watch_run_stopped` Tony event) with reason `max_cycles`.
- No broker execution, no paper trades, no orders.

## Agent handoff checks

- Update `AGENT_STATE.md`.
- List files changed.
- List commands run.
- Note failures.
- Note next step.
