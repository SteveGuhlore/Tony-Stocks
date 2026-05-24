# Dashboard Revamp Design Spec
**Date:** 2026-05-24  
**Status:** Approved — ready for implementation  
**Replaces:** Streamlit `src/trading_bot/dashboard/app.py` (2,242 lines)

---

## Problem

The current Streamlit dashboard is glitchy and architecturally limited:

- Full Python script reruns on every widget interaction
- Navigation is `st.button` + `st.session_state` + `st.rerun()` — fragile and unpredictable
- Custom CSS targets internal Streamlit DOM selectors that break on Streamlit version updates
- No real-time updates without polling hacks
- Key views (ranked stocks, stock detail, events) buried in legacy expanders
- No click-through on symbol mentions — no drill-down possible

---

## Decision

**Replace Streamlit with Next.js 15 (App Router) + FastAPI.**

- All Python logic — scoring, analytics, CLI, vault, repositories, tests — is **untouched**
- FastAPI adds a thin API layer wrapping existing `ScannerRepository` calls
- Next.js handles routing, state, and UI
- Docker Compose runs both services with one command

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, App Router, TypeScript |
| Styling | Tailwind CSS v4 + CSS custom properties |
| State / data fetching | TanStack Query (React Query v5) |
| Charts | Recharts (client components) |
| Animations | motion/react (motion-foundations + motion-ui) |
| Backend API | FastAPI + uvicorn |
| Backend logic | Existing Python codebase (unchanged) |
| Database | SQLite via existing `ScannerRepository` (unchanged) |
| Containers | Docker Compose (2 services: `api`, `web`) |
| Live updates | Server-Sent Events (SSE) for heartbeat + events |

---

## Design System — Financial Terminal Aesthetic

Inspired by Bloomberg Terminal: dark, dense, data-forward, monospaced numbers.

### Color Tokens

```css
--bg-base:      #050505;   /* terminal black */
--bg-surface:   #0f0f0f;   /* cards */
--bg-elevated:  #161616;   /* nested surfaces */
--border:       #1f1f1f;
--border-focus: #333333;

--text-primary:   #f0f0f0;
--text-secondary: #666666;
--text-muted:     #2a2a2a;

--green:   #00e676;   /* target hit, positive P&L, ACTIVE */
--red:     #ff3d3d;   /* stop hit, negative P&L, STOPPED */
--amber:   #ffab00;   /* watching, warnings, STALE */
--blue:    #448aff;   /* info, scan events, links */
--cyan:    #00e5ff;   /* Tony analysis, AI reads */
--violet:  #7c4dff;   /* pending triggers */
```

### Typography

```
Font-numbers: "JetBrains Mono", "Fira Code", monospace
  Used for: tickers, prices, scores, timestamps, data values

Font-ui: "Geist", "Inter", system-ui, sans-serif
  Used for: labels, nav items, prose, descriptions

Size scale: 10px / 11px / 13px / 16px / 22px
```

### Layout

- 4px base grid
- Cards: `12px` padding, `4px` border-radius
- Section gap: `16px`
- Dense table rows: `28px` height
- Sidebar: `52px` fixed width, icon + tooltip

---

## Navigation Structure

Six pages plus two global overlays:

```
Sidebar (fixed left, 52px)
  ▌T  — brand mark
  ⚡  Today        /today
  👁  Watchlist    /watchlist
  📊  Outcomes     /outcomes
  🔍  Scan         /scan
  📈  Analytics    /analytics
  ⚙   System       /system
  🔔  Bell icon    → Notification Drawer
```

**Global overlays (available from any page):**
- **Symbol Drawer** — right-side sheet, opens when any ticker is clicked
- **Notification Drawer** — right-side sheet, opens from bell icon

Active nav item: left border cyan, background `--bg-surface`.

Live watch indicator: pulsing dot beside brand mark.
- Green pulse: watch active, last scan < 10m
- Amber: last scan 10–60m or watch stale
- Red: watch stopped or scan > 60m

---

## Page Designs

### ⚡ Today — Morning Briefing + Live Monitor

Primary daily driver. Two modes: calm briefing (pre/post market) and live ops (market hours 9:30–16:00 ET).

```
┌─ MARKET BANNER (full width) ─────────────────────────┐
│  ● MARKET OPEN  09:34 ET  │  SPY -0.3%  QQQ +0.1%   │
└──────────────────────────────────────────────────────┘

┌─ KPI BAR ────────────────────────────────────────────┐
│  WATCHING  │  TRIGGERED  │  WIN RATE  │  LAST SCAN    │
└──────────────────────────────────────────────────────┘

Left column (38%)            Right column (62%)
─────────────────────────    ──────────────────────────
BRIEFING                     LIVE SETUPS
  Agent insight note           [TradeCard per active/watching position]
  (italic, from vault bridge)
                             RECENT ACTIVITY (SSE feed)
MARKET CONTEXT                 Chronological event stream
  Tony market read             Last 10-15 significant events

REVIEW TODAY
  Bullet list of action items
```

Live setups + activity feed update via SSE. KPI bar re-polls every 30s.

---

### 👁 Watchlist — Picks + Tracking

```
Filter chips: [ ALL ]  [ ACTIVE ]  [ WATCHING ]  [ PENDING ]  [ STALE ]

[TradeCard per symbol — entry/stop/target/R:R, colored status badge]
  Active: green left border
  Watching: amber left border
  Stale: red/amber pulsing indicator
  Click symbol → Symbol Drawer
```

---

### 📊 Outcomes — Results History

```
┌─ RESULTS KPI BAR ────────────────────────────────────┐
│  ACTIVE │ CLOSED │ TARGETS │ STOPS │ WIN RATE         │
└──────────────────────────────────────────────────────┘

Filter chips: [ ALL ]  [ OPEN ]  [ TARGETS ✅ ]  [ STOPS ❌ ]

[TradeCard per outcome — entry → exit price, P&L, outcome badge]
  Click symbol → Symbol Drawer
```

---

### 🔍 Scan — Ranked Stocks + Tony Reads

Previously buried in legacy expanders. Now first-class.

```
FILTERS
  Min score slider · Category select · Role select
  Tags multiselect · Primary only · Exclude ETFs

CANDIDATES TABLE (dense, terminal-style, clickable rows)
  SYM | SCORE | SETUP | CLOSE | ENTRY | STOP | TARGET | R:R | PLAN

TONY ANALYST READS
  [Expandable hypothesis cards — priority icon, symbol, action, setup]
  Market Context card
  Risk Warning card
  Data Quality card
```

Filter state persists in URL query params. Every row clickable → Symbol Drawer.

---

### 📈 Analytics — Backtest + Outcome Deep Dive

```
OVERVIEW KPIs
  Reviewed · Conclusive · Win Rate · Max Drawdown

SIMULATED EQUITY CURVE  [Recharts LineChart, "use client"]

BY SETUP CATEGORY       [Recharts BarChart + Table]
BY SCORE BUCKET         [Table]
BY UNIVERSE ROLE        [Table]

SIGNAL SCORECARD        [Table — V28 signal attribution data]

VAULT BRIDGE SUMMARY
  Tier 1/2/3 signal counts
  Sector cluster risk flags
  Sector ETF snapshot
```

---

### ⚙ System — Health + Config

```
DATA & SAFETY         [real_data_only, provider, demo_blocked, tony_status]
OPERATIONS            [watch_status, last_scan_age, api_requests, symbols_scanned]
HEALTH ISSUES         [warning/error banners when issues exist]
RECONCILIATION        [snapshot counts]
TRACKED POSITION GAPS [stale + missing symbols]

▼ Data Quality Panel
▼ Watch Health
▼ Market Day Review
▼ Tony Learning
▼ Legacy Developer Views
```

---

## Global Overlays

### Symbol Drawer (right sheet, ~480px)

Opens when any `<TickerSymbol>` component is clicked anywhere in the app.

```
[← close]   AAPL   ● ACTIVE   Score: 87

SCORE BREAKDOWN     [Recharts horizontal BarChart]
  Trend / Momentum / Volume / Risk / Setup Quality

TRADE PLAN
  Entry · Stop · Target · R/R · Plan valid/invalid

CANDLESTICK CHART   [Recharts, "use client", 60 days, SMA20/SMA50]

TONY HYPOTHESIS
  Priority · Action · Setup read · Concerns
  Full hypothesis text

REASONS + WARNINGS  [lists]

SNAPSHOT HISTORY    [last 5 snapshots, outcome + P&L]
```

Animation: `AnimatePresence mode="wait"`, slide-in from right.

---

### Notification Drawer (right sheet)

Opens from bell icon. Red badge count when unacknowledged warnings exist.

Shows last 50 significant Tony events, severity color-coded:
- `⛔ ERROR` — all_symbol_fallback, critical failures
- `⚠ WARNING` — rate_limit_warning, stale data, risk warnings
- `🔴 HIGH` — analyst_risk_warning, high_priority hypothesis
- `✅ INFO` — entry_triggered, scan_completed, target_hit

Click event row → expand full payload JSON.

---

## API Layer

New directory: `src/trading_bot/api/`

All endpoints are thin read-only wrappers around existing `ScannerRepository` methods. No business logic in the API layer. All responses use Pydantic models.

```
GET  /api/health
GET  /api/today                    KPIs + briefing + market context + activity feed
GET  /api/picks                    Tony picks (watchlist rows)
GET  /api/tracking                 Active tracking positions
GET  /api/outcomes                 Outcome cards + KPI bar
GET  /api/scan/latest              Latest scan results (filterable: min_score, category, role, tags)
GET  /api/scan/overview            Funnel metrics (scanned → candidates → picks)
GET  /api/analytics/backtest       Backtest review summary + equity curve
GET  /api/analytics/outcomes       Grouped analytics (setup, bucket, role, signal scorecard)
GET  /api/events                   Tony events (query: type, severity, symbol, limit, unacked_only)
GET  /api/events/stream            SSE — heartbeat every 5s + new significant events
GET  /api/system/health            System health summary
GET  /api/system/reconciliation    Snapshot reconciliation counts
GET  /api/snapshots                Candidate snapshots (filterable)
GET  /api/snapshots/{id}           Single snapshot detail
GET  /api/symbols/{symbol}/chart   OHLCV bars for Symbol Drawer chart
GET  /api/symbols/{symbol}/detail  Full detail: score, plan, Tony read, snapshot history
GET  /api/vault/bridge             Latest vault bridge export summary
GET  /api/insights                 Agent insights (last N)
```

CORS: allow `http://localhost:3000` in development, configurable via env.

---

## Live Updates (SSE)

`GET /api/events/stream` — `text/event-stream`

Emits:
- **Heartbeat (every 5s):** `{ type: "heartbeat", watch_status, last_scan_age_seconds, last_heartbeat_at }`
- **New events (on write):** `{ type: "event", event_type, severity, symbol, title, message, created_at }`

Frontend: `useSSE()` hook in `lib/sse.ts` wraps `EventSource` with automatic reconnect on disconnect. Consumers:
- Sidebar live dot (heartbeat)
- Today activity feed (new events)
- Notification badge count (warnings/errors)

---

## File Structure

```
TradingBotAgentProject/
│
├── src/trading_bot/
│   ├── api/                        ← NEW (only new Python code)
│   │   ├── __init__.py
│   │   ├── main.py                 ← FastAPI app, CORS, router registration
│   │   ├── schemas.py              ← Pydantic response models
│   │   └── routes/
│   │       ├── today.py
│   │       ├── picks.py
│   │       ├── outcomes.py
│   │       ├── scan.py
│   │       ├── analytics.py
│   │       ├── events.py           ← SSE stream
│   │       ├── system.py
│   │       ├── symbols.py
│   │       └── vault.py
│   └── [all existing modules — untouched]
│
├── dashboard-web/                  ← NEW (Next.js app)
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                ← redirect → /today
│   │   ├── today/page.tsx
│   │   ├── watchlist/page.tsx
│   │   ├── outcomes/page.tsx
│   │   ├── scan/page.tsx
│   │   ├── analytics/page.tsx
│   │   └── system/page.tsx
│   ├── components/
│   │   ├── layout/                 Sidebar, MarketBanner, TopBar
│   │   ├── terminal/               KPIBar, TradeCard, StatusBadge, TickerSymbol,
│   │   │                           ScanTable, ActivityFeed, FilterChips,
│   │   │                           TonyHypothesisCard, PriceValue
│   │   ├── charts/                 CandlestickChart, ScoreBreakdown, EquityCurve,
│   │   │                           OutcomeBar, ScoreDist  (all "use client")
│   │   └── overlays/               SymbolDrawer, NotificationDrawer, DrawerContext
│   ├── lib/
│   │   ├── api.ts                  Typed fetch wrappers
│   │   ├── queries.ts              All TanStack Query hooks
│   │   ├── sse.ts                  useSSE() hook
│   │   └── tokens.ts               Design token constants
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── Dockerfile
│
├── Dockerfile                      ← NEW (Python/FastAPI)
├── docker-compose.yml              ← NEW
├── docker-compose.prod.yml         ← NEW (no --reload, built Next.js)
└── Makefile                        ← NEW
```

---

## Docker Compose

### `docker-compose.yml` (development)

```yaml
version: "3.9"
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    command: uvicorn trading_bot.api.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./data:/app/data
      - ./config:/app/config
      - ./vault:/app/vault
      - ./.env:/app/.env:ro
    ports:
      - "8000:8000"
    environment:
      - PYTHONPATH=/app/src
    restart: unless-stopped

  web:
    build:
      context: ./dashboard-web
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - api
    restart: unless-stopped
```

### `Makefile`

```makefile
dev:        docker compose up
build:      docker compose build
prod:       docker compose -f docker-compose.prod.yml up -d
logs:       docker compose logs -f
shell-api:  docker compose exec api bash
shell-web:  docker compose exec web sh
test:       docker compose exec api python -m pytest
stop:       docker compose down
```

---

## What Is NOT Changing

Explicitly out of scope — must not be modified during implementation:

- All of `src/trading_bot/` except the new `api/` subdirectory
- All `config/` YAML files
- All `tests/` — existing 849 tests must continue to pass
- `data/trading_bot.db` schema
- All `scripts/`
- All project doc files (AGENTS.md, ARCHITECTURE_RULES.md, etc.)

The Streamlit `app.py` is deprecated but **not deleted** until the new dashboard is verified working end-to-end.

---

## Testing Approach

**API layer** (`tests/test_api_*.py`):
- Each endpoint tested against real in-memory SQLite (same pattern as existing repository tests)
- SSE endpoint: verify heartbeat events emitted
- No mocking of `ScannerRepository`

**Frontend** (`dashboard-web/`):
- Vitest + React Testing Library for terminal primitive components
- Playwright E2E: Today loads, Watchlist filters work, Symbol Drawer opens/closes

**Regression:**
- Full existing pytest suite (849 tests) must pass after API layer added
- Run via `make test`

---

## Build Order

1. Design tokens + Tailwind config
2. FastAPI skeleton (`main.py`, CORS, health endpoint, Dockerfiles)
3. Docker Compose + Makefile — verify `make dev` starts both services
4. All FastAPI routes + Pydantic schemas
5. Next.js shell — layout, sidebar, routing
6. Terminal UI primitives (KPIBar, TradeCard, StatusBadge, TickerSymbol, ScanTable)
7. Today page
8. Watchlist page
9. Outcomes page
10. Scan page
11. Analytics page (Recharts charts)
12. System page
13. Symbol Drawer overlay
14. Notification Drawer + SSE integration
15. Live dot + MarketBanner + ActivityFeed
16. Vault Bridge panel
17. Playwright E2E tests
