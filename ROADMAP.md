# Trading Bot Project - Roadmap

_Last updated: 2026-05-17_

## Phase 1 - V1/V2 scanner, scorer, and dashboard

Status: V1 scaffold, V2 swing scoring, V3 mid/small-cap universe role pass, candidate snapshot foundation, trade-plan validation, V4 snapshot follow-up update command, V4.5 demo outcome seeder, V5 scheduled watch mode, and V6 Tony Stocks internal event layer tested locally.

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
- `pytest` passes. Done with 45 tests.
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

## Phase 2 - Real API providers

Goals:

- Add provider adapters for Polygon, Alpaca, Finnhub, Financial Modeling Prep, and/or Twelve Data.
- Add rate-limit and retry/backoff handling.
- Improve large-universe ingestion.
- Keep all keys in environment variables only.

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
