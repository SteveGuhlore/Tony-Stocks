# Kinetic Tape — Bot Dashboard Rebuild (Design Spec)

_Design locked 2026-06-07 via superpowers brainstorming + visual companion + grill-me-codex (Act 1)._
_Operator: Stephen. Builder: Claude._

## 1. Goal

Replace the buggy `dashboard-web/` frontend (6th attempt) with a brand-new, visually stunning **and**
technically dense single-operator cockpit that shows **exactly what the first-pass scanner is doing** —
and how the smarter second-pass agent (Tony, in the Command Center) refined it. Keep the proven
FastAPI data spine; rebuild only the face. The dashboard is the **front-facing window into the
first-pass bot**; the second pass (Tony) is the deeper LLM agent that reaffirms / overrides / adjusts.

**Hard success criterion (the one that killed the last 5 attempts):** what we approved in mockups must
be what ships. A **design-fidelity guarantee** (§11) is a first-class workstream, not an afterthought.

## 2. Users & context

- **Single operator (Stephen) only.** No multi-user, no auth beyond network + action token, no public
  showcase polish budget. Expert user — optimize for density and "what is the bot doing right now."
- **Desktop-first, fully mobile-interactive.** Used at the desk on a large monitor AND from a phone
  while away (over Tailscale). Mobile must support real actions, not just glancing.

## 3. Scope

**In scope (this initiative):** the new frontend + a small set of backend control endpoints + a few
SQLite tables for personalization. **Out of scope (explicitly deferred to its own future initiative):**
scanner / scoring / strategy tuning — that becomes a full audit via grill-me-codex later. The dashboard
is built first as the instrument that makes that future tuning evidence-based (see the Scanner X-ray view).

**No bot-logic changes.** Wipe only `dashboard-web/`. The scanner, watch loop, paper engine, learn,
vault, and the 22-endpoint API are untouched except for additive new endpoints.

## 4. Information architecture — Concept A: "One Cockpit"

A single living cockpit that **morphs by market phase**, with a slim rail for depth and an overlay
deep-dive. (Chosen over multi-route B and rejected canvas C; C failed the mobile requirement.)

- **Phase morph (auto by market clock + manual override):** a `Prep / Live / Review` segmented control.
  - **Live** (market hours) = "The Tape" (the watchlist).
  - **Prep** (pre-open) = Morning shortlist + conviction + catalysts + "what changed overnight" + "plan for open."
  - **Review** (after close) = EOD recap (triggered, hits/misses, what the 2nd pass did, lessons).
- **Slim left rail → dedicated views:** Cockpit · Track Record · Paper Book · Scanner X-ray · System.
- **Symbol deep-dive = slide-over overlay** (the one good idea from the old dashboard — see §6).
- **⌘K command palette** — jump to any symbol / view / action by keyboard. Power accelerator.
- **Mobile reflow:** rail → bottom tab bar, side panel stacks, deep-dive goes full-screen. (No drag-arrange.)

## 5. The tape row (enriched, glanceable)

Each row is scannable in half a second and answers "is this worth a tap?" — full charts are gated to
the symbol screen so the tape stays fast across 1,000+ symbols:

| Element | Meaning |
|---|---|
| Symbol + sector | identity |
| Last + **day change %** | live price; change vs **prev close** (NOT position P/L — kept separate) |
| **Sparkline + RVOL** | intraday trend at a glance + is it actually active today |
| **Score glyph** | 0–100 + the 5 sub-score micro-bars (trend·momentum·volume·risk·setup), glowing |
| **Plan-rail** | live price marker between `stop · entry · target`; amber "approaching" zone, green past entry |
| **2nd pass** | Tony's verdict pill **+ his score** (e.g. `↑ reaffirm · 88`) next to the bot's 91 |
| Status | NEAR (pulse) / TRIGGERED / watching |

## 6. Symbol screen (dual-source slide-over)

Tap a row → sleek full-height drawer. **Pulls from BOTH passes, side by side** (the beloved feature):

- **Header:** symbol, last price + **day change (labeled)**, sector, setup, near badge, RVOL, close (✕).
- **Gated chart:** lightweight-charts candlesticks + plan lines (entry/stop/target) + crosshair; SMA/VWAP/volume toggles. This is where the graphs live.
- **Score comparison banner:** bot score vs **Tony's score** + delta.
- **Dual panes:** left (cyan) = **this scanner** (1st pass): score, 5 sub-scores, reasons[], warnings[],
  Tony-analyst deterministic read. Right (amber) = **Tony · deep agent** (2nd pass): verdict, **his score**,
  reasoning, any level adjustments (e.g. nudged entry 183.0→183.4), the edge it saw, returned_at.
- **Agreement track record on this symbol:** agreed-right / agreed-wrong / Tony-saved / Tony-missed.
- **Paper position:** status; when held → fill · qty · **position P/L since fill** (separate from day change).
- **Actions:** Pin · Note · Set alert · History.

## 7. Action surface (full, built in one pass)

All actions are new `POST` endpoints mirroring existing CLIs/kill-files, behind a confirm dialog +
the action token (§9). Sequenced in build (safety first) but all ship this initiative.

- **Safety (money-adjacent):** Stop watch (`STOP_WATCH_MODE`) · Pause paper (`STOP_PAPER_TRADING`) ·
  Flatten all (double-confirm, mirrors `paper-flatten`) · Flatten one · Re-protect (re-arm OCO) · Resume paper.
- **Workflow:** Trigger scan now · Re-run morning prep · Push bridge to CC (export-to-vault) · Acknowledge alert.
- **Watchlist:** Pin/star focus list · Add note · Add manual pick · Quarantine a symbol.
- **Alerts:** Phone push (Telegram) · Custom price alert · Snooze/mute · Tune alert thresholds.
- **Calibration (READ-ONLY):** See pending weight proposals. **Approve (Key 1) and Activate (Key 2) stay CLI-only.**
- **View (always):** filter/sort/search the tape · saved view presets · density/theme toggle · compare two symbols · time-travel a past date · journal · rate-a-call.

**Never** placeable from the dashboard: new entries (fire only via the watch loop — hard invariant), live weight activation, universe edits, nightly-learn trigger.

## 8. Realtime + notifications

- **Live updates:** reuse the existing SSE event stream (`/api/events/stream`) + TanStack Query polling.
  Live ticks during hours (15s/120s as today); calm/slow off-hours.
- **Phone push (away-from-desk):** **Telegram bot**, sent **server-side from the VM** (near-entry,
  triggered, stop violation). Tap a message → deep-links into the dashboard. Reuses existing Telegram tooling.

## 9. Security / remote access

- Dashboard reachable only on the **Tailscale** network. Read views need nothing extra.
- **Money-adjacent POST actions require a shared action token / PIN** (a fat-finger or a random tailnet
  device can't fire Flatten-all blind). No full login (single-operator local tool; overkill).

## 10. Visual system — "Kinetic Tape"

The locked design language. Reference implementations are the committed mockups in
`.superpowers/brainstorm/9752-1780851075/content/` (esp. `08-kinetic-system.html`, `09-enriched-row.html`,
`11-symbol-drawer-v2.html`). **These mockups are the visual contract — their CSS/SVG/tokens lift directly into code.**

- **Palette (semantic tokens, AA-checked on dark):** `--bg #0a0c0b`, `--panel #0f1311`, `--ink #eaf2e9`,
  `--mut #7e8a82`, `--lime #c4f042` (accent/score, used sparingly), `--cyan #37e0ff` (**BOT / 1st pass**),
  `--amber #ff9e2c` (**Tony / 2nd pass**), `--pos #46d39a`, `--neg #ff5d73`, `--warn #ffce4a`.
- **Type:** Space Grotesk (display/headings/symbols) + Space Mono (all numerics, tabular figures).
- **Motion language** (from `motion-foundations` + emil-design-eng):
  - Tokens: duration instant .08 / fast .18 / normal .35 / slow .6; easing smooth `cubic-bezier(.22,1,.36,1)`,
    sharp `cubic-bezier(.4,0,.2,1)`; springs `snappy/gentle/bouncy/instant/release`.
  - Rules: **transform/opacity only** (GPU); stagger rows 40ms; press `scale(.96)`; exit faster than enter;
    never `scale(0)`; origin-aware popovers; **full `prefers-reduced-motion`** (motion → ≤.2s opacity fades).
  - Signature motion: glowing score bars rise (staggered), near-entry pulse, drifting **universe field**.
- **Signature hero — the universe field:** the 1,000+ symbol universe rendered as a drifting, glowing
  field (lime/cyan nodes) behind the cockpit — built with **Pixi.js** (WebGL) for performance, paused
  under reduced-motion / low-end devices. Decorative-essential; degrades to a static gradient.

## 11. Design-fidelity guarantee (the make-it-stick workstream)

Closes the translation gap that killed prior attempts. **Non-negotiable, first-class:**

1. **Mockups are the spec, not inspiration.** Exact tokens/easing/fonts/SVG (plan-rail, score glyph,
   universe field) port directly from `.superpowers/brainstorm/` into `globals.css` + Tailwind theme + `lib/tokens.ts`.
2. **Tokens in code = single source of truth.** No ad-hoc hex/duration anywhere; every value is a named token.
3. **Component-first, verified-in-browser, before any page.** Build signature components → screenshot the
   real running app → diff against the mockup. Doesn't match = not done.
4. **Automated visual gate:** `ecc:gan-design` generator/evaluator scoring + `ecc:browser-qa` + Playwright
   screenshots at each step; `verification-before-completion` before any "done."
5. **Codex reviews the plan specifically for "where will this degrade in production?"**

## 12. Tech stack

- Keep: **Next.js 16 / React 19 / TypeScript / Tailwind 4 / TanStack Query**. Node 20 (VM gets Node 20 LTS).
- Motion: **`motion/react`** (Framer Motion v12) — never mix `framer-motion` import.
- Charts: **lightweight-charts** for candlesticks; **custom SVG + motion** for bespoke glyphs (score, plan-rail,
  funnel, attribution, head-to-head); **Pixi.js** for the universe field. **Drop Recharts.**
- Data: keep the **22 FastAPI endpoints**. Add additive **POST action endpoints** + SQLite tables
  (`pins`, `notes`, `presets`, `journal`, `call_ratings`, `price_alerts`). No scanner-logic changes.

## 13. Deploy

- Local dev is fully isolated (production runs on VM `trading-stack`; nothing live runs locally).
- VM gets **Node 20 LTS**; `update_vm.sh` builds the Next app once Node≥20. Runs **alongside** the CC dashboard.
- Telegram push + action token configured via env (never committed). Tailscale for remote access.

## 14. Testing & accessibility

- **vitest** (unit/lib), **Playwright** (E2E + the visual-diff gate), `ecc:gan-design` design loop.
- A11y: contrast AA (verified on dark), touch targets ≥44px, keyboard nav + ⌘K, `prefers-reduced-motion`,
  aria-live for alerts/toasts, screen-reader summaries on charts, no color-only meaning.

## 15. Open questions (non-blocking)

- **Naming:** Tony = the 2nd-pass Command Center agent (confirmed). The **first-pass bot/dashboard** name
  is open (mockups used "Tony" as a placeholder; that's actually the 2nd pass). Working label: "the Scanner."
  Operator to name it before final polish.
- Exact dashboard port on the VM (alongside CC) — pick at deploy.
- Whether the universe field renders the full 1,000+ or a representative sample for perf (decide at build via profiling).

## 16. Out of scope

Scanner/scoring/strategy tuning · live weight activation from UI · new-entry placement from UI ·
universe edits · multi-user/auth · the CC agent's own internals (separate workspace).
