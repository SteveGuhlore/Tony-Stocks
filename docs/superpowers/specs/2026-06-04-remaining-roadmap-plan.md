# Remaining Roadmap — One Clean Implementation Plan (next session)

**Created:** 2026-06-04 (after close). **Purpose:** Execute all remaining roadmap items in
**one focused session**, in the order below. **Paper-trading dashboard is LAST** (per operator).
Each step is self-contained: goal → files → approach → tests → commit. Default-safe, TDD,
real-data-only. Do code changes **after the 16:00 ET close**; never restart the live watch
loop during market hours.

## Current live state (as of this handoff)
- Watch loop **PID 40324**, funnel **ENABLED** (universe 543 → 542 shortlist; 1 earnings drop;
  ranked by analyst recommendation; `enrich_limit: 50`, `use_news_sentiment: false`,
  `earnings_blackout_days: 5`). Launched with `PYTHONUNBUFFERED=1` (logs stream).
- Paper sizing **now matched 1% of each account**: bot `max_notional_per_position: 1000` (1% of $100k);
  **CC = $10,000 (1% of $1M)**. Bracket TIF **gtc**; 31 carried $5k positions running off; all protected.
- Keys (live-tested): Twelve Data ✅, Finnhub recommendation ✅, FMP earnings + revenue-growth ✅
  (`/stable` API). Premium/paid gaps: Finnhub news-sentiment (403), FMP company-screener (402).
- `main` @ `b2a35e1`+. Full suite **824 passing**. Parity: `docs/CONTRACTS/execution-parity.md`.

---

## Build order

### 1. Funnel enrichment scaling (fix Finnhub 60/min without slow startup)
**Goal:** recommendation-rank the *whole* shortlist, not just the first `enrich_limit: 50`.
**Why:** at 50, only the first 50 symbols get a recommendation score; the rest rank at 0.
**Approach:** incremental **daily cache** + per-run budget, not a startup burst.
- New `reports/finnhub_reco_cache.json` (or a `repo` table): `{symbol: {score, fetched_date}}`.
- `gather_funnel_signals`: read cache first; only fetch symbols whose cache is stale/missing,
  capped at a per-run budget (e.g. 50) so each cycle warms ~50 more → full universe covered over a
  few cycles, never bursting the 60/min limit.
- Optional: a small token-bucket limiter in `research_providers` for safety.
**Files:** `src/trading_bot/data/research_providers.py`, cli funnel block, `config` (`enrich_per_run`).
**Tests:** cache hit skips fetch; budget respected; stale entries refetched. Extend `test_research_providers.py`.

### 2. Scan-coverage ET-date fix
**Goal:** coverage / `today_events` bucket by **ET market date**, not UTC, so after-hours scans
(past UTC midnight) stop showing `Universe:0/Scored:0` for the ET report date.
**Approach:** convert `scan_run.created_at` (UTC) → America/New_York date before bucketing; filter
"today" by ET market date.
**Files:** locate the coverage/scan-funnel builder (`analytics.py` and/or `cli` eod path — grep
`scan_coverage` / `percent_universe_covered_today`). Centralize an ET-date helper.
**Tests:** a scan_run at 2026-06-04T02:00Z (after-hours ET 2026-06-03) buckets to 2026-06-03 ET.

### 3. Funnel evaluation harness (the payoff)
**Goal:** measure **does each funnel stage help?** — paper win-rate / outcome quality **with vs
without** the screen, earnings-blackout, and recommendation rank, using the live outcomes.
**Approach:** pure replay over stored snapshot+outcome history: for each stage toggled on/off,
compute win-rate / avg-R on the resulting shortlist. Report a per-stage delta table.
**Files:** new `src/trading_bot/analytics/funnel_eval.py` (pure) + a `funnel-eval` CLI; reads
`tony_stocks_outcomes.json` + snapshot history. **Tests:** synthetic outcomes → known deltas.
**Guardrail:** research only; no profitability claims.

### 4. Tony teaching / divergence memory layer
**Goal:** when bot and CC disagree (Tony pass/override/adjust vs the bot's action), record the
divergence and grade it against the realized outcome — build a memory of *who is right when*.
**Spec:** `docs/superpowers/specs/2026-06-03-tony-teaching-divergence-design.md` (implement per that).
**Approach:** join CC verdicts (`tony_stocks_verdicts.json`) with bot outcomes on (symbol, pick_date);
classify each as agreed-right / agreed-wrong / cc-overrode-saved / cc-overrode-missed; persist a
rolling divergence ledger; feed the existing `agreement` block on `/api/command-center` ("does the
2nd pass help?" matrix). **Tests:** synthetic verdict+outcome pairs → correct quadrant tallies.

### 5. ✅ DONE — CC sizing aligned to $10k (parity complete)
CC now uses **$10,000/position (1% of $1M)**, matching the bot's $1k (1% of $100k). The head-to-head
is a clean 1%-of-account A/B. (`execution-parity.md` updated — no further action.)

### 6. (DECISION) Auto-universe growth — FMP screener is paid
The dynamic-universe engine (FMP `company-screener`) returns **402 (paid tier)**. Options:
(a) upgrade FMP to unlock the screener → funnel sources 1,000s dynamically; (b) alternative free
screener; (c) keep staged-manual growth via `scripts/expand_universe.py` (548 → 800 → …).
**No code until the operator picks a path.**

### 7. LAST — Paper-trading dashboard surface (Next.js)
**Goal:** make paper-traded names unmistakable on the dashboard.
- Board: "PAPER"/entered badge + real-P/L cell (fill price, qty, opened-at, live unrealized P/L).
- StatusBar: account chip (label, open count, realized P/L).
- Symbol drawer: actual paper entry (fill/time/bracket) vs the scanner's planned entry.
**Data:** `GET /api/paper/positions` (already serves this).
**⚠️ Caveat:** `dashboard-web/AGENTS.md` — "this is NOT the Next.js you know"; read
`node_modules/next/dist/docs/` before writing frontend code.

---

## Conventions for the executing session
- Branch off `main`; TDD; run the full suite (`scripts/run_tests.ps1`) green before commit.
- After-close only for any watch-loop restart; verify funnel + sizing in the startup log.
- Update `AGENT_STATE.md` before handoff.
