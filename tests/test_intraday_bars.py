"""Storage + chart-endpoint tests for the Kinetic Tape intraday_bars feature."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from trading_bot.api.main import app
from trading_bot.storage.database import initialize_database
from trading_bot.storage.repositories import ScannerRepository


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_upsert_is_idempotent_on_symbol_ts(tmp_path):
    db = tmp_path / "t.db"
    repo = ScannerRepository(db)
    ts = "2026-06-07T14:30:00+00:00"
    repo.upsert_intraday_bar(symbol="nvda", ts=ts, open=1, high=2, low=0.5, close=1.5, volume=100)
    repo.upsert_intraday_bar(symbol="NVDA", ts=ts, open=1, high=3, low=0.5, close=2.0, volume=200)
    bars = repo.list_intraday_bars("NVDA")
    assert len(bars) == 1  # upsert, not duplicate
    assert bars[0]["close"] == 2.0
    assert bars[0]["volume"] == 200


def test_list_returns_oldest_first(tmp_path):
    repo = ScannerRepository(tmp_path / "t.db")
    repo.upsert_intraday_bar(symbol="X", ts="2026-06-07T15:00:00+00:00", open=1, high=1, low=1, close=1, volume=1)
    repo.upsert_intraday_bar(symbol="X", ts="2026-06-07T14:00:00+00:00", open=1, high=1, low=1, close=1, volume=1)
    bars = repo.list_intraday_bars("X")
    assert [b["ts"] for b in bars] == ["2026-06-07T14:00:00+00:00", "2026-06-07T15:00:00+00:00"]


def test_prune_removes_old_bars(tmp_path):
    repo = ScannerRepository(tmp_path / "t.db")
    old = _iso(datetime.now(timezone.utc) - timedelta(days=20))
    fresh = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
    repo.upsert_intraday_bar(symbol="X", ts=old, open=1, high=1, low=1, close=1, volume=1)
    repo.upsert_intraday_bar(symbol="X", ts=fresh, open=1, high=1, low=1, close=1, volume=1)
    cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=10))
    removed = repo.prune_intraday_bars(before_ts=cutoff)
    assert removed == 1
    assert len(repo.list_intraday_bars("X")) == 1


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    initialize_database(str(db))
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    with TestClient(app) as c:
        yield c, db


def test_chart_unavailable_when_no_bars(client):
    c, _ = client
    data = c.get("/api/symbols/ZZZ/chart").json()
    assert data["status"] == "unavailable"
    assert data["bars"] == []
    assert data["symbol"] == "ZZZ"
    assert set(data["plan"].keys()) == {"entry", "stop", "target"}


def test_chart_ok_with_fresh_bars_and_contract(client):
    c, db = client
    repo = ScannerRepository(db)
    fresh = _iso(datetime.now(timezone.utc) - timedelta(minutes=5))
    repo.upsert_intraday_bar(symbol="NVDA", ts=fresh, open=180, high=185, low=179, close=183, volume=1000)
    data = c.get("/api/symbols/NVDA/chart").json()
    assert data["status"] == "ok"
    assert len(data["bars"]) == 1
    b = data["bars"][0]
    assert set(b.keys()) == {"t", "o", "h", "l", "c", "v"}
    assert b["c"] == 183.0
    assert data["timeframe"] == "intraday"


def test_chart_stale_when_bars_old(client):
    c, db = client
    repo = ScannerRepository(db)
    old = _iso(datetime.now(timezone.utc) - timedelta(days=3))
    repo.upsert_intraday_bar(symbol="MU", ts=old, open=1, high=1, low=1, close=1, volume=1)
    data = c.get("/api/symbols/MU/chart").json()
    assert data["status"] == "stale"
    assert len(data["bars"]) == 1
