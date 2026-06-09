# Trading Bot Project — Roadmap

_Last updated: 2026-06-09_

---

## Planned — next sessions

- ⏳ **TODO — Track Record equity chart: honest time axis + no dropped trading hours.**
  The bot-vs-Tony equity-compare chart (`GET /api/paper/equity-compare`, 1W/1H) plots by bar-index
  (weekends compress — fine, standard for intraday), but two real issues remain:
  (a) only 3 x-axis labels *sample* the range, so a present-but-unlabeled day (e.g. 6/8) reads as
  "missing"; and (b) `align_common` **intersects** the two accounts' timestamps, so if one account
  lacks a bar (Tony's CC account pre-funding, or a missing morning) those trading hours get DROPPED
  from BOTH lines. Fix: keep the **union** of timestamps (forward-fill the account missing a bar so
  neither line loses real hours), and add more / time-proportional x-axis ticks (or a true wall-clock
  axis with visible session breaks). Files: `analytics/equity_compare.py` (`align_common`),
  `dashboard-web/components/kinetic/MiniLine.tsx` (x-axis), `components/views/TrackRecordView.tsx`.
  Context: 2026-06-09 session shipped the endpoint + %-axis + crosshair + hourly + the divergence join
  fix + section explainers; this is the remaining polish.

- ✅ **DONE (2026-06-06) — Off-Hours Research Engine (Tasks 1–12, complete).** Read-only inverse
  watch loop (`off-hours-watch` CLI) + one-shot `off-hours-prep` CLI that assembles a ranked,
  catalyst-aware Morning Watchlist plan each off-hours window (weekdays 16:30→09:00 ET + weekends).
  Four fail-quiet sinks: `reports/morning_prep/<date>.json`, `vault/morning_prep/<date>.md`, CC
  bridge `morning-prep/<date>.md`, and `GET /api/morning-prep` + Next.js `/morning` tab. Hard
  invariant: ZERO execution path off-hours; enforced by `tests/test_off_hours_no_execution.py`.
  Default OFF (`off_hours.enabled: false`). Scheduled via `scripts/register_off_hours_task.ps1`.

- ✅ **DONE (2026-06-04 eve session) — Funnel enrichment scaling.** Daily `RecommendationCache`
  (`reports/finnhub_reco_cache.json`) + per-cycle budget (`enrich_per_run`): the funnel now ranks the
  WHOLE universe over a few cycles instead of only the first `enrich_limit`, never bursting Finnhub's
  free ~60/min tier. `warm_recommendation_cache` runs each watch cycle. Tests in `test_research_providers.py`.
- ✅ **DONE (2026-06-04 eve session) — Scan-coverage ET-date fix.** Verified the coverage builder already
  buckets after-hours scans by ET market date (`market_date_mask`); locked with `tests/test_scan_coverage_et_date.py`.
  Dormant `count_paper_orders_today` UTC/ET edge documented in `KNOWN_BACKLOG.md` (market-hours-gated).
- ✅ **DONE (2026-06-04 eve session) — Funnel evaluation harness.** `analytics/funnel_eval.py` +
  `funnel-eval` CLI: per funnel stage, win-rate/avg-R of KEPT vs DROPPED names over stored outcomes →
  "helps / hurts / neutral / insufficient_data" verdicts. Research only. Tests in `test_funnel_eval.py`.
- ✅ **DONE (2026-06-04 eve session) — Tony teaching / divergence memory layer.** `analytics/tony_divergence.py`
  + `tony-divergence` CLI (writes `reports/tony_teaching_log.json`): grades Tony's verdicts vs the bot's
  outcomes into agreement quadrants (agreed_right/wrong, cc_overrode_saved/missed, pending), reasoning
  preserved verbatim. `/api/command-center` agreement block now falls back to this ledger. Pure separation
  intact — never touches the bot's book. Tests in `test_tony_divergence.py` + `test_api_command_center.py`.
- ✅ **DONE (2026-06-04, after close) — Universe expansion 349 → 548.** Added 199 liquid names via
  `scripts/expand_universe.py`; raised `filters.max_universe_size` 350→600 (loader was truncating);
  suite green (789). Needs an attended pre-open watch restart to go live (see AGENT_STATE "Activation").
  Also fixed tonight: the EOD (16:00) bridge handoff that was silently never firing (slot label
  collision; `eod`→`1600` in `bridge_schedule.py`). Original staged plan below for reference:
- **Universe expansion — staged (tonight, after close).** Grow the scan universe beyond the current
  ~349 (V30) as the paper-outcome dataset grows. Interim step ahead of the full funnel: bump
  `config/universe_swing_research_config.yaml` in a measured stage (e.g. 349 → ~500) with full metadata
  per symbol, then verify rotation still covers the list at acceptable freshness without tripping Alpaca
  rate limits. Tune `watch_universe_rotation` (`max_symbols_per_cycle` / `rotating_bucket_size` / cadence)
  so coverage-vs-staleness stays healthy. NOTE: a raw count bump adds breadth but no new per-symbol data
  quality — the real lift is the staged funnel below, which should drive *which* names get added. Keep
  real-data-only enforcement; default-safe; add a coverage check.
- **Research Funnel v2 (tomorrow, after market).** Staged first-layer pick funnel before Tony:
  FMP screener + earnings calendar, Finnhub news-sentiment, Twelve Data breadth/fallback feeding the
  existing scorer; staged universe growth (350 → 800 → larger); evaluated against the now-live paper
  outcomes. Spec: `docs/superpowers/specs/2026-06-03-research-funnel-design.md`. Default-off, TDD.
- **Paper-trading dashboard surface — clearer paper-traded entries (requested 2026-06-03, after close).**
  Make it obvious on the dashboard which names the bot has actually *paper-traded* vs merely watching.
  Consuming `GET /api/paper/positions` (API ready; Next.js task):
  - Board: a real-P/L cell + a visible "PAPER" / entered badge distinguishing held positions from watch-only
    snapshots, showing fill/entry price, qty, opened-at time, and live unrealized P/L.
  - StatusBar account chip (book label "Trading Bot", open count, realized P/L).
  - Symbol drawer: show the bot's actual paper entry (fill price, time, bracket stop/target) when held,
    separate from the scanner's planned entry.
  Goal: zero ambiguity between "Tony flagged it", "trigger armed", and "bot is in a paper position".
- **Scan-coverage ET date fix.** Coverage buckets scan runs by UTC, so after-hours scans (past UTC
  midnight) show `Universe:0/Scored:0` for the ET report date. Make the filter ET-market-date aware.

---

## Naming clarification

Throughout this project "Tony" in older code, comments, and version notes refers to the **trading bot's internal analyst engine** — the deterministic scoring, self-review, memory summary, and rule suggestion system built into this repo. It is not an LLM agent.

The **Tony Stocks agent** is a separate Claude agent living in the AI Operations Command Center (`C:\Users\alexa\Downloads\AI Operations Command Center`). It does qualitative deep analysis on signals the bot surfaces and is a distinct system. Any roadmap item involving the Command Center or the agent explicitly says so.

---

## Completed — V1 through V37

| Version | What shipped |
|---------|-------------|
| V1–V7 | Core scanner, scorer, OHLCV providers, SQLite storage, Tony event layer, outcome analytics foundation |
| V8–V9.5 | Alpaca IEX adapter, batch fetching, universe rotation, 171-symbol universe |
| V10–V13 | Tony Analyst Engine, Watch Mode, Dashboard Command Center, Hypothesis-to-Outcome tracking |
| V14–V14.7 | Real-data-only enforcement, intraday data foundation, 5Min VWAP/opening-range reads |
| V15–V15.9 | Intraday trigger simulation, Active Tracking fields, frozen original plan at trigger, product dedupe, reassessment labels |
| V16–V16B | Tony memory engine, daily memory summary, New York market-date reporting |
| V17 | Tony self-review (strongest/weakest setup, tomorrow watch) |
| V18–V18A | Rule suggestions (confidence-tagged), safer future-outcome wording |
| V19 | Strategy versioning (v1, v1.1, ...) |
| V20 | Replay summary by setup category |
| V21–V21B | After-market review package, after-hours guard, EOD wording/NaN cleanup |
| V22–V23 | Approval package, approval/reject decision ledger |
| V24–V25 | Strategy proposal package, proposal replay |
| V26–V26D | Unified Watchlist + lifecycle, PATH/ledger fixes, fake-symbol filtering, Results source repair |
| V27–V27A | TRACE-style dashboard redesign, restore product filters after redesign |
| V28 | Tony Signal Scorecard |
| V29 | Scan coverage and scoring funnel report |
| V30 | Universe expansion 171 → 349 symbols |
| V31 | Discovery rotation diagnostics |
| V31A | Coverage vs rotation label consistency |
| V33 | Better skipped/not-scored reason categories |
| V34A | Terminal outcome backend fields (exit price, final P/L, days held) |
| V34B | Code review bug fixes (skip-reason double-count, no_eligible_setup accounting, dashboard error handling) |
| V35 | Backtest CLI — multi-ticker, date range, strategy params, report saving |
| V36B | Lightweight pre-screener funnel (filters before rotation) |
| V37 | Dashboard revamp — 4-tab Professional Slate design (Today / Watchlist / Outcomes / Research) |

**Current state:**
- Universe: 349 symbols | ~345 with bar data | ~98.85% coverage
- Fully scored per cycle: ~140 unique symbols | Scan cap: 175
- Provider: alpaca_iex
- After-market review: working
- Data integrity: V27A filters solid, PATH no longer silently lost

---

## Track A — Trading Bot Core

Improvements to the scanning, scoring, reporting, and dashboard system in this repo.

---

### A-Phase 1 — Stabilize Results and Position Ledger

**V34C — Results organization cleanup** _(next up after B-Phase 1)_
- Separate Active / Closed / Missed Entry / Waiting sections
- Make filters trustworthy, outcome labels clearer
- Closed outcomes freeze final P/L; active positions use live P/L
- Stop/target hit shows exit price + final P/L; entry-never-triggered shows N/A P/L
- Keep TRACE style; do not bypass V26D/V27A ledger filters

---

### A-Phase 2 — Rotation and Coverage Optimization

**V32 — Discovery rotation tuning**
- Always scan: active positions, stale/needs-review, high-priority triggers, core ETFs
- Rotate: four discovery buckets (A/B/C/D) round-robin
- Goal: stop repeating same discovery names every cycle; use 349-symbol universe more efficiently

**V32B — Rotation priority scoring**
- Higher-priority names checked more often; active and stale positions stay protected
- Low-priority names rotate less frequently; no scoring rule changes unless explicitly approved

---

### A-Phase 3 — Better Funnel Intelligence

**V33B — Skip reason refinement**
- Show skip reasons by cycle and by day; separate "not scored" from "not selected"
- Reason buckets: not_enough_bars, avg_volume_below_minimum, dollar_volume_below_minimum, price_outside_range, no_eligible_setup, already_tracked, quarantined, missing_real_data, stale_data, other

**V37B — Scoring eligibility report**
- Why did a stock get ranked high / low / ignored?
- Which score components mattered most? Which warnings lowered confidence?

---

### A-Phase 4 — API and Data Upgrade Planning

**V36 — API upgrade decision report**
- Provider, API requests, symbols requested vs returned, missing/stale/quarantined counts
- Recommendation: no upgrade needed / monitor / upgrade useful soon / upgrade needed

**V36C — Provider comparison plan**
- Compare Alpaca IEX, Alpaca SIP, Polygon, Finnhub, Twelve Data, Financial Modeling Prep
- By: cost, rate limits, real-time depth, historical bars, news, fundamentals, sector data

**V40 — Paid API integration** _(only after reports prove needed)_
- No live trading; keep Alpaca IEX fallback; provider health checks

---

### A-Phase 5 — Universe Expansion

**V38 — Expand to 500–1,000 symbols** _(only after V32 rotation is stable)_

**V39 — Broad screener funnel** _(required before thousands of symbols)_
- Cheap first pass (price/volume/liquidity/trend) → deep scan top candidates only

**V39B — Full-market discovery architecture** _(long-term)_
- 4,000–5,000+ symbols with staged filtering

---

### A-Phase 6 — Strategy Learning System

**V41 — Signal outcome attribution** — use V28 Signal Scorecard; show which signals worked vs failed by dimension

**V42 — Rule suggestion quality upgrade** — minimum thresholds, setup-specific suggestions, stronger "needs more data" logic

**V43 — Proposal replay upgrade** — deeper replay across target/stop/partial/missed/active; still report-only

**V44 — Human-approved strategy version bump** — suggestion → approve → proposal → replay → approve → new version recorded; no live trading

---

### A-Phase 7 — Paper Trading Readiness

**V45 — Paper-trading readiness checklist** — verify frozen entries, clean ledger, risk rules, reports working

**V46 — Paper position simulator** _(no broker)_ — simulate fills/exits/P/L from Tony triggers internally

**V47 — Paper broker adapter** _(only after simulator stable)_ — paper only; risk checks; order logs; duplicate guard

**V48 — Risk rules and kill switch** — max position size, max daily loss, max open positions, max drawdown, emergency stop, manual override

---

### A-Phase 8 — Dashboard Product Polish

**V35B — Reports / Approvals dashboard page** — EOD report, approval package, strategy proposal, signal scorecard, scan coverage all inside dashboard

**V35C — Dashboard health indicators** — last scan, data quality, active positions, ledger gaps, stale warnings

**V35D — Dark TRACE polish pass** _(only after data logic stable)_ — spacing, tables, card hierarchy, color states

---

### A-Phase 9 — Alerts and Automation

**V50 — Local alerting** — entry trigger, stop/target hit, stale tracking, data provider issue, ledger gap; start terminal/file/dashboard, later email/Discord/Slack

**V51 — Scheduled after-market review** — auto-run after close; reports ready when user gets home

**V52 — Morning startup helper** — one command: dashboard + provider health + watch + safety reminders

---

## Track B — Memory and Agent Integration

Obsidian vaults, bridge pipeline, and Tony Stocks agent in the AI Operations Command Center.
Full design spec: `docs/superpowers/specs/2026-05-23-obsidian-memory-layer-design.md`

---

### B-Phase 1 — EOD Memory Layer ← **THIS WEEKEND** ← IN SCOPE

**What gets built:**
- `src/trading_bot/vault/` module: `writer.py`, `bridge.py`, `sector_map.py`
- `vault/` directory in this repo: daily notes (10 sections), signal pages, outcomes, strategy, agent-context
- Bridge export: curated analyst brief → `AI Operations Command Center/bridge/tony-stocks/YYYY-MM-DD.md`
- `scripts/seed_vault.py`: one-time backfill from existing SQLite DB
- `vault:` block in `default_config.yaml`; `--vault-dir` / `--command-center-dir` args on `after-market-review`
- Standalone `export-to-vault` CLI command
- Tests: `test_vault_writer.py`, `test_vault_bridge.py`

No changes to scoring, triggers, rotation, trading logic, or existing tests.

---

### B-Phase 2 — Live Signal Handoff _(next sprint)_

During watch cycles, bot writes live alert to `bridge/tony-stocks/live/` on new high-conviction signal. Tony Stocks agent (Command Center) runs a `/loop` watching that folder, does deep analysis, writes verdict to `bridge/tony-stocks/verdicts/`. Bot reads verdicts next cycle and stores Tony's conviction score + notes in snapshot. Dashboard shows Tony's verdict on Watchlist cards. Latency ~5–10 min — fine for swing trading.

---

### B-Phase 3 — MCP Live Alerts _(future)_

Bot pushes real-time signal alerts via MCP when a signal triggers intraday. Includes entry level, target, stop, R/R, Tony's prior verdict.

---

### B-Phase 4 — MCP Paper Trading _(future)_

Bot initiates and manages paper trades via MCP. Live P/L updates streamed back. Full trade lifecycle in Vault 1.

---

### B-Phase 5 — MCP Live Trading _(future — safety gates required)_

Bot initiates live trades via MCP. All Phase 4 safety gates verified. Explicit human approval gate before any live order. Never enabled by default.

**Forward-compatibility constraint:** Vault 1 ticker page and outcomes schema must accommodate execution fields (fill price, order ID, broker confirmation) from B-Phase 1.

---

## Convergence Points

| Bot track | Memory/Agent track | When they meet |
|-----------|--------------------|----------------|
| A-Phase 7 (paper simulator) | B-Phase 4 (MCP paper trading) | Same paper trading goal, different layers — build together |
| A-Phase 9 (local alerts) | B-Phase 3 (MCP alerts) | Same alerting infrastructure, different delivery |
| A-Phase 6 (strategy learning) | B-Phase 2 (live Tony verdict) | Tony's conviction scores feed strategy learning over time |

---

## Recommended immediate sequence

1. **B-Phase 1** — Vault + bridge (this weekend, markets closed) ← starting now
2. **A-Phase 1 / V34C** — Results organization cleanup
3. **A-Phase 2 / V32** — Discovery rotation tuning
4. **B-Phase 2** — Live signal handoff to Tony Stocks agent
5. **A-Phase 3** — Better funnel intelligence
6. **A-Phase 6** — Strategy learning system
7. **A-Phase 7 + B-Phase 4** — Paper trading (converged)
