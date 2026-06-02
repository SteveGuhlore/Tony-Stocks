from __future__ import annotations

import asyncio
import functools
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
                df = await asyncio.to_thread(fetcher)
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
            df = await asyncio.to_thread(functools.partial(repo.list_candidate_snapshots, limit=500))
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

            if await asyncio.to_thread(is_market_open, now):
                await app.state.price_cache.refresh()
                await asyncio.sleep(15)
            else:
                # Fetch last-known prices even when market is closed so the UI
                # shows the previous close instead of dashes.
                await app.state.price_cache.refresh()
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Price poll loop error: %s", exc)
            await asyncio.sleep(30)
