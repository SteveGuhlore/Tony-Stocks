"""Smoke tests for personalization endpoints (pins/notes/presets/journal/ratings/alerts)."""
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


def test_pins_roundtrip(client):
    assert client.get("/api/personalize/pins").json()["pins"] == []
    client.post("/api/personalize/pins", json={"symbol": "nvda", "pinned": True})
    pins = client.get("/api/personalize/pins").json()["pins"]
    assert [p["symbol"] for p in pins] == ["NVDA"]
    client.post("/api/personalize/pins", json={"symbol": "NVDA", "pinned": False})
    assert client.get("/api/personalize/pins").json()["pins"] == []


def test_notes_roundtrip(client):
    client.post("/api/personalize/notes", json={"symbol": "AMD", "body": "watch the gap"})
    notes = client.get("/api/personalize/notes?symbol=AMD").json()["notes"]
    assert len(notes) == 1
    assert notes[0]["body"] == "watch the gap"


def test_presets_upsert(client):
    client.post("/api/personalize/presets", json={"name": "movers", "payload": {"sort": "rvol"}})
    client.post("/api/personalize/presets", json={"name": "movers", "payload": {"sort": "score"}})
    presets = client.get("/api/personalize/presets").json()["presets"]
    assert len(presets) == 1
    assert presets[0]["payload"] == {"sort": "score"}


def test_journal_and_ratings(client):
    client.post("/api/personalize/journal", json={"symbol": "HOOD", "entry": "took half off"})
    assert len(client.get("/api/personalize/journal").json()["journal"]) == 1
    client.post("/api/personalize/call-ratings", json={"symbol": "HOOD", "rating": 4, "note": "good"})
    ratings = client.get("/api/personalize/call-ratings?symbol=HOOD").json()["ratings"]
    assert ratings[0]["rating"] == 4


def test_price_alerts_lifecycle(client):
    r = client.post("/api/personalize/price-alerts", json={"symbol": "MU", "target_price": 130.0, "direction": "above"})
    alert_id = r.json()["id"]
    active = client.get("/api/personalize/price-alerts?active_only=true").json()["alerts"]
    assert len(active) == 1
    client.post(f"/api/personalize/price-alerts/{alert_id}/deactivate")
    assert client.get("/api/personalize/price-alerts?active_only=true").json()["alerts"] == []
