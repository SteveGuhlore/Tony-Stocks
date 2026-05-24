"""Tests for /api/prices endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_app(monkeypatch, *, with_keys: bool = True, cache_quotes: dict | None = None):
    if with_keys:
        monkeypatch.setenv("ALPACA_API_KEY", "key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    else:
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    from trading_bot.api.main import app

    mock_cache = MagicMock()
    mock_cache.snapshot.return_value = cache_quotes or {}
    mock_cache.get.return_value = None
    app.state.price_cache = mock_cache
    return TestClient(app, raise_server_exceptions=True)


def _make_quote(symbol: str = "AAPL", price: float = 150.0):
    from trading_bot.api.live_prices import LiveQuote
    return LiveQuote(
        symbol=symbol, price=price, bid=149.9, ask=150.1,
        prev_close=148.0, change_pct=0.013, day_open=148.5,
        day_high=151.0, day_low=148.0, day_volume=9_000_000,
        asof=datetime(2024, 1, 16, 14, 30, tzinfo=timezone.utc),
        is_live=True,
    )


def test_get_prices_503_no_keys(tmp_path, monkeypatch):
    client = _make_app(monkeypatch, with_keys=False)
    resp = client.get("/api/prices")
    assert resp.status_code == 503


def test_get_price_symbol_503_no_keys(tmp_path, monkeypatch):
    client = _make_app(monkeypatch, with_keys=False)
    resp = client.get("/api/prices/AAPL")
    assert resp.status_code == 503


def test_get_prices_empty_cache(tmp_path, monkeypatch):
    client = _make_app(monkeypatch, with_keys=True, cache_quotes={})
    with patch("trading_bot.api.routes.prices.market_status", return_value={
        "open": False, "next_open": None, "next_close": None, "timezone": "America/New_York"
    }):
        resp = client.get("/api/prices")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbols"] == []
    assert body["market"]["timezone"] == "America/New_York"


def test_get_price_symbol_404_unknown(tmp_path, monkeypatch):
    client = _make_app(monkeypatch, with_keys=True)
    resp = client.get("/api/prices/ZZZZ")
    assert resp.status_code == 404
