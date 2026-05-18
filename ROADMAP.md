# Trading Bot Project - Roadmap

_Last updated: 2026-05-18_

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

Status: Initial snapshot outcome analytics implemented and tested locally.

Goals:

- Compare outcomes by setup category, universe role, score bucket, warning type, and tags.
- Keep seeded demo fixture rows separated from real watch-mode rows by default.
- Produce CLI and dashboard summaries for model evaluation.
- Let Tony create one concise internal event when analytics runs.

Exit criteria:

- Outcome analytics service exists. Done.
- CLI command prints grouped summaries. Done.
- Dashboard tab displays grouped tables and basic charts. Done.
- Seeded demo rows are excluded by default. Done.
- Analytics remain research-only and do not create trades. Done.

## Phase 2 - Real API providers

Status: **V13 complete.** Tony Hypothesis-to-Outcome Tracking operational. Tony analyst reads stored with candidate snapshots at creation time. Outcome analytics groups by Tony fields. Dashboard Tony Learning panel. `TONY_ANALYSIS_VERSION = "v1"`. 321 tests pass, 0 errors.

V12: Workday Watch Mode operational. Watch run lifecycle tracked in SQLite. Heartbeat staleness detection. Market-hours guard. Tony lifecycle events. Dashboard Command Center (V11) shows real-time watch status. Analyst Engine (V10) produces deterministic reads every cycle. 282 tests pass, 0 errors.

Goals:

- Add provider adapters for Polygon, Alpaca, Finnhub, Financial Modeling Prep, and/or Twelve Data.
- Alpaca IEX (free tier): Done for historical daily bars + multi-symbol batch endpoint. Intraday timeframes supported by adapter but scanner uses daily bars.
- Rate-limit handling (sliding 60s window, buffer%, sleep): Done.
- Large-universe ingestion (175 symbols/cycle with rotation): Done.
- Universe rotation (core → open snapshots → prev candidates → round-robin discovery): Done.
- Batch fetch (`limit=10000`, 1–2 HTTP calls for 175 symbols): Done.
- Keep all keys in environment variables only: Done.

- Watch run lifecycle (heartbeat, stale detection, stop/error recording): Done (V12).
- Dashboard Command Center with live watch status: Done (V11/V12).
- Tony Analyst Engine (deterministic reads, priority labels, no LLM): Done (V10).
- Dashboard Command Center tab (first/default): Done (V11).

**Next validation step:** Run `watch --max-cycles 3` with real Alpaca keys; verify heartbeat resets in Command Center and `tony-events` shows `batch_fetch_summary`, `universe_rotation_summary`, `watch_run_stopped`.

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
