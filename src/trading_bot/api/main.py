from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trading_bot.api.live_prices import PriceCache, run_price_poll_loop
from trading_bot.api.routes import (
    health, today, picks, outcomes, scan, analytics, events, system, symbols, vault
)
from trading_bot.api.routes import prices as prices_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_path = os.environ.get("DATABASE_PATH", "data/trading_bot.db")
    app.state.vault_dir = os.environ.get("VAULT_DIR", "vault")

    live_queue: asyncio.Queue = asyncio.Queue()
    app.state.live_event_queue = live_queue

    cache = PriceCache(app.state.db_path)
    cache.set_event_queue(live_queue)
    app.state.price_cache = cache

    poll_task = asyncio.create_task(run_price_poll_loop(app))
    try:
        yield
    finally:
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
    allow_methods=["GET","POST"],
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

