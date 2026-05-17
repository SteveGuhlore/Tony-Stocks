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

## Future provider/data work

- Real provider adapters.
- Larger market universe ingestion.
- Rate-limit/backoff support.
- Corporate action and split/dividend adjustment checks.
- Sector/industry metadata.

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
