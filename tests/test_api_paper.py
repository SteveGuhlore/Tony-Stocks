"""Smoke tests for the paper-trading API route. Empty DB + seeded positions."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trading_bot.api.main import app
from trading_bot.storage.database import initialize_database
from trading_bot.storage.repositories import ScannerRepository


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    initialize_database(str(db))
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    with TestClient(app) as c:
        yield c, db


def test_paper_positions_empty(client):
    c, _ = client
    r = c.get("/api/paper/positions")
    assert r.status_code == 200
    data = r.json()
    assert data["open"] == [] and data["closed"] == []
    assert data["summary"]["open_count"] == 0
    assert "enabled" in data
    assert data["account_label"]


def test_paper_positions_with_data(client):
    c, db = client
    repo = ScannerRepository(db)
    repo.open_paper_position(account_label="tony", symbol="ZETA", qty=50, entry_price=100.0,
                             stop=95.0, target=115.0, broker_order_id="o1", snapshot_id=1,
                             opened_at="2026-06-02T14:31:00+00:00")
    repo.open_paper_position(account_label="tony", symbol="NVDA", qty=10, entry_price=120.0,
                             stop=114.0, target=130.0, broker_order_id="o2", snapshot_id=2,
                             opened_at="2026-06-02T14:32:00+00:00")
    repo.close_paper_position("NVDA", account_label="tony", result="target_hit", exit_price=130.0,
                              realized_pl=100.0, closed_at="2026-06-03T14:00:00+00:00")

    data = c.get("/api/paper/positions").json()
    assert data["summary"]["open_count"] == 1
    assert data["summary"]["closed_count"] == 1
    assert data["summary"]["target_hits"] == 1
    assert data["summary"]["realized_pl"] == 100.0
    assert data["summary"]["win_rate"] == 1.0
    assert {p["symbol"] for p in data["open"]} == {"ZETA"}
    assert data["closed"][0]["result"] == "target_hit"
