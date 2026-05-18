# Agent State / Handoff Log

_Last updated: 2026-05-18_

Use this file so Codex, Claude, Cursor, or any other agent can continue from the same context when the user switches because of usage limits.

---

## V15 handoff - Intraday Entry Trigger Simulation

### Current active task

V15 complete. Research-only intraday entry trigger simulation is implemented on candidate snapshots. V15 adds research-only intraday trigger simulation. It does not create paper trades or broker orders. Next: run one supervised market-hours `watch --max-cycles 1` and `update-snapshots` to validate live 5Min trigger hits on same-day snapshots.

### Files changed in this pass

- `config/default_config.yaml` - Added `entry_trigger_simulation` block and `entry_trigger_summary` Tony event.
- `src/trading_bot/settings.py` - Added `entry_trigger_simulation` config field.
- `src/trading_bot/storage/database.py` - Added nullable V15 snapshot columns via migrations.
- `src/trading_bot/storage/repositories.py` - Persist/read trigger fields; count helpers for dashboard.
- `src/trading_bot/snapshots/entry_triggers.py` - **NEW** planned-entry rules and 5Min trigger simulation.
- `src/trading_bot/snapshots/followup.py` - Outcomes evaluate from `actual_entry_time` when triggered.
- `src/trading_bot/snapshots/__init__.py` - Export V15 symbols.
- `src/trading_bot/cli.py` - Plan triggers at snapshot creation; simulate on `update-snapshots`; console summary.
- `src/trading_bot/tony/events.py` - `record_entry_trigger_summary()` and event type.
- `src/trading_bot/dashboard/app.py` - Candidate Snapshots + Command Center trigger metrics/columns.
- `tests/test_v15_entry_triggers.py` - **NEW** mocked trigger tests.
- `tests/test_database.py` - Schema assertions for V15 columns.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `FILE_STRUCTURE.md`, `AGENT_STATE.md` - Updated.

### New snapshot fields

- `snapshot_price`, `snapshot_bar_time`
- `planned_entry_price`, `planned_entry_rule`, `planned_entry_buffer_pct`
- `actual_entry_price`, `actual_entry_time`, `entry_status`
- `entry_trigger_source`, `entry_trigger_timeframe`, `entry_trigger_notes`

Legacy rows load with NULL trigger fields.

### Planned entry rule behavior

| Setup | Rule | Planned level |
|-------|------|----------------|
| Breakout Watch | `breakout_above_recent_high` | max(snapshot_price, recent intraday high) + buffer |
| Momentum Continuation | `momentum_break_5min_high_above_vwap` | recent 5Min high when above VWAP |
| Pullback Watch | `pullback_reclaim_vwap_or_prior_high` | max(VWAP, recent 5Min high) when available |
| Missing intraday / real data | `missing_intraday_context` / `no_intraday_trigger_rule` | no planned price; status `missing_real_data` or `no_intraday_trigger` |

These are research triggers, not buy/sell recommendations.

### Actual trigger simulation behavior

- Runs in `update-snapshots` when `entry_trigger_simulation.enabled: true`.
- Fetches real Alpaca 5Min bars (skipped when `real_data_only` and provider is not `alpaca_iex`).
- Uses only bars strictly after `snapshot_bar_time` or `snapshot_time`.
- Trigger when `bar.high >= planned_entry_price`; `actual_entry_time` = first qualifying bar; `actual_entry_price` = planned price (configurable).
- Same day without trigger → `pending`; after window → `expired` or `not_triggered`.
- Does not use end-of-day close as entry.

### No-lookahead protection

- `_bars_after_snapshot()` filters `index > snapshot_reference_time`.
- Pre-snapshot highs cannot trigger entry (covered by tests).

### Dashboard changes

- Candidate Snapshots table: snapshot/planned/actual entry columns and `entry_status`.
- Detail panel shows trigger fields.
- Command Center metrics: planned triggers today, triggered entries today, pending, expired/no-trigger.

### Tests/checks run

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli scan --config config/default_config.yaml --save-snapshots
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli update-snapshots --config config/default_config.yaml --limit 15
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli eod-report --config config/default_config.yaml
```

Results:

- Full test script: **278 passed** (106 pytest tmp teardown permission errors on Windows/WSL; no assertion failures in V15 tests).
- V15 unit tests: **15 passed** (5 teardown errors on tmp cleanup only).
- Scanner passed with Alpaca IEX (stale after-hours bars).
- `scan --save-snapshots` created 7 snapshots; planned entries printed above snapshot price (example: AVGO snapshot=420.6 planned=427.45).
- `update-snapshots` ran on 15 open rows (legacy rows without planned prices).
- `eod-report` completed.
- `watch --max-cycles 1` not run (outside market hours / not requested for safe path).

### Safety confirmation

No broker execution, live trading, automatic paper trades, orders, options/Greeks logic, API key logging, LLM trade decisions, or profitability claims were added. Demo provider is not used for trigger simulation when `real_data_only` is enabled.

### Next recommended task

Run `watch --max-cycles 1` during market hours, then `update-snapshots`, and verify `entry_status=triggered` rows have `actual_entry_time` on first post-snapshot 5Min bar. Compare `outcome-analytics --real-only --today` for trigger-aware outcomes.

---

## V14.7 handoff - Real-Data-Only Enforcement / No Demo Provider

### Current active task

V14.7 real-data-only enforcement implemented. First live market-hours Tony run completed successfully; next focus is real-data-only analytics hygiene before intraday scoring. Active Tony watch/learning runs are real-data-only. Demo provider data is never allowed in watch, snapshots, Tony learning, analytics, paper trading, or live trading. Tests may use mocks or recorded real fixtures, but not synthetic demo market series.

### Files changed in this pass

- `config/default_config.yaml` - Added real-data-only guard fields, disabled active demo fallback, disabled default demo snapshot seeding, and set Alpaca fail-safe/fallback flags false.
- `src/trading_bot/settings.py` - Added config fields and `real_data_only_enabled()`.
- `src/trading_bot/data/market_data.py` - Real-only Alpaca config forces `fail_safe_to_demo=false`; provider now tracks missing symbols separately from explicit dev fallback symbols.
- `src/trading_bot/storage/database.py` - Added nullable candidate snapshot data-source metadata columns.
- `src/trading_bot/storage/repositories.py` - Candidate snapshots and old demo seed snapshots can persist data-source metadata.
- `src/trading_bot/analytics/outcomes.py` - Analytics defaults to real rows only, adds `--include-demo`/legacy behavior support, and reports exclusion counts.
- `src/trading_bot/cli.py` - Real-only scan/watch rejects demo providers, records missing real-data symbols, excludes demo/legacy rows by default in analytics, and expands EOD report fields.
- `src/trading_bot/tony/analysis.py` - Missing real data is labeled `missing_real_data`; Tony learning uses real-only analytics by default.
- `src/trading_bot/tony/events.py` - Real-run event wording now reports missing real data and says no demo data was used.
- `src/trading_bot/dashboard/app.py` - Market Day Review now shows real rows, demo/legacy excluded rows, missing real-data symbols, quarantine candidates, and intraday real/stale counts.
- `tests/test_outcome_analytics.py`, `tests/test_database.py`, `tests/test_scanner_smoke.py`, `tests/test_tony_analyst.py` - Updated/added mocked tests for real-only defaults, include-demo review, missing-symbol behavior, schema compatibility, EOD output, and no paper/order behavior.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - Updated hard rule, status, backlog, and handoff notes.

### Behavior

- With `real_data_only: true`, active scan/watch refuses `demo_generated` and `demo_csv` providers.
- Alpaca no-bar or provider-missing symbols are marked missing real data, are not scored from demo data, do not create snapshots, and do not enter Tony learning.
- Snapshot classifications are now `real_alpaca`, `missing_real_data`, `recorded_real_fixture`, `legacy_unknown`, and old `demo_generated`.
- Outcome analytics defaults to real rows only and prints: `Real-data rows only. Demo and legacy rows excluded.`
- `--include-demo` explicitly reviews old demo rows; old demo rows are not deleted automatically.
- Repeated missing symbols such as `HCP`, `SAMSF`, `SMAR`, and `SQ` are report-only quarantine/replacement candidates.

### Tests/checks run

```powershell
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m compileall src\trading_bot
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_database.py tests/test_outcome_analytics.py tests/test_scanner_smoke.py tests/test_tony_analyst.py -q --basetemp=.pytest_tmp
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml --include-demo
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli eod-report --config config/default_config.yaml
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli tony-events --config config/default_config.yaml --limit 50
powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1
git diff --check
```

Results:

- Focused tests passed: 91 passed.
- Full test script passed: 371 passed.
- Scanner script completed. This sandbox blocked Alpaca HTTPS (`WinError 10013`), so 100 symbols were marked missing real data, 0 symbols were scored, and no demo fallback was used.
- Default `outcome-analytics` reviewed 77 `real_alpaca` rows and excluded demo/legacy/missing rows.
- `outcome-analytics --include-demo` reviewed 257 rows and explicitly surfaced old demo warning rows.
- `eod-report` completed and showed real symbols scanned as 0 after the blocked scanner smoke, repeated missing real-data symbols including `HCP`, `SAMSF`, `SMAR`, and `SQ`, plus the older live-run real-only snapshot counts.
- `watch --max-cycles 1` timed out because default config is market-hours-only and the command ran outside the configured market window; it waited for market open and did not scan, trade, or fallback to demo. The resulting running watch row was marked error with a verification-timeout note so the dashboard is not left with a stale running process.
- `tony-events --limit 50` completed.
- Dashboard script started Streamlit at `http://localhost:8501`; the command timed out because Streamlit runs in the foreground. No lingering Streamlit/Python process remained.
- `git diff --check` passed with CRLF normalization warnings only.

### Safety confirmation

No broker execution, live trading, automatic paper trades, orders, options/Greeks logic, API key logging, LLM trade decisions, or profitability claims were added. Tony remains research-only.

### Next recommended task

Run one supervised market-hours watch cycle with the hardened config. If `HCP`, `SAMSF`, `SMAR`, and `SQ` continue to report missing real data, manually quarantine or replace them before intraday scoring work.

---

## V14.7 handoff - Real Market-Day Review Cleanup

_(Prior handoffs retained below for history.)_
