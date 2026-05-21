# Agent State / Handoff Log

_Last updated: 2026-05-20_

Use this file so Codex, Claude, Cursor, or any other agent can continue from the same context when the user switches because of usage limits.

---

## V33 handoff - Better Skipped And Not-Scored Reasons

### Current active task

V33 is complete. Scan coverage reporting now uses more granular skip/not-scored reason categories instead of collapsing everything into broad buckets. No scoring, trigger, rotation, or trading behavior changes.

### Changes

- **`src/trading_bot/cli.py`**
  - Expanded `SCAN_SKIP_REASON_KEYS` from 6 to 11 keys: added `not_enough_bars`, `avg_volume_below_minimum`, `stale_data`, `no_eligible_setup`, `duplicate_tracked`. Old keys kept for backward compat.
  - Added `_SKIP_REASON_LABELS` dict mapping each key to a human-readable label for print/markdown output.
  - `run_scan()` loop:
    - Bar-count skip (`len(data) < 60`) now uses `not_enough_bars` instead of `not_enough_data`.
    - Liquidity check split: `avg_volume_below_minimum` when avg share volume fails; `liquidity_below_minimums` when dollar volume fails.
    - After scoring loop: counts symbols with weak/invalid setup_category (`Weak / Avoid`, `Overextended / Wait`, `Invalid Trade Plan`, `Insufficient Data`) → `no_eligible_setup`.
    - After Alpaca provider block: counts `provider.stale_symbols` → `stale_data` in skip_reason_counts and scan summary.
  - `_build_scan_coverage_summary()`: aggregates new keys; backward compat folds old `not_enough_data` payloads into `not_enough_bars`.
  - `_print_scan_coverage_summary()`: uses `_SKIP_REASON_LABELS` for human-readable output; omits zero-value backward-compat keys unless non-zero.
  - `_build_eod_report_markdown()`: uses `_SKIP_REASON_LABELS` for labeled markdown skip-reason list.

- **`tests/test_outcome_analytics.py`**
  - Updated `test_after_market_review_markdown_includes_scan_coverage_section` to match new label format.
  - Added 6 V33 tests: new keys in output, backward compat `not_enough_data` folding, unknown fallback, missing/quarantine specific reasons, labels in markdown, empty fallback all-zero.

### Files changed

- `src/trading_bot/cli.py`
- `tests/test_outcome_analytics.py`
- `AGENT_STATE.md`

### Tests/checks run

- `pytest -x -q -k "scan_coverage or skip_reason or v33"` → **12 passed**
- `pytest -x -q` → running

### Safety

No scoring changes. No trigger-rule changes. No rotation changes. No trading/paper/broker/orders. No demo data. No data deletion. No dashboard visual changes. The scan loop changes only affect which skip-reason bucket a symbol lands in — which symbols are scored is unchanged.

---

## V34A handoff - Terminal Outcome Model Fields

### Current active task

V34A is complete. Backend/model helpers for terminal exit price and final research P/L are added without changing dashboard layout or visuals.

### Changes

- **`src/trading_bot/snapshots/active_tracking.py`**
  - Added `compute_terminal_outcome_fields(snapshot: dict) -> dict` — pure helper that computes terminal outcome fields from any snapshot dict.
  - Returns: `is_terminal_outcome`, `terminal_exit_price`, `terminal_exit_reason`, `terminal_research_pl_pct`, `terminal_exit_price_note`.
  - `stop_hit` (tracking_status or outcome_label): exit price from `current_stop_price` → `original_stop_price` → `stop`.
  - `target_hit` (tracking_status or outcome_label): exit price from `current_target_price` → `original_target_price` → `target`.
  - Other closed states: exit price from `current_price` → `intraday_close` → `close` with inferred note.
  - Active positions and `insufficient_future_data` → `is_terminal_outcome=False`.
  - P/L = `(exit_price - original_entry_price) / original_entry_price * 100` (None when exit price unavailable).

- **`src/trading_bot/snapshots/__init__.py`**
  - Exported `compute_terminal_outcome_fields`.

- **`src/trading_bot/analytics/outcomes.py`**
  - Added `build_terminal_outcome_summary(rows: pd.DataFrame) -> dict` — aggregates per-row terminal fields into a summary with stop_hit, target_hit, other_closed groups, avg P/L, positive/negative counts, inferred_exit_price_count.
  - Added `OutcomeAnalytics.terminal_outcome_summary()` delegation method.

- **`src/trading_bot/analytics/__init__.py`**
  - Exported `build_terminal_outcome_summary`.

- **`src/trading_bot/cli.py`**
  - Imported `build_terminal_outcome_summary`.
  - `run_eod_report()`: calls `build_terminal_outcome_summary(prepared)` and includes `terminal_outcome_summary` in return dict.

- **`tests/test_v15_8_active_tracking.py`**
  - Added `TestTerminalOutcomeFields` class with 12 tests: stop_hit exit price, stop P/L, target_hit exit price, target P/L, active not terminal, insufficient_future_data not terminal, other closed inferred price, missing exit price note, stop_before_target, target_before_stop, current > original stop preference, current > original target preference, no broker/order fields.

- **`tests/test_outcome_analytics.py`**
  - Imported `build_terminal_outcome_summary` and `pytest`.
  - Added 7 V34A tests: empty df, stop P/L, target P/L, active excluded, insufficient excluded, inferred exit counted, EOD return dict includes key.

### Files changed

- `src/trading_bot/snapshots/active_tracking.py`
- `src/trading_bot/snapshots/__init__.py`
- `src/trading_bot/analytics/outcomes.py`
- `src/trading_bot/analytics/__init__.py`
- `src/trading_bot/cli.py`
- `tests/test_v15_8_active_tracking.py`
- `tests/test_outcome_analytics.py`
- `AGENT_STATE.md`

### Tests/checks run

- `pytest tests/test_v15_8_active_tracking.py tests/test_outcome_analytics.py -x -q` → **147 passed**
- `pytest -x -q` → running

### Safety

No dashboard visual changes (app.py and theme.py untouched). No scoring changes. No trigger-rule changes. No trading/paper/broker/orders. No demo data. No data deletion. No position-ledger filtering changes. Terminal P/L is research-only and uses stored stop/target levels, not actual filled prices.

---

## V31 handoff - Discovery Rotation Diagnostics

### Current active task

V31 is complete. `eod-report` and after-market review now include a research-only discovery rotation diagnostics section that measures whether Tony is rotating through the expanded universe or repeatedly scanning the same symbols.

### Changes

- **`src/trading_bot/analytics/outcomes.py`**
  - Added `build_rotation_diagnostics(scan_results_today, *, configured_universe_size, active_symbols, core_symbols, rotation_bucket_summary)` standalone function.
  - Returns: `note`, `unique_symbols_scanned`, `total_scan_appearances`, `repeat_scan_count`, `top_repeated_symbols` (symbol/scan_count/universe_role/repeat_label), `active_core_repeats`, `estimated_fresh_discovery`, `percent_universe_touched`, `rotation_bucket_summary`, `symbols_never_scanned_today`.
  - Active/core symbols labeled "expected (active/core)" in `repeat_label`; discovery repeats are not.
  - Added `OutcomeAnalytics.rotation_diagnostics()` delegation method.

- **`src/trading_bot/analytics/__init__.py`**
  - Added `build_rotation_diagnostics` to imports and `__all__`.

- **`src/trading_bot/cli.py`**
  - Added `build_rotation_diagnostics` to analytics import.
  - In `_build_scan_coverage_summary()`: calls `build_rotation_diagnostics()` and includes `rotation_diagnostics` in the returned dict.
  - Added `_print_rotation_diagnostics(diag)` helper.
  - In `_print_scan_coverage_summary()`: calls `_print_rotation_diagnostics()`.
  - In `_build_eod_report_markdown()`: added "### Discovery Rotation Diagnostics" subsection.

- **`tests/test_v31_rotation_diagnostics.py`** (new file, 17 tests)
  - 14 pure unit tests: empty df, no symbol column, unique count, repeat count, no repeats, fallback, no universe_role, active labeled expected, core labeled expected, discovery not expected, active_core_repeats empty, percent universe, percent none, note always present.
  - 3 integration tests using `_make_test_db` + `_patch_eod` helpers.

### Files changed

- `src/trading_bot/analytics/outcomes.py`
- `src/trading_bot/analytics/__init__.py`
- `src/trading_bot/cli.py`
- `tests/test_v31_rotation_diagnostics.py` (new)
- `tests/test_outcome_analytics.py` (import added)
- `AGENT_STATE.md`

### Tests/checks run

- `pytest tests/test_v31_rotation_diagnostics.py -x -q` → **17 passed**
- `pytest -x -q` → **691 passed**

### Safety

No scoring changes, no trigger-rule changes, no rotation-behavior changes, no broker/paper/live execution, no orders, no demo-data inclusion in active analytics, no dashboard visual changes, no data deletion. This is additive reporting only.

### Next recommended step

Collect real market days with the rotation diagnostics in EOD output to calibrate repeat thresholds before acting on them.

---

## V30 handoff - Safe Universe Expansion To 300-500 Symbols

### Current active task

V30 is complete. Tony's active research universe has been expanded in a staged, liquid-first way so scan coverage can increase without changing scoring rules, trigger rules, quarantine behavior, or trading execution behavior.

### Changes

- **`config/universe_swing_research_config.yaml`**
  - Added a staged liquid expansion batch made up of major sector ETFs plus liquid, actively traded common stocks across technology, financials, healthcare, industrials, energy, consumer, communication, real estate, and utilities.
  - Kept existing core/watchlist/priority symbols intact.
  - Left known bad symbols in the universe file so no data was deleted, but quarantine behavior still excludes them from real-data-only product flow.
  - Added notes clarifying that this is a staged expansion before a broader screener funnel and not a jump to thousands of symbols.
  - Raised `filters.max_universe_size` from `200` to `350`.

- **`config/default_config.yaml`**
  - Raised `max_symbols` from `100` to `175` so the expanded universe can actually increase scan coverage while still staying within the existing Alpaca/watch rotation caps.
  - Added a short note that this remains a staged pre-screener expansion.

- **`tests/test_universe.py`**
  - Updated production-universe expectations to the new size band.
  - Added coverage that default-config quarantine still removes `HCP`, `SAMSF`, `SMAR`, and `SQ` from real-data-only flow.
  - Added coverage that larger-universe rotation still respects the cycle cap, preserves core symbols first, and carries open/previous-priority symbols without duplicates.

### Current size

- Previous configured universe load: `171` symbols (`168` non-excluded)
- New configured universe load: `349` symbols (`346` non-excluded)
- Default scan cap now: `175` symbols per scan

### Files changed

- `config/default_config.yaml`
- `config/universe_swing_research_config.yaml`
- `tests/test_universe.py`
- `AGENT_STATE.md`

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` -> **674 passed**
- `git diff --check` -> passed (CRLF normalization warnings only)

### Safety

No scoring changes, no trigger-rule changes, no broker/paper/live/order changes, no quarantine removal, no data deletion, no demo data additions, and no dashboard visual changes. This is a staged universe/config expansion only.

### Next recommended step

Review a few live scan-coverage reports with the larger rotation pool before considering any further expansion beyond `350` or moving toward a full-market screener funnel.

---

## V29 handoff - Scan Coverage And Scoring Funnel Report

### Current active task

V29 is complete. `eod-report` and after-market review output now include a research-only scan coverage and scoring funnel section built from stored scan run data and Tony event payloads.

### Changes

- **`src/trading_bot/cli.py`**
  - `run_scan()` now records additive reporting metadata in the existing scan summary payload only: selected symbol list, scored symbol list, real-data symbol count, and best-available skip-reason counts.
  - Added scan-coverage helpers that aggregate latest-run funnel counts plus same-day unique coverage, batch/API usage, rotation bucket summary, and best-available skip reasons from stored scan/watch data.
  - `run_eod_report()` now prints a `Scan coverage and funnel:` section and returns `scan_coverage` in the result payload.
  - After-market markdown output now includes a `Scan Coverage And Funnel` section when coverage data is present.

- **`src/trading_bot/storage/repositories.py`**
  - Added recent scan-run listing and scan-results-by-run-id helpers so EOD reporting can aggregate today’s scan coverage without changing scan logic.

- **`tests/test_outcome_analytics.py`**
  - Added V29 coverage for coverage summary counts, not-scored count, missing/quarantine counts, percent-coverage fallback, skip-reason fallback, and markdown/EOD output presence.

### Files changed

- `src/trading_bot/cli.py`
- `src/trading_bot/storage/repositories.py`
- `tests/test_outcome_analytics.py`
- `AGENT_STATE.md`

### Safety

No scoring changes, no trigger-rule changes, no rotation-behavior changes, no broker/paper/live execution changes, no orders, no demo-data inclusion in active analytics, no dashboard visual changes, and no data deletion. This is additive reporting only.

### Next recommended step

Collect a few real market days with the new additive scan summary payloads so the coverage funnel and skip-reason counts can be reviewed on live data before considering any rotation or universe changes.

---

## V28 handoff - Tony Signal Scorecard

### Current active task

V28 is complete. Outcome analytics and `eod-report` now build a research-only Tony Signal Scorecard from existing stored real-only snapshot fields so future outcome attribution can be reviewed without changing scoring or trigger logic.

### Changes

- **`src/trading_bot/analytics/outcomes.py`**
  - Added `build_signal_scorecard()` plus `OutcomeAnalytics.signal_scorecard()`.
  - Scorecard groups existing stored signals by signal value and reports: `total_rows`, `triggered_rows`, `active_rows`, `conclusive_rows`, `target_hits`, `stop_hits`, `partial_moves`, and `insufficient_future_data`.
  - Included signal dimensions from existing data only: `setup_category`, above/below VWAP, opening-range breakout/breakdown, volume signal, ATR risk, market context, risk/reward bucket, reassessment label, score bucket, and universe role.
  - Added `SIGNAL_NOT_STORED` fallback for rows where a signal was not stored.
  - `insufficient_future_data` is counted as pending and excluded from conclusive/stop outcomes.

- **`src/trading_bot/cli.py`**
  - `run_outcome_analytics()` now prints and returns the Signal Scorecard.
  - `run_eod_report()` now prints an `Signal Scorecard:` section and returns it in the result payload.
  - After-market EOD markdown builder includes a Signal Scorecard section when present.

- **`tests/test_outcome_analytics.py`**
  - Added V28 coverage for sample signal rows, missing-signal fallback, real-only filtering, pending `insufficient_future_data`, and EOD signal-scorecard output.

### Files changed

- `src/trading_bot/analytics/__init__.py`
- `src/trading_bot/analytics/outcomes.py`
- `src/trading_bot/cli.py`
- `tests/test_outcome_analytics.py`

### Safety

No scoring changes, no trigger-rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion in active analytics, no dashboard visual changes, and no data deletion. Signal attribution is explicitly labeled preliminary and research-only.

### Next recommended step

Collect more real-only market days before using any signal-count differences for judgment. This pass is reporting only.

---

## V27A handoff - Restore V26D Ledger/Product Filters After V27 Visual Redesign

### Current active task

V27A is complete. V27 committed its helpers.py from the pre-V26A baseline, silently dropping all data integrity fixes. V27A re-applies all V26A-D fixes on top of V27 visual design without touching the render/theme layer.

### Regression cause

The V27 commit (`7a785fc`) was authored against the pre-V26A state of `helpers.py` and `app.py`. It added the unified Watchlist visual design but overwrote the V26A-D integrity fixes (DQ filters, stale lifecycle, Results ledger source, unreconciled diagnostic). The V26A-D changes had been in the working directory but were overwritten by the commit.

### Changes

**`helpers.py`**
- `_BAD_DQ_VALUES` frozenset: `{"missing_real_data", "fallback_data", "intraday_fallback_demo", "demo_data"}` (re-added)
- `_product_rows_only`: restored `used_demo_data`, `tony_data_quality_read`, `snapshot_provider` filters (HCP/SMAR/CYBR/SQ/TRUE fix)
- `_closed_results_pool`: re-added — wider pool allowing `missing_real_data` for prior-active rows
- `_is_stale_tracked_position`: re-added — detects PATH-style triggered+lost-real-data rows
- `build_stale_tracking_rows`: re-added — one stale row per prior-active symbol
- `WATCHLIST_LIFECYCLE_STATES`: re-added `stale_tracking_needs_review`
- `_LIFECYCLE_SORT_PRIORITY`: re-added — `active=0, weakening=1, stale=2, waiting=3, watching=4`
- `build_tony_watchlist_rows`: restored `quarantine_symbols` param, stale rows, lifecycle priority sort
- `_is_valid_tony_pick_row`: restored tony_analysis_version guard for priority_label
- `build_results_product_rows`: restored — active first, closed without pick_rows exclusion (PATH fix), only waiting_alert picks (no watching-only in Results)
- `collect_health_issues`: restored `stale_symbols` and `missing_tracked_symbols` params
- `find_unreconciled_tracked_symbols`: re-added — ledger gap diagnostic
- `build_pick_card_model`: restored watching-only N/A target/stop, `needed_before_entry`, updated status label

**`app.py`**
- Imports: added `build_stale_tracking_rows`, `find_unreconciled_tracked_symbols`
- `_dashboard_context`: re-added `stale_df`, `stale_symbols_list`, `missing_tracked`; passes both to `collect_health_issues`; returns in context dict
- `render_tony_watchlist`: restored quarantine_symbols passthrough, "Stale / Needs review" filter, `stale_tracking_needs_review` lifecycle card handling
- `render_results`: restored `research_snaps` for product cards (active positions no longer disappear on "Today" period filter)
- `render_system_health`: re-added "Tracked position ledger gaps" section

**`tests/test_v27a_regression.py`** (new file, 30 tests in 7 classes)
- `TestV27ADataQualityFilters`: demo/missing/quarantine/bad-DQ/fallback-provider/used-demo hidden from Watchlist
- `TestV27APathLifecycle`: stale detection, stale in Watchlist, not silently dropped, not in Results, derive_pick_phase stays tracking
- `TestV27ALifecycleSortOrder`: active before stale, stale before watching
- `TestV27AResultsLedger`: Results not empty with active positions, active phase, watching-only excluded, active symbols match Watchlist
- `TestV27AUnreconciledDiagnostic`: gap detection, terminal outcome ignored, stale set accounted, no triggered rows
- `TestV27AHealthIssues`: stale and missing_tracked warnings, silent when no gaps
- `TestV27AWatchingOnlyCardModel`: N/A target/stop, needed_before_entry, waiting_for_trigger has real values

### What happened to PATH

PATH had `entry_triggered=1`, `tracking_status=missing_real_data`, `data_source=missing_real_data`. In V27 baseline, `_product_rows_only` excluded `data_source=missing_real_data` rows and there was no stale path — so PATH disappeared entirely. After V27A: `_closed_results_pool` allows these rows; `build_stale_tracking_rows` picks PATH up; `build_tony_watchlist_rows` includes it as `stale_tracking_needs_review`. If no stored row exists at all, `find_unreconciled_tracked_symbols` produces a Settings/System Health error.

### Tests/checks run

- `pytest tests/test_v27a_regression.py tests/test_dashboard_helpers.py tests/test_dashboard_theme.py -x -q` → **212 passed**
- `pytest -x -q` → **662 passed**

### Safety

No scoring changes, no trigger-rule changes, no config changes, no broker/paper/live execution, no orders, no data deletion. All changes are dashboard filtering and diagnostic only.

---

## V26D handoff - Results Ledger Source + Unreconciled Symbol Diagnostics

### Current active task

V26D is complete. Results tab now uses the same tracked-position ledger as Watchlist. Missing tracked symbols (PATH-style) produce a health warning instead of disappearing silently. Ledger diagnostic wired into Settings/System Health.

### Changes

- **`find_unreconciled_tracked_symbols(snapshots, *, active_symbols, stale_symbols) -> list[str]`** — new public helper in `helpers.py`. Finds `entry_triggered=1` symbols not in active or stale sets and with no terminal outcome/tracking_status. Returns sorted list of gap symbols.
- **`collect_health_issues`** — added `missing_tracked_symbols: list[str] | None = None` parameter; appends an `st.error`-level warning when any unreconciled symbols are found.
- **`app.py: _dashboard_context`** — computes `missing_tracked` via `find_unreconciled_tracked_symbols(research_snaps, active_symbols=..., stale_symbols=...)` after building stale_df; appends missing_tracked warning to health_issues; returns `missing_tracked` in context dict.
- **`app.py: render_results`** — now loads `research_snaps = _load_research_snapshots(repo)` separately from `prepared`; uses `research_snaps` for `build_active_tracking_product_rows` and `build_results_product_rows` (product cards); `prepared` used for period-filtered stats text only. Fixes Results showing 0 cards when active positions exist.
- **`app.py: render_system_health`** — added "Tracked position ledger gaps" section: `st.warning` for stale symbols, `st.error` for missing_tracked symbols.

### Tests changed/added

- New `TestV26DResultsLedgerAndDiagnostics` class with 12 tests (appended to `test_dashboard_helpers.py`).
- Import of `find_unreconciled_tracked_symbols` added to test file.

### Files changed

- `src/trading_bot/dashboard/helpers.py`
- `src/trading_bot/dashboard/app.py`
- `tests/test_dashboard_helpers.py`

### Tests/checks run

- `.venv/Scripts/python -m pytest tests/test_dashboard_helpers.py -x -q` → **205 passed**
- `.venv/Scripts/python -m pytest -x -q` → **667 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no data deletion. All changes are dashboard display/filtering and diagnostic only.

---

## V26C handoff - Position Ledger Integrity + Strict Product Filters

### Current active task

V26C is complete. Stale tracking lifecycle added, watching-only cards cleaned up, stale symbols wired into Settings/System Health.

### Changes

- **`WATCHLIST_LIFECYCLE_STATES`** — added `"stale_tracking_needs_review"`.
- **`derive_pick_phase`** — reverted V26A change: `tracking_status=missing_real_data` stays `"tracking"` (not `"closed"`). Stale symbols now appear in Watchlist, not pushed to Results.
- **`_is_stale_tracked_position`** — new private helper: True when `entry_triggered=1`, `tracking_status=missing_real_data`, and an original entry price exists.
- **`build_stale_tracking_rows`** — new public function: uses `_closed_results_pool`; returns one row per prior-active symbol with `lifecycle_state=stale_tracking_needs_review`.
- **`_LIFECYCLE_SORT_PRIORITY`** — updated: `stale_tracking_needs_review=2`, `waiting_for_trigger=3`, `watching=4`.
- **`build_tony_watchlist_rows`** — now includes stale rows (at priority 2); stale symbols excluded from the pick frame.
- **`build_pick_card_model`** — for watching-only rows (no `has_planned_entry`): `target="N/A"`, `stop="N/A"`, `risk_reward="N/A"`, `needed_before_entry="Tony has not created an actionable trigger yet."`.
- **`collect_health_issues`** — added `stale_symbols: list[str] | None = None` parameter; appends a plain-English warning listing stale symbols when present.
- **`app.py: _dashboard_context`** — builds `stale_df` and `stale_symbols_list` before `collect_health_issues`; passes `stale_symbols` to it; returns `stale_df` and `stale_symbols` in context dict.
- **`app.py: render_tony_watchlist`** — added "Stale / Needs review" to lifecycle filter dropdown; handles `stale_tracking_needs_review` using `build_tracked_setup_card_model`.

### Tests changed/added

- 6 V26A/V26B tests updated to reflect V26C contract (PATH → Watchlist stale, not Results closed).
- New `TestV26CPositionLedger` class with 16 tests.

### Files changed

- `src/trading_bot/dashboard/helpers.py`
- `src/trading_bot/dashboard/app.py`
- `tests/test_dashboard_helpers.py`

### Tests/checks run

- `.venv/Scripts/python -m pytest -x -q` → **656 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no data deletion. All changes are display/lifecycle filtering only.

---

## V26B handoff - Watchlist Ordering + Results Product Cleanup

### Current active task

V26B is complete. Watchlist ordering, Results cleanup, PATH fix, and quarantine integration are all done.

### Changes

- **`_LIFECYCLE_SORT_PRIORITY`** — new module-level dict: `{active: 0, weakening: 1, waiting_for_trigger: 2, watching: 3}`.
- **`build_tony_watchlist_rows`** — added `quarantine_symbols: set[str] | None = None` parameter; sorts by lifecycle priority first (active → weakening → waiting_for_trigger → watching), then by time descending; filters quarantined symbols from output.
- **`_is_valid_tony_pick_row`** — when `tony_analysis_version` is present in the row, also requires a non-null `tony_priority_label`. Pre-Tony rows (no `tony_analysis_version`) pass through unchanged.
- **`build_results_product_rows`** — restructured: builds closed without excluding pick_rows (fixes PATH being blocked by old pick row); only includes `waiting_alert` phase picks (with a real planned entry trigger) in Results — plain watching-only rows are excluded.
- **`app.py: render_tony_watchlist`** — now passes `quarantine_symbols` from `_dashboard_context` into `build_tony_watchlist_rows`.

### Files changed

- `src/trading_bot/dashboard/helpers.py` — `_LIFECYCLE_SORT_PRIORITY`, `build_tony_watchlist_rows` (sort + quarantine), `_is_valid_tony_pick_row` (tony_analysis_version guard), `build_results_product_rows` (PATH fix + watching-only exclusion).
- `src/trading_bot/dashboard/app.py` — quarantine_symbols passed to `build_tony_watchlist_rows`.
- `tests/test_dashboard_helpers.py` — new `TestV26BWatchlistOrderingAndResultsCleanup` class with 14 tests.

### Tests/checks run

- `.venv/Scripts/python -m pytest -x -q` → **640 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no data deletion. All changes are dashboard display/filtering only.

---

## V26A handoff - Watchlist Data Quality + Prior-Active Lifecycle + Watching-Only Label

### Current active task

V26A is complete. Three gaps from V26 are closed:
1. HCP/SMAR/CYBR/SQ/TRUE-style symbols with demo, fallback, or bad-DQ data are now excluded from Tony Watchlist.
2. PATH-style prior-active symbols (tracking_status=missing_real_data + entry_triggered=1) now appear in Results as closed rather than vanishing silently.
3. Watching-only cards (no entry trigger) now read "Watching only — no actionable trigger yet" instead of "Watching only".

### Changes

- **`_BAD_DQ_VALUES`** — new module-level frozenset: `{"missing_real_data", "fallback_data", "intraday_fallback_demo", "demo_data"}`.
- **`_product_rows_only`** — strengthened: also filters `used_demo_data=1`, bad `tony_data_quality_read`, and snapshot_provider containing "demo" or "fallback".
- **`_closed_results_pool`** — new function: wider pool for closed results; allows prior-active rows (entry_triggered=1) even if missing_real_data, but always excludes demo_generated / legacy_unknown / used_demo_data.
- **`derive_pick_phase`** — now returns `"closed"` when `tracking_status == "missing_real_data"` (in addition to the existing `"invalidated"` check), preventing data-lost active symbols from staying in tracking.
- **`_is_valid_closed_result_row`** — now uses `_effective_tracking_target()` and `_effective_tracking_stop()` instead of `row.get("target")` / `row.get("stop")`, so prior-active rows with only `original_target_price` / `original_stop_price` are accepted as valid closed results.
- **`build_closed_results_product_rows`** — now uses `_closed_results_pool` instead of `_product_rows_only` as its data pool.
- **`build_pick_card_model`** — `status` for no-trigger rows changed from `"Watching only"` to `"Watching only — no actionable trigger yet"`.

### Files changed

- `src/trading_bot/dashboard/helpers.py` — all 7 changes above.
- `tests/test_dashboard_helpers.py` — new `TestV26ADataQualityAndLifecycle` class with 16 tests.

### Tests/checks run

- `.venv/Scripts/python -m pytest -x -q` → **626 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no data deletion. All changes are dashboard display/lifecycle filtering only.

---

## V26 handoff - Position Lifecycle + Unified Watchlist + Results Filters

### Current active task

V26 is complete. Tony Picks and Active Tracking are merged into one "Tony Watchlist" tab. Symbols with `tracking_status=invalidated` now surface in Results (not silently vanish). All Results filters return correct visible cards.

### Changes

- **`WATCHLIST_LIFECYCLE_STATES`** — new tuple constant in `helpers.py`: `watching`, `waiting_for_trigger`, `active`, `weakening`, `invalidated`, `closed`, `expired`.
- **`derive_pick_phase`** — now returns `"closed"` when `tracking_status == "invalidated"` or `reassessment_label == "invalidated"`, preventing active symbols from vanishing silently.
- **`_watchlist_lifecycle_state`** — new private helper mapping a row to its lifecycle state string.
- **`build_tony_watchlist_rows`** — new public function that combines pick rows + active tracking rows into one deduped list with a `lifecycle_state` column. Active tracking wins over pick when a symbol appears in both.
- **`app.py: render_tony_watchlist`** — new render function; shows pick cards for watching/waiting rows, tracking cards for active/weakening rows; lifecycle filter dropdown.
- **`app.py: main()`** — tabs changed from 5 ("Home", "Tony Picks", "Active Tracking", "Results", "Settings") to 4 ("Home", "Tony Watchlist", "Results", "Settings / System Health").
- **`app.py: render_home`** — Home stat grid now shows "Tony Watchlist" (combined count) instead of separate "Tony Picks".

### Files changed

- `src/trading_bot/dashboard/helpers.py` — `WATCHLIST_LIFECYCLE_STATES`, `derive_pick_phase` fix, `_watchlist_lifecycle_state`, `build_tony_watchlist_rows`.
- `src/trading_bot/dashboard/app.py` — `render_tony_watchlist`, merged tab list, Home stat grid, import added.
- `tests/test_dashboard_helpers.py` — 21 new V26 tests; `build_tony_watchlist_rows` imported.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **611 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All changes are dashboard display/lifecycle only.

---

## V25 handoff - Replay Strategy Proposal

### Current active task

V25 is complete. `after-market-review` now builds and saves a research-only proposal replay that compares the current baseline replay against any approved strategy proposal. Approved never means applied.

### Changes

- **`_MIN_CONCLUSIVE_FOR_PROPOSAL_VALIDATION = 3`** — local threshold constant in `cli.py`.
- **`_build_proposal_replay(report_date, proposal, baseline_replay)`** — three paths:
  - `no_approved_suggestions`: no approved decisions exist → replay skipped.
  - `insufficient_data`: approved decisions exist but `total_conclusive == 0` → "proposal cannot be validated yet."
  - `validated` / `preliminary`: has conclusive data; attaches each approved suggestion with baseline setup rates as context. `validated=True` when `total_conclusive >= 3`.
- **`_build_proposal_replay_markdown(replay)`** — markdown with header, validation status, baseline stats + setup rates table, approved suggestions list.
- **`run_after_market_review`** — step 7: builds replay from `analytics_result["replay_summary"]` (already computed) and `proposal`; saves `proposal_replay.json` + `proposal_replay.md`; prints validation status; adds to `files_created` (now 9 total); adds `proposal_replay` to return dict.

### Files changed

- `src/trading_bot/cli.py` — `_MIN_CONCLUSIVE_FOR_PROPOSAL_VALIDATION`, `_build_proposal_replay`, `_build_proposal_replay_markdown`, updated `run_after_market_review`.
- `tests/test_outcome_analytics.py` — 7 new V25 tests + `_amr_args_v25` / `_baseline_replay_with_conclusive` helpers; 3 existing file-count assertions updated (7→9).

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **590 passed**

### Safety

No scoring changes, no trigger rule changes, no config/default_config.yaml changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. Every replay carries `research_only: True` and a `not_applied_note`. Approved does not mean applied.

---

## V24 handoff - Strategy Proposal Package

### Current active task

V24 is complete. `after-market-review` now builds and saves a research-only strategy proposal derived from approved suggestion decisions. Approved never means applied.

### Changes

- **`_next_proposed_version(current)`** — simple version bumper: "v1"→"v1.1", "v1.1"→"v1.2", "v2"→"v2.1".
- **`_build_strategy_proposal(report_date, decisions, current_version)`** — filters decisions to `status=="approved"`, computes `proposed_version` (bumped only when approved suggestions exist), returns `{current_version, proposed_version, approved_count, approved_suggestions, not_applied_note, research_only}`.
- **`_build_strategy_proposal_markdown(proposal)`** — markdown with "Strategy Proposal — YYYY-MM-DD" header, approved suggestions list, or "No strategy proposal today." when empty.
- **`run_after_market_review`** — step 6: builds proposal from loaded decisions, saves `strategy_proposal.json` + `strategy_proposal.md`, prints summary, adds to `files_created` (now 7 total), adds `strategy_proposal` to return dict.

### Files changed

- `src/trading_bot/cli.py` — `_next_proposed_version`, `_build_strategy_proposal`, `_build_strategy_proposal_markdown`, updated `run_after_market_review`.
- `tests/test_outcome_analytics.py` — 6 new V24 tests + `_approved_decisions` helper; 3 existing V21/V22 file-count tests updated (5→7).

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **583 passed**

### Safety

No scoring changes, no trigger rule changes, no config/default_config.yaml changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. Every proposal carries `research_only: True` and a `not_applied_note` stating "Approved does not mean applied."

---

## V23 handoff - Human Approval Gate

### Current active task

V23 is complete. Rule suggestions can now be marked approved, rejected, applied_later, or needs_review via `record-suggestion-decision`. Decisions are stored in `reports/suggestion_decisions.json` and reflected in the approval package on the next `after-market-review` run. Approved never means applied.

### Changes

- **`_suggestion_key(suggestion, strategy_version)`** — 12-char sha256 key for stable suggestion identification across dates.
- **`_load_suggestion_decisions(output_dir)`** — reads `reports/suggestion_decisions.json`, returns dict keyed by suggestion_key.
- **`_save_suggestion_decision(output_dir, record)`** — upserts a decision record by suggestion_key.
- **`run_record_suggestion_decision(args)`** — reads the date's `approval_package.json`, looks up suggestion at `--index` (1-based), writes decision record with `{status, decided_at, note, not_applied: True}` to `suggestion_decisions.json`. Prints "Approved does not mean applied."
- **`_build_approval_package`** — now accepts optional `decisions` dict; enriches each suggestion with `status`, `decided_at`, `decision_note`, `not_applied` from prior decisions; returns `pending_count` (needs_review only) and new `decided_count`.
- **`run_after_market_review`** — loads decisions before building the approval package so prior decisions appear in the next day's package.
- **`record-suggestion-decision` CLI command** — `--date`, `--index` (required), `--status` (required, choices: approved/rejected/needs_review/applied_later), `--note`, `--output-dir`.

### Files changed

- `src/trading_bot/cli.py` — `hashlib` import; parser entry; `_suggestion_key`, `_load_suggestion_decisions`, `_save_suggestion_decision`, `run_record_suggestion_decision`; updated `_build_approval_package`; updated `run_after_market_review`; `main()` wire-up.
- `tests/test_outcome_analytics.py` — 8 new V23 tests + `_write_approval_package` helper.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **577 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. Every decision record carries `not_applied: True`. The `not_applied_note` in the package explicitly states "Approved does not mean applied." Decisions only update the JSON ledger.

---

## V22 handoff - Approval Package

### Current active task

V22 is complete. `after-market-review` now builds and saves a research-only approval package for pending rule suggestions.

### Changes

- **`_build_approval_package(report_date, suggestions, strategy_version)`** — assembles the approval dict: filters to `needs_review` suggestions, includes `pending_count`, `not_applied_note`, `research_only: True`.
- **`_build_approval_package_markdown(report_date, package)`** — builds readable markdown with numbered suggestion entries (confidence, reason, status, version) or "No approval items today." when empty.
- **`run_after_market_review`** — extracts suggestions from `eod_result["tony_self_review"]["rule_suggestions"]`, builds package, saves `approval_package.json` + `approval_package.md`, prints summary, adds both to `files_created` (now 5 total), adds `"approval_package"` to return dict.
- No suggestions auto-applied; all remain `status: needs_review`.

### Files changed

- `src/trading_bot/cli.py` — `_build_approval_package`, `_build_approval_package_markdown`, updated `run_after_market_review`.
- `tests/test_outcome_analytics.py` — 6 new V22 tests + `_sample_eod_with_suggestions` helper; updated 2 V21 tests (file count 3→5, added approval file assertions).

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **570 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All suggestions remain `needs_review`; the `not_applied_note` field explicitly states nothing has been applied.

---

## V21B handoff - Report Cleanup Consistency

### Current active task

V21B is complete. EOD/report wording now clearly separates raw rows, deduped positions, conclusive outcomes, and future-pending rows. NaN values render as N/A in tables. Negative conclusive count is prevented.

### Changes

- **`outcomes.py: build_tony_self_review`**
  - `conclusive = max(0, triggered - insufficient)` — prevents a negative count when insufficient > triggered due to data anomalies.
  - "conclusive row(s)" in needs_more_data → "rows with a finalized outcome" (clearer: this is triggered-minus-insufficient, not the rate-eligible conclusive set).
  - `{insufficient_count} triggered row(s) labeled insufficient_future_data` → `{insufficient_count} row(s) labeled insufficient_future_data` (not all of these are triggered; the label applies to the outcome window, not the trigger state).

- **`cli.py: _print_dataframe`** — `data.fillna("N/A").to_string()` replaces NaN with N/A in all report tables.

- **`cli.py: run_eod_report`**
  - Added `"Raw rows = full stored history; product rows = deduped, current-state-only view."` to the reconciliation section header.
  - Expanded data-quality notes with a row-type guide:
    - `raw rows` = all stored candidate snapshot history
    - `product rows` = deduped, current-state-only view
    - `insufficient_future_data` = outcome window still open, not a failure
    - `conclusive rows` = rows eligible for target/stop/partial/failure rate calculations

### Files changed

- `src/trading_bot/analytics/outcomes.py` — `build_tony_self_review`: `max(0, ...)` guard, wording fixes.
- `src/trading_bot/cli.py` — `_print_dataframe` NaN fix; EOD reconciliation note; data-quality row-type guide.
- `tests/test_outcome_analytics.py` — 5 new V21B tests.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **564 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All changes are display/wording only.

---

## V21A handoff - After-Hours Review Guard

### Current active task

V21A is complete. `after-market-review` now detects whether the current ET time is within regular market hours (9:30–16:00 weekdays) and skips live snapshot refresh by default when outside, preventing stale intraday loops.

### Changes

- **`_is_within_regular_market_hours(now=None)`** — new helper in `cli.py`. Returns True only for weekday 9:30–16:00 ET. No holiday calendar; weekends always treated as outside.
- **`after-market-review`** guard logic (priority order):
  1. `--skip-update-snapshots` → always skip (unchanged)
  2. `--force-update-snapshots` → always run, even outside hours
  3. Outside market hours → skip + print `"Outside market hours; skipping live snapshot refresh. Using stored close/tracking data."`
  4. Inside market hours → run normally
- Return dict gains `market_hours_active` and `snapshot_refresh_ran` for testability.
- `--force-update-snapshots` flag added to `after-market-review` parser.
- `update-snapshots` command behavior is **unchanged**.

### Files changed

- `src/trading_bot/cli.py` — `after-market-review` parser (`--force-update-snapshots`); `_is_within_regular_market_hours`; updated guard in `run_after_market_review`.
- `tests/test_outcome_analytics.py` — 10 new V21A tests (outside-hours skip, force override, inside-hours normal, skip-flag priority, report files still created, helper unit tests).

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **559 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. The guard only controls whether `update-snapshots` is called; the EOD report and analytics always run.

---

## V21 handoff - After-Market Review Package

### Current active task

V21 is complete. A single `after-market-review` CLI command now runs the full post-session review in one step: update-snapshots → EOD report → real-only outcome analytics → save reports to `reports/YYYY-MM-DD/`.

### Changes

- **`after-market-review` CLI command** added to `build_parser()` with `--config`, `--date`, `--skip-update-snapshots`, `--output-dir` flags.
- **`run_after_market_review(args)`** — calls `run_update_snapshots`, `run_eod_report`, and `run_outcome_analytics` in sequence; saves three files:
  - `eod_report.json` — full EOD report return dict (includes memory, self-review, suggestions, strategy version, replay, reconciliation)
  - `eod_report.md` — formatted markdown built from the return dict
  - `outcome_analytics.json` — slim outcome analytics return dict
  - Prints file paths to stdout.
- **`_build_eod_report_markdown(report_date, eod)`** — builds human-readable markdown from the eod-report dict; sections: Operational Summary, EOD Reconciliation, Tony Self-Review, Rule Suggestions, Strategy Version, Replay Summary.
- Uses America/New_York market date by default; `--date` overrides.
- Real-only filtering is always enforced for `outcome-analytics` step.
- Suggestions remain `status: needs_review` — nothing is auto-applied.

### Files changed

- `src/trading_bot/cli.py` — `after-market-review` parser; `run_after_market_review`; `_build_eod_report_markdown`; `main()` wire-up.
- `tests/test_outcome_analytics.py` — 8 new V21 tests + `_sample_eod_result()` helper.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **549 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All suggestions remain `needs_review` and are never auto-applied. Report files are read-only JSON/markdown artifacts.

---

## V20 handoff - Backtest Replay Foundation

### Current active task

V20 is complete. `eod-report` now prints a research-only replay summary that groups real-only outcome rows by setup_category and reports triggered/target/stop/partial/insufficient counts with rates computed on conclusive rows only.

### Changes

- **`build_replay_summary(rows, strategy_version)`** — new standalone function in `outcomes.py`. Groups by `setup_category`, computes per-setup counts and rates (target_rate, stop_rate on conclusive rows only). Flags `insufficient_future_data` rows in notes without treating them as failures. Returns `strategy_version`, `total_rows`, `total_triggered`, `total_conclusive`, `total_insufficient_future_data`, `setups` list, `notes` list.
- **`_empty_replay_summary(strategy_version)`** — zero-value fallback for empty input.
- **`OutcomeAnalytics.replay_summary(strategy_version)`** — convenience method on the dataclass.
- **`eod-report`** prints a "Replay summary" section and includes `replay_summary` in the return dict.

### Files changed

- `src/trading_bot/analytics/outcomes.py` — `build_replay_summary`, `_empty_replay_summary`, `replay_summary()` method.
- `src/trading_bot/analytics/__init__.py` — exported `build_replay_summary`.
- `src/trading_bot/cli.py` — imported `build_replay_summary`; replay print section in `run_eod_report`; added `"replay_summary": replay` to return dict.
- `tests/test_outcome_analytics.py` — imported `build_replay_summary`; 6 new V20 tests.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **541 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. Replay is strictly read-only and rates are never auto-applied.

---

## V19 handoff - Strategy Versioning Foundation

### Current active task

V19 is complete. Rule suggestions now carry a strategy version label and a full strategy version report is included in the EOD report output and return dict.

### Changes

- **`CURRENT_STRATEGY_VERSION = "v1"`** and **`SUGGESTION_STATUSES`** constants added to `outcomes.py`.
- **`generate_tony_rule_suggestions()`** now accepts an optional `strategy_version` parameter (defaults to `CURRENT_STRATEGY_VERSION`). Every suggestion dict includes `"strategy_version"`.
- **`build_strategy_version_report(suggestions, version)`** — new function that returns `current_version`, `pending_suggestions`, `status_counts`, the full suggestions list, and a plain-English note. Never auto-applies anything.
- **`eod-report`** prints a "Strategy version" section (version, pending suggestion count, status breakdown, note) and includes `strategy_version_report` in the return dict.

### Files changed

- `src/trading_bot/analytics/outcomes.py` — constants, `generate_tony_rule_suggestions` signature, `build_strategy_version_report`, `_no_data_suggestion` updated.
- `src/trading_bot/analytics/__init__.py` — exported `CURRENT_STRATEGY_VERSION`, `SUGGESTION_STATUSES`, `build_strategy_version_report`.
- `src/trading_bot/cli.py` — imported new symbols; strategy version print + return in `run_eod_report`.
- `tests/test_outcome_analytics.py` — imported new symbols; 6 new V19 tests.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` → **39 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **535 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All suggestions remain `status: needs_review` and are never auto-applied.

## V18A handoff - Active vs Future Outcome Wording

### Current active task

V18A is complete. Tony self-review and EOD report now correctly distinguish same-day active tracking from future outcome windows.

### Changes

- **`build_tony_self_review`**: `tomorrow_watch` now uses the reconciliation `deduped_active_positions` for the carry-over count (one per symbol), while the raw active row count from tracking data drives the note trigger. Raw triggered rows are exposed separately. `insufficient_future_data` rows are now called out in `needs_more_data` as "outcome windows are still open; these are not failures" rather than silently disappearing. Added same-day summary fields: `active_symbols`, `deduped_active_positions`, `raw_triggered_rows`, `waiting_picks`, `pending_triggers`.
- **`generate_tony_rule_suggestions`**: Now excludes `insufficient_future_data` rows from rate calculations. Only rows with conclusive outcomes (target/stop/partial/failure) count toward the denominator. If not enough conclusive rows exist, the no-data fallback message explains how many are still waiting.
- **`eod-report` self-review print section**: Added "Same-day summary" block showing deduped active positions, active symbols, waiting picks, raw triggered rows, and pending triggers.
- **`_empty_self_review`**: Added the new summary fields with zero defaults.

### Files changed

- `src/trading_bot/analytics/outcomes.py` — `build_tony_self_review`, `generate_tony_rule_suggestions`, `_empty_self_review`.
- `src/trading_bot/cli.py` — self-review print section in `run_eod_report`.
- `tests/test_outcome_analytics.py` — 4 new V18A tests.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` → **33 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **529 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion.

## V16B handoff - Date Consistency for Reports

### Current active task

V16B is complete. `eod-report` and `outcome-analytics` now use the same America/New_York market-date filtering everywhere.

- **`outcome-analytics --date YYYY-MM-DD`** added. Filters snapshots by ET market date. Prints `Report date: YYYY-MM-DD America/New_York`. Overrides `--today` when both are given.
- **`eod-report --date` watch-run scoping fixed.** Previously used `latest_watch_run()` (globally newest), which caused cross-date contamination. Now uses `_watch_run_summary_for_date()` to filter recent watch runs by ET `started_at` date and sum `cycles_completed` across all runs on that date. A date with no watch runs correctly reports 0 cycles.
- **`run_outcome_analytics` now returns a dict** (`snapshots_reviewed`, `symbols`, `date_filter`) for testability.

### Files changed

- `src/trading_bot/storage/repositories.py` — added `recent_watch_runs(limit=100)`.
- `src/trading_bot/cli.py` — added `--date` to `outcome-analytics` argparser; updated `run_outcome_analytics` to handle `--date`, apply the ET mask post-`prepared()`, print date header, return result dict; added `_watch_run_summary_for_date()` helper; replaced `repo.latest_watch_run()` in `run_eod_report` with the date-scoped helper.
- `tests/test_outcome_analytics.py` — added `_make_dummy_tony()` helper and 4 new V16B tests.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` → **29 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **525 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion. Stored timestamps remain UTC.

## V18 handoff - Tony Rule Suggestions

### Current active task

V18 is complete. Tony self-review now includes `rule_suggestions` — plain-English research-only scoring/filter ideas derived from real-only outcome rows. Suggestions are never applied automatically; each carries a confidence level (`low`/`medium`/`high`) and `status: needs_review`. A no-data fallback is returned when fewer than 3 triggered rows exist. The `eod-report` prints suggestions under "Rule suggestions (research-only, not applied automatically)". Suggestions are stored inside the Tony learning event payload alongside the memory summary.

### Files changed

- `src/trading_bot/analytics/outcomes.py` — added `generate_tony_rule_suggestions()`, `_no_data_suggestion()`, `_MIN_TRIGGERED_FOR_SUGGESTION`; added `rule_suggestions` field to `build_tony_self_review()` return and `_empty_self_review()`.
- `src/trading_bot/analytics/__init__.py` — exported `generate_tony_rule_suggestions`.
- `src/trading_bot/cli.py` — `eod-report` prints rule suggestions with confidence label and reason.
- `tests/test_outcome_analytics.py` — imported `generate_tony_rule_suggestions`; added 5 new tests.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` → **25 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **521 passed**

### Suggestion logic

| Condition | Suggestion | Confidence |
|-----------|-----------|------------|
| Triggered < 3 (total) | No rule changes suggested yet | low |
| Setup target_rate ≥ 67%, triggered ≥ 2 | Consider prioritizing that setup | medium (high if ≥ 5 rows and ≥ 80%) |
| Setup stop_rate ≥ 67%, triggered ≥ 2 | Consider raising score threshold / reducing frequency | medium (high if ≥ 5 rows and ≥ 80%) |
| No setup meets threshold | Patterns not consistent enough | low |

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion. Suggestions have `status: needs_review` and are never auto-applied.

## V17 handoff - Tony Self-Review Report

### Current active task

V17 is complete. `eod-report` now prints a plain-English Tony self-review section after the Tony memory summary. The self-review is derived from real-only outcome rows using V16 memory summary data and V15.9 reassessment labels. It covers: strongest setup, weakest setup, what worked, what failed, what needs more data, and tomorrow watch notes. The self-review is also stored in the Tony learning event payload inside `memory_summary.self_review`.

### Files changed

- `src/trading_bot/analytics/outcomes.py` — added `build_tony_self_review()` standalone function and `_empty_self_review()` helper; added `tony_self_review()` method on `OutcomeAnalytics`.
- `src/trading_bot/analytics/__init__.py` — exported `build_tony_self_review`.
- `src/trading_bot/cli.py` — imported `build_tony_self_review`; `eod-report` now computes and prints the self-review section; includes `tony_self_review` in the return payload; stores self-review inside the Tony learning event `memory_summary` payload.
- `tests/test_outcome_analytics.py` — imported `build_tony_self_review`; added four new tests: `test_tony_self_review_from_sample_rows`, `test_tony_self_review_empty_day_fallback`, `test_tony_self_review_real_only_filtering`, `test_eod_report_includes_self_review`.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` → **20 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **516 passed**

### Self-review output structure

```
Tony self-review:
  Research only. No scoring changes. No trigger changes. No trading behavior changes.
  Strongest setup: <best_setup_note from V16 memory>
  Weakest setup: <worst_setup_note from V16 memory>
  What worked:
    - <setup>: N target hit(s)... out of N triggered row(s).
  What failed:
    - <setup>: N stop or failure outcome(s) out of N triggered row(s).
  What needs more data:
    - <setup>: only N row(s) today — not enough context to read direction.
    - <setup>: reassessment flagged as needs_review — check current conditions.
  Tomorrow watch:
    - N active position(s) carry over — check reassessment labels at next open.
    - N pending trigger(s) still waiting — watch for intraday trigger levels.
    - N setup(s) flagged weakening — monitor for further deterioration.
```

### Known limitations

- Strongest/weakest setup notes are derived from the same `_best_worst_setup_notes` logic introduced in V16 and are only as meaningful as the current day's real-only sample size.
- The self-review is stored inside `memory_summary.self_review` in the Tony learning event payload, not in a separate dedicated field.

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion.

## V16A handoff - Market-Date Fix

### Current active task

V16A is complete. `eod-report`, `outcome-analytics --today`, and the daily Tony memory summary now use the America/New_York market date by default instead of the UTC calendar date.

### Root cause

Daily reporting code was mixing UTC-date string slicing with local-market expectations. That caused after-hours or near-midnight UTC rows to fall onto the wrong “today” bucket for `eod-report`, `outcome-analytics --today`, and the Tony memory summary.

### Files changed

- `src/trading_bot/analytics/outcomes.py` - added ET market-date helpers and switched `today=True` filtering from UTC date slicing to parsed America/New_York market-date matching.
- `src/trading_bot/analytics/__init__.py` - exported the ET market-date helpers.
- `src/trading_bot/cli.py` - `eod-report` now defaults to the ET market date, filters snapshots/events/update timestamps by ET market date, keeps explicit `--date` overrides, and prints `Report date: YYYY-MM-DD America/New_York`.
- `tests/test_outcome_analytics.py` - added ET boundary coverage, `eod-report` default-date coverage, explicit override coverage, and Tony memory date-alignment coverage.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v16a_outcomes` -> **16 passed**

### Known limitations

- This change only updates daily filtering/report semantics. Stored timestamps remain UTC and existing raw history is unchanged.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion.

## V16 handoff - Tony Memory Engine Foundation

### Current active task

V16 is complete. `eod-report` now builds a daily Tony memory summary from real-only outcome rows and stores the same research-only summary in the existing Tony learning event payload for later review.

### Root cause

Tony already stored raw outcome rows and could print grouped analytics, but there was no compact daily research memory artifact summarizing what triggered, what stayed active vs closed, what hit target/stop/partial outcomes, how reassessment labels were distributed, and what data-quality exclusions shaped that view.

### Files changed

- `src/trading_bot/analytics/outcomes.py` - added `daily_tony_memory_summary()` / `build_daily_tony_memory_summary()` plus setup, triggered, active/closed, reassessment, best/worst, and data-quality summary helpers.
- `src/trading_bot/analytics/__init__.py` - exported the new daily memory summary helper.
- `src/trading_bot/cli.py` - `eod-report` now prints a Tony memory summary section, returns it in the report payload, and stores it through the existing Tony learning event path; outcome-analytics learning events now also carry the same summary payload when applicable.
- `src/trading_bot/storage/database.py` - made additive migration loops idempotent against already-present columns so local DB initialization no longer fails on duplicate-column retries.
- `src/trading_bot/tony/events.py` - extended `record_tony_learning_updated()` payload to accept an optional `memory_summary`.
- `src/trading_bot/dashboard/helpers.py` - fixed boolean-index alignment when product filtering receives non-contiguous snapshot indexes.
- `tests/test_outcome_analytics.py` - added daily memory summary coverage for counts, real-only filtering, demo/legacy exclusion, reassessment rollups, raw-history-preserved notes, and no-deletion behavior.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v16_outcomes` -> **13 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v16_outcomes_fix` -> **13 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py -q --basetemp .pytest_tmp_v16_dashboard_helpers` -> **128 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` -> **509 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli eod-report --config config/default_config.yaml` -> succeeded
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml --real-only --today` -> succeeded

### Known limitations

- Best/worst setup notes are intentionally labeled preliminary and are only as useful as the current day’s real-only sample size.
- The memory summary is stored in the existing Tony event/reporting path, not in a new dedicated memory table.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion in Tony memory, no active-entry rewrites, and no raw-history deletion.

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
