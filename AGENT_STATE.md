# Agent State / Handoff Log

_Last updated: 2026-05-17_

Use this file so Codex, Claude, Cursor, or any other agent can continue from the same context when the user switches because of usage limits.

---

## V11 handoff — Dashboard Command Center UX

### Current active task

V11 complete. Dashboard Command Center built. 230 tests pass.

### Last agent used

Claude (claude-sonnet-4-6) via Claude Code.

### Files changed in V11

- `src/trading_bot/dashboard/helpers.py` — NEW. Pure, Streamlit-free helper functions for testing: `event_age_label()`, `is_fallback_provider()`, `filter_events_by_type()`, `latest_event_of_type()`, `is_current_cycle_event()`, `count_hypothesis_by_priority()`, `is_seeded_demo_snapshot()`, `snapshots_today_count()`.
- `src/trading_bot/dashboard/app.py` — Added:
  - Import of helpers module
  - `_cc_hypothesis_cards()` — compact hypothesis cards for Command Center (no buy/sell, allowed actions only)
  - `render_watch_health()` — universe size, rotation stats, API/batch requests, rate-limit warnings
  - `render_data_quality_panel()` — IEX single-exchange notice, fallback/stale counts, demo banner, no key values shown
  - `render_outcome_snapshot_panel()` — snapshots today (seeded excluded), open/watch, triggered, target/stop hit
  - `render_command_center()` — new first tab: Tony status, provider, scan/watch age, symbols scanned, API requests, fallback count, rate-limit warnings, snapshots today, analyst hypothesis cards, market context, data quality one-liner, risk warning, Watch Health + Data Quality panels side-by-side, Outcome Snapshot summary
  - Updated `main()`: added "Command Center" as first tab, shifted all existing tabs up by index. Total tabs: 10.
- `tests/test_dashboard_helpers.py` — NEW. 50 tests in 9 classes: `TestEventAgeLabel`, `TestIsFallbackProvider`, `TestFilterEventsByType`, `TestLatestEventOfType`, `TestIsCurrentCycleEvent`, `TestCountHypothesisByPriority`, `TestIsSeededDemoSnapshot`, `TestCurrentVsHistoricalSeparation`, `TestNoBrokerBehavior`, `TestSnapshotsTodayCount`.

### Tests/checks run in V11

- `pytest tests/test_dashboard_helpers.py -v` — **50 passed, 0 failures**
- `pytest --tb=short -q` (full suite) — **230 passed, 0 failures, 0 errors** (up from 180)

### Known issues / risks (V11)

- `render_watch_health()` pulls rotation stats from `universe_rotation_summary` event payload. If the payload schema of that event differs from what's expected (e.g., key name mismatch for `symbols_selected`), those cells will show "—". Safe fallback — no crash.
- `snapshots_today_count()` counts real snapshots created today (UTC). On days when no scan runs before midnight UTC, the count will be 0 at dashboard open even if the user thinks it's still "today" in their local timezone.
- Command Center Analyst Reads shows the 8 most recent `analyst_candidate_hypothesis` events, not necessarily from the latest scan cycle. Events are ordered by `created_at DESC` by the repo query. When the budget runs out mid-cycle, some candidates won't appear.
- `max_events_per_cycle: 25` is configured in `default_config.yaml` (increased from 20 in previous versions). If analyst reads are still getting cut off, raise further.

### Safe to continue?

Yes. 230 tests pass (0 failures, 0 errors). Command Center added as a read-only monitoring view. No broker execution, live trading, paper trades, order placement, API keys exposed, or LLM trade decisions were added. All safety constraints from V10 remain in force. Tony still says "analyst, not trader" in all UI text.

### Next recommended steps

1. Run `run_dashboard.ps1` and verify Command Center tab appears first and shows correct data.
2. Run `watch --max-cycles 1` with `config/universe_swing_research_config.yaml` to populate events, then refresh dashboard.
3. Verify hypothesis cards render correctly in Command Center — check priority icons, action labels, age labels.
4. If Analyst Reads cards are empty: confirm `max_events_per_cycle` is high enough (≥25) and `analyst_candidate_hypothesis` is in `create_events_for` list in `default_config.yaml`.
5. Consider adding outcome-to-hypothesis correlation once sufficient real-data snapshots accumulate (after several watch sessions).

---

## V10 handoff — Tony Analyst Engine Foundation

### Current active task

V10 complete. Tony Stocks analyst module built. 180 tests pass.

### Last agent used

Claude (claude-sonnet-4-6) via Claude Code.

### Files changed in V10

- `src/trading_bot/tony/analysis.py` — NEW. Deterministic analyst engine: `CandidateAnalysis` dataclass, `MarketContext` class, `analyze_candidates()` entry point. Seven private helpers: `_setup_read()`, `_volume_read()`, `_risk_read()`, `_data_quality()`, `_outcome_context()`, `_priority_and_action()`, `_build_hypothesis()`. Labels: setup_read (7 values), volume_read (5 values), risk_read (5 values), market_context_read (4 values), data_quality_read (5 values), outcome_context (4 values), priority_label (5 values). Allowed recommended_actions: `snapshot_only`, `watch_only`, `avoid`, `needs_more_data`, `reference_only`. No LLMs, no paper trades, no orders.
- `src/trading_bot/tony/events.py` — Added 4 new event methods: `record_analyst_candidate_hypothesis()`, `record_analyst_market_context()`, `record_analyst_data_quality()`, `record_analyst_risk_warning()`. Added 4 event types to `TonyConfig.create_events_for` default tuple.
- `src/trading_bot/tony/__init__.py` — Exported `CandidateAnalysis`, `MarketContext`, `analyze_candidates`.
- `src/trading_bot/cli.py` — Imported `analyze_candidates`, `MarketContext`. Wired analyst block into `run_scan()` after Alpaca events, before `tony.record_scan_completed()`. Builds benchmark_rows, candidate_rows, fallback/stale sets, loads outcome snapshots (seeded excluded), calls `analyze_candidates()`, then fires all 4 analyst events per cycle.
- `src/trading_bot/dashboard/app.py` — Updated `render_tony_stocks()`: added analyst status metric, "Analyst Reads" expander showing market context, data quality, risk warning, and candidate hypothesis events. Added real-vs-fallback event separation notice. Updated info banner to say "analyst, not trader".
- `config/default_config.yaml` — Added 4 analyst event types to `create_events_for` list.
- `tests/test_tony_analyst.py` — NEW. 59 tests in 10 test classes: `TestSetupRead`, `TestVolumeRead`, `TestRiskRead`, `TestMarketContext`, `TestDataQuality`, `TestPriorityAndAction`, `TestOutcomeContext`, `TestAnalyzeCandidates`, `TestTonyAnalystEvents`.

### Tests/checks run in V10

- `pytest` (via `run_tests.ps1`) — **180 passed, 0 failures, 0 errors** (up from 121).
- `provider-health` — PASSED. keys_present=True. 3 symbols, 0 fallback.
- `run_scanner.ps1` — 52 symbols scored. Analyst events generated:
  - `analyst_market_context`: market_supportive
  - `analyst_data_quality`: 42 candidates, 0 real IEX, 39 demo, 3 fallback, 0 stale
  - `analyst_risk_warning`: 9 candidates (wide ATR or high volatility)
  - `analyst_candidate_hypothesis`: DVN (high_priority, breakout_candidate, snapshot_only), DKNG (high_priority), OXY (high_priority), AVGO, U, RUN, SNOW, SMCI (all watch/watch_only)
- `watch --max-cycles 1` — 159 symbols, 3 API requests, 4 fallbacks, 0 rate-limit warnings.
- `tony-events --limit 30` — confirmed all 4 analyst event types present and correctly formatted.

### Known issues / risks (V10)

- `analyst_market_context` shows "SPY not in scan" when scanning from `default_config.yaml` because SPY is not in that universe's symbol list. Correct behavior — the analyst correctly reports no benchmark data. The `universe_swing_research_config.yaml` includes SPY and will show real market context.
- Analyst events created after Alpaca provider events; event budget (max_events_per_cycle=20) could run out if many provider events fire first. Tuning: increase `max_events_per_cycle` in config if analyst hypotheses are getting cut off.
- `analyst_data_quality` shows "0 real IEX" when the provider uses Alpaca IEX but all data uses demo fallback. Correct — the data_quality read tracks per-symbol quality, not provider type. Real IEX count increases once symbols aren't in fallback.
- `outcome_context` returns `not_enough_history` on first run because no real-data snapshots exist yet. This will improve once watch mode accumulates snapshots over real market sessions.

### Safe to continue?

Yes. 180 tests pass (0 failures, 0 errors). No broker execution, live trading, paper trades, order placement, API keys exposed, external notifications, or LLM trade decisions were added or changed. `recommended_action` is constrained to: snapshot_only, watch_only, avoid, needs_more_data, reference_only. Tony explicitly states "analyzing, not trading" in all hypotheses.

### Next recommended steps

1. Run `watch --max-cycles 1` with `config/universe_swing_research_config.yaml` to see analyst events with full 171-symbol universe and SPY/QQQ/IWM as benchmarks.
2. Check `tony-events --limit 30` for `analyst_market_context` with real benchmark data.
3. After accumulating real-data snapshots over several sessions, `outcome_context` will start returning `historically_positive/negative/mixed` instead of `not_enough_history`.
4. Consider adding `analyst_candidate_hypothesis` filter to the dashboard ranked view so high-priority analyst picks appear alongside scanner output.
5. Consider wiring analyst reads into the candidate_snapshots table (store `tony_hypothesis` in snapshot notes) for future outcome-to-hypothesis correlation.

---

## V9.5 handoff — Universe Expansion to 171 Symbols

### Current active task

V9.5 complete. Universe expanded from 39 to 171 symbols with full metadata. 121 tests pass.

### Last agent used

Claude (claude-sonnet-4-6) via Claude Code.

### Files changed in V9.5

- `config/universe_swing_research_config.yaml` — Expanded from 39 to 171 symbols across 14 sectors/themes: benchmarks (5), mega-cap references (13), semiconductors (9), software/cloud/SaaS (27), fintech/payments (10), consumer/e-commerce (20), healthcare/biotech (12), energy/cleantech (10), crypto-linked (5), AI/data infra (7), industrials/defense (10), financials (5), materials (4), med-tech (5), discovery pool (34). `max_universe_size: 200`. Each symbol has `name`, `universe_role`, `tags`, `sector`. Universe roles: `benchmark`, `reference`, `primary_candidate`, `speculative_candidate`, `excluded_by_default`. Tags include `watchlist_core` (9 symbols), `discovery` (34 symbols).
- `tests/test_universe.py` — Added 15 V9.5 production universe tests in 5 new classes: `TestProductionUniverseSize` (≥150 symbols, no duplicates, uppercase), `TestProductionUniverseBenchmarks` (SPY/QQQ/IWM present, roles), `TestProductionUniverseRoles` (all roles valid, ≥50 primary, ≥10 speculative), `TestProductionUniverseTags` (watchlist_core, discovery, no cross-contamination), `TestProductionUniverseRotationBudget` (core ≤50, active ≤200).
- `src/trading_bot/dashboard/app.py` — Added universe size metrics row (Universe Total, Active non-excluded, Watchlist Core, Discovery Pool) inside `render_data_provider_status()`. Added `load_universe` and `load_universe_tags` imports.
- `CURRENT_STATUS.md` — Updated to V9.5, added confirmed test results, updated next steps.
- `ROADMAP.md` — Updated Phase 2 status to V9.5 complete with detail on what was done.
- `TESTING_CHECKLIST.md` — Added production universe test area; added V9 scaling tests section; added V9 watch-mode validation section.

### Tests/checks run in V9.5

- `pytest` (via `run_tests.ps1`) — **121 passed, 0 failures, 0 errors** (up from 106).
- 15 new universe tests green: size, dedup, benchmarks, roles, tags, rotation budget.
- Universe loads 171 symbols: 5 benchmark, 13 reference, 104 primary_candidate, 46 speculative_candidate, 3 excluded_by_default.
- 9 watchlist_core symbols; 34 discovery-tagged symbols.

### Known issues / risks (V9.5)

- Dashboard universe metrics block (`render_data_provider_status`) silently skips if `universe_config_path` doesn't exist or YAML is malformed — uses bare `except Exception: pass`. This is intentional to avoid crashing the dashboard.
- Universe symbols are research/scanning universe only — not recommendations to buy or trade.
- Alpaca IEX single-exchange warning preserved in dashboard and all docs.

### Safe to continue?

Yes. 121 tests pass (0 failures, 0 errors). No broker execution, live trading, paper trades, order placement, API keys exposed, external notifications, or LLM trade decisions were added or changed.

### Next recommended steps

1. Run `watch --max-cycles 1` with real Alpaca keys to validate batch fetch at 171-symbol scale.
2. Check `tony-events --limit 30` for `batch_fetch_summary` (expect 1–2 requests), `universe_rotation_summary` (bucket_id, core/discovery counts).
3. If rate-limit warnings appear, reduce `max_symbols_per_cycle` or increase `request_sleep_seconds`.
4. Monitor rotation `bucket_id` across cycles to verify round-robin advances.

---

## V9.1 handoff — Runtime Verification Fix (pytest temp + batch limit)

### Current active task

V9.1 complete. Pytest temp cleanup fixed; batch request count reduced from 23 to 2 for 39 symbols.

### Last agent used

Claude (claude-sonnet-4-6) via Claude Code.

### Files changed in V9.1

- `scripts/run_tests.ps1` — Moved test session temp from `.pytest_tmp` (project dir, prone to Windows file-lock PermissionError) to `$env:LOCALAPPDATA\TradingBotTests\<session_id>`. Prunes stale sessions (>2h) silently. Removed `$ErrorActionPreference = "Stop"` from the script header so lock warnings don't abort the run.
- `pyproject.toml` — Added `tmp_path_retention_policy = "none"` so pytest does not try to delete old session dirs at startup (avoiding double-cleanup PermissionError).
- `src/trading_bot/data/market_data.py` — Changed batch limit in `_fetch_bars_batch` from `min(lookback_days + 60, 1000)` to `10000` (Alpaca documented max for `/v2/stocks/bars`). Root cause: Alpaca's multi-symbol endpoint interprets `limit` as total bars per page across all symbols; with limit=180 and 39 symbols × 107 bars = 4173 bars needed, that caused ~22 pagination requests. limit=10000 covers the full date range in one request.
- `tests/test_v9_scaling.py` — Added 7 new tests: `TestBatchLimitAudit` (verifies limit >= 10000 in batch params, independent single-symbol limit), `TestRequestCountMetadata` (verifies 1 HTTP call for N-symbol batch with no pagination, pagination increments both counters, reset clears all counters).

### Tests/checks run in V9.1

- `pytest` (via `run_tests.ps1`) — **106 passed, 0 failures, 0 errors** (up from 75 passed + 26 errors).
- `python -m trading_bot.cli provider-health` — PASSED. keys_present=True. 3 symbols, 0 fallback, latest bar 2026-05-15.
- `python -m trading_bot.cli scan` — 39 symbols, 23 scored, batch_fetch_summary: **2 request(s) (1 batch)** — confirmed fix.
- `python -m trading_bot.cli watch --max-cycles 1` — rotation bucket=0, 39 symbols (core=3, open=20, prev=0, discovery=16). batch_fetch_summary: **2 request(s) (1 batch)**. universe_rotation_summary recorded.
- `python -m trading_bot.cli tony-events --limit 30` — confirmed `batch_fetch_summary` shows "2 request(s) (1 batch, 0 fallback(s))" post-fix vs "23 request(s) (22 batch)" pre-fix.

### Known issues / risks (V9.1)

- `api_requests_used=2` (not 1) because SPY is filtered from `market_data` by liquidity/price, so `provider.fetch_ohlcv("SPY", ...)` is called separately after the batch as a benchmark fallback. This is expected and correct.
- Session temp dirs accumulate in `LOCALAPPDATA\TradingBotTests` until the 2-hour prune runs. On very active development sessions this is negligible (< 100MB total).
- `tmp_path_retention_policy = "none"` means pytest does not clean up after test sessions — this is intentional; the `run_tests.ps1` prune handles cleanup.

### Safe to continue?

Yes. 106 tests pass (0 failures, 0 errors). No broker execution, live trading, paper trades, order placement, API keys exposed, external notifications, or LLM trade decisions were added or changed. Alpaca IEX single-exchange warning preserved. Batch request count confirmed correct.

---

## V9 handoff — Real Data Scaling — 175 Symbols Every 5 Minutes

### Current active task

V9 complete. All 8 tasks implemented and tested.

### Last agent used

Claude (claude-sonnet-4-6) via Claude Code.

### Files changed in V9

- `config/default_config.yaml` — added `watch_universe_rotation` config block; updated `interval_minutes: 5`; updated alpaca config for batch + rate-limit settings; added `real_data_scan_scaled`, `rate_limit_warning`, `universe_rotation_summary`, `batch_fetch_summary`, `provider_fallback_summary` to Tony `create_events_for`.
- `config/universe_swing_research_config.yaml` — added IWM as benchmark symbol.
- `src/trading_bot/settings.py` — added `watch_universe_rotation: dict[str, Any] | None = None` field to `ScannerSettings`.
- `src/trading_bot/data/market_data.py` — added `RateLimiter` class (sliding 60s window, buffer%, sleep between calls); added `BATCH_URL` class constant on `AlpacaIEXProvider`; added `batch_requests_enabled`, `max_symbols_per_batch`, `stop_on_rate_limit`, `fallback_on_rate_limit`, `_rate_limiter`, `_requests_this_cycle`, `_batch_requests_this_cycle`, `_rate_limit_warnings_this_cycle` to `AlpacaIEXProvider`; added `reset_cycle_state()` reset for all cycle tracking; added `get_cycle_stats()`; added `fetch_ohlcv_batch()` (multi-symbol endpoint); added `_fetch_bars_batch()` (paginates BATCH_URL); added `_normalize_raw_bars()` (extracted helper used by both single and batch); updated `_build_alpaca_provider()` to wire RateLimiter and batch config; fixed `_normalize_raw_bars` to return empty DataFrame on empty bars.
- `src/trading_bot/data/universe_rotation.py` — new file: `RotationResult` dataclass + `WatchUniverseRotator` class (core → open snapshots → prev candidates → round-robin discovery, deduplication, max_per_cycle cap).
- `src/trading_bot/tony/events.py` — added 5 new V9 event types + record methods: `real_data_scan_scaled`, `rate_limit_warning`, `universe_rotation_summary`, `batch_fetch_summary`, `provider_fallback_summary`.
- `src/trading_bot/cli.py` — imported `RotationResult`, `WatchUniverseRotator`; fixed missing `results: list[Any] = []` initialization in `run_scan()`; updated `run_scan()` to support `override_symbols` from rotation; added batch vs per-symbol fetch path; added `skipped_count`; updated summary dict with `symbols_scanned`, `symbols_skipped`, `high_priority_symbols`, `api_requests_used`, `batch_requests_used`, `rate_limit_warnings`, `batch_mode`; updated post-scan Tony events to fire V9 events (`batch_fetch_summary`, `real_data_scan_scaled`, `provider_fallback_summary`, `rate_limit_warning`); updated `run_watch()` to initialize `WatchUniverseRotator` before the loop when enabled; wired rotation into each cycle (open snapshots → `get_cycle_symbols()` → `override_symbols` on scan_args → `update_previous_candidates()` → `record_universe_rotation_summary()`); added rotation stats to `cycle_summary`; added rotation bucket print in cycle summary output.
- `src/trading_bot/dashboard/app.py` — updated `render_data_provider_status()` to show batch mode, max RPM, rotation config (enabled, max/cycle, core max, bucket size), plus 3 new Tony event metrics: `batch_fetch_summary`, `real_data_scan_scaled`, `rate_limit_warning` counts; added rate-limit warning alert when count > 0.
- `tests/test_v9_scaling.py` — new file: 24 mocked tests covering batch normalisation, single-symbol fallback, rate limiter cap/tracking/reset/enforcement, 429 retry, universe rotation core/open/dedup/max, demo mode, safety constraints.

### Tests/checks run in V9

- `pytest tests/test_v9_scaling.py -v` — **24 passed**, 0 failures.
- `pytest tests/test_alpaca_provider.py -v` — **26 passed**, 0 failures.
- Full suite `run_tests.ps1` — **75 passed**, 0 failures, 26 pre-existing Windows PermissionError collection errors (not V9 related).

### Safety constraints (in effect, unchanged)

- No broker execution, live trading, paper trades, or order placement added.
- No options, margin, leverage, or short selling.
- API keys never printed or committed. Only `keys_present` bool in ProviderHealth.
- No LLM for trade decisions.
- Alpaca IEX is a single-exchange feed — warning preserved in all relevant output paths.
- `fail_safe_to_demo: true` — Alpaca errors fall back to demo, never crash the scan.

### Known issues / risks (V9)

- `_normalize_raw_bars` on empty bars now returns empty DataFrame correctly; `_fetch_bars` already handled this before the call.
- `fetch_ohlcv_batch` catches all exceptions and falls back to per-symbol demo — safe but not granular.
- Rate limiter `total_waits` counter is only accurate when a `rate_limiter` is attached to the provider; if `rate_limiter=None`, waits_count=0 in the rate-limit-warning Tony event.
- Universe rotation bucket index persists within one `run_watch()` session; restarts reset to bucket 0 (expected).
- `high_priority_symbols` threshold is `score_threshold_high_quality` (default 80); symbols above this carry forward to the next cycle via `update_previous_candidates()`.
- Dashboard batch/rotation metrics are read from recent Tony events (last 200). If no Alpaca scan has run, counts show 0.
- Pre-existing Windows PermissionError in pytest tmp-dir cleanup causes 26 test collection ERRORs across `test_database.py`, `test_universe.py`, etc. — not a V9 regression.

### Next recommended task

1. Run `python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1` with real Alpaca keys to validate batch fetch at scale.
2. Check `tony-events --limit 30` for `batch_fetch_summary`, `real_data_scan_scaled`, `universe_rotation_summary` events.
3. If rate-limit warnings appear, reduce `max_symbols_per_cycle` or increase `request_sleep_seconds`.
4. Monitor rotation bucket ID across cycles to verify round-robin advances.
5. Verify `FILE_STRUCTURE.md` includes `universe_rotation.py`.

### Safe to continue?

Yes. 75 tests pass. No broker execution, live trading, paper trades, order placement, hard-coded keys, external notifications, or LLM trade decisions were added. Alpaca IEX single-exchange warning preserved. All demo fallback paths intact.

---

## V8.5 handoff — Alpaca Real-Data Watch Validation + Tony Data Quality Guardrails

### Current active task

V8.5 complete and tested locally.

### Last agent used

Claude (claude-sonnet-4-6) via Claude Code.

### Files changed in V8.5

- `src/trading_bot/settings.py` — added `resolve_effective_provider(settings)` helper; `market_data.real_provider_enabled: true` + `market_data.provider` now wins over legacy top-level `provider:` field.
- `src/trading_bot/data/market_data.py` — added `dataclass` import; added `ProviderHealth` dataclass (keys_present bool only, never values; `passed` property; `to_dict()`); added `check_provider_health()` function.
- `src/trading_bot/tony/events.py` — added `real_provider_active`, `all_symbol_fallback`, `provider_health_passed`, `provider_health_failed` to default `create_events_for`; added four corresponding record methods.
- `src/trading_bot/cli.py` — imported `resolve_effective_provider`, `ProviderHealth`, `check_provider_health`; updated all `build_market_data_provider(settings.provider, ...)` call sites to use `resolve_effective_provider(settings)`; added all-symbol fallback detection + Tony events in `run_scan()`; added provider status startup banner in `run_watch()`; updated `data-check` to support `--symbols` multi-symbol and show configured vs effective + `keys_present` bool; added new `provider-health` command and `run_provider_health()`.
- `src/trading_bot/dashboard/app.py` — imported `resolve_effective_provider`; updated `render_data_provider_status()` to show configured vs effective provider, `real_provider_enabled`, last scan provider from DB, fallback/stale/all-symbol-fallback Tony event counts; updated `render_detail()` to use `resolve_effective_provider` and pass `market_data_config`.
- `config/default_config.yaml` — added `real_provider_active`, `all_symbol_fallback`, `provider_health_passed`, `provider_health_failed` to Tony `create_events_for`; added `label_single_exchange_warning: true` to alpaca config.
- `tests/test_alpaca_provider.py` — added 10 new V8.5 tests: provider precedence (4 cases), keys_present bool, demo health check pass, all-symbol fallback Tony event, check_provider_health with mocked Alpaca, check_provider_health no keys.
- `AGENT_STATE.md` — updated for V8.5.

### Tests/checks run in V8.5

- `pytest tests/test_alpaca_provider.py -v` — 26 passed (16 V8 + 10 new V8.5).
- `pytest -q` — 77 passed total. No failures.
- `python -m compileall src -q` — clean.
- `python -m trading_bot.cli scan --config config/default_config.yaml` — passed. Effective provider = alpaca_iex (from real_provider_enabled). All 30 symbols fell back to demo (expected — no real keys). All-symbol fallback warning printed and Tony `all_symbol_fallback` critical event recorded.
- `python -m trading_bot.cli data-check --config config/default_config.yaml --symbols PLTR,SOFI,HOOD` — passed. Shows configured vs effective, keys_present bool, fallback warning per symbol.
- `python -m trading_bot.cli provider-health --config config/default_config.yaml --symbols PLTR,SPY` — passed. Shows FAILED (all fallback, no real keys). keys_present=True (keys exist in env, but invalid).
- `python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1` — passed. Startup banner shows configured/effective provider, feed, timeframe, max symbols, IEX warning.
- `python -m trading_bot.cli tony-events --config config/default_config.yaml --limit 15` — passed. `all_symbol_fallback` critical event visible.

### Known issues / risks (V8.5)

- `keys_present: True` reflects env var presence, not validity. A 401 from Alpaca means the key is wrong/invalid even when keys_present is True.
- Provider health check shows FAILED when all symbols fall back (all-symbol fallback = using_fallback=True = passed=False). This is correct behavior.
- All-symbol fallback warning is expected until real valid Alpaca API keys are added to `.env`.
- Alpaca IEX is a single-exchange feed; not full SIP consolidated tape.
- Rate-limit/backoff not yet implemented — keep `max_symbols_per_scan: 30`.

### Next recommended task

1. Add real valid Alpaca API keys to `.env`.
2. Re-run `python -m trading_bot.cli provider-health --config config/default_config.yaml` — expect PASSED with real keys.
3. Re-run `python -m trading_bot.cli data-check --config config/default_config.yaml --symbols PLTR,SOFI,HOOD` — expect real bars (no fallback warnings).
4. Run `python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1` with real keys.
5. Check `tony-events` for `real_provider_active` event instead of `all_symbol_fallback`.
6. Review snapshot quality after first real-data cycle.
7. Add rate-limit/backoff handling before increasing max_symbols_per_scan beyond 30.
8. Commit a known-good baseline once first real-data cycle is reviewed.

### Safe to continue?

Yes. Default config still activates Alpaca IEX through `real_provider_enabled: true`, but falls back cleanly to demo without real keys. All 77 tests pass. No live trading, broker execution, order placement, hard-coded keys, external notifications, or LLM trade decisions were added. Keys are never printed or stored — only `keys_present` bool.

---

## V8 handoff — Alpaca IEX Market Data Provider Foundation

### Current active task

V8 Alpaca IEX Market Data Provider Foundation — complete and tested locally.

### Last agent used

Claude (claude-sonnet-4-6) via Claude Code.

### Files changed in V8

- `config/default_config.yaml` — added `market_data:` block with Alpaca config; added `data_provider_fallback` and `stale_data_warning` to Tony `create_events_for`.
- `.env.example` — added `ALPACA_DATA_FEED=iex`.
- `src/trading_bot/data/market_data.py` — added `AlpacaIEXProvider` class, `_build_alpaca_provider` helper; updated `build_market_data_provider` with `market_data_config` parameter.
- `src/trading_bot/settings.py` — added `market_data: dict[str, Any] | None = None` field.
- `src/trading_bot/cli.py` — imported `AlpacaIEXProvider`; added `data-check` command (`run_data_check`); updated scan/update-snapshots/seed-demo-snapshots to pass `market_data_config`; added Alpaca symbol cap; added Tony fallback/stale events after scan.
- `src/trading_bot/tony/events.py` — added `record_data_provider_fallback` and `record_stale_data_warning` methods; updated default `create_events_for`.
- `src/trading_bot/dashboard/app.py` — added `render_data_provider_status` section in Overview tab.
- `tests/test_alpaca_provider.py` — new file: 16 tests, all mocked, no real API calls.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `FILE_STRUCTURE.md`, `AGENT_STATE.md` — updated for V8.

### Tests/checks run in V8

- `pytest` — 67 passed (16 new Alpaca + 51 existing). No failures.
- `python -m compileall src` — passed.
- Scanner smoke test — passed with demo_generated provider.
- `python -m trading_bot.cli data-check --config config/default_config.yaml --symbol PLTR` — passed in demo mode, printed bars.
- Dashboard syntax verified clean.

### Known issues / risks (V8)

- Alpaca provider is disabled by default. User must set `provider: alpaca_iex` and add keys to `.env`.
- Alpaca IEX is a single-exchange feed; may differ from consolidated SIP tape. Not for production execution.
- Rate-limit/backoff not yet implemented — keep `max_symbols_per_scan: 30`.
- Market-hours awareness for Alpaca fetches not yet implemented.
- Intraday timeframe scanning (5Min/15Min) is supported by the adapter but the scanner still uses daily bars.

### Next recommended task

1. Add real Alpaca API keys to `.env`.
2. Run `python -m trading_bot.cli data-check --config config/default_config.yaml --symbol PLTR` with real keys.
3. If passes, run one watch cycle: `python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1`.
4. Review Tony Stocks events for any fallback or stale-data warnings.
5. Add rate-limit/backoff handling before increasing max_symbols_per_scan.
6. Commit a known-good baseline once first real-data cycle is reviewed.

### Safe to continue?

Yes. Default config still uses demo_generated. All existing tests pass. No live trading, broker execution, order placement, hard-coded keys, external notifications, or LLM trade decisions were added.

---

## V7 handoff — Outcome Analytics (previous)

### Current active task

V7 Outcome Analytics by setup category, role, score bucket, warning type, and seeded-demo status completed and tested locally.

## Current branch

`master`.

## Last agent used

Codex.

## Files changed in latest pass

- Updated `config/default_config.yaml` to allow Tony `outcome_analytics_updated` events.
- Added `src/trading_bot/analytics/__init__.py`.
- Added `src/trading_bot/analytics/outcomes.py` for candidate snapshot outcome analytics.
- Updated `src/trading_bot/storage/repositories.py` with analytics snapshot filtering.
- Updated `src/trading_bot/tony/events.py` with outcome analytics summary events.
- Updated `src/trading_bot/cli.py` with the `outcome-analytics` command and options.
- Updated `src/trading_bot/dashboard/app.py` with an Outcome Analytics tab.
- Added `tests/test_outcome_analytics.py`.
- Updated `tests/test_scanner_smoke.py` with an outcome analytics CLI smoke test.
- Updated `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `FILE_STRUCTURE.md`, and this handoff.

## Files inspected

- `AGENTS.md`
- `PROJECT_CONTEXT.md`
- `CURRENT_STATUS.md`
- `ROADMAP.md`
- `ARCHITECTURE_RULES.md`
- `DESIGN_RULES.md`
- `TESTING_CHECKLIST.md`
- `FILE_STRUCTURE.md`
- `KNOWN_BACKLOG.md`
- `AGENT_STATE.md`
- `config/default_config.yaml`
- `config/scoring_config.yaml`
- `config/universe_swing_research_config.yaml`
- `src/trading_bot/cli.py`
- `src/trading_bot/settings.py`
- `src/trading_bot/data/market_data.py`
- `src/trading_bot/scoring/score_engine.py`
- `src/trading_bot/storage/database.py`
- `src/trading_bot/storage/repositories.py`
- `src/trading_bot/snapshots/followup.py`
- `src/trading_bot/snapshots/seeding.py`
- `src/trading_bot/dashboard/app.py`
- `src/trading_bot/tony/events.py`
- `scripts/run_watch_mode.ps1`
- `tests/test_scanner_smoke.py`
- `tests/test_snapshot_followup.py`
- `tests/test_database.py`

## Tests/checks run

```powershell
$env:PYTHONPATH='src'; $env:TMP=(Join-Path (Get-Location) '.pytest_tmp'); $env:TEMP=$env:TMP; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py tests/test_scanner_smoke.py -q --basetemp .pytest_tmp
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m compileall src
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml --include-seeded
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli tony-events --config config/default_config.yaml --limit 20
powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1
git diff --check
git status --short
git branch --show-current
```

Results:

- Focused outcome analytics/scanner smoke tests passed: 12 passed.
- Compile check passed.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` passed: compileall passed and pytest passed with 51 tests.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1` passed and regenerated `outputs/latest_scan_results.csv`.
- `outcome-analytics` passed with seeded demo fixture rows excluded by default.
- `outcome-analytics --include-seeded` passed and clearly labeled seeded demo fixtures as not evidence of real market edge.
- `tony-events --limit 20` passed and printed recent events including outcome analytics updates.
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1` started Streamlit at `http://localhost:8501`; the command timed out because Streamlit runs in the foreground.
- `outputs/latest_scan_results.csv`, `data/trading_bot.db`, and `logs/trading_bot.log` exist.
- `git diff --check` reported only CRLF normalization warnings.
- `git status --short` worked but printed warnings about permission denied reading `C:\Users\alexa/.config/git/ignore`.

## Known issues / risks

- Tony Stocks is currently watcher/analyst only. It creates internal database events only.
- Tony does not send email, SMS, Discord, Telegram, or other external notifications.
- Tony does not use an LLM for trade decisions.
- Tony does not create manual picks, paper trades, broker orders, or live orders.
- Tony event acknowledgement/dismiss actions are not implemented yet.
- Outcome analytics are research summaries only; they do not prove a strategy edge.
- Seeded demo fixture rows are excluded by default and must stay separated from real watch-mode analysis.
- Watch mode is scanning/snapshot collection only; same-hour dedupe can produce 0 new snapshots during repeated tests.
- Real API providers are placeholders only.
- Follow-up fields are populated only when provider data has bars after `snapshot_time`; same-day daily demo snapshots correctly show `insufficient_future_data`.
- Seeded demo snapshots are dashboard/outcome tracker testing fixtures only and are not evidence of real market edge.
- Static market-cap/style tags are approximate demo metadata until real provider/fundamental metadata exists.

## Next recommended task

1. Collect several supervised non-seeded watch-mode sessions and review the Outcome Analytics tab.
2. Add Tony event acknowledgement/dismiss actions in the dashboard.
3. Consider external Tony notifications only after event volume and wording are reviewed.
4. Commit the current tested baseline.

## Exact commands to continue

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml --include-seeded
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli tony-events --config config/default_config.yaml --limit 20
powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1
```

## Risky assumptions

- The user will run commands from the project root.
- Tony event volume from high-score candidates is acceptable for the first event-layer pass and can be tuned with `max_events_per_cycle`.
- Tony modes beyond `watcher` and `analyst` are intentionally not implemented.
- Same-day snapshots have no future bars yet and will be labeled `insufficient_future_data`.
- Seeded outcomes are deterministic demo fixtures, not proof of strategy quality.
- Outcome summaries are only as useful as the snapshot history collected so far.

## Safe to continue?

Yes. Tests, scanner, outcome analytics CLI, Tony event CLI, and dashboard startup passed. No live trading, broker execution, API keys, real provider wiring, automatic paper trades, options, margin, leverage, short selling, external notifications, or LLM trade decisions were added.
