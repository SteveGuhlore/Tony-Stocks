# Plan: Kinetic Tape — Bot Dashboard Rebuild (frontend-only, extend the API spine)
_Locked via grill — by Claude + Stephen (2026-06-07). Rev 3 (post-Codex-round-1)._
_Full design: docs/superpowers/specs/2026-06-07-kinetic-tape-dashboard-design.md_

## Goal
Replace the buggy `dashboard-web/` (6th attempt) with a single-operator, mobile-interactive, motion-rich
"Kinetic Tape" cockpit that shows exactly what the first-pass scanner is doing and how the second-pass
agent (Tony) refined it. **No scanner/scoring/strategy decision-logic changes — additive API / control / read-model work only;**
rebuild the frontend and **extend** the FastAPI spine with the read models + aggregate + control
endpoints the design needs. **No change to how the scanner scans/scores or how paper sizes/trades** —
the only edits to the watch/paper processes are **minimal additive concurrency hooks** so they honor the
shared cross-process lock/preconditions (§A6); learn and vault stay untouched. Defining
requirement: what was approved in the mockups must ship AND must not break on real production data — the
prior 5 attempts failed on the **translation gap AND on degraded-data/runtime states**, so both are gated.

## Approach
One pass on branch `feat/kinetic-dashboard`, sequenced so each layer is verifiable before the next.
Dev against a LOCAL API on :8001. **Read-only parity on prod-shaped fixtures is proven BEFORE any POST
control is wired.** The old frontend stays recoverable via git history (tag `dashboard-web-legacy`).

### A. Backend first (additive to the kept spine — no scanner/scoring/trade logic changes)
1. **Env-role fence (safety foundation).** Add `ENV_ROLE` (`dev`|`prod`) + expected DB root, read at
   startup, plus an **account fingerprint sourced at runtime from the live broker account identity
   (broker API account id), NOT a config/YAML label**. **All money-adjacent POSTs are hard-disabled
   unless `ENV_ROLE=prod` AND the runtime broker account id matches the expected prod fingerprint** —
   so local dev physically cannot hit the VM account (enforces DEPLOY_RULES). Fail-closed. Unit-tested.
2. **Extend read models** to expose columns that already exist in storage but aren't surfaced:
   `current_price`, `research_unrealized_pl_pct`, `reassessment_label`, `time_active_minutes`,
   `original_entry/stop/target`. (Verify against `storage/database.py` / `repositories.py`.)
3. **`GET /api/cockpit` aggregate** — one read-optimized symbol view-model per row (scan score + 5
   sub-scores + setup + levels + tracking live fields + day-change from prices + Tony verdict+score from
   command-center + near/triggered status + sparkline series + RVOL + per-symbol agreement). Kills the
   six-way client join. Every field nullable/awaiting-safe.
4. **First-party chart endpoint with a locked data source.** Persist intraday bars already fetched by the
   existing price-poll/watch cycle into a new SQLite `intraday_bars` table (rolling **10-trading-day**
   retention); daily bars come from stored daily snapshots. The chart endpoint reads ONLY from these
   stored sources (never on-request yfinance in the hot path) and returns explicit `unavailable`/`stale`
   when a symbol has no/old bars (UI shows a labeled empty-chart state, never a broken axis). Replaces the
   current empty `chart_bars` / on-request yfinance trap.
5. **Extend `/api/paper/positions`** with marked-to-live unrealized per-position P/L + protection (OCO)
   status + minimal order metadata (needed by the drawer + re-protect control).
6. **Control endpoints + safety middleware.** POST routes mirroring CLIs/kill-files (stop-watch,
   pause/resume-paper, flatten-all/one, re-protect, trigger-scan, export-bridge, ack-alert). Each:
   typed-PIN for dangerous actions, **Origin/Host allowlist**, short-lived signed nonce + **idempotency
   key**, and an immutable `action_audit` row. **Concurrency is cross-process** — a shared SQLite
   advisory lock / lockfile honored by the API **and** the watch/paper processes (not an in-process
   mutex); conflicting state returns **409**. Each action declares **server-enforced preconditions**:
   stop-watch / pause-resume-paper are idempotent; **trigger-scan 409s if a scan is already running**;
   **flatten-all / flatten-one / re-protect require a position snapshot/version match** (act only on the
   version the operator saw, else 409). No command-queue service — cross-process locks + preconditions +
   idempotency suffice for a single-operator tool.
7. **Personalization tables (additive migrations):** `pins`,`notes`,`presets`,`journal`,`call_ratings`,
   `price_alerts`,`action_audit`. Never stage live `data/`/`vault/`.

### B. Frontend
8. **Prep & scaffold** — add deps (`lightweight-charts`,`pixi.js`,`motion`), remove `recharts`; tag
   `dashboard-web-legacy`; wipe `dashboard-web/` frontend; fresh Next 16 App-Router skeleton; build green.
9. **Tokens & theme (single source of truth)** — port Kinetic Tape tokens from the committed mockups
   (`.superpowers/brainstorm/.../08,09,11`) → `globals.css` + Tailwind theme + `lib/tokens.ts` +
   `lib/motion-tokens.ts`; Space Grotesk + Space Mono. No ad-hoc hex/durations after this.
10. **Data layer** — typed client + TanStack Query hooks (primary source = `/api/cockpit`); types keep
    transport `verdict` as **`string`**, normalized in ONE display helper (handles `pass`/unknown →
    "awaiting"). **Every quote-dependent view supports `live|delayed|stale|unavailable`** and falls back
    to last scan/snapshot close when `/api/prices` 503s. **SSE** = reconnect backoff + rehydrate-from-GET
    on reconnect; **polling is the source of truth, SSE best-effort.**
11. **Signature components, component-first + visual-diff verified** — score glyph, plan-rail, sparkline,
    verdict pill, near pulse, buttons (`scale(.96)`), Sonner toast, drawer shell, ⌘K shell, **Pixi
    universe field** (capped node count, paused off-screen/reduced-motion/low-end, static gradient
    fallback). Each screenshot-diffed vs its mockup before moving on.
12. **Cockpit shell** — top bar (clock, Prep/Live/Review morph auto+manual, equity), slim rail, mobile
    reflow (rail→bottom bar, side stacks, drawer full-screen).
13. **Live view "The Tape"** — **virtualized/windowed** rows from `/api/cockpit`; **per-row price store**
    so live ticks don't re-render the table; **animation only on visible rows**; sort/filter/search,
    saved presets, near-entry highlight.
14. **Symbol deep-dive (dual-source)** — gated lightweight-charts candles+plan lines (from the new chart
    endpoint, with unavailable/stale states), bot vs **Tony score** comparison + dual reasoning panes,
    per-symbol agreement, paper position (marked-to-live P/L since fill, **separate from day-change**),
    actions.
15. **Rail views** — Track Record · Paper Book · Scanner X-ray · System; each degrades cleanly to
    "awaiting" when CC/outcomes/record files are empty.
16. **Prep & Review phase content** — morning shortlist/catalysts (`/morning-prep`); EOD recap.
17. **Wire actions** behind confirm dialogs (Flatten-all double-confirm + PIN); **POST controls are wired
    only after read-only parity passes (step 19).**
18. **Telegram push** (server-side, VM only, env secrets) + ⌘K palette + full **A11y** pass
    (reduced-motion, AA, keyboard, aria-live, chart summaries, ≥44px).

### C. Verification (the real make-it-stick — BOTH gates required)
19. **Read-only parity gate** — recorded-real-fixture E2E against a **VM-shaped API** proving every read
    view renders correctly on prod-shaped data INCLUDING degraded states: empty CC files, stale watch
    run, **503 prices / missing keys**, empty outcomes, unknown verdicts, CORS/origin, env-role drift.
20. **Visual-diff gate** — `ecc:gan-design` + `ecc:browser-qa` + Playwright screenshots vs every mockup.
21. **Action gate** — audit-row + idempotency + env-fence assertions; confirm money POSTs are no-ops in
    `ENV_ROLE=dev`. Then `tsc --noEmit` + `next build` clean; vitest + Playwright green;
    `verification-before-completion` before "done."
22. **Deploy prep** — Node 20 LTS on VM; `update_vm.sh` builds once Node≥20; runs alongside CC; Tailscale
    + action token/PIN + Telegram env; attended deploy per DEPLOY_RULES (tandem test, verify before trust).

## Key decisions & tradeoffs
- **One Cockpit (morphing) + rail + overlay + ⌘K**; not multi-route, not canvas (canvas failed mobile).
- **`/api/cockpit` aggregate** view-model (Codex #6) — one prod-shaped contract instead of fragile client joins.
- **Backend-first**: extend read models + chart + paper marks + aggregate BEFORE the UI assumes them (Codex #3/4/5).
- **Env-role fence + per-action PIN/nonce/idempotency/audit** (Codex #1/2/11) over a bare shared token; no
  command-queue service (kill-files are idempotent; locks+idempotency suffice).
- **Perf budget** (Codex #7): virtualized tape, per-row price store, animation only on visible rows,
  capped/paused Pixi field — phones must stay at 60fps.
- **Resilience-by-default** (Codex #8/9/10): stale/503 fallbacks, SSE best-effort around polling truth,
  string verdicts normalized once.
- **Two verification gates** (Codex #12): prod-shaped degraded-data E2E AND visual-diff — the prior
  attempts broke on data/runtime states, not just visuals.
- **Read-only parity before POST controls** (Codex #13, adapted): de-risk in-place via sequencing + git
  recoverability rather than a parallel `/v2` package (operator wants wipe-only-`dashboard-web`).
- **Pixi.js universe field** signature hero with hard perf fallback; **lightweight-charts** candles;
  **custom SVG** glyphs.

## Risks / open questions
- Universe-field perf on a phone — capped node sample + profile; never block input.
- Action-token/PIN storage + nonce signing key handling (env only); ensure dev fence is fail-closed.
- Additive SQLite migrations — scoped git adds only; never stage live data.
- Telegram bot token (env only); rate limits.
- New chart endpoint data source (stored bars vs price cache) — confirm coverage at build.
- Naming: Tony = 2nd-pass agent (confirmed); first-pass bot/dashboard name open (non-blocking).
- Node 20 on Debian 12 VM (nodesource/nvm) + `update_vm.sh` gate.

## Out of scope
Scanner/scoring/strategy tuning (own future audit) · live weight activation from UI · new-entry placement
from UI · universe edits · multi-user/auth · CC agent internals · any change to scanner/watch/paper/learn/vault logic.
