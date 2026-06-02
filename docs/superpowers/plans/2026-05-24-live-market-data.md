# Live Market Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time Alpaca price polling, market-hour awareness, SSE live alerts, and live-price UI overlays to the Next.js trading dashboard.

**Architecture:** A `PriceCache` singleton on the FastAPI server polls Alpaca's `/v2/stocks/snapshots` endpoint every 15 s during market hours. A background task detects `near_entry` and `stop_violation` events and pushes them into an `asyncio.Queue` that feeds the existing SSE stream. The Next.js client polls `/api/prices` via TanStack Query (drops to 120 s when backgrounded) and subscribes to live alerts via the existing `useSSE` hook.

**Tech Stack:** Python 3.11+ / FastAPI / httpx / pandas-market-calendars; Next.js 15 / React / TanStack Query / Web Notifications API / Web Audio API.

---

## File Map

**Create (backend)**
- `src/trading_bot/api/market_calendar.py` — NYSE open/closed detection, next open/close timestamps
- `src/trading_bot/api/live_prices.py` — `LiveQuote` dataclass, `PriceCache` class, `run_price_poll_loop` background coroutine
- `src/trading_bot/api/routes/prices.py` — `GET /api/prices` and `GET /api/prices/{symbol}`
- `tests/test_market_calendar.py`
- `tests/test_price_cache.py`
- `tests/test_event_detection.py`
- `tests/test_api_prices.py`

**Modify (backend)**
- `requirements.txt` — add `pandas-market-calendars>=4.4`
- `src/trading_bot/api/schemas.py` — add `LiveQuoteSchema`, `MarketStatus`, `PricesResponse`
- `src/trading_bot/api/main.py` — init queue + `PriceCache` in lifespan, start poll task, register prices router
- `src/trading_bot/api/routes/events.py` — drain `app.state.live_event_queue` in SSE generator

**Create (frontend)**
- `dashboard-web/lib/sound.ts` — `playBeep(freqHz, durationMs)` via Web Audio API
- `dashboard-web/lib/hooks/useLivePrices.ts` — TanStack Query polling `/api/prices`, Page Visibility aware
- `dashboard-web/lib/hooks/useMarketStatus.ts` — selector over `useLivePrices`
- `dashboard-web/lib/hooks/useAlerts.ts` — wraps `useSSE`, filters `live_alert` events
- `dashboard-web/components/market/LivePrice.tsx` — inline price + change%; STALE/CLOSE badges
- `dashboard-web/components/market/DistanceToBar.tsx` — pill row showing % distance to entry/stop/target
- `dashboard-web/components/market/MarketClock.tsx` — sidebar footer clock with countdown
- `dashboard-web/components/alerts/ToastStack.tsx` — `ToastProvider` context + `useToast` hook + toast render
- `dashboard-web/components/alerts/AlertManager.tsx` — mounts in layout, dispatches Notifications + beeps + toasts
- `dashboard-web/components/alerts/PermissionBanner.tsx` — yellow top strip when `Notification.permission === "default"`

**Modify (frontend)**
- `dashboard-web/lib/types.ts` — add `LiveQuote`, `MarketStatus`, `PricesResponse`, `LiveAlertEvent`
- `dashboard-web/lib/api.ts` — add `prices()` and `priceSymbol()`
- `dashboard-web/app/layout.tsx` — wrap body in `ToastProvider`; mount `AlertManager`, `PermissionBanner`
- `dashboard-web/components/layout/Sidebar.tsx` — add `<MarketClock />` at bottom
- `dashboard-web/components/terminal/TradeCard.tsx` — add `"use client"`, `<LivePrice />`, `<DistanceToBar />`
- `dashboard-web/components/terminal/ScanTable.tsx` — add "NOW" column with `<LivePrice />`
- `dashboard-web/components/overlays/SymbolDrawer.tsx` — add live price header card

---

## Task 1: Add Python dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add pandas-market-calendars to requirements**

In `requirements.txt`, add after the `httpx` line:

```
pandas-market-calendars>=4.4
```

- [ ] **Step 2: Install the dependency**

```powershell
pip install "pandas-market-calendars>=4.4"
```

Expected: package installs without errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add pandas-market-calendars dependency for NYSE calendar"
```

---

## Task 2: Add Pydantic schemas

**Files:**
- Modify: `src/trading_bot/api/schemas.py`

- [ ] **Step 1: Append schemas to schemas.py**

At the bottom of `src/trading_bot/api/schemas.py`, after the `VaultBridgeSummary` class, add:

```python
class LiveQuoteSchema(BaseModel):
    symbol: str
    price: float
    bid: float | None
    ask: float | None
    prev_close: float
    change_pct: float
    day_open: float
    day_high: float
    day_low: float
    day_volume: float
    asof: str          # ISO-8601 datetime string
    is_live: bool


class MarketStatus(BaseModel):
    open: bool
    next_open: str | None   # ISO-8601; None if no session found in 14-day window
    next_close: str | None  # ISO-8601; current close when open, next close when closed
    timezone: str


class PricesResponse(BaseModel):
    symbols: list[LiveQuoteSchema]
    market: MarketStatus
```

- [ ] **Step 2: Verify Python parses cleanly**

```powershell
$env:PYTHONPATH = "src"; python -c "from trading_bot.api.schemas import PricesResponse, LiveQuoteSchema, MarketStatus; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/trading_bot/api/schemas.py
git commit -m "feat: add LiveQuoteSchema, MarketStatus, PricesResponse schemas"
```

---

## Task 3: Market calendar module

**Files:**
- Create: `src/trading_bot/api/market_calendar.py`
- Create: `tests/test_market_calendar.py`

- [ ] **Step 1: Write the failing tests first**

Create `tests/test_market_calendar.py`:

```python
"""Tests for NYSE market calendar helper."""
from __future__ import annotations
from datetime import datetime, timezone


def test_market_open_tuesday_midday():
    from trading_bot.api.market_calendar import is_market_open, market_status
    # 2024-01-16 (Tuesday) 14:35 UTC = 9:35 AM ET — open
    ts = datetime(2024, 1, 16, 14, 35, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is True
    s = market_status(ts)
    assert s["open"] is True
    assert s["next_close"] is not None
    assert s["timezone"] == "America/New_York"


def test_market_closed_before_open():
    from trading_bot.api.market_calendar import is_market_open, market_status
    # 2024-01-16 (Tuesday) 13:00 UTC = 8:00 AM ET — before open
    ts = datetime(2024, 1, 16, 13, 0, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is False
    s = market_status(ts)
    assert s["open"] is False
    assert s["next_open"] is not None


def test_market_closed_after_close():
    from trading_bot.api.market_calendar import is_market_open
    # 2024-01-16 (Tuesday) 21:30 UTC = 4:30 PM ET — after close at 21:00 UTC
    ts = datetime(2024, 1, 16, 21, 30, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is False


def test_market_closed_saturday():
    from trading_bot.api.market_calendar import is_market_open, market_status
    # 2024-01-13 (Saturday) 15:00 UTC
    ts = datetime(2024, 1, 13, 15, 0, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is False
    s = market_status(ts)
    assert s["open"] is False
    assert s["next_open"] is not None


def test_next_open_precedes_next_close_when_closed():
    from trading_bot.api.market_calendar import market_status
    # Saturday — next_open is Monday open, next_close is Monday close
    ts = datetime(2024, 1, 13, 15, 0, tzinfo=timezone.utc)
    s = market_status(ts)
    assert s["next_open"] < s["next_close"]


def test_market_closed_holiday():
    from trading_bot.api.market_calendar import is_market_open
    # 2024-01-15 (MLK Day) 15:00 UTC — NYSE closed
    ts = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
    assert is_market_open(ts) is False
```

- [ ] **Step 2: Run tests — expect ImportError**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_market_calendar.py -v
```

Expected: all tests **FAIL** with `ModuleNotFoundError: No module named 'trading_bot.api.market_calendar'`

- [ ] **Step 3: Implement market_calendar.py**

Create `src/trading_bot/api/market_calendar.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_market_calendars as mcal


def market_status(now: datetime | None = None) -> dict:
    """Return NYSE market status relative to `now` (UTC).

    Returns dict with keys: open (bool), next_open (ISO str | None),
    next_close (ISO str | None), timezone (str).
    """
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    cal = mcal.get_calendar("NYSE")
    ts_pd = pd.Timestamp(ts)

    start = (ts - timedelta(days=1)).strftime("%Y-%m-%d")
    end = (ts + timedelta(days=14)).strftime("%Y-%m-%d")
    schedule = cal.schedule(start_date=start, end_date=end)

    is_open = False
    next_open_ts: pd.Timestamp | None = None
    next_close_ts: pd.Timestamp | None = None

    for _, row in schedule.iterrows():
        open_ts: pd.Timestamp = row["market_open"]
        close_ts: pd.Timestamp = row["market_close"]

        if open_ts <= ts_pd < close_ts:
            is_open = True
            next_close_ts = close_ts
            future = schedule[schedule["market_open"] > close_ts]
            next_open_ts = future.iloc[0]["market_open"] if not future.empty else None
            break
        elif open_ts > ts_pd:
            next_open_ts = open_ts
            next_close_ts = close_ts
            break

    return {
        "open": is_open,
        "next_open": next_open_ts.isoformat() if next_open_ts is not None else None,
        "next_close": next_close_ts.isoformat() if next_close_ts is not None else None,
        "timezone": "America/New_York",
    }


def is_market_open(now: datetime | None = None) -> bool:
    return market_status(now)["open"]
```

- [ ] **Step 4: Run tests — expect all to pass**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_market_calendar.py -v
```

Expected: 6 tests **PASS**

- [ ] **Step 5: Commit**

```bash
git add src/trading_bot/api/market_calendar.py tests/test_market_calendar.py
git commit -m "feat: add NYSE market calendar helper with open/close detection"
```

---

## Task 4: PriceCache and background loop

**Files:**
- Create: `src/trading_bot/api/live_prices.py`

- [ ] **Step 1: Create live_prices.py**

Create `src/trading_bot/api/live_prices.py`:

```python
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import pandas as pd

from trading_bot.api.market_calendar import is_market_open
from trading_bot.storage.repositories import ScannerRepository

log = logging.getLogger(__name__)

ALPACA_DATA_URL = "https://data.alpaca.markets"
NEAR_ENTRY_THRESHOLD = 0.005       # 0.5% distance to entry triggers near_entry
NEAR_ENTRY_COOLDOWN_SECS = 300     # 5-minute per-symbol cooldown
SYMBOL_REBUILD_SECS = 300          # rebuild symbol set every 5 minutes


@dataclass
class LiveQuote:
    symbol: str
    price: float
    bid: float | None
    ask: float | None
    prev_close: float
    change_pct: float
    day_open: float
    day_high: float
    day_low: float
    day_volume: float
    asof: datetime
    is_live: bool


class PriceCache:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._quotes: dict[str, LiveQuote] = {}
        self._previous_prices: dict[str, float] = {}
        self._symbols: set[str] = set()
        self._near_entry_cooldown: dict[str, datetime] = {}
        self._stop_fired: set[int] = set()
        self._event_queue: asyncio.Queue | None = None
        self._api_key: str | None = os.environ.get("ALPACA_API_KEY")
        self._api_secret: str | None = os.environ.get("ALPACA_SECRET_KEY")

    def set_event_queue(self, q: asyncio.Queue) -> None:
        self._event_queue = q

    def has_keys(self) -> bool:
        return bool(self._api_key and self._api_secret)

    async def rebuild_symbol_set(self) -> None:
        repo = ScannerRepository(self._db_path)
        symbols: set[str] = set()
        for fetcher in (
            lambda: repo.latest_scan_results(),
            lambda: repo.list_candidate_snapshots(limit=500),
            lambda: repo.manual_picks(),
        ):
            try:
                df = fetcher()
                if not df.empty and "symbol" in df.columns:
                    symbols.update(str(s).upper() for s in df["symbol"].dropna())
            except Exception as exc:
                log.debug("rebuild_symbol_set fetch error: %s", exc)
        self._symbols = symbols

    async def refresh(self) -> None:
        if not self.has_keys():
            return
        if not self._symbols:
            return

        symbols_csv = ",".join(sorted(self._symbols))
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{ALPACA_DATA_URL}/v2/stocks/snapshots",
                    params={"symbols": symbols_csv, "feed": "iex"},
                    headers={
                        "APCA-API-KEY-ID": self._api_key,
                        "APCA-API-SECRET-KEY": self._api_secret,
                    },
                )
                resp.raise_for_status()
                data: dict = resp.json()
        except Exception as exc:
            log.warning("Alpaca snapshot fetch failed: %s", exc)
            return

        now = datetime.now(timezone.utc)
        new_quotes: dict[str, LiveQuote] = {}

        for symbol, snap in data.items():
            try:
                trade = snap.get("latestTrade", {})
                quote = snap.get("latestQuote", {})
                day_bar = snap.get("dailyBar", {})
                prev_bar = snap.get("prevDailyBar", {})
                price = float(trade.get("p", 0) or 0)
                prev_close = float(prev_bar.get("c", 0) or 0)
                change_pct = (price - prev_close) / prev_close if prev_close else 0.0
                asof_raw = trade.get("t", "")
                try:
                    asof = datetime.fromisoformat(asof_raw.replace("Z", "+00:00"))
                except Exception:
                    asof = now
                new_quotes[symbol] = LiveQuote(
                    symbol=symbol,
                    price=price,
                    bid=float(quote["bp"]) if quote.get("bp") is not None else None,
                    ask=float(quote["ap"]) if quote.get("ap") is not None else None,
                    prev_close=prev_close,
                    change_pct=change_pct,
                    day_open=float(day_bar.get("o", 0) or 0),
                    day_high=float(day_bar.get("h", 0) or 0),
                    day_low=float(day_bar.get("l", 0) or 0),
                    day_volume=float(day_bar.get("v", 0) or 0),
                    asof=asof,
                    is_live=True,
                )
            except Exception as exc:
                log.debug("Failed to parse quote for %s: %s", symbol, exc)

        if self._event_queue is not None and new_quotes:
            await self._detect_events(new_quotes)

        self._previous_prices = {s: q.price for s, q in self._quotes.items()}
        self._quotes.update(new_quotes)

    async def _detect_events(self, new_quotes: dict[str, LiveQuote]) -> None:
        try:
            repo = ScannerRepository(self._db_path)
            df = repo.list_candidate_snapshots(limit=500)
        except Exception as exc:
            log.debug("Event detection DB read failed: %s", exc)
            return
        if df.empty:
            return

        now = datetime.now(timezone.utc)

        for _, row in df.iterrows():
            symbol = str(row.get("symbol", "")).upper()
            quote = new_quotes.get(symbol)
            if quote is None or quote.price == 0:
                continue

            entry = row.get("entry")
            stop = row.get("stop")
            entry_triggered = bool(row.get("entry_triggered", False))
            outcome_label = row.get("outcome_label")
            snapshot_id = int(row.get("id", 0))
            outcome_is_null = outcome_label is None or (
                isinstance(outcome_label, float) and pd.isna(outcome_label)
            )
            prev_price = self._previous_prices.get(symbol, 0.0)

            # near_entry: price crosses into 0.5% of entry, not yet triggered
            if (
                not entry_triggered
                and entry is not None
                and not (isinstance(entry, float) and pd.isna(entry))
            ):
                entry_val = float(entry)
                if entry_val > 0:
                    dist = abs(quote.price - entry_val) / entry_val
                    prev_dist = (
                        abs(prev_price - entry_val) / entry_val if prev_price else 1.0
                    )
                    last_fired = self._near_entry_cooldown.get(symbol)
                    in_cooldown = (
                        last_fired is not None
                        and (now - last_fired).total_seconds() < NEAR_ENTRY_COOLDOWN_SECS
                    )
                    if (
                        dist < NEAR_ENTRY_THRESHOLD
                        and prev_dist >= NEAR_ENTRY_THRESHOLD
                        and not in_cooldown
                    ):
                        self._near_entry_cooldown[symbol] = now
                        await self._event_queue.put({  # type: ignore[union-attr]
                            "type": "live_alert",
                            "alert_type": "near_entry",
                            "symbol": symbol,
                            "price": quote.price,
                            "entry": entry_val,
                        })

            # stop_violation: triggered, still open, price drops below stop
            if (
                entry_triggered
                and outcome_is_null
                and stop is not None
                and not (isinstance(stop, float) and pd.isna(stop))
                and snapshot_id not in self._stop_fired
            ):
                stop_val = float(stop)
                if stop_val > 0 and quote.price < stop_val:
                    self._stop_fired.add(snapshot_id)
                    await self._event_queue.put({  # type: ignore[union-attr]
                        "type": "live_alert",
                        "alert_type": "stop_violation",
                        "symbol": symbol,
                        "price": quote.price,
                        "stop": stop_val,
                    })

    def snapshot(self) -> dict[str, LiveQuote]:
        return dict(self._quotes)

    def get(self, symbol: str) -> LiveQuote | None:
        return self._quotes.get(symbol.upper())


async def run_price_poll_loop(app) -> None:  # type: ignore[type-arg]
    """Background task: poll Alpaca every 15s (market hours) or 60s (closed)."""
    last_rebuild: datetime | None = None

    while True:
        try:
            now = datetime.now(timezone.utc)
            if last_rebuild is None or (now - last_rebuild).total_seconds() > SYMBOL_REBUILD_SECS:
                await app.state.price_cache.rebuild_symbol_set()
                last_rebuild = now

            if is_market_open(now):
                await app.state.price_cache.refresh()
                await asyncio.sleep(15)
            else:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Price poll loop error: %s", exc)
            await asyncio.sleep(30)
```

- [ ] **Step 2: Verify import**

```powershell
$env:PYTHONPATH = "src"; python -c "from trading_bot.api.live_prices import PriceCache, LiveQuote, run_price_poll_loop; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/trading_bot/api/live_prices.py
git commit -m "feat: add PriceCache and background price poll loop"
```

---

## Task 5: PriceCache unit tests

**Files:**
- Create: `tests/test_price_cache.py`

- [ ] **Step 1: Write tests**

Create `tests/test_price_cache.py`:

```python
"""Unit tests for PriceCache — Alpaca calls are mocked."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from trading_bot.storage.database import initialize_database


def _make_cache(tmp_path, monkeypatch, *, with_keys: bool = True):
    from trading_bot.api.live_prices import PriceCache
    if with_keys:
        monkeypatch.setenv("ALPACA_API_KEY", "test_key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    else:
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    db = tmp_path / "test.db"
    initialize_database(str(db))
    return PriceCache(str(db))


def _alpaca_payload():
    return {
        "AAPL": {
            "latestTrade": {"p": 190.5, "t": "2024-01-16T14:30:00Z"},
            "latestQuote": {"bp": 190.4, "ap": 190.6},
            "dailyBar": {"o": 189.0, "h": 191.0, "l": 188.5, "v": 12_000_000},
            "prevDailyBar": {"c": 189.0},
        }
    }


def test_refresh_noop_without_keys(tmp_path, monkeypatch):
    cache = _make_cache(tmp_path, monkeypatch, with_keys=False)
    asyncio.run(cache.refresh())
    assert cache.snapshot() == {}


def test_refresh_noop_with_empty_symbol_set(tmp_path, monkeypatch):
    cache = _make_cache(tmp_path, monkeypatch)
    # _symbols is empty by default — should return without calling Alpaca
    asyncio.run(cache.refresh())
    assert cache.snapshot() == {}


def test_refresh_populates_quotes(tmp_path, monkeypatch):
    cache = _make_cache(tmp_path, monkeypatch)
    cache._symbols = {"AAPL"}

    mock_instance = MagicMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    mock_resp = MagicMock()
    mock_resp.json.return_value = _alpaca_payload()
    mock_resp.raise_for_status.return_value = None
    mock_instance.get = AsyncMock(return_value=mock_resp)

    with patch("trading_bot.api.live_prices.httpx.AsyncClient", return_value=mock_instance):
        asyncio.run(cache.refresh())

    quotes = cache.snapshot()
    assert "AAPL" in quotes
    q = quotes["AAPL"]
    assert q.price == 190.5
    assert q.bid == 190.4
    assert q.ask == 190.6
    assert q.day_open == 189.0
    assert q.is_live is True
    assert abs(q.change_pct - (190.5 - 189.0) / 189.0) < 1e-9


def test_refresh_keeps_old_quotes_on_alpaca_failure(tmp_path, monkeypatch):
    from trading_bot.api.live_prices import LiveQuote
    cache = _make_cache(tmp_path, monkeypatch)
    cache._symbols = {"AAPL"}
    cache._quotes = {"AAPL": LiveQuote(
        symbol="AAPL", price=100.0, bid=None, ask=None,
        prev_close=99.0, change_pct=0.01, day_open=99.5, day_high=101.0,
        day_low=99.0, day_volume=500_000, asof=datetime.now(timezone.utc), is_live=True,
    )}

    mock_instance = MagicMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    mock_instance.get = AsyncMock(side_effect=Exception("network error"))

    with patch("trading_bot.api.live_prices.httpx.AsyncClient", return_value=mock_instance):
        asyncio.run(cache.refresh())

    assert cache.get("AAPL") is not None
    assert cache.get("AAPL").price == 100.0


def test_rebuild_symbol_set_empty_db(tmp_path, monkeypatch):
    cache = _make_cache(tmp_path, monkeypatch)
    asyncio.run(cache.rebuild_symbol_set())
    assert isinstance(cache._symbols, set)


def test_get_unknown_symbol_returns_none(tmp_path, monkeypatch):
    cache = _make_cache(tmp_path, monkeypatch)
    assert cache.get("ZZZZ") is None
```

- [ ] **Step 2: Run tests**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_price_cache.py -v
```

Expected: 6 tests **PASS**

- [ ] **Step 3: Commit**

```bash
git add tests/test_price_cache.py
git commit -m "test: add PriceCache unit tests"
```

---

## Task 6: Event detection tests

**Files:**
- Create: `tests/test_event_detection.py`

- [ ] **Step 1: Write tests**

Create `tests/test_event_detection.py`:

```python
"""Tests for near_entry and stop_violation event detection in PriceCache."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd

from trading_bot.storage.database import initialize_database


def _make_cache(tmp_path, monkeypatch):
    from trading_bot.api.live_prices import PriceCache
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    db = tmp_path / "test.db"
    initialize_database(str(db))
    cache = PriceCache(str(db))
    q = asyncio.Queue()
    cache.set_event_queue(q)
    return cache, q


def _quote(symbol: str, price: float):
    from trading_bot.api.live_prices import LiveQuote
    return LiveQuote(
        symbol=symbol, price=price, bid=None, ask=None,
        prev_close=price - 1.0, change_pct=0.01,
        day_open=price - 0.5, day_high=price + 1.0, day_low=price - 1.0,
        day_volume=1_000_000, asof=datetime.now(timezone.utc), is_live=True,
    )


def _snapshot_df(*, symbol="AAPL", entry=100.0, stop=95.0, target=110.0,
                 entry_triggered=False, outcome_label=None, snap_id=1):
    return pd.DataFrame([{
        "id": snap_id, "symbol": symbol,
        "entry": entry, "stop": stop, "target": target,
        "entry_triggered": entry_triggered,
        "outcome_label": outcome_label,
    }])


def test_near_entry_fires_on_crossing(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)
    cache._previous_prices = {"AAPL": 101.0}   # was outside 0.5%

    with patch.object(ScannerRepository, "list_candidate_snapshots",
                      return_value=_snapshot_df(entry=100.0)):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 100.3)}))

    assert not q.empty()
    evt = q.get_nowait()
    assert evt["alert_type"] == "near_entry"
    assert evt["symbol"] == "AAPL"
    assert evt["entry"] == 100.0


def test_near_entry_does_not_fire_when_already_inside(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)
    # Previous price was also within 0.5% — no crossing, no event
    cache._previous_prices = {"AAPL": 100.2}

    with patch.object(ScannerRepository, "list_candidate_snapshots",
                      return_value=_snapshot_df(entry=100.0)):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 100.3)}))

    assert q.empty()


def test_near_entry_cooldown_prevents_spam(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)
    cache._previous_prices = {"AAPL": 101.0}
    cache._near_entry_cooldown["AAPL"] = datetime.now(timezone.utc)

    with patch.object(ScannerRepository, "list_candidate_snapshots",
                      return_value=_snapshot_df(entry=100.0)):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 100.3)}))

    assert q.empty()


def test_near_entry_skips_triggered_snapshots(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)
    cache._previous_prices = {"AAPL": 101.0}

    with patch.object(ScannerRepository, "list_candidate_snapshots",
                      return_value=_snapshot_df(entry=100.0, entry_triggered=True)):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 100.3)}))

    assert q.empty()


def test_stop_violation_fires_once(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)

    df = _snapshot_df(entry=100.0, stop=95.0, entry_triggered=True, outcome_label=None, snap_id=42)

    with patch.object(ScannerRepository, "list_candidate_snapshots", return_value=df):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 94.0)}))

    assert not q.empty()
    evt = q.get_nowait()
    assert evt["alert_type"] == "stop_violation"
    assert evt["symbol"] == "AAPL"

    # Second call with same snapshot — must not fire again
    with patch.object(ScannerRepository, "list_candidate_snapshots", return_value=df):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 93.0)}))

    assert q.empty()


def test_stop_violation_skips_closed_outcomes(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)

    df = _snapshot_df(entry=100.0, stop=95.0, entry_triggered=True,
                      outcome_label="target_hit", snap_id=7)

    with patch.object(ScannerRepository, "list_candidate_snapshots", return_value=df):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 94.0)}))

    assert q.empty()
```

- [ ] **Step 2: Run tests**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_event_detection.py -v
```

Expected: 6 tests **PASS**

- [ ] **Step 3: Commit**

```bash
git add tests/test_event_detection.py
git commit -m "test: add event detection tests for near_entry and stop_violation"
```

---

## Task 7: Prices router

**Files:**
- Create: `src/trading_bot/api/routes/prices.py`
- Create: `tests/test_api_prices.py`

- [ ] **Step 1: Write failing tests first**

Create `tests/test_api_prices.py`:

```python
"""Tests for GET /api/prices endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trading_bot.api.main import app
from trading_bot.storage.database import initialize_database


@pytest.fixture()
def client_no_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    db = tmp_path / "test.db"
    initialize_database(str(db))
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_with_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    db = tmp_path / "test.db"
    initialize_database(str(db))
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    with TestClient(app) as c:
        yield c


def test_prices_503_without_keys(client_no_keys):
    r = client_no_keys.get("/api/prices")
    assert r.status_code == 503
    assert "Alpaca keys not configured" in r.json()["detail"]


def test_prices_symbol_503_without_keys(client_no_keys):
    r = client_no_keys.get("/api/prices/AAPL")
    assert r.status_code == 503


def test_prices_empty_cache_with_keys(client_with_keys):
    r = client_with_keys.get("/api/prices")
    assert r.status_code == 200
    data = r.json()
    assert data["symbols"] == []
    assert "market" in data
    assert isinstance(data["market"]["open"], bool)
    assert "next_open" in data["market"]
    assert "timezone" in data["market"]


def test_prices_symbol_404_when_not_in_cache(client_with_keys):
    r = client_with_keys.get("/api/prices/ZZZZ")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests — expect 404 (route not registered)**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_api_prices.py -v
```

Expected: tests for `/api/prices` return **404** (router not yet registered)

- [ ] **Step 3: Implement prices.py**

Create `src/trading_bot/api/routes/prices.py`:

```python
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from trading_bot.api.market_calendar import market_status
from trading_bot.api.schemas import LiveQuoteSchema, MarketStatus, PricesResponse

router = APIRouter(tags=["prices"])


def _has_keys() -> bool:
    return bool(os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY"))


def _no_keys() -> None:
    raise HTTPException(status_code=503, detail="Alpaca keys not configured")


def _quote_to_schema(q) -> LiveQuoteSchema:
    return LiveQuoteSchema(
        symbol=q.symbol,
        price=q.price,
        bid=q.bid,
        ask=q.ask,
        prev_close=q.prev_close,
        change_pct=q.change_pct,
        day_open=q.day_open,
        day_high=q.day_high,
        day_low=q.day_low,
        day_volume=q.day_volume,
        asof=q.asof.isoformat(),
        is_live=q.is_live,
    )


@router.get("/prices", response_model=PricesResponse)
def get_prices(request: Request) -> PricesResponse:
    if not _has_keys():
        _no_keys()
    cache = request.app.state.price_cache
    quotes = cache.snapshot()
    ms = market_status()
    return PricesResponse(
        symbols=[_quote_to_schema(q) for q in quotes.values()],
        market=MarketStatus(**ms),
    )


@router.get("/prices/{symbol}", response_model=LiveQuoteSchema)
def get_price_symbol(symbol: str, request: Request) -> LiveQuoteSchema:
    if not _has_keys():
        _no_keys()
    cache = request.app.state.price_cache
    quote = cache.get(symbol.upper())
    if quote is None:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol.upper()} not in cache")
    return _quote_to_schema(quote)
```

- [ ] **Step 4: Commit prices.py (tests still fail until Task 8 wires it)**

```bash
git add src/trading_bot/api/routes/prices.py tests/test_api_prices.py
git commit -m "feat: add /api/prices endpoints (not yet registered in main)"
```

---

## Task 8: Wire main.py — lifespan, queue, background task, prices router

**Files:**
- Modify: `src/trading_bot/api/main.py`

- [ ] **Step 1: Replace main.py**

Overwrite `src/trading_bot/api/main.py` with:

```python
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trading_bot.api.routes import (
    health, today, picks, outcomes, scan, analytics, events, system, symbols, vault
)
from trading_bot.api.routes import prices as prices_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from trading_bot.api.live_prices import PriceCache, run_price_poll_loop

    app.state.db_path = os.environ.get("DATABASE_PATH", "data/trading_bot.db")
    app.state.vault_dir = os.environ.get("VAULT_DIR", "vault")

    app.state.live_event_queue = asyncio.Queue()
    cache = PriceCache(app.state.db_path)
    cache.set_event_queue(app.state.live_event_queue)
    app.state.price_cache = cache

    poll_task = asyncio.create_task(run_price_poll_loop(app))

    yield

    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Trading Bot API", version="1.0.0", lifespan=lifespan)

_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

for _router in (
    health.router,
    today.router,
    picks.router,
    outcomes.router,
    scan.router,
    analytics.router,
    events.router,
    system.router,
    symbols.router,
    vault.router,
    prices_router.router,
):
    app.include_router(_router, prefix="/api")
```

- [ ] **Step 2: Run prices tests — expect PASS**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_api_prices.py -v
```

Expected: 4 tests **PASS**

- [ ] **Step 3: Run full smoke suite — confirm no regressions**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_api_smoke.py -v
```

Expected: all existing smoke tests **PASS**

- [ ] **Step 4: Commit**

```bash
git add src/trading_bot/api/main.py
git commit -m "feat: wire PriceCache background task and prices router into FastAPI lifespan"
```

---

## Task 9: Modify events.py — drain live_event_queue in SSE

**Files:**
- Modify: `src/trading_bot/api/routes/events.py`

- [ ] **Step 1: Replace event_stream function**

Replace the entire `event_stream` function in `src/trading_bot/api/routes/events.py` (the `@router.get("/events/stream")` block and everything inside it) with:

```python
@router.get("/events/stream")
async def event_stream(request: Request):
    db_path = request.app.state.db_path
    live_queue: asyncio.Queue | None = getattr(request.app.state, "live_event_queue", None)

    async def generate():
        repo = ScannerRepository(db_path)
        last_id = None
        while True:
            if await request.is_disconnected():
                break
            try:
                # Drain any live price-alert events queued since last tick
                if live_queue is not None:
                    while not live_queue.empty():
                        try:
                            event = live_queue.get_nowait()
                            yield "data: " + json.dumps(event) + "\n\n"
                        except asyncio.QueueEmpty:
                            break

                scan = repo.latest_scan_run()
                watch = repo.latest_watch_run()
                age = None
                if scan and scan.get("created_at"):
                    try:
                        created = datetime.fromisoformat(scan["created_at"].replace("Z", "+00:00"))
                        age = int((datetime.now(timezone.utc) - created).total_seconds())
                    except Exception:
                        pass
                hb = {
                    "type": "heartbeat",
                    "watch_status": watch.get("status") if watch else "unknown",
                    "last_scan_age_seconds": age,
                    "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
                }
                yield "data: " + json.dumps(hb) + "\n\n"
                edf = repo.list_tony_events(limit=5)
                if not edf.empty:
                    nid = int(edf.iloc[0]["id"])
                    if last_id is None:
                        last_id = nid
                    elif nid > last_id:
                        for _, row in edf[edf["id"] > last_id].iterrows():
                            p = {
                                "type": "event",
                                "event_type": row.get("event_type", ""),
                                "severity": row.get("severity", ""),
                                "symbol": _nan(row.get("symbol")),
                                "title": row.get("title", ""),
                                "message": row.get("message", ""),
                                "created_at": row.get("created_at", ""),
                            }
                            yield "data: " + json.dumps(p) + "\n\n"
                        last_id = nid
            except Exception as exc:
                err = {"type": "error", "message": str(exc)}
                yield "data: " + json.dumps(err) + "\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

- [ ] **Step 2: Run all backend tests**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/ -v
```

Expected: all tests **PASS**

- [ ] **Step 3: Commit**

```bash
git add src/trading_bot/api/routes/events.py
git commit -m "feat: drain live_event_queue in SSE stream for near_entry/stop_violation alerts"
```

---

## Task 10: Frontend types and API calls

**Files:**
- Modify: `dashboard-web/lib/types.ts`
- Modify: `dashboard-web/lib/api.ts`

- [ ] **Step 1: Append types to types.ts**

At the bottom of `dashboard-web/lib/types.ts`, append:

```typescript
export interface LiveQuote {
  symbol: string
  price: number
  bid: number | null
  ask: number | null
  prev_close: number
  change_pct: number
  day_open: number
  day_high: number
  day_low: number
  day_volume: number
  asof: string        // ISO-8601
  is_live: boolean
}

export interface MarketStatus {
  open: boolean
  next_open: string | null
  next_close: string | null
  timezone: string
}

export interface PricesResponse {
  symbols: LiveQuote[]
  market: MarketStatus
}

export interface LiveAlertEvent {
  type: "live_alert"
  alert_type: "near_entry" | "stop_violation" | "entry_triggered"
  symbol: string
  price: number
  entry?: number
  stop?: number
}
```

- [ ] **Step 2: Add API calls to api.ts**

Inside the `api` object in `dashboard-web/lib/api.ts`, add these two lines after the `vaultBridge` line (before the closing `}`):

```typescript
  prices: () => get<import("./types").PricesResponse>("/api/prices"),
  priceSymbol: (symbol: string) => get<import("./types").LiveQuote>(`/api/prices/${symbol}`),
```

- [ ] **Step 3: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add dashboard-web/lib/types.ts dashboard-web/lib/api.ts
git commit -m "feat: add LiveQuote, PricesResponse types and api.prices() calls"
```

---

## Task 11: Sound utility

**Files:**
- Create: `dashboard-web/lib/sound.ts`

- [ ] **Step 1: Create sound.ts**

Create `dashboard-web/lib/sound.ts`:

```typescript
/**
 * Plays a pure sine-wave beep via Web Audio API.
 * Silently no-ops if AudioContext is unavailable or blocked by browser policy.
 */
export function playBeep(freqHz: number, durationMs: number): void {
  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const ctx = new AudioCtx()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.type = "sine"
    osc.frequency.value = freqHz
    gain.gain.setValueAtTime(0.12, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + durationMs / 1000)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + durationMs / 1000)
    osc.onended = () => ctx.close()
  } catch {
    // AudioContext blocked — silent fallback
  }
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/lib/sound.ts
git commit -m "feat: add playBeep Web Audio utility"
```

---

## Task 12: useLivePrices hook

**Files:**
- Create: `dashboard-web/lib/hooks/useLivePrices.ts`

- [ ] **Step 1: Create hooks directory**

```powershell
New-Item -ItemType Directory -Force "dashboard-web/lib/hooks"
```

- [ ] **Step 2: Create useLivePrices.ts**

Create `dashboard-web/lib/hooks/useLivePrices.ts`:

```typescript
"use client"
import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { PricesResponse } from "@/lib/types"

const ACTIVE_INTERVAL = 15_000      // 15s when tab is visible
const BACKGROUND_INTERVAL = 120_000 // 120s when tab is hidden

export function useLivePrices() {
  const [refetchInterval, setRefetchInterval] = useState(ACTIVE_INTERVAL)

  useEffect(() => {
    const onVisibility = () =>
      setRefetchInterval(document.hidden ? BACKGROUND_INTERVAL : ACTIVE_INTERVAL)
    document.addEventListener("visibilitychange", onVisibility)
    return () => document.removeEventListener("visibilitychange", onVisibility)
  }, [])

  return useQuery<PricesResponse>({
    queryKey: ["livePrices"],
    queryFn: () => api.prices(),
    refetchInterval,
    staleTime: 10_000,
    retry: false,   // 503 (no keys configured) should not retry
  })
}
```

- [ ] **Step 3: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add dashboard-web/lib/hooks/useLivePrices.ts
git commit -m "feat: add useLivePrices hook with Page Visibility polling"
```

---

## Task 13: useMarketStatus hook

**Files:**
- Create: `dashboard-web/lib/hooks/useMarketStatus.ts`

- [ ] **Step 1: Create useMarketStatus.ts**

Create `dashboard-web/lib/hooks/useMarketStatus.ts`:

```typescript
"use client"
import { useLivePrices } from "./useLivePrices"
import type { MarketStatus } from "@/lib/types"

export function useMarketStatus(): MarketStatus | null {
  const { data } = useLivePrices()
  return data?.market ?? null
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/lib/hooks/useMarketStatus.ts
git commit -m "feat: add useMarketStatus hook"
```

---

## Task 14: useAlerts hook

**Files:**
- Create: `dashboard-web/lib/hooks/useAlerts.ts`

- [ ] **Step 1: Create useAlerts.ts**

Create `dashboard-web/lib/hooks/useAlerts.ts`:

```typescript
"use client"
import { useCallback } from "react"
import { useSSE } from "@/lib/sse"
import { api } from "@/lib/api"
import type { LiveAlertEvent } from "@/lib/types"

export function useAlerts(onAlert: (evt: LiveAlertEvent) => void): void {
  const handler = useCallback(
    (msg: unknown) => {
      const m = msg as { type?: string }
      if (m?.type === "live_alert") {
        onAlert(msg as LiveAlertEvent)
      }
    },
    [onAlert],
  )
  useSSE(api.streamUrl(), handler)
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/lib/hooks/useAlerts.ts
git commit -m "feat: add useAlerts hook for SSE live_alert events"
```

---

## Task 15: LivePrice component

**Files:**
- Create: `dashboard-web/components/market/LivePrice.tsx`

- [ ] **Step 1: Create market directory**

```powershell
New-Item -ItemType Directory -Force "dashboard-web/components/market"
```

- [ ] **Step 2: Create LivePrice.tsx**

Create `dashboard-web/components/market/LivePrice.tsx`:

```tsx
"use client"
import { useLivePrices } from "@/lib/hooks/useLivePrices"

interface LivePriceProps {
  symbol: string
  entry?: number | null
}

const mono: React.CSSProperties = { fontFamily: "JetBrains Mono, monospace", fontSize: 11 }

export function LivePrice({ symbol, entry }: LivePriceProps) {
  const { data } = useLivePrices()
  const quote = data?.symbols.find(q => q.symbol === symbol.toUpperCase())

  if (!quote) {
    return <span style={{ ...mono, color: "var(--text-secondary)" }}>—</span>
  }

  const stale = Date.now() - new Date(quote.asof).getTime() > 45_000

  if (!quote.is_live) {
    return (
      <span style={{ ...mono, color: "var(--text-secondary)" }}>
        ${quote.price.toFixed(2)}{" "}
        <span style={{ fontSize: 9 }}>CLOSE</span>
      </span>
    )
  }

  if (stale) {
    return (
      <span style={{ ...mono, color: "var(--text-secondary)" }}>
        ${quote.price.toFixed(2)}{" "}
        <span style={{ fontSize: 9 }}>STALE</span>
      </span>
    )
  }

  const changeColor = quote.change_pct >= 0 ? "var(--green)" : "var(--red)"
  const changeStr = `${quote.change_pct >= 0 ? "+" : ""}${(quote.change_pct * 100).toFixed(2)}%`
  const entryDeltaPct =
    entry != null && entry > 0
      ? ((quote.price - entry) / entry) * 100
      : null

  return (
    <span style={mono}>
      <span style={{ color: changeColor }}>${quote.price.toFixed(2)}</span>
      <span style={{ color: changeColor, marginLeft: 4, fontSize: 9 }}>{changeStr}</span>
      {entryDeltaPct !== null && (
        <span style={{ color: "var(--text-secondary)", marginLeft: 4, fontSize: 9 }}>
          {entryDeltaPct >= 0 ? "+" : ""}
          {entryDeltaPct.toFixed(1)}% to entry
        </span>
      )}
    </span>
  )
}
```

- [ ] **Step 3: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add dashboard-web/components/market/LivePrice.tsx
git commit -m "feat: add LivePrice component with live/stale/close states"
```

---

## Task 16: DistanceToBar component

**Files:**
- Create: `dashboard-web/components/market/DistanceToBar.tsx`

- [ ] **Step 1: Create DistanceToBar.tsx**

Create `dashboard-web/components/market/DistanceToBar.tsx`:

```tsx
interface DistanceToBarProps {
  current: number
  entry?: number | null
  stop?: number | null
  target?: number | null
}

function pill(
  label: string,
  current: number,
  level: number,
  color: string,
): React.ReactElement {
  const pct = ((level - current) / current) * 100
  const arrow = pct > 0 ? "↑" : "↓"
  return (
    <span style={{
      background: "var(--bg-elevated)", padding: "2px 6px", borderRadius: 3,
      fontFamily: "JetBrains Mono, monospace", fontSize: 10, color,
    }}>
      {arrow}{Math.abs(pct).toFixed(1)}% {label}
    </span>
  )
}

export function DistanceToBar({ current, entry, stop, target }: DistanceToBarProps) {
  if (!current) return null
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
      {entry != null && pill("entry", current, entry, "var(--cyan)")}
      {stop != null && pill("stop", current, stop, "var(--red)")}
      {target != null && pill("target", current, target, "var(--green)")}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/components/market/DistanceToBar.tsx
git commit -m "feat: add DistanceToBar pill component"
```

---

## Task 17: MarketClock component

**Files:**
- Create: `dashboard-web/components/market/MarketClock.tsx`

- [ ] **Step 1: Create MarketClock.tsx**

Create `dashboard-web/components/market/MarketClock.tsx`:

```tsx
"use client"
import { useEffect, useState } from "react"
import { useMarketStatus } from "@/lib/hooks/useMarketStatus"

function countdown(isoTarget: string): string {
  const diff = new Date(isoTarget).getTime() - Date.now()
  if (diff <= 0) return "now"
  const h = Math.floor(diff / 3_600_000)
  const m = Math.floor((diff % 3_600_000) / 60_000)
  const s = Math.floor((diff % 60_000) / 1000)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function formatNextOpen(isoStr: string): string {
  return new Date(isoStr).toLocaleString("en-US", {
    weekday: "short", hour: "numeric", minute: "2-digit",
    timeZone: "America/New_York",
  })
}

export function MarketClock() {
  const market = useMarketStatus()
  const [, tick] = useState(0)

  useEffect(() => {
    const id = setInterval(() => tick(n => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  if (!market) return null

  return (
    <div style={{
      fontSize: 9, fontFamily: "JetBrains Mono, monospace",
      color: "var(--text-secondary)", textAlign: "center",
      padding: "6px 4px", borderTop: "1px solid var(--border)",
    }}>
      {market.open ? (
        <>
          <div style={{ color: "var(--green)" }}>● OPEN</div>
          {market.next_close && (
            <div>closes {countdown(market.next_close)}</div>
          )}
        </>
      ) : (
        <>
          <div style={{ color: "var(--red)" }}>● CLOSED</div>
          {market.next_open && (
            <div style={{ fontSize: 8 }}>{formatNextOpen(market.next_open)}</div>
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

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/components/market/MarketClock.tsx
git commit -m "feat: add MarketClock sidebar component with live countdown"
```

---

## Task 18: Toast infrastructure

**Files:**
- Create: `dashboard-web/components/alerts/ToastStack.tsx`

- [ ] **Step 1: Create alerts directory**

```powershell
New-Item -ItemType Directory -Force "dashboard-web/components/alerts"
```

- [ ] **Step 2: Create ToastStack.tsx**

Create `dashboard-web/components/alerts/ToastStack.tsx`:

```tsx
"use client"
import {
  createContext, useCallback, useContext, useState,
  type ReactNode,
} from "react"

interface Toast {
  id: number
  text: string
}

interface ToastCtx {
  addToast: (text: string) => void
}

const ToastContext = createContext<ToastCtx>({ addToast: () => {} })
export const useToast = () => useContext(ToastContext)

let _nextId = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((text: string) => {
    const id = ++_nextId
    setToasts(prev => [...prev, { id, text }])
  }, [])

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div style={{
        position: "fixed", bottom: 16, right: 16, zIndex: 500,
        display: "flex", flexDirection: "column-reverse", gap: 8,
        maxWidth: 340, pointerEvents: "none",
      }}>
        {toasts.map(t => (
          <div key={t.id} style={{
            background: "var(--bg-elevated)", border: "1px solid var(--amber)",
            borderRadius: 6, padding: "10px 14px",
            fontFamily: "JetBrains Mono, monospace", fontSize: 12,
            display: "flex", alignItems: "center", justifyContent: "space-between",
            gap: 12, pointerEvents: "all",
          }}>
            <span style={{ color: "var(--text-primary)" }}>{t.text}</span>
            <button
              onClick={() => dismiss(t.id)}
              style={{
                background: "none", border: "none",
                color: "var(--text-secondary)", cursor: "pointer",
                fontSize: 14, padding: 0,
              }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
```

- [ ] **Step 3: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add dashboard-web/components/alerts/ToastStack.tsx
git commit -m "feat: add ToastProvider and useToast for persistent alert toasts"
```

---

## Task 19: AlertManager component

**Files:**
- Create: `dashboard-web/components/alerts/AlertManager.tsx`

- [ ] **Step 1: Create AlertManager.tsx**

Create `dashboard-web/components/alerts/AlertManager.tsx`:

```tsx
"use client"
import { useCallback } from "react"
import { useAlerts } from "@/lib/hooks/useAlerts"
import { useToast } from "./ToastStack"
import { playBeep } from "@/lib/sound"
import type { LiveAlertEvent } from "@/lib/types"

export function AlertManager() {
  const { addToast } = useToast()

  const handleAlert = useCallback(
    (evt: LiveAlertEvent) => {
      const { alert_type, symbol, price } = evt
      const priceStr = `$${price.toFixed(2)}`

      if (alert_type === "entry_triggered") {
        playBeep(880, 200)
        if (typeof Notification !== "undefined" && Notification.permission === "granted") {
          new Notification(`Entry triggered: ${symbol}`, { body: `Price ${priceStr}` })
        } else {
          addToast(`Entry triggered: ${symbol} @ ${priceStr}`)
        }
      } else if (alert_type === "near_entry") {
        if (typeof Notification !== "undefined" && Notification.permission === "granted") {
          new Notification(`Near entry: ${symbol}`, {
            body: `${priceStr} is within 0.5% of entry`,
          })
        } else {
          addToast(`Near entry: ${symbol} @ ${priceStr}`)
        }
      } else if (alert_type === "stop_violation") {
        playBeep(330, 400)
        addToast(`STOP VIOLATION: ${symbol} @ ${priceStr}`)
      }
    },
    [addToast],
  )

  useAlerts(handleAlert)
  return null
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/components/alerts/AlertManager.tsx
git commit -m "feat: add AlertManager for SSE live alerts with Notification + beep + toast"
```

---

## Task 20: PermissionBanner component

**Files:**
- Create: `dashboard-web/components/alerts/PermissionBanner.tsx`

- [ ] **Step 1: Create PermissionBanner.tsx**

Create `dashboard-web/components/alerts/PermissionBanner.tsx`:

```tsx
"use client"
import { useState } from "react"

export function PermissionBanner() {
  const [dismissed, setDismissed] = useState(false)

  if (typeof Notification === "undefined") return null
  if (Notification.permission !== "default" || dismissed) return null

  return (
    <div style={{
      position: "fixed", top: 0, left: 52, right: 0, zIndex: 300,
      background: "var(--amber)", padding: "7px 16px",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      fontFamily: "JetBrains Mono, monospace", fontSize: 11,
    }}>
      <span style={{ color: "var(--bg-base)" }}>
        Enable browser alerts for entry/stop events?
      </span>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={() => { void Notification.requestPermission(); setDismissed(true) }}
          style={{
            background: "var(--bg-base)", border: "none", color: "var(--amber)",
            cursor: "pointer", padding: "3px 10px", borderRadius: 3, fontSize: 11,
            fontFamily: "JetBrains Mono, monospace",
          }}
        >
          Allow
        </button>
        <button
          onClick={() => setDismissed(true)}
          style={{
            background: "none", border: "none",
            color: "var(--bg-base)", cursor: "pointer", fontSize: 11,
          }}
        >
          Not now
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/components/alerts/PermissionBanner.tsx
git commit -m "feat: add PermissionBanner for browser notification consent"
```

---

## Task 21: Wire layout.tsx

**Files:**
- Modify: `dashboard-web/app/layout.tsx`

- [ ] **Step 1: Replace layout.tsx**

Overwrite `dashboard-web/app/layout.tsx` with:

```tsx
import type { Metadata } from "next"
import "./globals.css"
import { Providers } from "@/lib/providers"
import { DrawerProvider } from "@/components/overlays/DrawerContext"
import { Sidebar } from "@/components/layout/Sidebar"
import { SymbolDrawer } from "@/components/overlays/SymbolDrawer"
import { NotificationDrawer } from "@/components/overlays/NotificationDrawer"
import { ToastProvider } from "@/components/alerts/ToastStack"
import { AlertManager } from "@/components/alerts/AlertManager"
import { PermissionBanner } from "@/components/alerts/PermissionBanner"

export const metadata: Metadata = {
  title: "Trading Bot",
  description: "Financial terminal dashboard",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ display: "flex", minHeight: "100vh", background: "var(--bg-base)" }}>
        <Providers>
          <DrawerProvider>
            <ToastProvider>
              <PermissionBanner />
              <Sidebar />
              <main style={{
                flex: 1, marginLeft: 52, padding: "16px",
                overflowY: "auto", minHeight: "100vh",
              }}>
                {children}
              </main>
              <SymbolDrawer />
              <NotificationDrawer />
              <AlertManager />
            </ToastProvider>
          </DrawerProvider>
        </Providers>
      </body>
    </html>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/app/layout.tsx
git commit -m "feat: mount ToastProvider, AlertManager, PermissionBanner in root layout"
```

---

## Task 22: Wire Sidebar — add MarketClock footer

**Files:**
- Modify: `dashboard-web/components/layout/Sidebar.tsx`

- [ ] **Step 1: Replace Sidebar.tsx**

Overwrite `dashboard-web/components/layout/Sidebar.tsx` with:

```tsx
"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { MarketClock } from "@/components/market/MarketClock"

const NAV = [
  { href: "/today",     icon: "⚡", label: "Today"     },
  { href: "/watchlist", icon: "👁", label: "Watchlist" },
  { href: "/outcomes",  icon: "📊", label: "Outcomes"  },
  { href: "/scan",      icon: "🔍", label: "Scan"      },
  { href: "/analytics", icon: "📈", label: "Analytics" },
  { href: "/system",    icon: "⚙", label: "System"    },
]

export function Sidebar() {
  const pathname = usePathname()
  return (
    <nav style={{
      position: "fixed", left: 0, top: 0, bottom: 0, width: 52,
      background: "var(--bg-surface)", borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column", alignItems: "center",
      paddingTop: 12, gap: 4, zIndex: 100,
    }}>
      <div style={{
        fontSize: 16, fontWeight: 700, color: "var(--cyan)",
        fontFamily: "JetBrains Mono, monospace", marginBottom: 12,
      }}>T</div>
      {NAV.map(({ href, icon, label }) => {
        const active = pathname.startsWith(href)
        return (
          <Link key={href} href={href} title={label} style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            width: 40, height: 40, borderRadius: 4, textDecoration: "none", fontSize: 18,
            background: active ? "var(--bg-elevated)" : "transparent",
            borderLeft: active ? "2px solid var(--cyan)" : "2px solid transparent",
            transition: "all 0.15s",
          }}>
            {icon}
          </Link>
        )
      })}
      <div style={{ flex: 1 }} />
      <div style={{ width: "100%" }}>
        <MarketClock />
      </div>
    </nav>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/components/layout/Sidebar.tsx
git commit -m "feat: add MarketClock to Sidebar footer"
```

---

## Task 23: Wire TradeCard — LivePrice and DistanceToBar

**Files:**
- Modify: `dashboard-web/components/terminal/TradeCard.tsx`

- [ ] **Step 1: Replace TradeCard.tsx**

Overwrite `dashboard-web/components/terminal/TradeCard.tsx` with:

```tsx
"use client"
import { StatusBadge } from "./StatusBadge"
import { TickerSymbol } from "./TickerSymbol"
import { PriceValue } from "./PriceValue"
import { LivePrice } from "@/components/market/LivePrice"
import { DistanceToBar } from "@/components/market/DistanceToBar"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import type { CandidateSnapshot, ManualPick } from "@/lib/types"

const LEFT_BORDER: Record<string, string> = {
  "open/watch": "var(--amber)", watching: "var(--amber)",
  active: "var(--green)", triggered: "var(--green)",
  pending: "var(--violet)",
  target_hit: "var(--green)", target_before_stop: "var(--green)",
  stop_hit: "var(--red)", stop_before_target: "var(--red)", failed_setup: "var(--red)",
}

type CardData =
  | Pick<CandidateSnapshot, "symbol" | "status" | "setup_category" | "entry" | "stop" | "target" | "risk_reward" | "total_score">
  | ManualPick

export function TradeCard({ data }: { data: CardData }) {
  const sym = data.symbol
  const status = data.status
  const borderColor = LEFT_BORDER[status] ?? "var(--border)"
  const isSnap = "total_score" in data
  const entry  = isSnap ? (data as CandidateSnapshot).entry         : (data as ManualPick).planned_entry
  const stop   = isSnap ? (data as CandidateSnapshot).stop          : (data as ManualPick).planned_stop
  const target = isSnap ? (data as CandidateSnapshot).target        : (data as ManualPick).planned_target
  const rr     = isSnap ? (data as CandidateSnapshot).risk_reward   : null
  const score  = isSnap ? (data as CandidateSnapshot).total_score   : null

  const { data: prices } = useLivePrices()
  const livePrice = prices?.symbols.find(q => q.symbol === sym.toUpperCase())?.price ?? null

  return (
    <div style={{
      background: "var(--bg-surface)", border: "1px solid var(--border)",
      borderLeft: `3px solid ${borderColor}`, borderRadius: 4,
      padding: "10px 14px", marginBottom: 8,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <TickerSymbol symbol={sym} />
          <StatusBadge status={status} />
          {"setup_category" in data && (
            <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
              {(data as CandidateSnapshot).setup_category}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <LivePrice symbol={sym} entry={entry} />
          {score !== null && (
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, color: "var(--cyan)", fontWeight: 600 }}>
              {score?.toFixed(1)}
            </span>
          )}
        </div>
      </div>
      <div style={{ display: "flex", gap: 16, fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}>
        <span style={{ color: "var(--text-secondary)" }}>Entry <PriceValue value={entry} /></span>
        <span style={{ color: "var(--red)" }}>Stop <PriceValue value={stop} /></span>
        <span style={{ color: "var(--green)" }}>Target <PriceValue value={target} /></span>
        {rr !== null && <span style={{ color: "var(--text-secondary)" }}>R:R {rr?.toFixed(1)}:1</span>}
      </div>
      {livePrice != null && (
        <DistanceToBar current={livePrice} entry={entry} stop={stop} target={target} />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/components/terminal/TradeCard.tsx
git commit -m "feat: add LivePrice and DistanceToBar to TradeCard"
```

---

## Task 24: Wire ScanTable — add NOW column

**Files:**
- Modify: `dashboard-web/components/terminal/ScanTable.tsx`

- [ ] **Step 1: Replace ScanTable.tsx**

Overwrite `dashboard-web/components/terminal/ScanTable.tsx` with:

```tsx
"use client"
import { TickerSymbol } from "./TickerSymbol"
import { LivePrice } from "@/components/market/LivePrice"
import type { ScanResultRow } from "@/lib/types"

function rr(r: ScanResultRow): string {
  if (!r.entry || !r.stop || !r.target) return "—"
  const risk = r.entry - r.stop
  const reward = r.target - r.entry
  if (risk <= 0) return "—"
  return `${(reward / risk).toFixed(1)}:1`
}

function entryDelta(r: ScanResultRow): string {
  if (!r.close || !r.entry || r.close === 0) return ""
  const pct = ((r.entry - r.close) / r.close) * 100
  if (Math.abs(pct) < 0.01) return "at mkt"
  return pct > 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`
}

export function ScanTable({ results }: { results: ScanResultRow[] }) {
  if (!results.length)
    return <p style={{ color: "var(--text-secondary)", padding: 16 }}>No results</p>
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dense-table">
        <thead>
          <tr>
            {["SYM", "SCORE", "SETUP", "CLOSE", "NOW", "ENTRY", "STOP", "TARGET", "R:R", "PLAN"].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {results.map(r => (
            <tr key={r.symbol}>
              <td><TickerSymbol symbol={r.symbol} /></td>
              <td style={{
                color: r.score >= 80 ? "var(--green)" : r.score >= 65 ? "var(--amber)" : "var(--text-primary)",
              }}>
                {r.score.toFixed(1)}
              </td>
              <td style={{ color: "var(--text-secondary)", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis" }}>
                {r.setup_category}
              </td>
              <td style={{ fontFamily: "JetBrains Mono, monospace" }}>${r.close.toFixed(2)}</td>
              <td><LivePrice symbol={r.symbol} /></td>
              <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                ${r.entry.toFixed(2)}
                {entryDelta(r) && (
                  <span style={{ fontSize: 9, color: "var(--text-secondary)", marginLeft: 4 }}>
                    {entryDelta(r)}
                  </span>
                )}
              </td>
              <td style={{ color: "var(--red)", fontFamily: "JetBrains Mono, monospace" }}>${r.stop.toFixed(2)}</td>
              <td style={{ color: "var(--green)", fontFamily: "JetBrains Mono, monospace" }}>${r.target.toFixed(2)}</td>
              <td style={{ fontFamily: "JetBrains Mono, monospace" }}>{rr(r)}</td>
              <td style={{ color: r.trade_plan_valid ? "var(--green)" : "var(--red)" }}>
                {r.trade_plan_valid ? "✓" : "✗"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add dashboard-web/components/terminal/ScanTable.tsx
git commit -m "feat: add NOW column to ScanTable with live prices"
```

---

## Task 25: Wire SymbolDrawer — live price header

**Files:**
- Modify: `dashboard-web/components/overlays/SymbolDrawer.tsx`

- [ ] **Step 1: Replace SymbolDrawer.tsx**

Overwrite `dashboard-web/components/overlays/SymbolDrawer.tsx` with:

```tsx
"use client"
import { useQuery } from "@tanstack/react-query"
import { AnimatePresence, motion } from "motion/react"
import { api } from "@/lib/api"
import { useDrawer } from "./DrawerContext"
import { StatusBadge } from "@/components/terminal/StatusBadge"
import { PriceValue } from "@/components/terminal/PriceValue"
import { ScoreBreakdown } from "@/components/charts/ScoreBreakdown"
import { LivePrice } from "@/components/market/LivePrice"
import { DistanceToBar } from "@/components/market/DistanceToBar"
import { useLivePrices } from "@/lib/hooks/useLivePrices"

export function SymbolDrawer() {
  const { symbolDrawer, closeSymbol } = useDrawer()
  const { data } = useQuery({
    queryKey: ["symbolDetail", symbolDrawer],
    queryFn: () => api.symbolDetail(symbolDrawer!),
    enabled: !!symbolDrawer,
  })
  const { data: prices } = useLivePrices()
  const liveQuote = symbolDrawer
    ? prices?.symbols.find(q => q.symbol === symbolDrawer.toUpperCase())
    : undefined

  return (
    <AnimatePresence>
      {symbolDrawer && (
        <>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={closeSymbol}
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 200 }}
          />
          <motion.div
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
            style={{
              position: "fixed", top: 0, right: 0, bottom: 0, width: 480,
              background: "var(--bg-surface)", borderLeft: "1px solid var(--border)",
              zIndex: 201, overflowY: "auto", padding: 20,
            }}>

            {/* Header row */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <button onClick={closeSymbol} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 16 }}>←</button>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 20, fontWeight: 700, color: "var(--cyan)" }}>{symbolDrawer}</span>
                {data?.latest_snapshot && <StatusBadge status={data.latest_snapshot.status} />}
              </div>
              {data?.latest_snapshot?.total_score !== null && (
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 18, color: "var(--cyan)" }}>
                  {data?.latest_snapshot?.total_score?.toFixed(1)}
                </span>
              )}
            </div>

            {/* Live price card */}
            <div className="card" style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 6 }}>
                Live Price
              </div>
              <div style={{ marginBottom: liveQuote ? 6 : 0 }}>
                <LivePrice symbol={symbolDrawer} entry={data?.latest_snapshot?.entry} />
              </div>
              {liveQuote && data?.latest_snapshot && (
                <DistanceToBar
                  current={liveQuote.price}
                  entry={data.latest_snapshot.entry}
                  stop={data.latest_snapshot.stop}
                  target={data.latest_snapshot.target}
                />
              )}
            </div>

            {data?.latest_scan_result && (
              <div className="card" style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>Score Breakdown</div>
                <ScoreBreakdown scores={{
                  trend: data.latest_scan_result.trend_score,
                  momentum: data.latest_scan_result.momentum_score,
                  volume: data.latest_scan_result.volume_score,
                  risk: data.latest_scan_result.risk_score,
                  setup_quality: data.latest_scan_result.setup_quality_score,
                }} />
              </div>
            )}

            {data?.latest_snapshot && (
              <div className="card" style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>Trade Plan</div>
                <div style={{ display: "flex", gap: 16, fontFamily: "JetBrains Mono, monospace", fontSize: 12 }}>
                  <span>Entry <PriceValue value={data.latest_snapshot.entry} /></span>
                  <span style={{ color: "var(--red)" }}>Stop <PriceValue value={data.latest_snapshot.stop} /></span>
                  <span style={{ color: "var(--green)" }}>Target <PriceValue value={data.latest_snapshot.target} /></span>
                  {data.latest_snapshot.risk_reward !== null && (
                    <span style={{ color: "var(--text-secondary)" }}>R:R {data.latest_snapshot.risk_reward?.toFixed(1)}:1</span>
                  )}
                </div>
              </div>
            )}

            {data?.latest_snapshot?.tony_hypothesis && (
              <div className="card" style={{ marginBottom: 12, borderLeft: "3px solid var(--cyan)" }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--cyan)", letterSpacing: "0.08em", marginBottom: 6 }}>Tony Hypothesis</div>
                {data.latest_snapshot.tony_priority_label && (
                  <div style={{ fontSize: 11, color: "var(--amber)", marginBottom: 4 }}>{data.latest_snapshot.tony_priority_label} — {data.latest_snapshot.tony_recommended_action}</div>
                )}
                {data.latest_snapshot.tony_setup_read && (
                  <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: "0 0 6px" }}>{data.latest_snapshot.tony_setup_read}</p>
                )}
                <p style={{ fontSize: 11, color: "var(--text-primary)", margin: 0, fontStyle: "italic" }}>{data.latest_snapshot.tony_hypothesis}</p>
              </div>
            )}

            {(data?.recent_snapshots?.length ?? 0) > 1 && (
              <div className="card">
                <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>Snapshot History</div>
                {data?.recent_snapshots?.slice(1, 6).map(s => (
                  <div key={s.id} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid var(--border)", fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}>
                    <span style={{ color: "var(--text-secondary)" }}>{s.snapshot_time.slice(0, 10)}</span>
                    <StatusBadge status={s.outcome_label ?? s.status} />
                    <span>{s.total_score?.toFixed(1) ?? "—"}</span>
                  </div>
                ))}
              </div>
            )}

            {!data && (
              <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>Loading {symbolDrawer}...</p>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```powershell
cd dashboard-web; npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Run all backend tests — final check**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/ -v
```

Expected: all tests **PASS**

- [ ] **Step 4: Commit**

```bash
git add dashboard-web/components/overlays/SymbolDrawer.tsx
git commit -m "feat: add live price header card to SymbolDrawer"
```

---

## Spec Coverage Matrix

| Spec requirement | Task(s) |
|---|---|
| PriceCache + LiveQuote dataclass | 4 |
| Background poll 15s/60s | 4 (`run_price_poll_loop`) |
| Symbol set rebuild every 5 min | 4 |
| Alpaca batch `/v2/stocks/snapshots` call | 4 (`refresh`) |
| On failure: keep cache, log, retry | 4 (`refresh` exception handler) |
| NYSE market calendar helper | 3 |
| `near_entry` detection + 5-min cooldown | 4 (`_detect_events`) |
| `stop_violation` detection + once-per-snapshot | 4 (`_detect_events`) |
| Events pushed to asyncio.Queue | 4 |
| `GET /api/prices` | 7 |
| `GET /api/prices/{symbol}` | 7 |
| 503 when no Alpaca keys | 7 |
| SSE drains live_event_queue | 9 |
| Background task wired in lifespan | 8 |
| `useLivePrices` with Page Visibility | 12 |
| `useMarketStatus` | 13 |
| `useAlerts` | 14 |
| `LivePrice` (live/stale/close/no-data) | 15 |
| `DistanceToBar` pills | 16 |
| `MarketClock` with 1s countdown | 17 |
| `AlertManager` (Notification + beep + toast) | 19 |
| `PermissionBanner` | 20 |
| `playBeep` | 11 |
| Frontend types + API calls | 10 |
| Root layout wiring | 21 |
| Sidebar MarketClock | 22 |
| TradeCard integration | 23 |
| ScanTable NOW column | 24 |
| SymbolDrawer live price header | 25 |
| Pydantic schemas | 2 |
| Python dependency | 1 |
