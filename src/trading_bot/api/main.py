from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trading_bot.api.live_prices import PriceCache, run_price_poll_loop
from trading_bot.api.routes import (
    health, today, picks, outcomes, scan, analytics, events, system, symbols, vault, paper,
    command_center, morning_prep, cockpit,
)
from trading_bot.api.routes import prices as prices_router
from trading_bot.settings import load_dotenv_if_present


# Project root resolved from this file's location, so defaults work regardless of cwd.
# SQLite silently creates an empty DB when a relative path resolves to a missing file,
# which previously caused empty API responses when uvicorn launched outside the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load .env so Alpaca keys are present for live prices regardless of how
    # uvicorn was launched. setdefault means real OS env vars still win.
    load_dotenv_if_present(_PROJECT_ROOT / ".env")

    app.state.db_path = os.environ.get("DATABASE_PATH", str(_PROJECT_ROOT / "data" / "trading_bot.db"))
    app.state.vault_dir = os.environ.get("VAULT_DIR", str(_PROJECT_ROOT / "vault"))
    app.state.reports_dir = os.environ.get("REPORTS_DIR", str(_PROJECT_ROOT / "reports"))

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
    paper.router,
    command_center.router,
    morning_prep.router,
    cockpit.router,
):
    app.include_router(_router, prefix="/api")

