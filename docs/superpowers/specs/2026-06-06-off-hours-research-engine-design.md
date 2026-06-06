# Off-Hours Research Engine ("Pre-Open Prep") — Design Spec

_Date: 2026-06-06 · Branch: `feat/off-hours-research` · Status: design (awaiting spec review)_

## 1. Purpose

During market hours the bot can only afford a rate-limited rotating scan. The off-hours
window — **weekdays 16:30→09:00 ET and all weekend** — is currently dead time (the watch
loop just sleeps). This engine uses that window to do every bit of prep that can't happen
live, so a **ranked, catalyst-aware, freshly-recalibrated Morning Watchlist + plan** is
waiting at the next open.

## 2. Hard safety invariants (non-negotiable)

1. **No off-hours auto-entry, EVER.** The engine *prepares* entries (armed watchlist +
   planned levels) but contains **no execution path**. It never imports or calls
   `execution.paper_engine.run_paper_cycle`, any broker, or order submission. Actual entry
   (paper now, real money later) happens **only during regular market hours** via the
   existing live watch loop. An order can never originate off-hours. Enforced by a guard
   test asserting the off-hours orchestrator never touches the broker/paper engine.
2. **Read-only on trading.** No live trading, no config/threshold/risk edits. Divergence
   calibration only *surfaces* human-gated proposals; the two-key `activate-strategy-version`
   path stays manual and untouched.
3. **Real-data-only.** Daily bars from Alpaca; demo-data guard respected. No synthetic data
   in any prep artifact.
4. **Fail-quiet per sink.** Every sink write is independently guarded; one bad sink never
   crashes the loop or aborts the others (mirrors `run_learn`).
5. **Pure CC separation preserved.** The Command Center handoff is a one-way bridge file
   only. The bot never reads/acts on a live CC verdict in this engine.

## 3. Architecture

Follows the established project pattern: **pure cores in `analytics/`, data adapters in
`data/`, orchestration in `cli.py`, fail-quiet sinks**. ~80% reuse of existing machinery.

### 3.1 New pure cores (fully unit-tested)

- **`analytics/off_hours_window.py`** — inverse of the market-hours guard.
  - `is_off_hours(now_et) -> bool`: True on weekdays 16:30–09:00 (next day) and all weekend.
  - `current_phase(now_et) -> Phase`: `post_close | overnight | pre_open | weekend | market_hours`.
  - `next_market_open(now_et) -> datetime`.
  - Pure, timezone-aware (`America/New_York`), holiday-aware via existing market calendar if
    available (degrade gracefully to weekday logic).

- **`analytics/catalyst_enrichment.py`** — pure. Given injected provider outputs, builds a
  per-symbol `CatalystTags`: `upcoming_earnings_date`, `earnings_blackout` (bool, within N
  days), `analyst_rec_trend` (up/down/flat from Finnhub recommendation deltas),
  `news_sentiment` (if available), `revenue_growth`. No HTTP in the core — providers are
  passed in. Missing provider data → tags simply absent (never an error).

- **`analytics/morning_prep.py`** — pure assembler. Combines:
  deep-scan ranked candidates + catalyst tags + overnight learning facts + open paper
  positions (read-only) + calibration proposals + (optional) pre-market gaps →
  a `MorningPrep` dataclass: ranked names each with `{symbol, score, setup, entry, stop,
  target, rr, conviction, catalysts, warnings}`, a `what_changed_overnight` block, and a
  `plan_for_open` summary. Pure and deterministic; LLM narration is layered on top, never
  inside.

- **`data/premarket_provider.py`** — the pluggable seam (start-the-process, stub now).
  - `PreMarketProvider` protocol: `get_premarket_quote(symbol) -> PreMarketQuote | None`.
  - `NullPreMarketProvider` — used now; returns `None` so gap data is simply skipped.
  - Documented `AlpacaSipPreMarketProvider` / `PolygonPreMarketProvider` placeholders for
    later. The assembler accepts an injected provider, so a real pre-market feed is a
    one-line wiring change with zero core changes.

### 3.2 Reused as-is (orchestrated, not rewritten)

`run_scan` (called with the **full universe**, paced to respect Alpaca limits — off-hours has
no live-cadence pressure), `data/research_providers.py` (FMP/Finnhub/Twelve Data adapters),
`run_learn` (nightly learning), `tony-divergence` (teaching-log rebuild),
`divergence_calibration` (surface proposals), `funnel_eval` (`--save-report`),
`emit-outcomes`, `learning_narrator` (LLM briefing with deterministic fallback), the vault
writers + bridge pattern + FastAPI route pattern.

### 3.3 Orchestration — inverse-watch loop

- **`off-hours-watch` CLI** = symmetric mirror of the live watch loop. Wakes on a slow
  cadence (default 30 min), checks `current_phase`, runs the due phase if not already done
  this ET day (disk-idempotent, like `_emit_due_bridges`), sleeps during `market_hours`.
  This is a **separate process** from the trading watch loop and has **no paper-engine
  wiring** (invariant #1).
- **`off-hours-prep` CLI** = one-shot manual regeneration of the full plan, runnable anytime.
- `scripts/register_off_hours_task.ps1` registers the loop as a Windows scheduled task.

### 3.4 Phased checkpoints inside the window (disk-idempotent per ET day)

| Phase | Time (ET) | Work |
|-------|-----------|------|
| `post_close` | ~16:35 weekdays | `emit-outcomes` → deep full-universe daily-bar scan on the day's closes → initial shortlist + catalysts → write all sinks |
| `overnight` | ~02:30 | `run_learn` + `tony-divergence` + `divergence-calibration` + `funnel-eval` on settled data → re-assemble with "what we learned" → rewrite sinks |
| `pre_open` | ~08:15 weekdays | final catalyst refresh (earnings confirmed, rec changes; later pre-market gaps) → finalize Morning Watchlist + briefing + bridge |
| `weekend` | Sat + Sun afternoon | full pipeline so Monday is prepped |

## 4. Sinks (all four, each fail-quiet)

- **File:** `reports/morning_prep/<ET-date>.json` + a markdown summary alongside.
- **Vault:** `vault/morning_prep/<ET-date>.md` via new `vault/morning_prep_writer.py`
  (mirror of `vault/learning_writer.py`). Obsidian-linked to signal pages.
- **Bridge:** `{command_center_dir}/bridge/tony-stocks/morning-prep/<ET-date>.md` + a new
  contract `docs/CONTRACTS/morning-prep-bridge.md` (one-way; pure separation). The CC's Tony
  agent ingests the pre-open plan for deep analysis.
- **Dashboard:** `GET /api/morning-prep` (FastAPI route, reads the JSON artifact, never
  writes) + a new Next.js `/morning` "Morning Prep" tab consuming it. The tab clearly labels
  every name as **PLANNED** (not entered) to reinforce invariant #1 visually.

LLM briefing prose (via `learning_narrator` pattern) is written from VERIFIED `MorningPrep`
facts only, with deterministic template fallback on any error/missing key — never fails the run.

### 4.1 Artifact shape (`reports/morning_prep/<ET-date>.json`)

ET market date format `YYYY-MM-DD`. Synthetic example (numbers are placeholder zeros):

```json
{"generated_at": "2026-06-08T08:15:00-04:00", "et_date": "2026-06-08", "phase": "pre_open",
 "shortlist": [{"symbol": "NVDA", "score": 0.0, "setup": "Breakout Watch", "entry": 0.0,
   "stop": 0.0, "target": 0.0, "rr": 0.0, "conviction": "medium",
   "catalysts": {"upcoming_earnings_date": null, "earnings_blackout": false,
     "analyst_rec_trend": "flat", "news_sentiment": null, "revenue_growth": null},
   "warnings": []}],
 "what_changed_overnight": "string", "plan_for_open": "string"}
```

## 5. Config

New `off_hours:` block in `config/default_config.yaml` (and `ScannerSettings.off_hours`):
`enabled` (default false), `cadence_minutes`, phase times, `earnings_blackout_days`,
`shortlist_size`, `full_universe_scan` (bool), `premarket_provider` (default `null`),
`enrich_budget`. Default-off and inert until explicitly enabled + scheduled.

## 6. Testing

- **Pure cores:** `test_off_hours_window.py`, `test_catalyst_enrichment.py`,
  `test_morning_prep.py`, `test_premarket_provider.py` (Null path),
  `test_morning_prep_writer.py`.
- **Safety guard:** `test_off_hours_no_execution.py` — asserts the off-hours orchestrator
  never imports/calls the broker or `run_paper_cycle` (invariant #1), and that
  `is_off_hours`/`should_trade` keep entries market-hours-only.
- **Orchestrator e2e:** `test_off_hours_e2e.py` in a throwaway temp sandbox (mirror
  `test_learning_e2e`): runs a full phase, asserts all four sinks written, idempotency on
  re-run, and **zero mutation of the real workspace** (sha256 fingerprint before/after).
- **API smoke:** `GET /api/morning-prep` in `test_api_morning_prep.py`.
- **Frontend:** `tsc --noEmit` clean for the `/morning` tab.

## 7. Out of scope (deliberate)

- Real pre-market data feed (seam built + stubbed; wiring a paid provider is a later task).
- Any off-hours execution / auto-entry (forbidden by invariant #1).
- Changing the live watch loop's behavior (the two loops are independent processes).

## 8. Build order (for the implementation plan)

1. `off_hours_window` core + tests.
2. `premarket_provider` seam (Null) + tests.
3. `catalyst_enrichment` core + tests.
4. `morning_prep` assembler core + tests.
5. `morning_prep_writer` (vault) + bridge contract + tests.
6. CLI orchestration (`off-hours-prep`, `off-hours-watch`) + config + safety guard test.
7. e2e sandbox test.
8. API route + smoke test.
9. Next.js `/morning` tab + tsc.
10. `register_off_hours_task.ps1` + docs (AGENT_STATE, ROADMAP).
