# Trading Bot Project - Known Backlog

_Last updated: 2026-05-19_

## Immediate

- **(Item 2, 2026-06-04) Scan-coverage ET-date bucketing is verified ET-correct and locked** by
  `tests/test_scan_coverage_et_date.py` (after-hours 02:00 UTC scan buckets to the prior ET day). The
  original UTC-bucketing bug was already fixed via `market_date_mask` (V16A); the new tests guard it.
  **Dormant edge still open (low priority):** `ScannerRepository.count_paper_orders_today` compares
  `substr(submitted_at,1,10)` (UTC date) against the ET `day` the watch loop passes. Harmless today
  because paper orders only submit during market hours (09:30–16:00 ET), when the ET and UTC dates
  coincide — but if extended-hours submission is ever enabled the daily-order cap could miscount across
  UTC midnight. Fix when paper trading goes extended-hours: bucket by ET market date consistently.
- Review V15.9 reassessment labels after several real market-hours refresh cycles to confirm `still_valid / weakening / invalidated / needs_review` wording stays intuitive without implying trading instructions.
- Review V16 Tony memory summaries after several real-only market days to confirm the preliminary best/worst setup notes stay useful and do not overstate sparse data.
- Review V16A ET market-date reporting after the next after-hours run to confirm `eod-report` and `outcome-analytics --today` now match the intended New York session without surprising users near UTC midnight.
- V15.8C reconciliation reporting is implemented. Manual review is still useful after market-hours runs to confirm raw/history counts and current product counts remain intuitive as snapshot volume grows.
- Tony descriptions are still repetitive across some dashboard cards. Future Tony Explanation Engine work should generate more varied skill-specific explanations while keeping the main product view history-free.
- V15.8B dashboard semantics are implemented. Manual browser click-through is still pending to confirm Home text, Tony Picks trigger messaging, Active Tracking closing-price labeling, and Results filters/cards end to end.
- V15.8A symbol-level dashboard dedupe is implemented. Manual browser click-through is still pending to confirm Home, Tony Picks, Active Tracking, and Results visually match the new product rules end to end.
- Review V15 planned/triggered entry fields on new candidate snapshots after a market-hours watch session (`entry_status`, `planned_entry_price`, `actual_entry_time`).
- Backfill planned entry fields for older open snapshots is not automatic; only new snapshots get plans at creation time.
- Review the trade-plan validation fields in `outputs/latest_scan_results.csv`, scan results, and candidate snapshots.
- Review the Candidate Snapshots dashboard section.
- Review snapshot follow-up outcome labels after future bars exist.
- Review seeded demo outcome rows in the dashboard. These are testing fixtures only and are not evidence of real market edge.
- Run Scheduled Watch Mode during a supervised demo session and review snapshot volume/dedupe behavior.
- Review Tony Stocks event volume and wording after a supervised watch-mode session.
- Review Outcome Analytics after collecting several non-seeded watch-mode sessions.
- Review V14.5 intraday watch summaries during a supervised market session; confirm VWAP/opening-range labels are understandable and snapshots show Tony intraday fields.
- First live market-hours Tony run completed successfully; next focus is real-data-only analytics hygiene before intraday scoring.
- Review real-data-only analytics after each market-hours run using `outcome-analytics --today --provider alpaca_iex` and `eod-report`; default analytics now excludes demo and legacy rows.
- V15.7E enriched Home preview cards (picks + tracking) while keeping Tony Picks / Active Tracking as full-detail tabs.
- V15.7D fixed Active Tracking NameError (`render_tracking_position_card` import); Home status/missing-data copy softened.
- V15.7C fixed raw HTML showing on Home/Results (theme `render_html` + complete stat-grid fragments); Home vs Tony Picks separation done.
- V15.7B visual polish complete (`src/trading_bot/dashboard/theme.py`); optional: responsive tweaks for mobile Streamlit.
- V15.7A fixed NaN/JSON parse crash on Tony Picks; card HTML polish applied.
- V15.8 complete: frozen original plan + active tracking refresh fields on `candidate_snapshots`; dashboard Active Tracking uses them.
- V15.7 trading-app dashboard shell is live; legacy tables under Settings / System Health only.
- V15.5 Command Center is simplified for non-technical review; preserved under Settings legacy expander.
- V15.2 quarantines `HCP`, `SAMSF`, `SMAR`, and `SQ` in `config/default_config.yaml` for real-data-only runs (symbols still in universe YAML). Review after next market-hours watch; add more symbols to quarantine only after manual review.
- Optional: add replacement tickers to universe YAML with full metadata if a quarantined name has a valid IEX symbol (not auto-applied).
- Hard rule: active Tony watch/learning runs are real-data-only. Demo provider data is never allowed in watch, snapshots, Tony learning, analytics, paper trading, or live trading. Tests may use mocks or recorded real fixtures, but not synthetic demo market series.
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
- Add a cleanup/archive workflow for old demo or mixed-fallback snapshots only after real-data filters have been validated.
- Decide later whether intraday features should influence scoring. For now they are Tony research context only.
- Review `intraday_analysis_summary` event volume and dashboard wording after several market-hours watch cycles.

## Alpaca IEX + V9.5 universe — immediate follow-ups

- Add Alpaca API keys to `.env` and test `data-check` with real keys.
- Run `watch --max-cycles 1` with `config/universe_swing_research_config.yaml` and review Tony events for `batch_fetch_summary`, `universe_rotation_summary`, fallback/stale warnings.
- Review snapshot quality after first real-data scan at 171-symbol scale.
- If rate-limit warnings appear, reduce `max_symbols_per_cycle` or increase `request_sleep_seconds`.
- Monitor rotation `bucket_id` across watch cycles to verify round-robin discovery advances.
- Add market-hours awareness so watch mode skips Alpaca fetches when the market is closed.
- Add richer intraday session handling, premarket/after-hours controls, and market-calendar awareness before using intraday reads heavily.
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
