# Design Spec — Research Funnel v2 (multi-stage pre-Tony pick layer)

**Date:** 2026-06-03
**Status:** Draft for review
**Scope:** Expand the bot's *first layer* — how it goes from a large universe to a
short, high-quality watchlist — before handing off to Tony (the Command Center) and
the now-live paper-trading loop. Adds FMP / Finnhub / Twelve Data as research inputs.

## Why now
Paper trading records **real outcomes** (`tony_stocks_outcomes.json` + `paper_positions`).
That makes every first-layer change **measurable** — we can A/B a funnel tweak against
actual paper win-rate instead of guessing. The current first layer is the weak link:
~349 hand-curated symbols, a single price feed (Alpaca IEX), and **no fundamental or
catalyst signal** before scoring.

## Current state
`load_universe` (~349) → `pre_screen_universe` (price/volume from cached scan rows) →
`WatchUniverseRotator` (≤175/cycle) → technical scoring (trend/momentum/volume/risk/
setup) → snapshots → bridge → Tony. One price source; no fundamentals/news/earnings.

## Target funnel (cheap → expensive per symbol)
1. **Universe (1,000s)** — FMP **stock screener** pulls a large liquid set
   (price > $5, ADV/$-vol band, mkt-cap band, optional sector spread) instead of a
   hand-curated list. Cache daily.
2. **Cheap bulk screen** — price / dollar-volume / relative-strength vs SPY +
   **earnings-blackout** (drop names reporting within N days) → top few hundred.
3. **Catalyst / quality filter** — Finnhub **news sentiment** + recommendation trend +
   a light fundamental sanity gate (no negative-growth junk) → annotate + rank.
4. **Technical scoring (existing engine)** — runs only on survivors (keeps API cost sane).
5. **Hand-off** — bridge → Tony deep dive → paper trades → **outcomes** (evaluation).

## Provider roles (keys already in `.env`)
- **FMP** — wide screener, fundamentals, **earnings calendar**, analyst estimates →
  stages 1-3 (the screen + quality gate + earnings blackout).
- **Finnhub** — news + **news sentiment**, recommendation trends, insider, earnings →
  stage 3 (catalyst layer).
- **Twelve Data** — broad price/indicator coverage → **breadth + fallback price source**
  (reduces single-feed Alpaca dependency).

## Architecture
- Extend the existing provider-adapter pattern (`data/market_data.py`) with thin
  adapters: `FmpProvider`, `FinnhubProvider`, `TwelveDataProvider`. Each behind a
  capability interface (`screen()`, `fundamentals()`, `news_sentiment()`,
  `earnings_calendar()`, `quote()` as applicable).
- **One consistent price source for *scoring*** (keep Alpaca/Twelve as the scoring feed;
  use the others for enrichment/breadth/fallback only — never mix feeds mid-score).
- Caching + rate-limit layer per provider (daily fundamentals/screener cache; respect
  free-tier limits). Provider-failover so a down API degrades, not breaks.
- New `data/research_funnel.py` orchestrating the stages with a `FunnelResult` carrying
  per-stage counts (universe → screened → catalyst-passed → scored) for EOD diagnostics.

## Phased plan (each phase: tests + commit)
1. **Provider adapters** (TDD with recorded fixtures / mocks; no live calls in CI):
   FMP screener + earnings, Finnhub news-sentiment, Twelve Data quotes. Behind flags.
2. **Funnel orchestration** — pure `build_funnel(...)` staging logic (universe → screen →
   catalyst → shortlist), fully unit-tested with synthetic provider outputs.
3. **Wire into `run_watch`** behind a `research_funnel.enabled` flag (default off); funnel
   feeds the rotator's universe. Diagnostics in the EOD report (stage counts).
4. **Staged universe growth** — 350 → 800 → larger, watching coverage + API cost + scan
   time each step. No jump to thousands without the screener funnel in front.
5. **Evaluation harness** — compare paper win-rate / outcome quality **with vs without**
   each funnel stage (uses the live outcomes). This is the payoff: data-driven funnel.

## Other first-layer ideas (backlog)
- Market-regime gate on the bot side (VIX/SPY) mirroring the CC's regime read.
- Sector diversification cap (avoid 5 correlated names).
- Multi-timeframe confirmation; ADV/liquidity floor; gap/halt filters.

## Guardrails
- Research only; no profitability claims. Real-data-only rules still apply.
- Keep scoring feed consistent; enrichment feeds are advisory.
- Everything behind flags, default off; TDD; staged rollout.
- Respect free-tier rate limits (cache aggressively; batch where possible).

## Open questions (settle at execution start)
- Universe definition for FMP screener (which mkt-cap / liquidity bands)?
- Earnings-blackout window (N days before/after)?
- Is news-sentiment a *filter* (drop) or only a *rank/annotate* signal at first?
- Target universe size for stage 1 of the rollout (800? 1500?).
