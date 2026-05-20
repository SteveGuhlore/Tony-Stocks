# Trading Bot Project - Roadmap

_Last updated: 2026-05-19_

## Phase 1 - V1/V2 scanner, scorer, and dashboard

Status: V1 scaffold, V2 swing scoring, V3 mid/small-cap universe role pass, candidate snapshot foundation, trade-plan validation, V4 snapshot follow-up update command, V4.5 demo outcome seeder, V5 scheduled watch mode, V6 Tony Stocks internal event layer, and V7 outcome analytics tested locally.

Goals:

- Load a configurable stock universe.
- Fetch or generate OHLCV data through provider adapters.
- Calculate explainable technical indicators.
- Score and rank stocks using config-driven weights.
- Save scan runs/results to SQLite.
- Export latest results to CSV.
- Show dashboard views for scan review, manual picks, paper journal, and basic performance.
- Add swing-trade setup categories, ETF/benchmark warnings, mega-cap warnings, and dashboard review filters.
- Add mid/small-cap focused demo universe, universe roles, profile-aware demo data, primary candidate ranking, and CSV smoke coverage.
- Add candidate snapshots so scan signals can be tracked later without creating paper trades.

Exit criteria:

- `python -m compileall src` passes. Done.
- `pytest` passes. Done with 51 tests.
- Scanner runs with demo data and writes SQLite/CSV output. Done.
- Snapshot command saves eligible candidate snapshots. Done.
- Dashboard opens and reads latest scan. Startup verified.

## Phase 1B - Missed opportunity tracking

Status: Initial follow-up update command, demo outcome seeder, and scheduled scan/snapshot watch mode tested locally with demo daily data.

Goals:

- Track candidate snapshots after scan time.
- Update highest/lowest price seen and follow-up return fields.
- Label missed opportunities, failed setups, and untriggered watches.
- Keep this separate from paper trades and live execution.

Exit criteria:

- Follow-up update command or script exists. Done.
- Outcome fields are populated from demo or future provider data. Done when future bars exist; same-day daily demo runs correctly mark insufficient future data.
- Dashboard can compare setup categories by follow-up result. Initial outcome summary/filter added.
- Demo seeded historical snapshots exist for dashboard/outcome testing only. Done; they are not evidence of real market edge.
- Scheduled Watch Mode can collect snapshots during the day. Done; it is scanning/snapshot collection only and does not place paper or live trades.
- Tony Stocks can create internal watcher/analyst events for scans, snapshot updates, high-score candidates, and watch cycles. Done; it does not send external notifications or trade.
- Outcome analytics can compare setup categories, score buckets, universe roles, warning types, and seeded-demo fixture separation. Done; seeded demo rows are excluded by default and are not evidence of real market edge.

## Phase 1C - Tony Stocks watcher/analyst layer

Status: Initial internal event log implemented and tested locally.

Goals:

- Give the scanner a deterministic internal watcher persona.
- Create structured events for dashboard review and future notifications.
- Keep Tony as watcher/analyst only until paper-trade rules are explicit and tested.
- Avoid LLM-based trade decisions.

Exit criteria:

- Tony event table exists. Done.
- Scan/update/watch flows create events. Done.
- Dashboard can display Tony events. Done.
- CLI can print recent Tony events. Done.
- Tony does not create paper trades or live trades. Done.

## Phase 1D - Outcome analytics and model evaluation

Status: Real-data-only outcome analytics implemented and tested locally. First live market-hours Tony run completed successfully; next focus is real-data-only analytics hygiene before intraday scoring.

Goals:

- Compare outcomes by setup category, universe role, score bucket, warning type, and tags.
- Keep demo, missing-real-data, and legacy rows excluded from active watch/learning analytics by default.
- Produce CLI and dashboard summaries for model evaluation.
- Let Tony create one concise internal event when analytics runs.
- Hard rule: active Tony watch/learning runs are real-data-only. Demo provider data is never allowed in watch, snapshots, Tony learning, analytics, paper trading, or live trading. Tests may use mocks or recorded real fixtures, but not synthetic demo market series.

Exit criteria:

- Outcome analytics service exists. Done.
- CLI command prints grouped summaries. Done.
- Dashboard tab displays grouped tables and basic charts. Done.
- Seeded demo rows are excluded by default. Done.
- Analytics remain research-only and do not create trades. Done.

## Phase 2 - Real API providers

Status: **V15.7 complete** for trading-app style five-tab dashboard shell (no scoring/trading/DB changes). **V15.5 complete** for beginner-friendly Command Center dashboard UX. **V15.2 complete** for config-driven symbol quarantine during real-data-only runs. **V15 complete** for research-only intraday entry trigger simulation on candidate snapshots. **V14.7 complete** for real-data-only enforcement. V15 adds research-only intraday trigger simulation. It does not create paper trades or broker orders. Outcome analytics now separates `real_alpaca`, `demo_generated`, `mixed_fallback`, and `unknown_legacy` snapshots, and the CLI/dashboard include market-day review tooling. Daily scoring remains the default.

V13: Tony Hypothesis-to-Outcome Tracking operational. Tony analyst reads stored with candidate snapshots at creation time. Outcome analytics groups by Tony fields. Dashboard Tony Learning panel. `TONY_ANALYSIS_VERSION = "v1"`. 321 tests pass, 0 errors.

V12: Workday Watch Mode operational. Watch run lifecycle tracked in SQLite. Heartbeat staleness detection. Market-hours guard. Tony lifecycle events. Dashboard Command Center (V11) shows real-time watch status. Analyst Engine (V10) produces deterministic reads every cycle. 282 tests pass, 0 errors.

Goals:

- Add provider adapters for Polygon, Alpaca, Finnhub, Financial Modeling Prep, and/or Twelve Data.
- Alpaca IEX (free tier): Done for historical daily bars + multi-symbol batch endpoint. V14 adds 5Min intraday fetch support for Tony research reads; scanner scoring still uses daily bars by default.
- Rate-limit handling (sliding 60s window, buffer%, sleep): Done.
- Large-universe ingestion (175 symbols/cycle with rotation): Done.
- Universe rotation (core → open snapshots → prev candidates → round-robin discovery): Done.
- Batch fetch (`limit=10000`, 1–2 HTTP calls for 175 symbols): Done.
- Keep all keys in environment variables only: Done.

- Watch run lifecycle (heartbeat, stale detection, stop/error recording): Done (V12).
- Dashboard Command Center with live watch status: Done (V11/V12).
- Tony Analyst Engine (deterministic reads, priority labels, no LLM): Done (V10).
- Dashboard Command Center tab (first/default): Done (V11).
- Intraday VWAP/opening-range research reads: Initial foundation done (V14) and watch/snapshot verification tightened (V14.5). Not entry automation.

**Next validation step:** After the next supervised market-hours run, compare `outcome-analytics --real-only --today --provider alpaca_iex` with `eod-report` and confirm demo/fallback/legacy rows are excluded before any intraday scoring work.

**Alpaca IEX notice:** Alpaca IEX is a single-exchange feed and may differ from consolidated SIP market tape. It is for research and scanning only. Not for production execution decisions. **Universe symbols are curated for research/scanning and are not recommendations to buy or trade any security.**

## Phase 3 - Paper execution integration

Goals:

- Add paper broker adapter.
- Log order intents and fills.
- Keep real orders disabled.
- Add explicit risk approvals before any simulated order.

## Phase 4 - Strategy validation and backtesting

Goals:

- Add scanner-to-backtest review workflow.
- Track whether manual picks worked over time.
- Add benchmark and sector-relative comparisons.
- Add out-of-sample validation and parameter sensitivity tests.

## Phase 5 - Live trading safety gates

Goals:

- Keep `live_trading_enabled: false` by default.
- Require explicit user approval before any live mode.
- Require separate broker credentials, risk limits, emergency stop, logs, and passing tests.
- Start only with tiny size after paper validation.

## Future research

- News/sentiment scoring.
- Fundamentals scoring.
- Sector and industry relative strength.
- Alerting.
- Risk dashboard.
- Scheduled scans.

## V15.8A note

- Product dashboard symbol dedupe is complete: one Tony Pick card per symbol, one Active Tracking card per symbol, fixed first valid triggered entry per active symbol, and later rows only refresh live tracking fields plus Results still-active counts.

## V15.8B note

- Product dashboard semantics are now aligned around `Entry trigger`, fixed `Active entry` / `Tracked from`, after-hours `Closing price`, risk/reward helper text, and Results stock cards/filters driven by the same deduped symbol-level product rows as Home, Tony Picks, and Active Tracking.
- Future Tony Explanation Engine work: Tony descriptions are still repetitive in some cards. A later pass should create more varied skill-specific explanations without surfacing raw history on the main dashboard.

## V15.8C note

- `eod-report` now includes a raw-vs-product reconciliation section showing that dashboard dedupe/hiding changes visibility only; it does not delete candidate snapshot history from `data/trading_bot.db`.
- Settings / System Health includes a small reconciliation summary so product visibility counts can be compared against raw retained rows without exposing full history on the main dashboard.
