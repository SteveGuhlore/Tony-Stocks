# Agent State / Handoff Log

_Last updated: 2026-05-19_

Use this file so Codex, Claude, Cursor, or any other agent can continue from the same context when the user switches because of usage limits.

---

## V15.9 handoff - Tony Reassessment Labels

### Current active task

V15.9 is complete. Active tracked research setups now receive deterministic Tony reassessment labels during the existing refresh path: `still_valid`, `weakening`, `invalidated`, or `needs_review`.

### Root cause

Active Tracking already refreshed current price, research P/L, and status, but it had no compact research-only interpretation of whether the tracked setup still looked intact, was weakening, had effectively invalidated, or simply lacked enough current real context for a clean read.

### Files changed

- `src/trading_bot/storage/database.py` - added additive `reassessment_label` snapshot column.
- `src/trading_bot/storage/repositories.py` - repository updates now accept `reassessment_label`.
- `src/trading_bot/snapshots/active_tracking.py` - added deterministic reassessment derivation and stored label/note updates during active tracking refresh; tracked summary counts now include reassessment buckets.
- `src/trading_bot/snapshots/__init__.py` - exported reassessment constants/helper.
- `src/trading_bot/tony/events.py` - enabled `tracked_setup_updated` by default and expanded its payload/message with reassessment counts.
- `tests/test_v15_8_active_tracking.py` - label assignment, fixed entry preservation, demo-skip behavior, migration/repository support, and no-deletion coverage.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_v15_8_active_tracking.py -q --basetemp .pytest_tmp_v159_tracking` -> **23 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v159_outcomes` -> **10 passed**

### Known limitations

- Reassessment currently renders through the existing `reassessment_note` path on Active Tracking; there is not yet a dedicated visual pill/field for `reassessment_label`.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no order placement, no demo-data injection, no active-entry rewrites, and no snapshot deletion.

## V15.8C handoff - EOD Data Reconciliation

### Current active task

V15.8C is complete. `eod-report` now prints a raw-vs-product reconciliation section that proves dashboard dedupe/hiding changes visibility only and does not delete raw candidate snapshot history. Settings / System Health also includes a compact reconciliation summary.

### Root cause

The product dashboard intentionally hides duplicates, stale history rows, and incomplete product rows, but there was no explicit report proving those raw rows still existed in storage. That left the system looking lossy even though the database retained the full history.

### Files changed

- `src/trading_bot/analytics/outcomes.py` - added `classified_snapshots()` for raw history classification before active filters.
- `src/trading_bot/dashboard/helpers.py` - added `summarize_product_reconciliation()` for raw snapshot rows vs current product-view counts.
- `src/trading_bot/cli.py` - `eod-report` now prints reconciliation counts and an explicit raw-history-preserved note.
- `src/trading_bot/dashboard/app.py` - Settings / System Health now shows a small reconciliation summary.
- `tests/test_outcome_analytics.py` - reconciliation counts, raw-vs-product distinction, and no-deletion coverage.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v158c_outcomes` -> **10 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py -q --basetemp .pytest_tmp_v158c_helpers` -> **128 passed**

### Known limitations

- The compact Settings reconciliation summary uses the current research snapshot slice already loaded by the dashboard, not a separate full raw-history table dump. The full raw proof remains the CLI `eod-report` output and the legacy developer views.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no order placement, no demo-data injection, no snapshot deletion, and no API key output.

## V15.8B handoff - Product Dashboard Semantics: Entry Triggers, Current Positions, Closing Price, Results Rehaul

### Current active task

V15.8B code/test work is complete. Main dashboard product views now use entry-trigger vs active-entry semantics, after-hours closing-price labeling, deduped current-state Results filters/cards, and short complete Home preview sentences. Focus next on full Windows command run + manual browser verification.

### Root cause

Even after V15.8A symbol dedupe, the product layer was still exposing raw/internal semantics: `Planned entry` wording implied buy-now behavior, Home preview text clipped awkwardly, Results still behaved like a count summary instead of a current clean product state, and after-hours prices were not clearly labeled as closing prices.

### Files changed

- `src/trading_bot/dashboard/helpers.py` - added entry-trigger distance/risk-reward/trigger-explanation helpers; upgraded pick/tracking card models; added current-state Results row/filter/card/count helpers; aligned Results summary counts with deduped product semantics.
- `src/trading_bot/dashboard/theme.py` - changed visible labels to `Entry trigger`; preview cards use complete short sentences; tracking cards use dynamic current/closing price labels; added Results stock-card renderer and expanded summary bubbles.
- `src/trading_bot/dashboard/app.py` - Tony Picks / Active Tracking captions now explain trigger and risk/reward semantics; Results now renders deduped filters plus actual stock cards from current product rows.
- `tests/test_dashboard_helpers.py`, `tests/test_dashboard_theme.py` - added V15.8B coverage for trigger wording, trigger distance/explanations, fixed active entry + latest closing/current price, risk/reward fallback, Results filters/cards/counts, and no `NaN` / `unknown` product strings.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py tests/test_dashboard_theme.py -q --basetemp .pytest_tmp_v158b_focus` -> **140 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v158b_outcomes` -> **8 passed**

### Known limitations

- Full `run_tests.ps1`, CLI report commands, and `run_dashboard.ps1` have not yet been rerun for V15.8B in this handoff entry.
- Manual browser click-through is still pending for Home, Tony Picks, Active Tracking, and Results.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no order placement, no demo-data injection into product views, no snapshot deletion, and no API key output.

## V15.8 handoff - Freeze Original Plan + Active Tracking Fields

## V15.8A handoff - One Active Position Per Symbol + Planned vs Active Entry Cleanup

### Current active task

V15.8A complete. Main product dashboard views now collapse raw snapshot history into one current product card per symbol. The first valid triggered research entry stays fixed for Active Tracking, and later rows only refresh live tracking fields for that same symbol. **488 tests passed.**

### Root cause

Home, Tony Picks, Active Tracking, and Results were rendering and counting raw snapshot rows directly. Repeated watch cycles therefore surfaced duplicate symbols, stale planned-entry rows, incomplete triggered rows, and still-active counts that did not match visible active cards.

### Files changed

- `src/trading_bot/dashboard/helpers.py` - symbol-level product-row builders for Tony Picks and Active Tracking; fixed-entry anchor + latest-live-field overlay; stricter product-row filtering; results still-active alignment; planned vs active entry card fields.
- `src/trading_bot/dashboard/app.py` - product tabs and Home now consume deduped symbol-level rows; pending alert count on Home is symbol-level.
- `src/trading_bot/dashboard/theme.py` - pick/tracking cards now separate Planned entry, Active entry/Tracked from, and Current price.
- `tests/test_dashboard_helpers.py`, `tests/test_dashboard_theme.py` - dedupe/fixed-entry/latest-price/NaN cleanup/results-alignment coverage.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` -> **488 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py tests/test_dashboard_theme.py -q --basetemp .pytest_tmp_dashboard` -> **130 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_v15_8_active_tracking.py -q --basetemp .pytest_tmp_v158` -> **17 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli eod-report --config config/default_config.yaml`
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml --real-only --today`
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1` -> Streamlit startup verified at `http://localhost:8501`

### Known limitations

- Full manual browser click-through was not completed from this terminal session. Startup is verified; visual tab-by-tab inspection is still recommended.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no trade placement, no demo data injection, no history deletion, and no API key output.

### Current active task

V15.8 complete. Frozen original plan on trigger; live research tracking fields refresh during `update-snapshots`. **480 tests passed.**

### New tracking fields (nullable on `candidate_snapshots`)

`original_entry_price`, `original_target_price`, `original_stop_price`, `original_plan_captured_at`, `tracking_status`, `tracking_started_at`, `current_price`, `current_price_at`, `research_unrealized_pl_pct`, `current_target_price`, `current_stop_price`, `reassessment_note`, `last_reassessed_at`, `invalidation_reason`, `time_active_minutes`, `pick_phase`

### Files changed

- `src/trading_bot/storage/database.py` — V15.8 migrations
- `src/trading_bot/storage/repositories.py` — allow tracking field updates
- `src/trading_bot/snapshots/active_tracking.py` — **NEW** freeze/refresh/status logic
- `src/trading_bot/snapshots/__init__.py` — exports
- `src/trading_bot/cli.py` — freeze + refresh in `update-snapshots`
- `src/trading_bot/tony/events.py` — `tracked_setup_updated` event
- `src/trading_bot/dashboard/helpers.py` — card model uses frozen/current fields
- `src/trading_bot/dashboard/theme.py` — reassessment note on full tracking card
- `tests/test_v15_8_active_tracking.py` — **NEW**
- `tests/test_database.py`, `tests/test_dashboard_helpers.py` — updated
- Docs updated

### Safety

No broker, paper, live, orders, demo fake prices when `real_data_only` + non-Alpaca provider.

### Next

Market-hours validation: trigger a setup, run `update-snapshots`, confirm frozen plan + live P/L on Active Tracking tab.

---

## V15.7E handoff - Home Briefing Card Enrichment

### Current active task

V15.7E complete. Home Top 3 pick/tracking preview cards enriched (pills + compact metrics). Home status/missing-data copy calmer (count-only symbols on Home). **463 tests passed** (full suite via project venv).

### Files changed

- `src/trading_bot/dashboard/theme.py` — `build_pick_preview_card_html`, `build_tracking_preview_card_html`, preview CSS.
- `src/trading_bot/dashboard/helpers.py` — `tony_status_home_message`, `format_home_missing_data_summary`, preview field constants.
- `tests/test_dashboard_helpers.py`, `tests/test_dashboard_theme.py` — V15.7E coverage.
- Docs updated.

### Manual verify

`scripts\run_dashboard.ps1` → Home cards show entry/target/stop and tracking levels; Tony Picks / Active Tracking still full detail.

### Safety

No scoring, entry trigger, DB, broker, paper, live, demo, or API-key changes.

### Next

V15.8: freeze Original Plan at trigger + live `current_price` refresh during watch cycles.

---

## V15.7D handoff - Active Tracking Render Hotfix + Home Clarity

### Current active task

V15.7D complete. Fixed Active Tracking `NameError` (missing theme import). Home status and missing-data copy softened for after-hours. **116 dashboard tests passed** (`test_dashboard_helpers.py`, `test_dashboard_theme.py`). Run full `run_tests.ps1` on Windows for full suite.

### Root cause

V15.7C refactored theme imports in `app.py` and dropped `render_tracking_position_card` while `render_active_tracking()` still called it.

### Files changed

- `src/trading_bot/dashboard/app.py` — re-import `render_tracking_position_card`; pass `watch_error_message` to Home status.
- `src/trading_bot/dashboard/helpers.py` — calmer `tony_status_home_message()`; `format_home_missing_data_summary()`.
- `tests/test_dashboard_theme.py` — import protection tests.
- `tests/test_dashboard_helpers.py` — status + missing-data tests.
- Docs updated.

### Manual verify

Streamlit started at http://localhost:8501 (WSL agent smoke: import + `streamlit run` OK). On Windows, run `scripts\run_dashboard.ps1` and click all five tabs — especially Active Tracking.

### Safety

No scoring, entry trigger, DB, broker, paper, live, demo, or API-key changes.

### Next

V15.8: freeze Original Plan at trigger + live `current_price` refresh during watch cycles.

---

## V15.7C handoff - Dashboard Render Fix + Home/Picks Separation

### Current active task

V15.7C complete. Fixed raw HTML on Home/Results; separated Home (executive briefing) from Tony Picks (full picker). **447 tests passed.**

### Root cause

Block-level theme HTML was emitted without consistent `st.markdown(..., unsafe_allow_html=True)` via a central helper; partial/broken fragments (and a bad `motionless` placeholder pass) caused Streamlit to show literal tags as page text after the first stat tile.

### Files changed

- `src/trading_bot/dashboard/theme.py` — `render_html()`, clean `build_stat_grid_html()`, preview card renderers, balanced div helpers.
- `src/trading_bot/dashboard/app.py` — Home briefing layout; Tony Picks full picker copy; `waiting_for_market` in context.
- `tests/test_dashboard_theme.py` — stat grid HTML + `render_html` tests.
- `tests/test_dashboard_helpers.py` — home preview cap, status messages, briefing items.
- `CURRENT_STATUS.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md`.

### Manual verify

`powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1` → http://localhost:8501 — Home short briefing, Tony Picks full cards, Results stat tiles styled.

### Safety

No scoring, entry trigger, DB, broker, paper, live, demo, or API-key changes.

### Next

V15.8: freeze Original Plan at trigger + live `current_price` refresh during watch cycles.

---

## V15.7B hotfix - Theme CSS NameError

Fixed `_TONY_APP_CSS` NameError (`TONY_APP_CSS` renamed to `_TONY_APP_CSS`). Added `tests/test_dashboard_theme.py`. **438 tests passed.**

---

## V15.7B handoff - Visual Product Polish

### Current active task

V15.7B complete. Modern AI stock-picker visual layer (theme.py). **436 tests passed.** UI only.

### Files changed

- `src/trading_bot/dashboard/theme.py` - **NEW** app CSS, hero, stat tiles, signal/tracking/results cards.
- `src/trading_bot/dashboard/app.py` - wired theme into Home, Picks, Tracking, Results.
- Docs updated.

### Next

V15.8: freeze Original Plan + live current_price refresh.

---

## V15.7A handoff - Dashboard Crash Fix + Card Polish

### Current active task

V15.7A complete. Fixed TypeError on Tony Picks (NaN `tony_reasons_json`). Removed `$nan`/`+nan%` from UI. Card CSS polish. **436 tests passed.**

### Files changed

- `src/trading_bot/dashboard/helpers.py` - safe `_parse_json_list`, display formatters, home sort/filter.
- `src/trading_bot/dashboard/app.py` - HTML card polish, home pick/tracking selection.
- `tests/test_dashboard_helpers.py` - V15.7A tests.

### Next

V15.8: freeze Original Plan at trigger + live current_price refresh.

---

## V15.7 handoff - Trading-App Dashboard Shell

### Current active task

V15.7 complete. Five-tab Tony Stocks dashboard (Home, Tony Picks, Active Tracking, Results, Settings / System Health). Legacy developer views under Settings only. No DB/scoring/trigger changes.

### Files changed

- `src/trading_bot/dashboard/helpers.py` - V15.7 helpers: pick phase, card models, research P/L, results/system health summaries.
- `src/trading_bot/dashboard/app.py` - Five-tab shell, card renderers, legacy views in Settings.
- `tests/test_dashboard_helpers.py` - V15.7 tests (14 new cases).
- Docs updated.

### Tests/checks

- `run_tests.ps1`: **421 passed**.
- `eod-report`: OK.
- `outcome-analytics --real-only`: run locally if needed.
- `run_dashboard.ps1`: start Streamlit and spot-check five tabs.

### Safety

No scoring, entry trigger, broker, paper, live, demo, or API-key changes. No new DB columns.

### Next

V15.8: freeze Original Plan at trigger + live current_price refresh in watch cycle.

---

## V15.5 handoff - Dashboard UI/UX Simplification

### Current active task

V15.5 complete. Command Center redesigned for non-technical 30-second review. V15.5 simplifies the dashboard for non-technical review. It does not change trading/scoring behavior. Next: market-hours watch validation.

### Files changed

- `src/trading_bot/dashboard/helpers.py` - Beginner-friendly Command Center helpers (status, data safety, market read, top watches, triggers, EOD, health/review).
- `src/trading_bot/dashboard/app.py` - Command Center redesign; advanced details in collapsed expander.
- `tests/test_dashboard_helpers.py` - V15.5 helper tests added.
- Docs updated.

### Tests/checks

- `run_tests.ps1`: **407 passed** (includes V15.5 `test_dashboard_helpers.py`).
- `eod-report --config config/default_config.yaml`: OK (research-only banner; 7 real snapshots today).
- `outcome-analytics --real-only`: OK (7 real_alpaca rows; demo excluded).
- `run_dashboard.ps1`: Streamlit started at http://localhost:8501 (Command Center import OK).

### Safety

No scoring, entry trigger, broker, paper, live, demo, or API-key changes.

### Next

Market-hours `watch --max-cycles 1` with simplified Command Center review.

---

## V15.2 handoff - Symbol Quarantine for Missing Real Data

### Current active task

V15.2 complete. HCP, SAMSF, SMAR, and SQ are quarantined in config for real-data-only scan/watch (non-destructive; still in universe YAML). Next: market-hours `watch --max-cycles 1` to validate cleaner Tony runs.

### Files changed

- `config/default_config.yaml` - `symbol_quarantine` block; Tony `symbol_quarantine_applied` event.
- `src/trading_bot/data/symbol_quarantine.py` - **NEW** quarantine load/filter helpers.
- `src/trading_bot/settings.py` - `symbol_quarantine` config field.
- `src/trading_bot/cli.py` - Filter before fetch/score; watch rotation pool; eod-report output.
- `src/trading_bot/tony/events.py` - `record_symbol_quarantine_applied()`.
- `src/trading_bot/dashboard/app.py` - Market Day Review quarantine display.
- `tests/test_symbol_quarantine.py` - **NEW** (7 tests).
- Docs updated.

### Tests/checks

- `run_tests.ps1`: **391 passed**, All tests passed.
- `run_scanner.ps1`: quarantine printed; symbols loaded 97 (4 excluded from 101-cap slice).
- `eod-report`: lists configured quarantine HCP, SAMSF, SMAR, SQ.
- `outcome-analytics --real-only`: 7 real_alpaca rows.

### Safety

No trading, scoring rule, broker, paper, live, demo, or API-key changes.

### Next

Market-hours watch validation with quarantine active.

---

## V15.1 handoff - Windows pytest temp cleanup

### Current active task

V15.1 complete. `scripts/run_tests.ps1` now uses `%LOCALAPPDATA%\TradingBotTests\pytest` for `--basetemp` and a separate `tmp` folder for `TMP`/`TEMP`. `tests/conftest.py` sets the same default when pytest is run without `--basetemp`. Full suite: **384 passed, 0 teardown errors**.

### Root cause

Pytest basetemp under the repo (`.pytest_tmp` or `.pytest_tmp_sessions`) hit Windows `PermissionError` on teardown. Common causes: IDE/WSL file locks on the project tree, stale locked temp dirs, and SQLite `tmp_path` dirs under a locked parent. Moving basetemp to `%LOCALAPPDATA%\TradingBotTests` avoids those locks. Setting `TMP`/`TEMP` to a sibling `tmp` folder (not the basetemp root) avoids extra files blocking basetemp deletion.

### Files changed

- `scripts/run_tests.ps1` - LOCALAPPDATA basetemp/tmp, prune old sessions, explicit exit codes.
- `tests/conftest.py` - **NEW** default basetemp outside repo; autouse `gc.collect()` after each test.
- `pyproject.toml` - Comment on basetemp policy.
- `.gitignore` - Ignore `.pytest_tmp_sessions/`.
- `src/trading_bot/snapshots/followup.py` - One-line tz-naive normalize for `actual_entry_time` vs daily index (exposed after clean runner; not a trading-rule change).
- `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - Updated.

### Tests/checks run

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

Result: **384 passed in 101.72s**, `All tests passed.`, no teardown errors.

### Safety confirmation

No trading, scoring, broker, paper, live, demo, or API-key changes beyond test infrastructure and one datetime comparison normalize in outcome follow-up.

### Next recommended task

Run `watch --max-cycles 1` during market hours and validate V15 intraday trigger simulation on live 5Min bars.

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
