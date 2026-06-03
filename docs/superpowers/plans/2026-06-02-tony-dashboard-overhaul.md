# Tony Dashboard Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 7-page `dashboard-web` UI with Tony's cockpit — a dense "Tape" board of picks, a ticker deep-dive, and a two-record Track Record — built up from the real data.

**Architecture:** Next.js 16 / React 19 / Tailwind 4 app. This plan is **Plan 1 of 6 (Foundation)**: a pure-logic lib (formatting + rail math + status/verdict derivation) under TDD with Vitest, the anti-AI design tokens, the ambient `StatusBar`, and the app-shell/routing collapse (`/` = Board, `/record` = Track Record). Surfaces are built on this foundation in Plans 2–6 (roadmap at the end).

**Tech Stack:** TypeScript, Next.js 16 (modified — read `node_modules/next/dist/docs/` before app code), React 19, Tailwind 4, @tanstack/react-query, recharts, Vitest (added here).

**Spec:** `docs/superpowers/specs/2026-06-02-tony-dashboard-overhaul-design.md`

**Working dir for all commands:** `dashboard-web/` (the Next.js app root; `@/*` aliases to this dir).

---

## File Structure (Plan 1)

- Create `dashboard-web/vitest.config.ts` — test runner config (node env, `@` alias).
- Modify `dashboard-web/package.json` — add `test`/`test:watch` scripts + `vitest` devDep.
- Create `dashboard-web/lib/format.ts` — pure display formatters.
- Create `dashboard-web/lib/format.test.ts` — its tests.
- Create `dashboard-web/lib/plan.ts` — Plan Rail geometry (pure).
- Create `dashboard-web/lib/plan.test.ts` — its tests.
- Create `dashboard-web/lib/signal.ts` — status + verdict derivation (pure).
- Create `dashboard-web/lib/signal.test.ts` — its tests.
- Modify `dashboard-web/app/globals.css` — replace color tokens with the anti-AI palette.
- Create `dashboard-web/components/layout/StatusBar.tsx` — ambient status rail.
- Modify `dashboard-web/app/layout.tsx` — use `StatusBar` (top bar) instead of `Sidebar` (left rail).
- Modify `dashboard-web/app/page.tsx` — `/` becomes the Board placeholder (no redirect).
- Create `dashboard-web/app/record/page.tsx` — Track Record placeholder.

> Old pages (`app/today`, `watchlist`, `picks`, `scan`, `outcomes`, `analytics`, `system`) and `components/layout/Sidebar.tsx` are **left in place but unlinked** after this plan; each is deleted in the later plan that replaces its data. This keeps every commit shippable.

---

### Task 1: Add Vitest test harness

**Files:**
- Create: `dashboard-web/vitest.config.ts`
- Modify: `dashboard-web/package.json`

- [ ] **Step 1: Install Vitest**

Run (in `dashboard-web/`): `npm install -D vitest@^2`
Expected: adds `vitest` to devDependencies, no peer-dep errors that block install.

- [ ] **Step 2: Create the Vitest config**

Create `dashboard-web/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config"
import path from "node:path"

export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
})
```

- [ ] **Step 3: Add test scripts**

In `dashboard-web/package.json`, add to `"scripts"`:

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 4: Add a temporary smoke test**

Create `dashboard-web/lib/smoke.test.ts`:

```ts
import { describe, it, expect } from "vitest"

describe("harness", () => {
  it("runs", () => {
    expect(1 + 1).toBe(2)
  })
})
```

- [ ] **Step 5: Run the suite to prove the harness works**

Run: `npm test`
Expected: PASS, 1 test passed.

- [ ] **Step 6: Delete the smoke test, commit**

```bash
rm lib/smoke.test.ts
git add package.json package-lock.json vitest.config.ts
git commit -m "chore(dashboard): add vitest test harness

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `lib/format.ts` — display formatters (TDD)

Pure functions shared by every surface. `formatPrice`, `formatSignedPct`, `plPercent` (price vs entry — the P/L column), `scanAgeLabel`.

**Files:**
- Create: `dashboard-web/lib/format.ts`
- Test: `dashboard-web/lib/format.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-web/lib/format.test.ts`:

```ts
import { describe, it, expect } from "vitest"
import { formatPrice, formatSignedPct, plPercent, scanAgeLabel } from "@/lib/format"

describe("formatPrice", () => {
  it("formats to 2 decimals", () => expect(formatPrice(124.857)).toBe("124.86"))
  it("renders em dash for null", () => expect(formatPrice(null)).toBe("—"))
})

describe("formatSignedPct", () => {
  it("adds + for non-negative", () => expect(formatSignedPct(2.85)).toBe("+2.85%"))
  it("keeps - for negative", () => expect(formatSignedPct(-1.1)).toBe("-1.10%"))
  it("renders em dash for null", () => expect(formatSignedPct(null)).toBe("—"))
})

describe("plPercent", () => {
  it("computes percent vs entry", () => expect(plPercent(121.4, 124.86)).toBeCloseTo(2.85, 1))
  it("is null when not in trade", () => {
    expect(plPercent(null, 124.86)).toBeNull()
    expect(plPercent(121.4, undefined)).toBeNull()
  })
})

describe("scanAgeLabel", () => {
  it("handles no scan", () => expect(scanAgeLabel(null)).toBe("no scan yet"))
  it("handles under a minute", () => expect(scanAgeLabel(30)).toBe("just now"))
  it("handles minutes", () => expect(scanAgeLabel(125)).toBe("2m ago"))
  it("handles hours", () => expect(scanAgeLabel(7200)).toBe("2h ago"))
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run lib/format.test.ts`
Expected: FAIL — cannot find module `@/lib/format`.

- [ ] **Step 3: Implement**

Create `dashboard-web/lib/format.ts`:

```ts
export const EM_DASH = "—"

export function formatPrice(n: number | null | undefined): string {
  return n == null ? EM_DASH : n.toFixed(2)
}

export function formatSignedPct(n: number | null | undefined): string {
  if (n == null) return EM_DASH
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`
}

export function plPercent(
  entry: number | null | undefined,
  price: number | null | undefined,
): number | null {
  if (entry == null || price == null) return null
  return ((price - entry) / entry) * 100
}

export function scanAgeLabel(seconds: number | null | undefined): string {
  if (seconds == null) return "no scan yet"
  if (seconds < 60) return "just now"
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  return `${Math.round(seconds / 3600)}h ago`
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run lib/format.test.ts`
Expected: PASS, all assertions green.

- [ ] **Step 5: Commit**

```bash
git add lib/format.ts lib/format.test.ts
git commit -m "feat(dashboard): add display formatters (price, pct, P/L, scan age)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `lib/plan.ts` — Plan Rail geometry (TDD)

The Rail draws stop→entry→target left-to-right with a live marker. `railPositionPct(level)` maps any price to a 0–100 position across the [stop, target] span (clamped). Used for both the entry tick and the live marker.

**Files:**
- Create: `dashboard-web/lib/plan.ts`
- Test: `dashboard-web/lib/plan.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-web/lib/plan.test.ts`:

```ts
import { describe, it, expect } from "vitest"
import { railPositionPct } from "@/lib/plan"

const stop = 117.9, entry = 121.4, target = 129.0

describe("railPositionPct", () => {
  it("puts stop at 0 and target at 100", () => {
    expect(railPositionPct(stop, { stop, entry, target })).toBe(0)
    expect(railPositionPct(target, { stop, entry, target })).toBe(100)
  })
  it("places entry between them", () => {
    const p = railPositionPct(entry, { stop, entry, target })
    expect(p).toBeGreaterThan(0)
    expect(p).toBeLessThan(100)
    expect(p).toBeCloseTo(31.5, 0) // (121.4-117.9)/(129-117.9)
  })
  it("clamps prices outside the span", () => {
    expect(railPositionPct(110, { stop, entry, target })).toBe(0)
    expect(railPositionPct(140, { stop, entry, target })).toBe(100)
  })
  it("returns null when any level is missing or live is missing", () => {
    expect(railPositionPct(124, { stop: null, entry, target })).toBeNull()
    expect(railPositionPct(null, { stop, entry, target })).toBeNull()
  })
  it("returns null on a degenerate span", () => {
    expect(railPositionPct(120, { stop: 120, entry: 120, target: 120 })).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run lib/plan.test.ts`
Expected: FAIL — cannot find module `@/lib/plan`.

- [ ] **Step 3: Implement**

Create `dashboard-web/lib/plan.ts`:

```ts
export interface PlanLevels {
  stop: number | null | undefined
  entry: number | null | undefined
  target: number | null | undefined
}

/**
 * Map a price to its 0–100 position on the Rail, which runs stop (0) → target (100).
 * Clamped to [0,100]. Returns null if any level, the price, or a non-degenerate span is unavailable.
 */
export function railPositionPct(
  price: number | null | undefined,
  { stop, target }: PlanLevels,
): number | null {
  if (price == null || stop == null || target == null) return null
  const lo = Math.min(stop, target)
  const hi = Math.max(stop, target)
  if (hi - lo === 0) return null
  const pct = ((price - lo) / (hi - lo)) * 100
  return Math.max(0, Math.min(100, pct))
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run lib/plan.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/plan.ts lib/plan.test.ts
git commit -m "feat(dashboard): add Plan Rail geometry (railPositionPct)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `lib/signal.ts` — status & verdict derivation (TDD)

Maps raw snapshot fields to the Board's display vocabulary: a `StatusKind` (triggered/armed/watching/closed) and a Command-Center `VerdictKind` with label + tone. Tones are token names used by later components.

**Files:**
- Create: `dashboard-web/lib/signal.ts`
- Test: `dashboard-web/lib/signal.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-web/lib/signal.test.ts`:

```ts
import { describe, it, expect } from "vitest"
import { verdictDisplay, statusKind } from "@/lib/signal"

describe("verdictDisplay", () => {
  it("maps known verdicts to label + tone", () => {
    expect(verdictDisplay("reaffirm")).toEqual({ label: "✓ reaffirm", tone: "green" })
    expect(verdictDisplay("adjust")).toEqual({ label: "◐ adjust", tone: "amber" })
    expect(verdictDisplay("override")).toEqual({ label: "⊘ override", tone: "red" })
    expect(verdictDisplay("close")).toEqual({ label: "✕ close", tone: "red" })
  })
  it("treats null/unknown as awaiting handoff", () => {
    expect(verdictDisplay(null)).toEqual({ label: "⋯ awaiting", tone: "muted" })
    expect(verdictDisplay("banana")).toEqual({ label: "⋯ awaiting", tone: "muted" })
  })
})

describe("statusKind", () => {
  it("is triggered when entry fired and not closed", () =>
    expect(statusKind({ entry_triggered: true, status: "open" })).toBe("triggered"))
  it("is closed when status says closed", () =>
    expect(statusKind({ entry_triggered: true, status: "closed" })).toBe("closed"))
  it("is watching when not triggered", () =>
    expect(statusKind({ entry_triggered: false, status: "open" })).toBe("watching"))
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run lib/signal.test.ts`
Expected: FAIL — cannot find module `@/lib/signal`.

- [ ] **Step 3: Implement**

Create `dashboard-web/lib/signal.ts`:

```ts
export type Tone = "green" | "red" | "amber" | "azure" | "brass" | "muted"
export type StatusKind = "triggered" | "armed" | "watching" | "closed"
export type VerdictKind = "reaffirm" | "adjust" | "override" | "close"

const VERDICTS: Record<VerdictKind, { label: string; tone: Tone }> = {
  reaffirm: { label: "✓ reaffirm", tone: "green" },
  adjust: { label: "◐ adjust", tone: "amber" },
  override: { label: "⊘ override", tone: "red" },
  close: { label: "✕ close", tone: "red" },
}

export function verdictDisplay(verdict: string | null | undefined): { label: string; tone: Tone } {
  if (verdict && verdict in VERDICTS) return VERDICTS[verdict as VerdictKind]
  return { label: "⋯ awaiting", tone: "muted" }
}

export function statusKind(s: { entry_triggered: boolean; status: string | null }): StatusKind {
  if (s.status === "closed") return "closed"
  if (s.entry_triggered) return "triggered"
  return "watching"
}
```

> Note: `armed` (near-entry) is derived later from live price vs entry distance in Plan 2; `statusKind` here covers the snapshot-only states.

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run lib/signal.test.ts`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `npm test`
Expected: PASS — format + plan + signal suites all green.

- [ ] **Step 6: Commit**

```bash
git add lib/signal.ts lib/signal.test.ts
git commit -m "feat(dashboard): add status & verdict derivation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Anti-AI design tokens

Replace the cyan-on-pure-black palette in `globals.css` with the spec §6 tokens. CSS-only; verified by manual run.

**Files:**
- Modify: `dashboard-web/app/globals.css:4-23` (the `:root` block)

- [ ] **Step 1: Replace the `:root` token block**

In `dashboard-web/app/globals.css`, replace the existing `:root { ... }` (lines 4–23) with:

```css
:root {
  --bg-base:      #0a0c10;
  --bg-surface:   #0c0f14;
  --bg-elevated:  #0e1218;
  --border:       #1a1f27;
  --border-soft:  #14181f;
  --border-focus: #2a3340;
  --text-primary:   #e8ebf0;
  --text-secondary: #9aa3b2;
  --text-tertiary:  #5f6776;
  --text-muted:     #2a313c;
  --green:   #36d399;
  --red:     #ff6363;
  --amber:   #e0a64d;
  --brass:   #c7ad6a;
  --accent:  #5b9dff; /* Tony / azure */
  --cyan:    #5b9dff; /* legacy alias → accent (kept so old pages still compile) */
  --blue:    #5b9dff;
  --violet:  #7c4dff;
}
```

> Keep `--cyan`/`--blue` as aliases of `--accent` so the still-present old pages compile until they're deleted in later plans.

- [ ] **Step 2: Update the focus ring color**

In `globals.css`, the `*:focus-visible` rule uses `var(--cyan)` — leave it; it now resolves to azure. No change needed.

- [ ] **Step 3: Verify the app still builds**

Run: `npm run build`
Expected: build succeeds (type-check + compile) with no errors.

- [ ] **Step 4: Commit**

```bash
git add app/globals.css
git commit -m "feat(dashboard): anti-AI design tokens (ink base, azure+brass accents)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `StatusBar` — the ambient rail

Top bar replacing the left icon-rail: Tony wordmark + scanning dot, market clock, KPI cluster (Watching/Triggered/Win), nav links (Board / Record), events bell. Consumes existing `api.today` + `useMarketStatus`, and the Task 2 formatters.

**Files:**
- Create: `dashboard-web/components/layout/StatusBar.tsx`

- [ ] **Step 1: Implement the component**

Create `dashboard-web/components/layout/StatusBar.tsx`:

```tsx
"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useMarketStatus } from "@/lib/hooks/useMarketStatus"
import { scanAgeLabel } from "@/lib/format"

const NAV = [
  { href: "/", label: "Board" },
  { href: "/record", label: "Track Record" },
]

export function StatusBar() {
  const pathname = usePathname()
  const { data } = useQuery({ queryKey: ["today"], queryFn: api.today, refetchInterval: 30_000 })
  const market = useMarketStatus()

  const scanning = data?.watch.status === "running"
  const wr = data?.kpis.win_rate

  return (
    <header style={{
      position: "fixed", top: 0, left: 0, right: 0, height: 48, zIndex: 100,
      display: "flex", alignItems: "center", gap: 18, padding: "0 16px",
      background: "var(--bg-surface)", borderBottom: "1px solid var(--border)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          width: 7, height: 7, borderRadius: "50%",
          background: scanning ? "var(--green)" : "var(--text-tertiary)",
          boxShadow: scanning ? "0 0 8px var(--green)" : "none",
        }} />
        <span style={{ fontWeight: 800, letterSpacing: "0.04em", color: "var(--text-primary)" }}>TONY</span>
        <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
          {scanning ? "scanning" : "idle"} · {scanAgeLabel(data?.watch.last_scan_age_seconds ?? null)}
        </span>
      </div>

      <span className="mono" style={{ fontSize: 12, color: "var(--brass)" }}>
        ● {market?.open ? "MARKET OPEN" : "MARKET CLOSED"}
      </span>

      <nav style={{ display: "flex", gap: 4, marginLeft: 8 }}>
        {NAV.map(({ href, label }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href)
          return (
            <Link key={href} href={href} aria-current={active ? "page" : undefined} style={{
              fontSize: 12, padding: "4px 10px", borderRadius: 6, textDecoration: "none",
              color: active ? "var(--text-primary)" : "var(--text-secondary)",
              background: active ? "var(--bg-elevated)" : "transparent",
            }}>{label}</Link>
          )
        })}
      </nav>

      <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--text-secondary)", marginLeft: "auto" }}>
        <span>Watching <b style={{ color: "var(--text-primary)" }}>{data?.kpis.watching ?? "—"}</b></span>
        <span>Triggered <b style={{ color: "var(--text-primary)" }}>{data?.kpis.triggered ?? "—"}</b></span>
        <span>Win <b style={{ color: "var(--green)" }}>{wr != null ? `${Math.round(wr * 100)}%` : "—"}</b></span>
      </div>
    </header>
  )
}
```

- [ ] **Step 2: Commit (wired up in Task 7)**

```bash
git add components/layout/StatusBar.tsx
git commit -m "feat(dashboard): add ambient StatusBar (scanning, clock, KPIs, nav)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: App shell + routing collapse

Swap the left `Sidebar` for the top `StatusBar`, make `/` the Board placeholder (no redirect), add `/record` placeholder. Old pages remain reachable-but-unlinked.

**Files:**
- Modify: `dashboard-web/app/layout.tsx`
- Modify: `dashboard-web/app/page.tsx`
- Create: `dashboard-web/app/record/page.tsx`

- [ ] **Step 1: Update the layout**

Replace `dashboard-web/app/layout.tsx` with:

```tsx
import type { Metadata } from "next"
import "./globals.css"
import { Providers } from "@/lib/providers"
import { DrawerProvider } from "@/components/overlays/DrawerContext"
import { StatusBar } from "@/components/layout/StatusBar"
import { LazyDrawers } from "@/components/overlays/LazyDrawers"
import { AlertManager } from "@/components/alerts/AlertManager"
import { PermissionBanner } from "@/components/alerts/PermissionBanner"

export const metadata: Metadata = { title: "Tony", description: "Tony's trading cockpit" }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ background: "var(--bg-base)", minHeight: "100vh" }}>
        <Providers>
          <DrawerProvider>
            <PermissionBanner />
            <StatusBar />
            <main className="app-main" style={{ paddingTop: 48, minHeight: "100vh" }}>
              <div style={{ padding: 16 }}>{children}</div>
            </main>
            <LazyDrawers />
            <AlertManager />
          </DrawerProvider>
        </Providers>
      </body>
    </html>
  )
}
```

- [ ] **Step 2: Make `/` the Board placeholder**

Replace `dashboard-web/app/page.tsx` with:

```tsx
export default function BoardPage() {
  return (
    <div>
      <h1 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>
        The Board
      </h1>
      <p style={{ color: "var(--text-tertiary)", fontSize: 12 }}>
        Tony's picks land here (Plan 2).
      </p>
    </div>
  )
}
```

- [ ] **Step 3: Add the Track Record placeholder**

Create `dashboard-web/app/record/page.tsx`:

```tsx
export default function RecordPage() {
  return (
    <div>
      <h1 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>
        Track Record
      </h1>
      <p style={{ color: "var(--text-tertiary)", fontSize: 12 }}>
        Tony vs Tony Stocks lands here (Plan 4).
      </p>
    </div>
  )
}
```

- [ ] **Step 4: Build to verify**

Run: `npm run build`
Expected: build succeeds; `/` and `/record` compile.

- [ ] **Step 5: Manual smoke (the verification gate)**

Run: `npm run dev`, open `http://localhost:3000`.
Confirm: top StatusBar shows TONY + scanning dot + clock + Watching/Triggered/Win + Board/Track Record nav; `/` shows "The Board" placeholder; `/record` shows "Track Record" placeholder; no left sidebar; no console errors.

- [ ] **Step 6: Commit**

```bash
git add app/layout.tsx app/page.tsx app/record/page.tsx
git commit -m "feat(dashboard): collapse shell to StatusBar + Board/Record routes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Plan 1 — done-when

- `npm test` green (format + plan + signal suites).
- `npm run build` succeeds.
- App boots: top StatusBar, `/` Board placeholder, `/record` placeholder, no left sidebar, no console errors.
- Old pages still exist but are unlinked (deleted in later plans).

---

## Roadmap — Plans 2–6 (expand each into its own plan when reached)

Each builds on Plan 1's lib + tokens + shell, ships independently, and ends with `npm test` + `npm run build` + a manual smoke.

**Plan 2 — The Board ("The Tape"), Tony layer.** Build `BoardTable`, `PlanRail` (uses `railPositionPct`), `VerdictChip`, `DualScore`, `UniverseToggle`. Render the 9 Watches columns (Ticker · Last·Day · P/L · Plan Rail · R:R · Tony · T.STK · Verdict · Status) from `api.tracking`/`api.today` + `useLivePrices`; the leaner Universe set from `api.scanLatest`. Derive `armed` from live-vs-entry distance (new tested helper in `lib/signal.ts`). Row click opens the deep-dive. Delete `app/today`, `app/watchlist`, `app/picks`, `app/scan`. Tests: column derivation, armed threshold, P/L vs day-% never swapped, Universe column set.

**Plan 3 — Ticker deep-dive + PlanChart.** Elevate `SymbolDrawer` into `DeepDive`: header + big Rail, dual-analysis columns (Tony sub-scores/reasons/warnings; Tony Stocks verdict/reasoning with awaiting-degradation), "this pick's life" timeline. Build `PlanChart` (candlesticks + volume + price/date axes + crosshair readout + stop/entry/target plan lines; line toggle) from `api.symbolChart` using recharts. Tests: chart data shaping, plan-line placement, crosshair readout selection, degradation when CC data absent.

**Plan 4 — Track Record.** Build `TwoRecordHeader`, overlaid `EquityCurve` (reuse recharts component), `AgreementMatrix`, setup-breakdown bars from `api.outcomes` + `api.analytics`. Tony layer first; CC series behind the typed contract degrade to empty. Always-on research disclaimer. Delete `app/outcomes`, `app/analytics`. Tests: KPI derivation, agreement-matrix tallying, empty-state rendering.

**Plan 5 — Second-layer (Command Center) wiring.** Define the typed contract for structured Tony Stocks output (per-pick score/verdict/reasoning/returned-at + second record + agreement tallies). Add `api` methods reading it; fill the slots built in Plans 2–4; verify graceful degradation end-to-end. Coordinate the **separate backend task** that exposes this from the vault/Command Center bridge. Delete `app/system` (folds into StatusBar popover). Tests: contract parsing, degradation, agreement math against fixtures.

**Plan 6 — Polish.** Motion (reduced-motion safe), empty/error/loading states across surfaces, responsive reflow (table → stacked rows on phone), and a full a11y re-verification (contrast on the new palette, focus-visible, 44px coarse targets) per the spec §10 checklist. Remove `components/layout/Sidebar.tsx`.

---

## Self-Review (Plan 1)

- **Spec coverage (Plan 1 scope):** tokens §6 → Task 5; StatusBar/ambient rail §5.1 → Task 6; routing collapse §4 (`/`=Board, `/record`) → Task 7; pure-logic foundation for Rail §5.1, P/L vs day §5.1, verdict/status §5.1 → Tasks 2–4. Remaining spec sections are explicitly assigned to Plans 2–6 in the roadmap.
- **Placeholder scan:** no TBD/TODO; every code step has complete code; commands have expected output.
- **Type consistency:** `railPositionPct(price, PlanLevels)` signature consistent across Task 3 test + impl + Plan 2 usage note; `verdictDisplay`/`statusKind` names consistent Task 4 test + impl; `scanAgeLabel` consistent Task 2 + StatusBar Task 6; tokens referenced by StatusBar (`--green`, `--brass`, `--text-*`) all defined in Task 5.
