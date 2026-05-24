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
