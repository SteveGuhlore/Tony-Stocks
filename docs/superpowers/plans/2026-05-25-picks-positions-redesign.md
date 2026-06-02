# Picks / Positions Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated `/picks` page with rich position cards showing entry vs live price, unrealized P&L, a risk gauge bar, and bot thesis; redesign Watchlist as a compact table; slim down Today page.

**Architecture:** Five new files in `components/picks/` and `app/picks/`; three existing pages modified. No backend changes. All data from `api.tracking()` + `api.picks()` + `useLivePrices()`. The `PositionCard` renders in two modes — `triggered=true` shows P&L, `triggered=false` shows distance-to-entry only (P&L is never shown for pre-entry positions).

**Tech Stack:** Next.js 15 App Router, TanStack Query v5, TypeScript, inline CSS (project convention — no Tailwind classes in new files), `useLivePrices` hook, `useDrawer` hook for SymbolDrawer integration.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `dashboard-web/components/picks/TimeInTrade.tsx` | Format and display "3d 14h in trade" / "watching 2d" |
| Create | `dashboard-web/components/picks/PLBadge.tsx` | Large P&L % badge with tinted background (triggered only) |
| Create | `dashboard-web/components/picks/RiskGauge.tsx` | Horizontal bar: stop→marker→target, entry line, day H/L ticks |
| Create | `dashboard-web/components/picks/PositionCard.tsx` | Full position card (triggered + watching modes) |
| Create | `dashboard-web/app/picks/page.tsx` | Picks page: KPI bar, IN TRADE, WATCHING, MANUAL sections |
| Modify | `dashboard-web/components/layout/Sidebar.tsx` | Add Picks nav item between Watchlist and Outcomes |
| Modify | `dashboard-web/app/watchlist/page.tsx` | Replace TradeCards with compact dense table |
| Modify | `dashboard-web/app/today/page.tsx` | Replace "Live Setups" TradeCards with slim ActivePositionRow |

---

## Task 1: TimeInTrade component

**Files:**
- Create: `dashboard-web/components/picks/TimeInTrade.tsx`

- [ ] **Step 1: Create the file**

```tsx
"use client"

function formatDuration(ms: number): string {
  const totalMinutes = Math.floor(ms / 60000)
  const totalHours = Math.floor(totalMinutes / 60)
  const days = Math.floor(totalHours / 24)
  if (days >= 1) return `${days}d ${totalHours % 24}h`
  if (totalHours >= 1) return `${totalHours}h ${totalMinutes % 60}m`
  return `${totalMinutes}m`
}

interface Props {
  since: string | null
  label: "in trade" | "watching"
}

export function TimeInTrade({ since, label }: Props) {
  if (!since) return <span style={{ color: "var(--text-secondary)", fontSize: 11 }}>—</span>
  const ms = Date.now() - new Date(since).getTime()
  if (ms < 0) return null
  const dur = formatDuration(ms)
  return (
    <span style={{ color: "var(--text-secondary)", fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}>
      {label === "watching" ? `watching ${dur}` : `${dur} in trade`}
    </span>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```powershell
git add dashboard-web/components/picks/TimeInTrade.tsx
git commit -m "feat: add TimeInTrade component"
```

---

## Task 2: PLBadge component

**Files:**
- Create: `dashboard-web/components/picks/PLBadge.tsx`

- [ ] **Step 1: Create the file**

```tsx
"use client"

interface Props {
  entry: number
  currentPrice: number
}

export function PLBadge({ entry, currentPrice }: Props) {
  const pct     = ((currentPrice - entry) / entry) * 100
  const positive = pct >= 0
  const color   = positive ? "var(--green)" : "var(--red)"
  const bg      = positive ? "rgba(0,230,118,0.08)" : "rgba(255,61,61,0.08)"
  const border  = positive ? "rgba(0,230,118,0.2)"  : "rgba(255,61,61,0.2)"
  const sign    = positive ? "+" : ""
  const arrow   = positive ? "▲" : "▼"

  return (
    <div style={{
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: 6,
      padding: "6px 14px",
      textAlign: "center",
      minWidth: 100,
    }}>
      <div style={{
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 22,
        fontWeight: 700,
        color,
        lineHeight: 1.1,
      }}>
        {sign}{pct.toFixed(2)}%
      </div>
      <div style={{ fontSize: 10, color, opacity: 0.8, marginTop: 2 }}>
        {arrow} unrealized
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```powershell
git add dashboard-web/components/picks/PLBadge.tsx
git commit -m "feat: add PLBadge component"
```

---

## Task 3: RiskGauge component

**Files:**
- Create: `dashboard-web/components/picks/RiskGauge.tsx`

The bar spans `stop` → `target`. In triggered mode: red fill stop→entry, green fill entry→price when above entry. In watching mode: dim bar, dashed entry line (the goal), marker dot only. The glowing circular marker transitions smoothly as price updates. Day high/low appear as amber tick marks inside the bar when available.

- [ ] **Step 1: Create the file**

```tsx
"use client"

interface Props {
  entry: number
  stop: number
  target: number
  currentPrice: number | null
  triggered: boolean
  dayHigh?: number
  dayLow?: number
}

function clamp(v: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, v))
}

function toPct(value: number, stop: number, range: number) {
  return clamp((value - stop) / range * 100, 0, 100)
}

export function RiskGauge({ entry, stop, target, currentPrice, triggered, dayHigh, dayLow }: Props) {
  const range = target - stop
  if (range <= 0) return null

  const entryPct = toPct(entry, stop, range)
  const pricePct = currentPrice !== null ? toPct(currentPrice, stop, range) : null
  const highPct  = dayHigh !== undefined && dayHigh > stop && dayHigh < target
    ? toPct(dayHigh, stop, range) : null
  const lowPct   = dayLow  !== undefined && dayLow  > stop && dayLow  < target
    ? toPct(dayLow,  stop, range) : null

  const aboveEntry    = currentPrice !== null && currentPrice > entry
  const atOrBelowStop = currentPrice !== null && currentPrice <= stop

  const markerColor = atOrBelowStop ? "var(--red)"
    : aboveEntry ? "var(--green)"
    : "var(--amber)"

  return (
    <div style={{ userSelect: "none", marginBottom: 8 }}>
      {/* ── bar ── */}
      <div style={{
        position: "relative",
        height: 8,
        borderRadius: 4,
        background: "rgba(255,255,255,0.04)",
        overflow: "visible",
        marginBottom: 22,
      }}>
        {/* risk zone fill: stop → entry */}
        {triggered && (
          <div style={{
            position: "absolute", left: 0, width: `${entryPct}%`, height: "100%",
            borderRadius: "4px 0 0 4px",
            background: "rgba(255,61,61,0.18)",
          }} />
        )}

        {/* profit zone fill: entry → currentPrice when above entry */}
        {triggered && pricePct !== null && pricePct > entryPct && (
          <div style={{
            position: "absolute",
            left: `${entryPct}%`,
            width: `${pricePct - entryPct}%`,
            height: "100%",
            background: "rgba(0,230,118,0.22)",
          }} />
        )}

        {/* day low tick */}
        {lowPct !== null && (
          <div style={{
            position: "absolute", left: `${lowPct}%`,
            top: -3, bottom: -3, width: 1,
            background: "rgba(255,171,0,0.45)",
            transform: "translateX(-50%)",
          }} />
        )}

        {/* day high tick */}
        {highPct !== null && (
          <div style={{
            position: "absolute", left: `${highPct}%`,
            top: -3, bottom: -3, width: 1,
            background: "rgba(255,171,0,0.45)",
            transform: "translateX(-50%)",
          }} />
        )}

        {/* entry line */}
        <div style={{
          position: "absolute",
          left: `${entryPct}%`,
          top: -4, bottom: -4, width: 2,
          background: triggered ? "var(--cyan)" : "rgba(0,229,255,0.35)",
          borderRadius: 1,
          transform: "translateX(-50%)",
        }} />

        {/* current price marker — glows, transitions left as price updates */}
        {pricePct !== null && (
          <div style={{
            position: "absolute",
            left: `${pricePct}%`,
            top: "50%",
            transform: "translate(-50%, -50%)",
            width: 14, height: 14,
            borderRadius: "50%",
            background: markerColor,
            boxShadow: `0 0 8px 2px ${markerColor}55`,
            border: "2px solid var(--bg-base)",
            zIndex: 2,
            transition: "left 0.6s ease",
          }} />
        )}
      </div>

      {/* ── labels ── */}
      <div style={{
        position: "relative", height: 12,
        fontSize: 9, fontFamily: "JetBrains Mono, monospace",
        color: "var(--text-secondary)",
      }}>
        <span style={{ position: "absolute", left: 0, whiteSpace: "nowrap" }}>
          STOP ${stop.toFixed(2)}
        </span>
        <span style={{
          position: "absolute",
          left: `${entryPct}%`,
          transform: "translateX(-50%)",
          color: "var(--cyan)",
          whiteSpace: "nowrap",
        }}>
          ${entry.toFixed(2)}
        </span>
        <span style={{ position: "absolute", right: 0, whiteSpace: "nowrap" }}>
          TARGET ${target.toFixed(2)}
        </span>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```powershell
git add dashboard-web/components/picks/RiskGauge.tsx
git commit -m "feat: add RiskGauge with glowing marker, fills, and day H/L ticks"
```

---

## Task 4: PositionCard component

**Files:**
- Create: `dashboard-web/components/picks/PositionCard.tsx`

Two visual modes:
- `triggered=true`: header shows time-in-trade; price row `Entry $X → Now $Y`; right side `PLBadge`; gauge has red/green fills
- `triggered=false`: header shows watching duration; price row `Live $X → Entry $Y` (entry in cyan); right side `X% to entry` in amber; gauge is dim with no fills

`TickerSymbol` already opens the SymbolDrawer via `useDrawer` internally — no extra wiring needed.

- [ ] **Step 1: Create the file**

```tsx
"use client"

import { StatusBadge } from "@/components/terminal/StatusBadge"
import { TickerSymbol } from "@/components/terminal/TickerSymbol"
import { TimeInTrade } from "./TimeInTrade"
import { PLBadge } from "./PLBadge"
import { RiskGauge } from "./RiskGauge"
import type { LiveQuote } from "@/lib/types"

export interface PositionCardProps {
  symbol: string
  status: string
  setupCategory: string | null
  entry: number | null
  stop: number | null
  target: number | null
  rr: number | null
  score: number | null
  triggeredAt: string | null
  watchingSince: string | null
  triggered: boolean
  thesis: string | null
  thesisLabel: string | null
  thesisAction: string | null
  quote: LiveQuote | undefined
}

export function PositionCard({
  symbol, status, setupCategory, entry, stop, target, rr, score,
  triggeredAt, watchingSince, triggered,
  thesis, thesisLabel, thesisAction, quote,
}: PositionCardProps) {
  const price = quote?.price ?? null
  const hasLevels = entry !== null && stop !== null && target !== null
  const since = triggered ? triggeredAt : watchingSince

  const distPct = (entry !== null && price !== null && entry !== 0)
    ? ((price - entry) / entry) * 100
    : null

  const borderColor = triggered
    ? (price !== null && entry !== null && price >= entry ? "var(--green)" : "var(--amber)")
    : "var(--border)"

  const lbl: React.CSSProperties = {
    fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em",
    color: "var(--text-secondary)", marginBottom: 2,
  }
  const priceNum: React.CSSProperties = {
    fontFamily: "JetBrains Mono, monospace", fontSize: 17, fontWeight: 600,
  }

  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderLeft: `3px solid ${borderColor}`,
      borderRadius: 6,
      padding: "14px 16px",
      marginBottom: 10,
      transition: "border-left-color 0.6s ease",
    }}>

      {/* ── Header ── */}
      <div style={{
        display: "flex", alignItems: "flex-start",
        justifyContent: "space-between", marginBottom: 14,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <TickerSymbol symbol={symbol} />
          <StatusBadge status={status} />
          {setupCategory && (
            <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{setupCategory}</span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0, marginLeft: 12 }}>
          {score !== null && (
            <span style={{
              fontSize: 10, color: "var(--cyan)",
              fontFamily: "JetBrains Mono, monospace",
              background: "rgba(0,229,255,0.08)",
              borderRadius: 3, padding: "1px 6px",
            }}>
              {score.toFixed(1)}
            </span>
          )}
          <TimeInTrade since={since} label={triggered ? "in trade" : "watching"} />
        </div>
      </div>

      {/* ── Price row ── */}
      <div style={{
        display: "flex", alignItems: "center",
        justifyContent: "space-between", marginBottom: 16,
      }}>
        {triggered ? (
          <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
            {entry !== null && (
              <div>
                <div style={lbl}>Entry</div>
                <div style={{ ...priceNum, color: "var(--text-secondary)" }}>${entry.toFixed(2)}</div>
              </div>
            )}
            <div style={{ fontSize: 16, color: "var(--text-secondary)", paddingBottom: 2 }}>→</div>
            <div>
              <div style={lbl}>Now</div>
              <div style={{ ...priceNum, color: "var(--text-primary)" }}>
                {price !== null ? `$${price.toFixed(2)}` : "—"}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
            <div>
              <div style={lbl}>Live</div>
              <div style={{ ...priceNum, color: "var(--text-primary)" }}>
                {price !== null ? `$${price.toFixed(2)}` : "—"}
              </div>
            </div>
            {entry !== null && (
              <>
                <div style={{ fontSize: 16, color: "var(--text-secondary)", paddingBottom: 2 }}>→</div>
                <div>
                  <div style={lbl}>Entry</div>
                  <div style={{ ...priceNum, color: "var(--cyan)" }}>${entry.toFixed(2)}</div>
                </div>
              </>
            )}
          </div>
        )}

        {/* P&L (triggered) or distance-to-entry (watching) */}
        {triggered && entry !== null && price !== null ? (
          <PLBadge entry={entry} currentPrice={price} />
        ) : !triggered && distPct !== null ? (
          <div style={{ textAlign: "right" }}>
            <div style={lbl}>To Entry</div>
            <div style={{
              fontFamily: "JetBrains Mono, monospace", fontSize: 20, fontWeight: 700,
              color: Math.abs(distPct) <= 2 ? "var(--amber)" : "var(--text-secondary)",
            }}>
              {distPct > 0 ? "+" : ""}{distPct.toFixed(2)}%
            </div>
          </div>
        ) : null}
      </div>

      {/* ── Risk gauge ── */}
      {hasLevels && (
        <RiskGauge
          entry={entry!}
          stop={stop!}
          target={target!}
          currentPrice={price}
          triggered={triggered}
          dayHigh={quote?.day_high}
          dayLow={quote?.day_low}
        />
      )}

      {/* ── Bot thesis ── */}
      {thesis && (
        <div style={{
          marginTop: 12, padding: "8px 10px",
          background: "var(--bg-elevated)",
          borderRadius: 4, borderLeft: "2px solid var(--cyan)",
        }}>
          {(thesisLabel || thesisAction) && (
            <div style={{ fontSize: 10, color: "var(--amber)", marginBottom: 4, fontWeight: 600 }}>
              {[thesisLabel, thesisAction].filter(Boolean).join(" — ")}
            </div>
          )}
          <p style={{
            margin: 0, fontSize: 11,
            color: "var(--text-secondary)",
            fontStyle: "italic", lineHeight: 1.5,
          }}>
            "{thesis}"
          </p>
        </div>
      )}

      {/* ── Levels footer ── */}
      <div style={{
        display: "flex", gap: 16, marginTop: 12,
        fontSize: 10, fontFamily: "JetBrains Mono, monospace",
      }}>
        {stop   !== null && <span style={{ color: "var(--red)"            }}>SL ${stop.toFixed(2)}</span>}
        {target !== null && <span style={{ color: "var(--green)"          }}>TP ${target.toFixed(2)}</span>}
        {rr     !== null && <span style={{ color: "var(--text-secondary)" }}>R:R {rr.toFixed(1)}:1</span>}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```powershell
git add dashboard-web/components/picks/
git commit -m "feat: add PositionCard, PLBadge, RiskGauge, TimeInTrade components"
```

---

## Task 5: /picks page

**Files:**
- Create: `dashboard-web/app/picks/page.tsx`

Four sections (each only renders if non-empty): IN TRADE (triggered bot snaps, P&L desc), MANUAL — IN TRADE, WATCHING FOR ENTRY (non-triggered bot snaps, score desc), MANUAL — WATCHING. KPI bar shows counts + avg P&L. Empty state when nothing exists.

- [ ] **Step 1: Create the file**

```tsx
"use client"

import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { PositionCard } from "@/components/picks/PositionCard"
import type { CandidateSnapshot, ManualPick } from "@/lib/types"

function isSnapshotTriggered(s: CandidateSnapshot) { return s.entry_triggered }
function isManualTriggered(p: ManualPick) { return p.status === "active" || p.status === "triggered" }

function calcPL(entry: number | null, price: number | undefined): number | null {
  if (!entry || !price) return null
  return ((price - entry) / entry) * 100
}

function avgOf(vals: (number | null)[]): number | null {
  const nums = vals.filter((v): v is number => v !== null)
  return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null
}

function KPIBar({ inTrade, watching, avgPct }: { inTrade: number; watching: number; avgPct: number | null }) {
  const lbl: React.CSSProperties = {
    fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em",
    color: "var(--text-secondary)", marginBottom: 4,
  }
  const val: React.CSSProperties = {
    fontSize: 20, fontFamily: "JetBrains Mono, monospace",
    fontWeight: 700, color: "var(--text-primary)", lineHeight: 1,
  }
  const positive = avgPct !== null && avgPct >= 0
  return (
    <div style={{
      display: "flex", gap: 32, padding: "14px 16px",
      background: "var(--bg-surface)", border: "1px solid var(--border)",
      borderRadius: 6, marginBottom: 20,
    }}>
      <div><div style={lbl}>In Trade</div><div style={val}>{inTrade}</div></div>
      <div><div style={lbl}>Watching</div><div style={val}>{watching}</div></div>
      {avgPct !== null && (
        <div>
          <div style={lbl}>Avg P&L</div>
          <div style={{ ...val, color: positive ? "var(--green)" : "var(--red)" }}>
            {positive ? "+" : ""}{avgPct.toFixed(2)}%
          </div>
        </div>
      )}
    </div>
  )
}

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em",
      color: "var(--text-secondary)", marginBottom: 10, marginTop: 4,
    }}>
      {label}
      <span style={{
        background: "var(--bg-elevated)", borderRadius: 10,
        padding: "1px 7px", fontSize: 10,
      }}>
        {count}
      </span>
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{ textAlign: "center", padding: "60px 16px", color: "var(--text-secondary)" }}>
      <div style={{ fontSize: 36, marginBottom: 12 }}>💼</div>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, color: "var(--text-primary)" }}>
        No picks yet
      </div>
      <div style={{ fontSize: 11 }}>
        Add picks from the Watchlist or wait for the bot to generate scan candidates
      </div>
    </div>
  )
}

export default function PicksPage() {
  const { data: tracking } = useQuery({ queryKey: ["tracking"], queryFn: api.tracking, refetchInterval: 30_000 })
  const { data: picks }    = useQuery({ queryKey: ["picks"],    queryFn: api.picks,    refetchInterval: 60_000 })
  const liveQuotes = useLivePrices()

  const allSnaps       = [...(tracking?.active ?? []), ...(tracking?.watching ?? [])]
  const triggeredSnaps = allSnaps.filter(isSnapshotTriggered)
  const watchingSnaps  = allSnaps.filter(s => !isSnapshotTriggered(s))

  const allManual       = picks?.picks ?? []
  const triggeredManual = allManual.filter(isManualTriggered)
  const watchingManual  = allManual.filter(p => !isManualTriggered(p))

  const plValues = triggeredSnaps.map(s => calcPL(s.entry, liveQuotes[s.symbol]?.price))
  const avgPL    = avgOf(plValues)

  const totalInTrade  = triggeredSnaps.length + triggeredManual.length
  const totalWatching = watchingSnaps.length  + watchingManual.length
  const isEmpty       = totalInTrade === 0 && totalWatching === 0

  const sortedTriggered = triggeredSnaps.slice().sort((a, b) => {
    const pa = calcPL(a.entry, liveQuotes[a.symbol]?.price) ?? -999
    const pb = calcPL(b.entry, liveQuotes[b.symbol]?.price) ?? -999
    return pb - pa
  })

  const sortedWatching = watchingSnaps.slice().sort((a, b) =>
    (b.total_score ?? 0) - (a.total_score ?? 0)
  )

  return (
    <div>
      <h1 style={{
        fontSize: 13, fontWeight: 600, marginBottom: 16,
        color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em",
      }}>
        💼 Picks
      </h1>

      {isEmpty ? <EmptyState /> : (
        <>
          <KPIBar inTrade={totalInTrade} watching={totalWatching} avgPct={avgPL} />

          {sortedTriggered.length > 0 && (
            <>
              <SectionHeader label="In Trade" count={sortedTriggered.length} />
              {sortedTriggered.map(s => (
                <PositionCard
                  key={s.id}
                  symbol={s.symbol}
                  status={s.status}
                  setupCategory={s.setup_category}
                  entry={s.entry}
                  stop={s.stop}
                  target={s.target}
                  rr={s.risk_reward}
                  score={s.total_score}
                  triggeredAt={s.entry_triggered_at}
                  watchingSince={s.snapshot_time}
                  triggered={true}
                  thesis={s.tony_hypothesis}
                  thesisLabel={s.tony_priority_label}
                  thesisAction={s.tony_recommended_action}
                  quote={liveQuotes[s.symbol]}
                />
              ))}
            </>
          )}

          {triggeredManual.length > 0 && (
            <>
              <SectionHeader label="Manual — In Trade" count={triggeredManual.length} />
              {triggeredManual.map(p => (
                <PositionCard
                  key={`m-${p.id}`}
                  symbol={p.symbol}
                  status={p.status}
                  setupCategory={null}
                  entry={p.planned_entry}
                  stop={p.planned_stop}
                  target={p.planned_target}
                  rr={null}
                  score={null}
                  triggeredAt={p.picked_at}
                  watchingSince={p.picked_at}
                  triggered={true}
                  thesis={p.notes}
                  thesisLabel={null}
                  thesisAction={null}
                  quote={liveQuotes[p.symbol]}
                />
              ))}
            </>
          )}

          {sortedWatching.length > 0 && (
            <>
              <SectionHeader label="Watching for Entry" count={sortedWatching.length} />
              {sortedWatching.map(s => (
                <PositionCard
                  key={s.id}
                  symbol={s.symbol}
                  status={s.status}
                  setupCategory={s.setup_category}
                  entry={s.entry}
                  stop={s.stop}
                  target={s.target}
                  rr={s.risk_reward}
                  score={s.total_score}
                  triggeredAt={s.entry_triggered_at}
                  watchingSince={s.snapshot_time}
                  triggered={false}
                  thesis={s.tony_hypothesis}
                  thesisLabel={s.tony_priority_label}
                  thesisAction={s.tony_recommended_action}
                  quote={liveQuotes[s.symbol]}
                />
              ))}
            </>
          )}

          {watchingManual.length > 0 && (
            <>
              <SectionHeader label="Manual — Watching" count={watchingManual.length} />
              {watchingManual.map(p => (
                <PositionCard
                  key={`m-${p.id}`}
                  symbol={p.symbol}
                  status={p.status}
                  setupCategory={null}
                  entry={p.planned_entry}
                  stop={p.planned_stop}
                  target={p.planned_target}
                  rr={null}
                  score={null}
                  triggeredAt={null}
                  watchingSince={p.picked_at}
                  triggered={false}
                  thesis={p.notes}
                  thesisLabel={null}
                  thesisAction={null}
                  quote={liveQuotes[p.symbol]}
                />
              ))}
            </>
          )}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```powershell
git add dashboard-web/app/picks/
git commit -m "feat: add /picks page with KPI bar, IN TRADE, WATCHING, MANUAL sections"
```

---

## Task 6: Sidebar nav update

**Files:**
- Modify: `dashboard-web/components/layout/Sidebar.tsx` (lines 6–13, the NAV array)

- [ ] **Step 1: Replace the NAV array**

```typescript
const NAV = [
  { href: "/today",     icon: "⚡", label: "Today"     },
  { href: "/watchlist", icon: "👁", label: "Watchlist" },
  { href: "/picks",     icon: "💼", label: "Picks"     },
  { href: "/outcomes",  icon: "📊", label: "Outcomes"  },
  { href: "/scan",      icon: "🔍", label: "Scan"      },
  { href: "/analytics", icon: "📈", label: "Analytics" },
  { href: "/system",    icon: "⚙",  label: "System"    },
]
```

- [ ] **Step 2: Verify TypeScript and build**

```powershell
cd dashboard-web
npx tsc --noEmit
npx next build
```

Expected build output includes `/picks` in the route list:
```
Route (app)
  ○ /
  ○ /analytics
  ○ /outcomes
  ○ /picks
  ○ /scan
  ○ /system
  ○ /today
  ○ /watchlist
```

- [ ] **Step 3: Commit**

```powershell
git add dashboard-web/components/layout/Sidebar.tsx
git commit -m "feat: add Picks nav item to sidebar"
```

---

## Task 7: Watchlist table redesign

**Files:**
- Modify: `dashboard-web/app/watchlist/page.tsx` (full rewrite)

Replaces TradeCard-based layout with two compact `dense-table` tables. `DistCell` handles the DIST/P&L column: green/red for triggered rows (unrealized P&L), amber when within 2% of entry for watching rows. `TickerSymbol` already calls `openSymbol` on click via `useDrawer`; the whole row also calls `openSymbol` for full-row click.

- [ ] **Step 1: Full rewrite of watchlist/page.tsx**

```tsx
"use client"

import { useState } from "react"
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { FilterChips } from "@/components/terminal/FilterChips"
import { TickerSymbol } from "@/components/terminal/TickerSymbol"
import { StatusBadge } from "@/components/terminal/StatusBadge"
import { useDrawer } from "@/components/overlays/DrawerContext"
import type { CandidateSnapshot, ManualPick, LiveQuote } from "@/lib/types"

const FILTERS = ["ALL", "ACTIVE", "WATCHING", "PENDING"]

function matchFilter(s: CandidateSnapshot, f: string) {
  if (f === "ALL")      return true
  if (f === "ACTIVE")   return ["active", "triggered", "open/watch"].includes(s.status)
  if (f === "WATCHING") return s.status === "watching"
  if (f === "PENDING")  return s.status === "pending"
  return true
}

function DistCell({ entry, quote, triggered }: {
  entry: number | null
  quote: LiveQuote | undefined
  triggered: boolean
}) {
  const price = quote?.price
  if (!entry || !price) return <span style={{ color: "var(--text-secondary)" }}>—</span>
  const pct = ((price - entry) / entry) * 100
  const positive = pct >= 0
  if (triggered) {
    return (
      <span style={{
        fontFamily: "JetBrains Mono, monospace", fontWeight: 600,
        color: positive ? "var(--green)" : "var(--red)",
      }}>
        {positive ? "+" : ""}{pct.toFixed(2)}%
      </span>
    )
  }
  const nearEntry = Math.abs(pct) <= 2
  return (
    <span style={{
      fontFamily: "JetBrains Mono, monospace",
      color: nearEntry ? "var(--amber)" : "var(--text-secondary)",
    }}>
      {pct > 0 ? "+" : ""}{pct.toFixed(2)}%
    </span>
  )
}

function SnapshotTable({ snapshots }: { snapshots: CandidateSnapshot[] }) {
  const liveQuotes = useLivePrices()
  const { openSymbol } = useDrawer()
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dense-table">
        <thead>
          <tr>
            {["SYM", "STATUS", "SETUP", "LIVE", "ENTRY", "DIST / P&L", "SCORE"].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {snapshots.map(s => {
            const quote = liveQuotes[s.symbol]
            const triggered = s.entry_triggered
            return (
              <tr
                key={s.id}
                onClick={() => openSymbol(s.symbol)}
                style={triggered ? { borderLeft: "2px solid var(--green)" } : {}}
              >
                <td><TickerSymbol symbol={s.symbol} /></td>
                <td><StatusBadge status={s.status} /></td>
                <td style={{
                  color: "var(--text-secondary)",
                  maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis",
                }}>
                  {s.setup_category ?? "—"}
                </td>
                <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {quote ? `$${quote.price.toFixed(2)}` : "—"}
                </td>
                <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {s.entry ? `$${s.entry.toFixed(2)}` : "—"}
                </td>
                <td>
                  <DistCell entry={s.entry} quote={quote} triggered={triggered} />
                </td>
                <td style={{
                  fontFamily: "JetBrains Mono, monospace",
                  color: (s.total_score ?? 0) >= 80 ? "var(--green)"
                       : (s.total_score ?? 0) >= 65 ? "var(--amber)"
                       : "var(--text-secondary)",
                }}>
                  {s.total_score?.toFixed(1) ?? "—"}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ManualTable({ picks }: { picks: ManualPick[] }) {
  const liveQuotes = useLivePrices()
  const { openSymbol } = useDrawer()
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dense-table">
        <thead>
          <tr>
            {["SYM", "STATUS", "LIVE", "ENTRY", "DIST / P&L"].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {picks.map(p => {
            const quote = liveQuotes[p.symbol]
            const triggered = p.status === "active" || p.status === "triggered"
            return (
              <tr key={p.id} onClick={() => openSymbol(p.symbol)}>
                <td><TickerSymbol symbol={p.symbol} /></td>
                <td><StatusBadge status={p.status} /></td>
                <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {quote ? `$${quote.price.toFixed(2)}` : "—"}
                </td>
                <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {p.planned_entry ? `$${p.planned_entry.toFixed(2)}` : "—"}
                </td>
                <td>
                  <DistCell entry={p.planned_entry} quote={quote} triggered={triggered} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function AddPickForm({ onDone }: { onDone: () => void }) {
  const [sym, setSym] = useState("")
  const [entry, setEntry] = useState("")
  const [stop, setStop] = useState("")
  const [target, setTarget] = useState("")
  const [notes, setNotes] = useState("")
  const qc = useQueryClient()
  const mut = useMutation({
    mutationFn: () => api.addPick({
      symbol: sym.toUpperCase(),
      entry:  entry  ? parseFloat(entry)  : undefined,
      stop:   stop   ? parseFloat(stop)   : undefined,
      target: target ? parseFloat(target) : undefined,
      notes,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["picks"] }); onDone() },
  })
  const inp: React.CSSProperties = {
    background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3,
    color: "var(--text-primary)", padding: "4px 8px", fontSize: 11,
    fontFamily: "JetBrains Mono, monospace", width: "100%", outline: "none",
  }
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--cyan)", letterSpacing: "0.08em", marginBottom: 10 }}>
        Add Manual Pick
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", gap: 8, marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Symbol *</div>
          <input style={inp} placeholder="AAPL" value={sym} onChange={e => setSym(e.target.value.toUpperCase())} />
        </div>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Entry</div>
          <input style={inp} placeholder="0.00" type="number" step="0.01" value={entry} onChange={e => setEntry(e.target.value)} />
        </div>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Stop</div>
          <input style={inp} placeholder="0.00" type="number" step="0.01" value={stop} onChange={e => setStop(e.target.value)} />
        </div>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Target</div>
          <input style={inp} placeholder="0.00" type="number" step="0.01" value={target} onChange={e => setTarget(e.target.value)} />
        </div>
      </div>
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Notes</div>
        <input style={inp} placeholder="Optional notes..." value={notes} onChange={e => setNotes(e.target.value)} />
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={() => mut.mutate()} disabled={!sym || mut.isPending}
          style={{
            background: "var(--cyan)", color: "#000", border: "none", borderRadius: 3,
            padding: "5px 14px", fontSize: 11, fontWeight: 600, cursor: "pointer",
            opacity: (!sym || mut.isPending) ? 0.5 : 1,
          }}>
          {mut.isPending ? "Adding..." : "Add Pick"}
        </button>
        <button onClick={onDone}
          style={{
            background: "transparent", color: "var(--text-secondary)",
            border: "1px solid var(--border)", borderRadius: 3,
            padding: "5px 14px", fontSize: 11, cursor: "pointer",
          }}>
          Cancel
        </button>
        {mut.isError && (
          <span style={{ fontSize: 10, color: "var(--red)", alignSelf: "center" }}>
            Failed — check symbol
          </span>
        )}
      </div>
    </div>
  )
}

export default function WatchlistPage() {
  const [filter, setFilter] = useState("ALL")
  const [showForm, setShowForm] = useState(false)
  const { data: tracking } = useQuery({ queryKey: ["tracking"], queryFn: api.tracking, refetchInterval: 30_000 })
  const { data: picks }    = useQuery({ queryKey: ["picks"],    queryFn: api.picks,    refetchInterval: 60_000 })

  const snapshots   = [...(tracking?.active ?? []), ...(tracking?.watching ?? [])]
  const filtered    = snapshots.filter(s => matchFilter(s, filter))
  const manualPicks = picks?.picks ?? []

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h1 style={{
          fontSize: 13, fontWeight: 600, color: "var(--text-secondary)",
          textTransform: "uppercase", letterSpacing: "0.08em", margin: 0,
        }}>
          👁 Watchlist
        </h1>
        <button onClick={() => setShowForm(v => !v)}
          style={{
            background: showForm ? "var(--bg-elevated)" : "var(--cyan)",
            color: showForm ? "var(--text-secondary)" : "#000",
            border: "1px solid var(--border)", borderRadius: 3,
            padding: "4px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer",
          }}>
          {showForm ? "✕ Cancel" : "+ Add Pick"}
        </button>
      </div>

      {showForm && <AddPickForm onDone={() => setShowForm(false)} />}

      <FilterChips options={FILTERS} value={filter} onChange={setFilter} />

      {filtered.length > 0 ? (
        <SnapshotTable snapshots={filtered} />
      ) : (
        <p style={{ color: "var(--text-secondary)", fontSize: 11, padding: "8px 0" }}>
          No positions match this filter
        </p>
      )}

      {manualPicks.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div style={{
            fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em",
            color: "var(--text-secondary)", marginBottom: 8,
          }}>
            Manual Picks ({manualPicks.length})
          </div>
          <ManualTable picks={manualPicks} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```powershell
git add dashboard-web/app/watchlist/page.tsx
git commit -m "feat: redesign watchlist as compact table with DIST/P&L column"
```

---

## Task 8: Today page slim summary rows

**Files:**
- Modify: `dashboard-web/app/today/page.tsx` (full rewrite)

Replaces the TradeCard "Live Setups" section with slim `ActivePositionRow` — 32px height, symbol + status + entry→now + P&L on one line. Only triggered positions shown. Watching positions are intentionally omitted (they belong on Watchlist/Picks). Adds "View all in Picks →" link.

- [ ] **Step 1: Full rewrite of today/page.tsx**

```tsx
"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { KPIBar } from "@/components/terminal/KPIBar"
import { ActivityFeed } from "@/components/terminal/ActivityFeed"
import { TickerSymbol } from "@/components/terminal/TickerSymbol"
import { StatusBadge } from "@/components/terminal/StatusBadge"
import type { CandidateSnapshot, LiveQuote } from "@/lib/types"

function PLText({ entry, price }: { entry: number | null; price: number | undefined }) {
  if (!entry || !price) {
    return <span style={{ color: "var(--text-secondary)", fontFamily: "JetBrains Mono, monospace" }}>—</span>
  }
  const pct = ((price - entry) / entry) * 100
  const positive = pct >= 0
  return (
    <span style={{
      fontFamily: "JetBrains Mono, monospace", fontSize: 12, fontWeight: 700,
      color: positive ? "var(--green)" : "var(--red)",
    }}>
      {positive ? "+" : ""}{pct.toFixed(2)}% {positive ? "▲" : "▼"}
    </span>
  )
}

function ActivePositionRow({ snapshot, quote }: { snapshot: CandidateSnapshot; quote: LiveQuote | undefined }) {
  const price = quote?.price
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "6px 0", borderBottom: "1px solid var(--border)", minHeight: 32,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <TickerSymbol symbol={snapshot.symbol} />
        <StatusBadge status={snapshot.status} />
        {snapshot.entry !== null && (
          <span style={{
            fontSize: 11, fontFamily: "JetBrains Mono, monospace",
            color: "var(--text-secondary)",
          }}>
            ${snapshot.entry.toFixed(2)}
            {price !== undefined && <> → ${price.toFixed(2)}</>}
          </span>
        )}
      </div>
      <PLText entry={snapshot.entry} price={price} />
    </div>
  )
}

export default function TodayPage() {
  const { data, isLoading } = useQuery({ queryKey: ["today"], queryFn: api.today, refetchInterval: 30_000 })
  const liveQuotes = useLivePrices()

  if (isLoading) return <div style={{ color: "var(--text-secondary)" }}>Loading...</div>
  if (!data) return null

  const wr = data.kpis.win_rate
  const triggered = data.active_snapshots.filter(s => s.entry_triggered)

  return (
    <div>
      <h1 style={{
        fontSize: 13, fontWeight: 600, marginBottom: 16,
        color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em",
      }}>
        ⚡ Today
      </h1>

      <KPIBar items={[
        { label: "Watching",  value: data.kpis.watching },
        { label: "Triggered", value: data.kpis.triggered },
        { label: "Win Rate",  value: wr !== null ? `${(wr * 100).toFixed(0)}%` : "—" },
        { label: "Watch",     value: data.watch.status ?? "—" },
        { label: "Last Scan", value: data.watch.last_scan_age_seconds !== null
            ? `${Math.round(data.watch.last_scan_age_seconds / 60)}m ago` : "—" },
      ]} />

      <div style={{ display: "grid", gridTemplateColumns: "38% 1fr", gap: 16 }}>
        <div>
          <div style={{
            fontSize: 10, textTransform: "uppercase",
            letterSpacing: "0.08em", color: "var(--text-secondary)", marginBottom: 8,
          }}>
            Recent Activity
          </div>
          <ActivityFeed events={data.recent_events} />
        </div>

        <div>
          <div style={{
            display: "flex", alignItems: "center",
            justifyContent: "space-between", marginBottom: 8,
          }}>
            <div style={{
              fontSize: 10, textTransform: "uppercase",
              letterSpacing: "0.08em", color: "var(--text-secondary)",
            }}>
              Active Positions
            </div>
            <Link href="/picks" style={{ fontSize: 10, color: "var(--cyan)", textDecoration: "none" }}>
              View all in Picks →
            </Link>
          </div>

          {triggered.length > 0 ? triggered.map(s => (
            <ActivePositionRow key={s.id} snapshot={s} quote={liveQuotes[s.symbol]} />
          )) : (
            <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>No active positions</p>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Full TypeScript check and build**

```powershell
cd dashboard-web
npx tsc --noEmit
npx next build
```

Expected: TypeScript clean, build output shows 8 routes including `/picks`.

- [ ] **Step 3: Final commit**

```powershell
git add dashboard-web/app/today/page.tsx
git commit -m "feat: today page shows slim active position rows with P&L and Picks link"
```

---

## Self-Review

**Spec coverage:** All items covered.
- No P&L shown for watching picks: enforced in `PositionCard` — `PLBadge` only renders when `triggered && entry !== null && price !== null` ✅
- Watching mode shows "To Entry %" in amber, never P&L ✅
- Day H/L ticks on gauge ✅
- Score badge on card header ✅
- Glowing marker with CSS transition ✅
- Picks sorted: triggered by P&L desc, watching by score desc ✅
- Empty state on Picks page ✅
- "View all in Picks →" link on Today ✅

**Type consistency across all tasks:**
- `PositionCardProps` defined in Task 4, used identically in Task 5 ✅
- `TimeInTrade` props `{ since: string|null, label: "in trade"|"watching" }` — used exactly in Task 4 ✅
- `PLBadge` props `{ entry: number, currentPrice: number }` — rendered only when both guaranteed non-null in Task 4 ✅
- `RiskGauge` props `{ entry, stop, target, currentPrice, triggered, dayHigh?, dayLow? }` — passed from `PositionCard` with optional `quote?.day_high` / `quote?.day_low` in Task 4 ✅
- `DistCell` props `{ entry, quote, triggered }` — consistent in Tasks 7 ✅
