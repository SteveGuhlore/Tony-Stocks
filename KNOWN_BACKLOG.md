# Trading Bot Project - Known Backlog

_Last updated: 2026-05-17_

## Immediate

- Review the trade-plan validation fields in `outputs/latest_scan_results.csv`, scan results, and candidate snapshots.
- Review the Candidate Snapshots dashboard section.
- Review snapshot follow-up outcome labels after future bars exist.
- Review seeded demo outcome rows in the dashboard. These are testing fixtures only and are not evidence of real market edge.
- Run Scheduled Watch Mode during a supervised demo session and review snapshot volume/dedupe behavior.
- Review Tony Stocks event volume and wording after a supervised watch-mode session.
- Review Outcome Analytics after collecting several non-seeded watch-mode sessions.
- Initialize git and make an initial commit after checks pass.

## V1/V2 follow-ups

- Improve dashboard edit flows for existing manual picks and paper trades.
- Add chart cache controls and better missing-data handling.
- Add score history charts by symbol.
- Add persisted user notes editing in stock detail.
- Add score bucket outcome tracking for manual picks.
- Add configurable dashboard defaults for role/tag filters.
- Add real sector/market-cap metadata once provider/fundamentals support exists.
- Add snapshot dedupe tuning if multiple same-hour scans should be retained.
- Add dashboard styling/filters for explicitly viewing invalid trade plans without mixing them into primary opportunities.
- Add exports and deeper drilldowns for outcome analytics if the dashboard view is not enough.
- Add a cleanup/archive command for old demo seeded snapshots if local fixture data gets noisy.
- Add persisted watch-mode heartbeat/status history if the dashboard needs a true process-health panel.
- Add market calendar/holiday awareness for watch-mode market-hours checks.
- Add Tony event acknowledgement/dismiss actions in the dashboard.
- Add external Tony notifications later through explicit opt-in channels.
- Add a stricter seeded-demo cleanup or labeling workflow before any real provider data is introduced.

## Alpaca IEX + V9.5 universe — immediate follow-ups

- Add Alpaca API keys to `.env` and test `data-check` with real keys.
- Run `watch --max-cycles 1` with `config/universe_swing_research_config.yaml` and review Tony events for `batch_fetch_summary`, `universe_rotation_summary`, fallback/stale warnings.
- Review snapshot quality after first real-data scan at 171-symbol scale.
- If rate-limit warnings appear, reduce `max_symbols_per_cycle` or increase `request_sleep_seconds`.
- Monitor rotation `bucket_id` across watch cycles to verify round-robin discovery advances.
- Add market-hours awareness so watch mode skips Alpaca fetches when the market is closed.
- Periodically review and prune universe symbols (delist risk, liquidity changes).
- NOTE: Alpaca IEX is a single-exchange feed. Do not treat as consolidated SIP tape.
- NOTE: Universe symbols are curated for research/scanning only — not buy/sell recommendations.

## Future provider/data work

- Rate-limit/backoff support (needed before large universe with Alpaca).
- Polygon, Finnhub, FMP, or Twelve Data adapters.
- Corporate action and split/dividend adjustment checks.
- Sector/industry metadata.
- Larger market universe ingestion (post rate-limit handling).

## Future scoring/research work

- News/sentiment scoring.
- Fundamentals scoring.
- Sector/industry relative strength.
- Advanced backtesting.
- Pick outcome tracking by score bucket.
- Strategy validation reports.

## Future execution/risk work

- Paper broker execution.
- Live trading approval gates.
- Risk dashboard.
- Alerting.
- Emergency stop verification.
- Tony paper-trader mode only after explicit paper-entry rules and tests exist.

## Do not do yet

- Do not enable live trading.
- Do not add options trading.
- Do not add margin/leverage.
- Do not add short selling.
- Do not add black-box AI trade decisions.
