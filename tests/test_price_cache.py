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
