from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trading_bot.api.routes import (
    health, today, picks, outcomes, scan, analytics, events, system, symbols, vault
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_path = os.environ.get("DATABASE_PATH", "data/trading_bot.db")
    app.state.vault_dir = os.environ.get("VAULT_DIR", "vault")
    yield


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
):
    app.include_router(_router, prefix="/api")

