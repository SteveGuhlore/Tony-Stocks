# Agent State / Handoff Log

_Last updated: 2026-05-17_

Use this file so Codex, Claude, Cursor, or any other agent can continue from the same context when the user switches because of usage limits.

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
