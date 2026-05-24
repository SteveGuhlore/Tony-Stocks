"""Smoke tests for the FastAPI layer — empty DB, no live data needed."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trading_bot.api.main import app
from trading_bot.storage.database import initialize_database


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    initialize_database(str(db))
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_today(client):
    r = client.get("/api/today")
    assert r.status_code == 200
    data = r.json()
    assert "kpis" in data
    assert "watch" in data


def test_scan_overview(client):
    r = client.get("/api/scan/overview")
    assert r.status_code == 200
    assert "scanned" in r.json()


def test_scan_latest(client):
    r = client.get("/api/scan/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["results"] == []
    assert data["total"] == 0


def test_outcomes(client):
    r = client.get("/api/outcomes")
    assert r.status_code == 200
    assert "kpis" in r.json()


def test_system_health(client):
    r = client.get("/api/system/health")
    assert r.status_code == 200
    assert "open_snapshots" in r.json()


def test_events(client):
    r = client.get("/api/events")
    assert r.status_code == 200
    data = r.json()
    assert data["events"] == []
    assert data["total"] == 0


def test_vault_bridge_missing(client):
    r = client.get("/api/vault/bridge")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_symbol_detail(client):
    r = client.get("/api/symbols/AAPL/detail")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "AAPL"
    assert data["latest_snapshot"] is None
