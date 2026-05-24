# Live Market Data Subsystem — Design Spec

**Date:** 2026-05-24
**Subsystem:** A (of A/B/C/D dashboard roadmap)
**Goal:** Transform the Next.js dashboard from a static daily-report into a live trading monitor with real-time prices, market-hour awareness, and multi-tier trade alerts.

---

## 1. Scope and Constraints

**In scope:**
- Live price polling for all tracked symbols (scan candidates ∪ manual picks ∪ active snapshots — typically 80–100)
- Market-hour gating: live data 9:30am–4:00pm ET (regular session only); cached close outside hours
- Three event types streamed via SSE: `entry_triggered`, `near_entry`, `stop_violation`
- Multi-tier client alerts: desktop notifications, audio beep, in-app toast
- "Distance to entry/stop/target" inline visualization
- Always-visible market clock badge

**Explicitly out of scope:**
- Pre-market / after-hours pricing
- Demo mode for missing API keys (return 503 with clear error instead)
- Order placement / execution
- Pre-IPO / OTC / crypto symbols

**Constraints:**
- Alpaca free-tier rate limit: 200 req/min (we'll use ~4 req/min)
- One Alpaca batch call per 15s during market hours (`/v2/stocks/snapshots`)
- Auto-pause to 120s polling when browser tab is backgrounded (Page Visibility API)

---

## 2. Architecture

### 2.1 Server: PriceCache + background task

**`src/trading_bot/api/live_prices.py`** — singleton in-memory cache:

```python
@dataclass
class LiveQuote:
    symbol: str
    price: float            # latest trade price
    bid: float | None
    ask: float | None
    prev_close: float
    change_pct: float       # (price - prev_close) / prev_close
    day_open: float
    day_high: float
    day_low: float
    day_volume: float
    asof: datetime          # quote timestamp
    is_live: bool           # false outside market hours

class PriceCache:
    _quotes: dict[str, LiveQuote]
    _symbols_refreshed_at: datetime
    _last_alpaca_call_at: datetime | None
    _previous_prices: dict[str, float]  # for crossing detection

    async def refresh(self) -> None: ...
    async def rebuild_symbol_set(self, repo) -> None: ...   # every 5 min
    def snapshot(self) -> dict[str, LiveQuote]: ...
    def get(self, symbol: str) -> LiveQuote | None: ...
```

**Background task** (started in `main.py` lifespan):
- Loop: check market open → if open, refresh quotes → sleep 15s. If closed, sleep 60s and re-check.
- Symbol set rebuilt every 5 min from `repo.list_candidate_snapshots() ∪ repo.manual_picks() ∪ repo.latest_scan_results()` (deduped uppercase)
- Calls Alpaca `GET /v2/stocks/snapshots?symbols=<csv>` — one request returns latest trade, latest quote, today bar, prev-day bar for every symbol
- On Alpaca failure: keep previous cache values, log warning, retry next cycle
- On detected events (see §2.3): push into a shared `asyncio.Queue` consumed by the SSE endpoint

### 2.2 Market-hours helper

**`src/trading_bot/api/market_calendar.py`** — thin wrapper over `pandas_market_calendars`:

```python
def market_status(now: datetime | None = None) -> dict:
    """Returns {open: bool, next_open: iso, next_close: iso, timezone}"""

def is_market_open(now: datetime | None = None) -> bool: ...
```

NYSE calendar only; regular hours only (no early-close handling for v1 beyond what the calendar reports).

### 2.3 Event detection (server-side)

In `PriceCache.refresh()` after fetching fresh quotes:

- **`near_entry`**: for each active snapshot where `entry` is set and `entry_triggered=False`, if `|price - entry| / entry < 0.005` (0.5%) and was *not* within 0.5% on the previous tick → emit. 5-minute cooldown per symbol to avoid spam.
- **`stop_violation`**: for each snapshot where `entry_triggered=True` and `outcome_label IS NULL`, if `price < stop` → emit. Once per snapshot only.
- **`entry_triggered`**: NOT emitted here — already handled by the existing bot watch cycle. We just relay it from the tony_events table via the existing SSE event loop.

Events go into `app.state.live_event_queue` (asyncio.Queue). The existing `/api/events/stream` endpoint reads from this queue in addition to its DB heartbeat loop.

### 2.4 API endpoints

**New router** `src/trading_bot/api/routes/prices.py`:

- `GET /api/prices` → `PricesResponse`:
  ```json
  {
    "symbols": [{"symbol": "SLB", "price": 57.45, "bid": 57.43, "ask": 57.47,
                 "prev_close": 57.00, "change_pct": 0.0079,
                 "day_open": 57.10, "day_high": 57.60, "day_low": 56.95,
                 "day_volume": 4250000, "asof": "...", "is_live": true}],
    "market": {"open": true, "next_open": "...", "next_close": "...",
               "timezone": "America/New_York"}
  }
  ```
- `GET /api/prices/{symbol}` → single `LiveQuote`
- Both return `503` with `{"detail": "Alpaca keys not configured"}` if no keys present at startup

### 2.5 Client: hooks and components

**Hooks** (`dashboard-web/lib/hooks/`):
- `useLivePrices()` — TanStack Query polling `/api/prices` every 15s; uses Page Visibility API to drop to 120s when `document.hidden`. Returns `{quotes: Map<string, LiveQuote>, market: MarketStatus}`.
- `useMarketStatus()` — selector over `useLivePrices()` returning just market + countdown computed client-side.
- `useAlerts()` — connects to SSE `/api/events/stream`, manages browser Notification permission, dispatches to AlertManager.

**Components** (`dashboard-web/components/market/`):
- `<LivePrice symbol entry?>` — `$57.45 +1.4%` color-coded green/red vs `prev_close` (daily change); if `entry` prop is provided, an additional inline delta vs entry is shown ("+1.4% to entry"). Gray with "STALE" badge if `Date.now() - asof > 45s`. Gray if `!is_live` with "CLOSE" badge.
- `<DistanceToBar current entry stop target />` — three pill row: `↑3.2% entry · ↓5.1% stop · ↑12.4% target`, each colored by direction.
- `<MarketClock />` — sidebar footer: `🟢 OPEN · closes in 2h 14m` or `🔴 CLOSED · opens Mon 9:30am`. Countdown updates every second client-side from cached `next_open`/`next_close`.

**Alerts** (`dashboard-web/components/alerts/`):
- `<AlertManager />` — mounted in root layout, no UI when idle. Subscribes via `useAlerts()`.
  - `entry_triggered` → `new Notification(...)` + `playBeep(880Hz, 200ms)` from `lib/sound.ts`
  - `near_entry` → `new Notification(...)` only (no sound)
  - `stop_violation` → in-app toast (persistent, dismissible) + `playBeep(330Hz, 400ms)` (lower tone)
- `<PermissionBanner />` — top-of-page yellow strip if `Notification.permission === "default"`: "Enable browser alerts? [Allow] [Not now]"
- `<ToastStack />` — bottom-right stack of persistent toasts

**Integrations into existing pages:**
- `Sidebar.tsx` footer → add `<MarketClock />`
- `TradeCard.tsx` → add `<LivePrice />` next to entry, `<DistanceToBar />` below stop/target row
- `ScanTable.tsx` → new "NOW" column between CLOSE and ENTRY with `<LivePrice />`
- `SymbolDrawer.tsx` → header section with live price + big DistanceToBar
- `app/layout.tsx` → mount `<AlertManager />` + `<PermissionBanner />` globally

---

## 3. Data Flow

```
[Alpaca snapshots API]
        │ (every 15s during market hours, batch of ~80 symbols)
        ▼
[PriceCache.refresh()] ──► detects near_entry / stop_violation ──► [event queue]
        │                                                                │
        ▼                                                                ▼
[GET /api/prices]                                          [GET /api/events/stream]
        │                                                                │
        ▼                                                                ▼
[useLivePrices hook]                                            [useAlerts hook]
   poll every 15s                                              SSE persistent
   (120s when hidden)                                                    │
        │                                                                ▼
        ▼                                                  [AlertManager]
[LivePrice, DistanceToBar, MarketClock]              fires Notification + sound + toast
```

---

## 4. Failure Modes

| Failure | Behavior |
|---|---|
| Alpaca keys missing | `/api/prices` returns 503. Frontend shows red banner. Existing pages still work (no live overlay). |
| Alpaca call fails mid-session | Keep previous cache, log warning, retry next cycle. Frontend shows STALE badge after 45s. |
| SSE connection drops | Existing 5s reconnect logic in `useSSE`. Brief alert gap on reconnect — acceptable. |
| Browser notification denied | AlertManager falls back to in-app toast for ALL event types (no silent failure). |
| Tab in background | Polling drops to 120s; alerts still fire via SSE (which stays open). |
| Symbol delisted / no data | Cache marks it `is_live=false`, returns `null` for unknown symbols. UI shows "—". |
| Quote older than 45s | Frontend `STALE` badge. Distinguishable from `CLOSE` (off-hours). |

---

## 5. Testing Plan

**Backend (pytest):**
- `test_market_calendar.py` — open/closed at known UTC times, next-open/next-close calculations
- `test_price_cache.py` — refresh with mocked Alpaca client, stale-data handling, symbol-set rebuild
- `test_event_detection.py` — near_entry triggers, cooldown, stop_violation single-fire
- `test_api_prices.py` — `/api/prices` empty cache (returns []), populated cache, missing keys → 503

**Frontend:**
- Component snapshot tests for LivePrice (live / stale / off-hours / no-data states)
- MarketClock countdown rendering at known timestamps
- AlertManager dispatches correct alert type per SSE event

**Manual:**
- During market hours: open dashboard, confirm prices update every 15s, MarketClock shows OPEN
- After hours: confirm prices show CLOSE badge, no Alpaca calls in logs
- Trigger a near_entry event manually in DB → confirm desktop notification fires
- Background the tab for 2 min → confirm polling slows, then resumes on focus

---

## 6. Files

**Create:**
- `src/trading_bot/api/live_prices.py`
- `src/trading_bot/api/market_calendar.py`
- `src/trading_bot/api/routes/prices.py`
- `dashboard-web/lib/hooks/useLivePrices.ts`
- `dashboard-web/lib/hooks/useMarketStatus.ts`
- `dashboard-web/lib/hooks/useAlerts.ts`
- `dashboard-web/lib/sound.ts`
- `dashboard-web/components/market/LivePrice.tsx`
- `dashboard-web/components/market/DistanceToBar.tsx`
- `dashboard-web/components/market/MarketClock.tsx`
- `dashboard-web/components/alerts/AlertManager.tsx`
- `dashboard-web/components/alerts/PermissionBanner.tsx`
- `dashboard-web/components/alerts/ToastStack.tsx`
- `tests/test_market_calendar.py`
- `tests/test_price_cache.py`
- `tests/test_event_detection.py`
- `tests/test_api_prices.py`

**Modify:**
- `src/trading_bot/api/main.py` — start price-cache background task in lifespan, register prices router, init event queue
- `src/trading_bot/api/routes/events.py` — read from `app.state.live_event_queue` alongside existing DB polling
- `src/trading_bot/api/schemas.py` — add `LiveQuote`, `MarketStatus`, `PricesResponse`
- `dashboard-web/lib/types.ts` — add LiveQuote, MarketStatus, AlertEvent types
- `dashboard-web/lib/api.ts` — add `prices()`, `priceSymbol()` calls
- `dashboard-web/app/layout.tsx` — mount AlertManager + PermissionBanner + ToastStack
- `dashboard-web/components/layout/Sidebar.tsx` — add MarketClock to footer
- `dashboard-web/components/terminal/TradeCard.tsx` — embed LivePrice + DistanceToBar
- `dashboard-web/components/terminal/ScanTable.tsx` — add NOW column
- `dashboard-web/components/overlays/SymbolDrawer.tsx` — live price header section

---

## 7. Open Questions / Future Work

- **Per-symbol near-entry threshold override** — currently global 0.5%. Could allow per-snapshot override via a new column. Deferred.
- **Sound preferences** — currently fixed 880Hz / 330Hz tones. A settings page could allow custom sounds. Deferred to Subsystem D.
- **Pre/post market** — Alpaca's IEX feed supports it. Add behind a feature flag in v2 if requested.
- **WebSocket migration** — if polling proves insufficient (e.g., for scalping workflow), migrate to Alpaca WebSocket. Current design isolates the data source behind PriceCache to make this swap straightforward.

---

**End of spec.**

