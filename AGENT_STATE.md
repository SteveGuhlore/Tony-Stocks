# Agent State / Handoff Log

_Last updated: 2026-05-18_

Use this file so Codex, Claude, Cursor, or any other agent can continue from the same context when the user switches because of usage limits.

---

## V14.5 handoff - Real Intraday Provider Enforcement (bugfix)

### Current active task

V14.5 bugfix complete and tested locally. Watch/scan Tony analysis now labels daily vs intraday data quality separately, does not call real Alpaca daily/intraday reads `demo_data`, and enforces `intraday.require_real_provider` + `allow_demo_fallback: false` by marking symbols `intraday_data_missing` instead of silently using demo intraday bars. Intraday summary events and console output include provider, real/missing/demo-fallback/stale counts.

### Last agent used

Cursor (Auto).

### Files changed in V14.5 bugfix

- `src/trading_bot/tony/analysis.py` - Renamed daily real label to `daily_real_alpaca`; integrated intraday-specific data-quality labels (`intraday_real_alpaca`, `intraday_missing`, `intraday_fallback_demo`, `stale_intraday`); hypothesis notes no longer say demo when real Alpaca is used.
- `src/trading_bot/scoring/score_engine.py` - `Demo data only` warning only when `market_data_source != "real"`.
- `src/trading_bot/cli.py` - Pass `market_data_source` to scoring; track intraday-only fallback/stale via Counter before/after intraday fetch; pass intraday quality sets into `analyze_candidates`; expanded intraday summary/console fields.
- `src/trading_bot/tony/events.py` - `analyst_data_quality` and `intraday_analysis_summary` messages include new label counts and provider/fallback metadata.
- `src/trading_bot/dashboard/app.py` - Data Quality panel reads `daily_real_alpaca` (with legacy fallback key).
- `tests/test_v14_5_intraday_provider.py` - NEW. Mocked tests for daily/intraday provider enforcement and label behavior.
- `tests/test_database.py` - Updated snapshot fixture label to `daily_real_alpaca`.

### Root cause

1. **Daily mislabeling:** `score_engine` appended `Demo data only` on every swing scan regardless of provider. Tony `_data_quality` could treat that warning as `demo_data` when provider checks were incomplete in some paths.
2. **Intraday mislabeling:** Intraday fetch reused Alpaca `fallback_symbols` without isolating intraday-only fallbacks, and Tony `_data_quality` did not consider intraday availability separately from daily scan quality. When intraday failed with fallback disabled, features were marked missing but daily `data_quality_read` could still imply demo.

### Provider path fix

- Daily scan: `resolve_effective_provider` → `AlpacaIEXProvider.fetch_ohlcv_batch` / `fetch_ohlcv` (unchanged).
- Intraday Tony reads: `_fetch_intraday_features_for_tony` uses same `AlpacaIEXProvider` with 5Min timeframe; snapshots `fallback_before` / `stale_before` Counters, computes `intraday_fallback_symbols` and `intraday_stale_symbols` only from changes during intraday fetch.
- When `require_real_provider: true` and provider is not `AlpacaIEXProvider`, all symbols marked `intraday_data_missing` with `intraday_provider=skipped_require_real`.

### Demo fallback enforcement

- `allow_demo_fallback: false` → symbols in `intraday_fallback_symbols` get `IntradayFeatures(data_available=False, status=intraday_data_missing)`; no demo bars used for Tony reads.
- Entire batch failure with fallback disabled → all missing, `intraday_provider=none_fetch_failed`.
- Tony `data_quality_read` uses `intraday_missing` / `intraday_fallback_demo` instead of `demo_data` when intraday is the issue.

### Data quality label behavior

| Label | When |
|-------|------|
| `daily_real_alpaca` | Daily Alpaca IEX, intraday not enabled or not the limiting factor |
| `intraday_real_alpaca` | Daily + intraday both real Alpaca |
| `intraday_missing` | Intraday enabled but no real intraday bars (fallback disabled) |
| `intraday_fallback_demo` | Intraday fell back to demo during fetch |
| `stale_intraday` | Intraday bars older than stale threshold |
| `demo_data` | Demo-generated daily provider only |
| `fallback_data` | Daily scan fell back to demo |

Hypothesis text uses `demo-generated data` only for `demo_data` / `intraday_fallback_demo`, not for real Alpaca paths.

### Tests/checks run

```powershell
$env:PYTHONPATH='src'; .venv\Scripts\python.exe -m pytest tests/test_v14_5_intraday_provider.py tests/test_tony_analyst.py tests/test_scanner_smoke.py tests/test_intraday_features.py tests/test_database.py -q --basetemp .pytest_tmp
$env:PYTHONPATH='src'; .venv\Scripts\python.exe -m pytest --basetemp .pytest_tmp -q
```

Results:

- Focused V14.5 bugfix tests: **112 passed**.
- Full suite: **362 passed** (31 new tests in `test_v14_5_intraday_provider.py`).
- `run_tests.ps1` / `run_scanner.ps1` / `data-check` / `watch` / `tony-events` not re-run in this WSL session (Windows `.venv` only; `powershell` unavailable). Re-run on Windows host with Alpaca keys for live validation.

### Runtime validation (user should run on Windows)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli data-check --config config/default_config.yaml --symbols PLTR,SOFI,HOOD --timeframe 5Min
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli tony-events --config config/default_config.yaml --limit 50
```

Expected after fix with real Alpaca connectivity:

- `analyst_data_quality` shows `daily_real_alpaca` / `intraday_real_alpaca` counts, not 61 `demo_data`.
- Candidate hypotheses do not say `demo-generated data` when daily and intraday are real Alpaca.
- `intraday_analysis_summary` shows `provider=alpaca_iex`, real/missing/demo_fallback/stale counts, `allow_demo_fallback=false`.
- If intraday fails with fallback disabled: `intraday_missing` labels, not `demo_data`.

### Safety confirmation

- No broker execution, live trading, paper trades, orders, options/Greeks, or LLM trade decisions added.
- No API keys printed or committed.
- Intraday reads remain research-only; scoring unchanged.

### Next recommended task

Run `watch --max-cycles 1` on Windows during market hours with real Alpaca keys and confirm `tony-events` data-quality and intraday summary match live 5Min usage.

---

## V14.5 handoff - Intraday Watch Activation + Snapshot Verification

### Current active task

V14.5 complete and tested locally. Watch mode now prints intraday configuration at startup, scan/watch cycles print intraday summary counts, Tony records one `intraday_analysis_summary` event per enabled scan cycle, and tests verify intraday reads attach to Tony hypotheses and candidate snapshots when enabled. Intraday reads remain research-only and do not affect scoring.

### Last agent used

Codex.

### Files changed in V14.5

- `config/default_config.yaml` - Added `intraday.max_symbols_per_cycle` and enabled `intraday_analysis_summary` Tony events.
- `src/trading_bot/cli.py` - Added intraday summary stats, watch startup output, scan/watch console output, fallback accounting, and summary payloads.
- `src/trading_bot/tony/events.py` - Added `record_intraday_analysis_summary()`.
- `src/trading_bot/dashboard/app.py` - Command Center now shows latest intraday summary event metrics.
- `tests/test_scanner_smoke.py` - Added scan/snapshot intraday attachment test and summary-count test.
- `tests/test_tony_analyst.py` - Added intraday summary event coverage.
- `tests/test_database.py` - Tightened legacy snapshot intraday-null compatibility.
- Updated `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, and this handoff.

### Tests/checks run in V14.5

```powershell
$env:PYTHONPATH='src'; $env:TMP=(Join-Path (Get-Location) '.pytest_tmp'); $env:TEMP=$env:TMP; .\.venv\Scripts\python.exe -m pytest tests/test_scanner_smoke.py::test_scan_intraday_enabled_attaches_tony_reads_to_snapshots tests/test_scanner_smoke.py::test_intraday_summary_counts_reads_without_orders tests/test_tony_analyst.py::TestTonyAnalystEvents::test_analyst_events_created tests/test_database.py::test_create_and_list_candidate_snapshots -q --basetemp .pytest_tmp
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli provider-health --config config/default_config.yaml
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli data-check --config config/default_config.yaml --symbols PLTR,SOFI,HOOD --timeframe 5Min
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli tony-events --config config/default_config.yaml --limit 50
powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1
git diff --check
git status --short
```

Results:

- Focused V14.5 tests passed: 4 passed.
- Full test stack passed: 331 passed.
- Scanner passed and regenerated `outputs/latest_scan_results.csv`; Alpaca HTTPS was blocked in this environment, so daily and intraday Alpaca fetches fell back to demo.
- Scanner printed intraday summary: 82 requested, 0 with data, 82 missing, 82 fallback.
- Provider health command ran and reported FAILED because outbound HTTPS to Alpaca was blocked; keys were present and demo fallback returned bars.
- `data-check --timeframe 5Min` passed for PLTR, SOFI, and HOOD using demo fallback; it printed 5Min bars, VWAP, above-VWAP status, day change, and opening range.
- `watch --max-cycles 1` passed; watch startup printed intraday config, scan cycle printed intraday summary, 9 snapshots were created, 183 snapshots were updated, and the watch stopped cleanly.
- `tony-events --limit 50` passed and showed `intraday_analysis_summary`.
- Snapshot spot check confirmed latest created rows have `tony_intraday_read='intraday_data_missing'` and `intraday_timeframe='5Min'` when real intraday fetch fell back and fallback is disallowed.
- Dashboard started at `http://localhost:8501`; command timed out because Streamlit runs in the foreground.
- `git diff --check` reported only CRLF normalization warnings.
- `git status --short` worked but printed permission warnings reading `C:\Users\alexa/.config/git/ignore`.

### Known issues / risks

- Intraday reads still do not influence scoring.
- Real Alpaca IEX intraday watch behavior depends on outbound HTTPS connectivity and valid keys.
- Alpaca IEX remains a single-exchange feed, not SIP consolidated tape.
- No broker execution, live trading, orders, options, margin, leverage, shorting, automatic paper trades, or LLM trade decisions were added.

### Next recommended task

Run `watch --max-cycles 3` during market hours with real Alpaca connectivity and inspect `intraday_analysis_summary` events plus snapshot intraday columns for multiple cycles.
