# Picks / Positions Redesign

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the dashboard into three clearly-purposed surfaces — Today (quick summary), Watchlist (compact scannable table of all monitored stocks), and a new Picks page (rich position tracker with P&L, risk gauge, time in trade, and bot thesis).

**Architecture:** New `/picks` route with `PositionCard` component that renders in two modes — "triggered" (in trade, shows P&L) and "watching" (awaiting entry, shows distance to entry only). Watchlist page becomes a dense table. Today page drops big TradeCards in favour of slim two-line summary rows.

**Tech Stack:** Next.js 15 App Router, TanStack Query v5, TypeScript, inline CSS (project convention), `useLivePrices` hook for live data.

---

## Page Map (after this change)

| Route | Purpose | Key change |
|---|---|---|
| `/today` | Quick-glance summary | Replace TradeCards with slim `ActivePositionRow` list |
| `/watchlist` | All monitored stocks | Replace TradeCards with compact `WatchlistTable` |
| `/picks` | Position tracker | **New page** with rich `PositionCard` per pick |

---

## Data Model

All data already available — no new backend endpoints needed.

### Bot picks (triggered)
Source: `api.tracking()` → `active[]` filtered to `entry_triggered === true`
Fields used: `symbol`, `status`, `setup_category`, `entry`, `stop`, `target`, `risk_reward`, `total_score`, `entry_triggered_at`, `tony_hypothesis`, `tony_recommended_action`, `tony_priority_label`

### Bot picks (watching, not yet entered)
Source: `api.tracking()` → `active[]` + `watching[]` where `entry_triggered === false`
Fields used: same minus `entry_triggered_at` (use `snapshot_time` as "watching since")

### Manual picks
Source: `api.picks()` → `picks[]`
Fields used: `symbol`, `status`, `planned_entry`, `planned_stop`, `planned_target`, `picked_at`, `notes`
Triggered detection: `status === "active"` or `status === "triggered"`

### Live price
Source: `useLivePrices()` → `Record<string, LiveQuote>` keyed by symbol
Used for: current price, P&L computation, gauge marker position

---

## P&L and Gauge Logic

### P&L (triggered picks only)
```
pnl_pct = (live_price - entry) / entry * 100
```
- Positive → green, prefix `+`
- Negative → red, no prefix
- **Never shown for watching picks** — no entry has occurred

### Risk gauge position (0–100% across the bar)
The bar spans `stop` → `target`. The "now" marker position:
```
marker_pct = clamp((price - stop) / (target - stop) * 100, 0, 100)
entry_pct  = clamp((entry - stop) / (target - stop) * 100, 0, 100)
```
The entry line is always drawn on the bar. The marker is coloured:
- `price < entry` → amber (in risk zone, haven't hit target yet)
- `price >= entry` → green (in profit zone)
- `price <= stop`  → deep red (at or below stop)

### Watching gauge (no entry triggered)
The bar still spans stop → target but is styled differently:
- Gauge is muted (dim colours)
- Entry line is the goal line, drawn as a dashed vertical
- Marker shows live price position approaching entry
- No fill — just the marker dot
- Label below: "X% to entry" in amber

### Time in trade
```
triggered:        duration(now - entry_triggered_at)  → "3d 14h in trade"
watching (bot):   duration(now - snapshot_time)        → "watching 2d"
manual triggered: duration(now - picked_at)            → "3d 14h in trade"
manual watching:  duration(now - picked_at)            → "watching 2d"
```
Format: show `Xd Yh` if ≥ 1 day, else `Xh Ym` if ≥ 1 hour, else `Xm`.

---

## Components

### New: `components/picks/PositionCard.tsx`
Props:
```typescript
interface PositionCardProps {
  symbol: string
  status: string
  setupCategory: string | null
  entry: number | null
  stop: number | null
  target: number | null
  rr: number | null
  score: number | null
  triggeredAt: string | null   // entry_triggered_at or picked_at (when triggered)
  watchingSince: string | null // snapshot_time or picked_at (when watching)
  triggered: boolean           // true = in-trade mode, false = watching mode
  thesis: string | null        // tony_hypothesis or notes
  thesisLabel: string | null   // tony_priority_label
  thesisAction: string | null  // tony_recommended_action
  quote: LiveQuote | undefined
}
```

**Triggered mode layout:**
```
┌──────────────────────────────────────────────────────────┐
│  AAPL  [TRIGGERED]  Bull Flag          3d 14h in trade   │
├──────────────────────────────────────────────────────────┤
│  Entry $142.50  →  Now $148.30        +4.07% ▲           │
│                                                          │
│  [■■■■■■■■■■■│●══════════════════════════]               │
│  STOP $138   ENTRY $142.50                TARGET $162    │
│                                                          │
│  "Bull consolidation above 20EMA — breakout continuation"│
│                                         [Tony · HOLD]   │
└──────────────────────────────────────────────────────────┘
```

**Watching mode layout:**
```
┌──────────────────────────────────────────────────────────┐
│  MSFT  [WATCHING]   EMA Bounce         watching 2d       │
├──────────────────────────────────────────────────────────┤
│  Live $415.20                          −1.1% to entry    │
│                                                          │
│  [────────────────────●  ┊  ────────────────────]        │
│  STOP $408           NOW  ENTRY $420       TARGET $445   │
│                                                          │
│  "Awaiting pullback to 20EMA before entry trigger"       │
└──────────────────────────────────────────────────────────┘
```

Rules enforced:
- **P&L section does not render at all in watching mode** — no `→ Now` arrow, no P&L badge
- Watching mode shows "X% to entry" in amber (distance, not profit)
- Gauge omitted entirely if `entry`, `stop`, or `target` is null
- If `quote` is undefined: show `—` for live price, `—` for P&L, omit gauge

### New: `components/picks/RiskGauge.tsx`
Props: `{ entry: number, stop: number, target: number, currentPrice: number | null, triggered: boolean }`

Triggered mode:
- Horizontal bar fills from stop to `currentPrice`
- Red fill: stop → entry zone
- Green fill: entry → currentPrice (if above entry)
- Entry line drawn as a solid vertical tick
- Circular marker at `currentPrice` position, coloured green/amber/red based on zone

Watching mode:
- Bar is dim (low opacity)
- No fill — just the horizontal line
- Entry line drawn as a dashed vertical tick (the target to reach)
- Circular marker at `currentPrice` position in amber

Labels below bar: `STOP $X` left, `ENTRY $X` at entry_pct position, `TARGET $X` right.

### New: `components/picks/PLBadge.tsx`
Props: `{ entry: number, currentPrice: number }`
- Renders `+4.07% ▲` or `−2.30% ▼`
- Font: JetBrains Mono, font-size 22px, font-weight 700
- Colour: `var(--green)` positive, `var(--red)` negative
- **Only rendered in triggered mode**

### New: `components/picks/TimeInTrade.tsx`
Props: `{ since: string | null, label: "in trade" | "watching" }`
- Formats duration from `since` to now
- Renders e.g. `"3d 14h in trade"` or `"watching 2d"`
- Colour: `var(--text-secondary)`, font-size 11px

### New: `app/picks/page.tsx`
Data fetching:
```typescript
const { data: tracking } = useQuery({ queryKey: ["tracking"], queryFn: api.tracking, refetchInterval: 30_000 })
const { data: picks }    = useQuery({ queryKey: ["picks"],    queryFn: api.picks,    refetchInterval: 60_000 })
const liveQuotes = useLivePrices()
```

Sections rendered (each only if non-empty):
1. **KPI bar** — `IN TRADE: N | WATCHING: N | AVG P&L: +X.X%` (avg only from triggered)
2. **IN TRADE** — triggered bot snapshots sorted by P&L desc, then triggered manual picks
3. **WATCHING FOR ENTRY** — non-triggered bot snapshots sorted by score desc
4. **MANUAL PICKS** — manual picks not already shown in IN TRADE, watching-mode cards

Empty state: `"No picks yet — add one from the Watchlist"` if everything is empty.

### Modified: `app/watchlist/page.tsx`
Replace `TradeCard` instances with a compact `WatchlistTable`:

Columns: `SYM | STATUS | SETUP | LIVE | ENTRY | DIST | SCORE`

- **DIST/P&L** (single column, same header for all rows): `(live - entry) / entry * 100`
  - Non-triggered rows: value styled amber if within 2% of entry, muted otherwise — labelled as distance to entry
  - Triggered rows: value styled green (positive) or red (negative) — this is their unrealized P&L
- Triggered rows get a thin green left border on the `<tr>`
- Click any row → `openSymbol(symbol)` (SymbolDrawer, no change)
- AddPickForm stays at top
- FilterChips stay (ALL / ACTIVE / WATCHING / PENDING)
- Manual picks appear in a second table section below: `MANUAL PICKS (N)`

### Modified: `app/today/page.tsx`
Replace the TradeCard-based "Live Setups" section with slim rows:

```typescript
// New inline component used only in today/page.tsx
function ActivePositionRow({ snapshot, quote }: { snapshot: CandidateSnapshot, quote: LiveQuote | undefined }) {
  // renders: AAPL  TRIGGERED  +4.07% ▲  Entry $142.50 → $148.30
  // height: ~32px, monospace numbers, no gauge, no thesis
}
```

- Only triggered snapshots (`entry_triggered === true`) shown here
- "View all in Picks →" link at bottom of section using Next.js `<Link href="/picks">`
- If no triggered positions: show "No active positions" in muted text

### Modified: `components/layout/Sidebar.tsx`
Insert after Watchlist entry:
```typescript
{ href: "/picks", icon: "💼", label: "Picks" }
```

---

## Error and Edge Cases

| Scenario | Behaviour |
|---|---|
| No Alpaca keys (503) | `useLivePrices` returns `{}`. Cards show `—` for price/P&L. Gauge hidden. No crash. |
| Null entry/stop/target | Gauge omitted. P&L shows `—`. DIST column shows `—`. |
| Price at or below stop | Gauge marker clamps to 0%, shown in `var(--red)`. |
| Price above target | Gauge marker clamps to 100%, badge shows `+X% ▲` in bright green. |
| No picks at all | Picks page shows friendly empty state, not blank. |
| Manual pick, no planned_entry | Watching mode, no gauge. |

---

## What Does NOT Change

- `TradeCard` component — left as-is (keep in codebase for now)
- `DistanceToBar` component — unchanged
- `ScanTable` component — unchanged
- All backend API routes — no changes
- `SymbolDrawer` — unchanged

---

## Testing Checklist

- [ ] `/picks` loads with empty DB — no error, shows empty state
- [ ] Triggered snapshot → "IN TRADE" section with P&L badge and gauge
- [ ] Watching snapshot → "WATCHING FOR ENTRY" section, zero P&L shown anywhere
- [ ] Manual pick `status="active"` → triggered card with P&L
- [ ] Manual pick `status="watching"` → watching card, no P&L
- [ ] Gauge marker clamps at stop (0%) and target (100%) without layout breakage
- [ ] Time in trade: `"3d 14h in trade"`, `"4h 20m in trade"`, `"watching 2d"` format correctly
- [ ] P&L badge green when above entry, red when below
- [ ] Watchlist table DIST column: amber near entry, green/red for triggered
- [ ] Watchlist row click opens SymbolDrawer
- [ ] Today "Live Setups" shows only triggered picks as slim rows
- [ ] "View all in Picks →" link navigates to `/picks`
- [ ] Picks nav item active when on `/picks`
- [ ] No P&L anywhere for any watching/pre-entry position
