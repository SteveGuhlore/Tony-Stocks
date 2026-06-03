# Design Spec — Tony Dashboard Overhaul ("The Cockpit")

**Date:** 2026-06-02
**Status:** Draft for review
**Author:** brainstorming session (Stephen + Claude)
**Scope:** Full UI/IA overhaul of `dashboard-web` (Next.js 16 / React 19 / Tailwind 4)
**Companion mockups:** `.superpowers/brainstorm/1587-1780441694/content/*.html` (screens 01–12)

---

## 1. Problem

The current dashboard is 7 pages (Today, Watchlist, Picks, Outcomes, Scan, Analytics, System) that overlap heavily — four of them (Today / Watchlist / Picks / Outcomes) are different slices of the same "tracked setups" data, and Scan overlaps Watchlist. The user has to tab-hop to assemble a single thought. The visual language is a generic neon-cyan-on-black "AI terminal." The user wants a fresh-slate, simpler, denser, more intentional cockpit built up from what the data actually is.

## 2. Product truth (what the dashboard is)

This is **Tony's cockpit**. Tony is a first-pass agent that scans the live market every 5 minutes, scores candidates, sets entry/stop/target, writes a thesis, and **makes picks** — then tracks his own paper record. His picks are the product.

A **second, independent agent** — "Tony Stocks" in the Command Center — consumes Tony's picks (it does **not** scan the market), does deeper web research / financials / company analysis, produces **its own score and verdict** (reaffirm / adjust / close / override), and tracks **its own** record. The two agents race each other; over time we learn whether the second pass improves outcomes. Records are paper now; the system is designed so a real-money ledger can layer on later.

**The flywheel:** Scan → Pick (score + plan + thesis) → Track (target/stop) → Hand off to Command Center (verdict + 2nd record) → Learn → better picks. The UI is shaped like this loop, not like a pile of tabs.

## 3. Goals / Non-goals

**Goals**
- Collapse 7 overlapping pages into **2 surfaces + 1 deep-dive + an ambient rail**.
- Make **Tony's picks the unmistakable hero**, scannable in high volume.
- Surface **both agents** per pick (dual score + verdict) and over time (two records racing).
- Show **live price + P/L** wherever applicable, never confusing daily change with P/L-vs-entry.
- A deliberate **anti-"AI-generic" visual system**: warm ink base, single restrained accent, color = meaning only.
- Degrade gracefully where second-layer (Command Center) data isn't wired yet.

**Non-goals**
- No real-money execution / brokerage integration in this overhaul (design leaves room for it).
- No "expected time to target" projection line yet (no ETA data exists; slot deferred).
- No profit claims; Track Record stays research-framed.
- Not rebuilding the Command Center's own surface — only reflecting its verdict/score/record here.

## 4. Information architecture

| New surface | Replaces | Purpose |
|---|---|---|
| **① The Board** (home, `/`) | Today, Watchlist, Picks, Scan | Tony's live scored picks as a dense table ("The Tape"); toggle Watches ↔ full scanned Universe |
| **② Track Record** (`/record`) | Outcomes, Analytics | Two-record scoreboard: Tony vs Tony Stocks, equity, agreement matrix, breakdowns |
| **↳ Ticker deep-dive** (slide-over) | (elevates SymbolDrawer) | "Why he picked it" — dual analysis, chart-with-plan, pick timeline |
| **· Ambient status rail** (persistent header) | System | Scanning state, market clock, KPIs, events bell |

Old nav (52px emoji icon-rail sidebar) is replaced by the **ambient status bar** at top + 2 nav items. `System` data shrinks into the status bar (with an optional detail popover); it is no longer a page.

## 5. Surface specs

### 5.1 The Board ("The Tape") — screens 06, 08

**Ambient status bar (top):** Tony wordmark + live scanning dot ("scanning · last 2m ago") · market clock (open/closed + time) · KPI cluster (Watching N · Triggered N · Win %) · events bell with unacked count.

**Sub-header:** `Watches · N ↔ Universe · N` segmented toggle · sort control (default: Tony score desc) · setup-category filter chips (All / Breakout / Pullback / Momentum / …).

**Universe view (leaner, scan-audit):** when toggled to Universe, the table switches to a leaner column set appropriate to un-picked names — **Ticker · Last·Day · Tony score · setup category · R:R · top reasons/tags** — dropping the pick-only columns (P/L, Plan Rail, Verdict, Status) that have nothing to show pre-pick. Columns intentionally differ between modes because Watches answers "how are my picks doing" and Universe answers "what is the scanner seeing."

**Table columns (left→right):**
1. **Ticker** (bold) + tiny sector/universe-role sub-label
2. **Last · Day** — live price; small grey "% day" (vs prev close) beneath it
3. **P/L** — % vs Tony's entry, shown only once triggered; else "near entry" / "—"
4. **Plan (the Rail)** — horizontal ladder stop→entry→target with a glowing live-price marker; exact stop/entry/target labels under the ends; numbers also on hover. Pre-entry rows render a dim/dashed rail with no marker.
5. **R:R**
6. **Tony** score (accent azure)
7. **T.STK** score (Command Center; "⋯" when awaiting)
8. **Verdict** — ✓ reaffirm / ◐ adjust / ⊘ override / ✕ close / ⋯ awaiting
9. **Status** — ▲ triggered / ◉ armed / ○ watching / ✕ closed

Row states designed: triggered+profit, triggered+loss, armed near-entry, watching pre-entry/awaiting-CC, overridden→closed. Row click → ticker deep-dive. Selected row gets a left accent border + raised background.

### 5.2 Ticker deep-dive (slide-over) — screen 09

Slides from the right; Board dims behind. Sections:
- **Header:** ticker, name, sector, setup type; in-trade time + handoff age; live price + "% day" + P/L; a larger Rail with exact stop/entry/target + R:R.
- **Chart** (see 5.3).
- **Dual analysis (two columns):**
  - *Tony · first pass:* score + four sub-score bars (Trend / Momentum / Volume / Risk), thesis prose, ✓ reasons, ⚠ warnings.
  - *Tony Stocks · Command Center:* score + verdict + its own reasoning (financials / earnings window / web research) + "returned X after handoff". Degrades to "⋯ awaiting handoff" when absent.
- **"This pick's life" timeline:** scanned → picked → armed → triggered → CC verdict, with timestamps.

### 5.3 The deep-dive chart — screens 10, 11

- **What it is:** the ticker's daily OHLC price history (default 60 days, from `symbolChart`) with Tony's **stop / entry / target drawn as horizontal plan lines**.
- **Render:** candlesticks + a volume strip (default), with a one-tap toggle to a calm closing-price line/area. Candles chosen because they expose the volume thrust + momentum Tony scores on.
- **Axes & readout (always on):** price axis (right), date axis (bottom), and a crosshair that reads out date + OHLC on hover.
- **Deferred:** "expected time to target" projection line — **not built** (no ETA data emitted by Tony yet). Leave a clean extension point; do not render false-precision forecasts.

### 5.4 Track Record (`/record`) — screen 12

- **Two-record header:** Tony vs Tony Stocks — win rate, avg R, target hits, stop hits.
- **Overlaid equity curves:** both agents' simulated paper equity on one chart, since-date labeled.
- **Agreement matrix ("does the 2nd pass help?"):** agreed&right / agreed&wrong / CC-overrode&saved / CC-overrode&missed + a one-line net read.
- **Breakdown:** Tony win rate by setup category (extensible to score bucket / universe role from existing backtest data).
- **Disclaimer:** research-only / simulated / not advice / past ≠ future — always visible.

## 6. Visual system (anti-AI)

Replace the cyan-on-pure-black tokens. Proposed palette (final values tuned during build):

| Token | Value | Use |
|---|---|---|
| `--bg-base` | `#0a0c10` | warm ink, not pure black |
| `--bg-surface` | `#0c0f14` | bars, panels |
| `--bg-elevated` | `#0e1218` | selected rows, cards |
| `--border` | `#1a1f27` / `#14181f` | dividers |
| `--text-primary` | `#e8ebf0` | values |
| `--text-secondary` | `#9aa3b2` | labels |
| `--text-tertiary` | `#5f6776` | micro-labels |
| `--accent` (Tony) | `#5b9dff` (azure) | Tony score, live marker, selection |
| `--brass` | `#c7ad6a` | market/alert/armed state |
| `--green` | `#36d399` | P/L+, target, reaffirm |
| `--red` | `#ff6363` | P/L−, stop, override/close |
| `--amber` | `#e0a64d` | adjust / caution |

Principles: **color carries meaning only** (P/L, verdict, plan levels). Numbers are tabular monospace; identity/labels are sans (Geist). Dense but every row breathes (≈ generous row height vs today's 28px). Keep existing a11y posture (focus-visible rings, reduced-motion, WCAG-checked contrasts) — re-verify against the new palette.

## 7. Data model & backend dependencies

**Already served** (`lib/api.ts`): today, picks, tracking, outcomes, scan/latest + overview, analytics/backtest, events (+ SSE stream), system/health, symbol detail + chart, prices (+ per-symbol), vault bridge.

**Sufficient for v1 of:** the Board (Tony layer), deep-dive (Tony layer + chart), Track Record (Tony layer), ambient rail, live prices/SSE.

**Missing — required for the second (Command Center) layer:** structured Tony Stocks output per pick (score, verdict enum, reasoning, returned-at) and the second record (win rate, avg R, equity series) + agreement-matrix tallies. Today only an unstructured text "vault bridge" exists.

→ **Decision:** build all second-layer UI slots now, reading from a typed contract; render **"⋯ awaiting handoff"** / hide comparison panels when the data is absent. A backend task to expose Command Center output structurally is a **dependency, tracked separately** — the frontend overhaul does not block on it and must not break without it.

## 8. Component mapping

- **Keep / refactor:** `MarketClock`, `LivePrice`, `useLivePrices`, `useMarketStatus`, `useAlerts`, `sse.ts`, `ScanTable`→Board table, `SymbolDrawer`→deep-dive, `EquityCurve`/`ScoreBreakdown` (recharts) → Track Record + sub-scores, `ToastStack`/`AlertManager`/`PermissionBanner` (alerts).
- **New:** `StatusBar` (ambient rail), `BoardTable` + `PlanRail` (the rail cell), `VerdictChip`, `DualScore`, `DeepDive` (compose), `PlanChart` (candles+volume+axes+crosshair+plan lines), `TwoRecordHeader`, `AgreementMatrix`, `UniverseToggle`.
- **Remove pages:** `app/today`, `app/watchlist`, `app/picks`, `app/scan`, `app/outcomes`, `app/analytics`, `app/system` → consolidated into `app/(board)` home + `app/record`. Old `Sidebar` replaced by `StatusBar`.
- **Inline-styles → tokens:** migrate the pervasive `style={{}}` usage toward the token system / Tailwind utilities for consistency (scoped to touched files; not a blanket refactor).
- **AGENTS.md note:** this is a modified Next.js — read `node_modules/next/dist/docs/` before writing app code; heed deprecations.

## 9. Risks & guardrails

- **No profit claims.** Track Record stays "simulated / research / past ≠ future."
- **No false precision.** ETA projection deferred until real horizon data exists.
- **Don't bypass risk rules / enable live trading.** Design is read-only/advisory; no order entry.
- **Graceful degradation** is a hard requirement, not a nicety — every Command Center slot must render sanely empty.
- **Density vs accessibility:** keep ≥ WCAG AA contrast and ≥44px coarse-pointer targets even while dense.
- **Scope creep:** real-money ledger, projection line, and CC backend contract are explicitly out of this overhaul.

## 10. Testing checklist

- Board renders all five row states from fixture data; day-% vs P/L never swapped; Rail marker position math correct (stop/entry/target/live).
- Watches ↔ Universe toggle, sort, and filter chips work and are keyboard-operable.
- Deep-dive opens/closes (click + Esc + focus trap), shows dual analysis, degrades when CC data absent.
- PlanChart: candles, volume, axes, crosshair readout, plan lines; line-toggle; reduced-motion respected.
- Track Record: two-record header, overlaid equity, agreement matrix, setup breakdown; disclaimer always present.
- Live prices/SSE update without layout shift; "scanning" dot reflects watch status.
- a11y: contrast re-checked on new palette; focus-visible rings; 44px coarse targets. Responsive: desktop dense, tablet/phone reflow (table → stacked rows).
- No regression in existing API consumption; demo-mode (no keys) still renders.

## 11. Phasing (suggested for the plan)

1. Visual tokens + `StatusBar` + app shell / routing collapse.
2. `BoardTable` + `PlanRail` + Universe toggle (Tony layer, live prices).
3. `DeepDive` + `PlanChart` (Tony layer + chart).
4. `TrackRecord` (Tony layer).
5. Second-layer (Command Center) slots + degradation, behind the typed contract.
6. Polish: motion, empty/error states, responsive, a11y re-verification.

## 12. Resolved decisions / open questions

**Resolved:**
- **Routes:** `/` *is* the Board (no redirect); Track Record at `/record`.
- **Universe columns:** leaner scan-audit set (see §5.1), distinct from Watches.

**Still open (can settle during planning):**
- Status-bar "System" detail: popover vs a thin expandable strip? (lean: popover)
