"""Tests for GET /api/morning-prep.

Contract:
- Always returns 200 with MorningPrepResponse.
- Missing dir / missing file / corrupt file → 200 with well-formed empty response.
- When a valid report exists, it is mapped correctly to the schema.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from trading_bot.api.main import app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient wired to a fresh tmp reports dir (no real files)."""
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setenv("REPORTS_DIR", str(reports))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c, reports


# ── Sample payload (mirrors MorningPrep.to_dict() shape) ──────────────────────

_CANDIDATE = {
    "symbol": "NVDA",
    "score": 0.92,
    "setup": "breakout",
    "entry": 120.5,
    "stop": 115.0,
    "target": 135.0,
    "rr": 2.636,
    "conviction": "high",
    "catalysts": {"earnings_blackout": False, "days_to_earnings": 45},
    "warnings": [],
}

_REPORT = {
    "generated_at": "2026-06-06T04:00:00-04:00",
    "et_date": "2026-06-06",
    "phase": "pre_open",
    "shortlist": [_CANDIDATE],
    "what_changed_overnight": "3 new lessons; calibration: on-track",
    "plan_for_open": "1 names armed; 1 high-conviction; 0 in earnings blackout.",
}


# ── Never-500 contract ─────────────────────────────────────────────────────────

def test_returns_200_when_morning_prep_dir_missing(tmp_path, monkeypatch):
    """No reports/morning_prep dir at all → 200 with empty shortlist."""
    reports = tmp_path / "reports"
    reports.mkdir()
    # Do NOT create morning_prep subdir
    monkeypatch.setenv("REPORTS_DIR", str(reports))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        r = c.get("/api/morning-prep")
    assert r.status_code == 200
    data = r.json()
    assert data["shortlist"] == []
    assert data["generated_at"] == ""
    assert data["et_date"] == ""
    assert data["phase"] == ""


def test_returns_200_when_no_files_in_dir(client):
    """Dir exists but no JSON files → 200 with empty shortlist."""
    c, _ = client
    r = c.get("/api/morning-prep")
    assert r.status_code == 200
    data = r.json()
    assert data["shortlist"] == []


def test_returns_200_on_corrupt_json(client):
    """Corrupt JSON file → 200 with empty shortlist (NEVER 500)."""
    c, reports = client
    prep_dir = reports / "morning_prep"
    prep_dir.mkdir()
    (prep_dir / "2026-06-06.json").write_text("{ this is not json", encoding="utf-8")
    r = c.get("/api/morning-prep")
    assert r.status_code == 200
    data = r.json()
    assert data["shortlist"] == []


def test_returns_200_on_empty_file(client):
    """Empty file → 200 with empty shortlist (NEVER 500)."""
    c, reports = client
    prep_dir = reports / "morning_prep"
    prep_dir.mkdir()
    (prep_dir / "2026-06-06.json").write_text("", encoding="utf-8")
    r = c.get("/api/morning-prep")
    assert r.status_code == 200
    data = r.json()
    assert data["shortlist"] == []


# ── Correct mapping ────────────────────────────────────────────────────────────

def test_maps_full_report(client):
    """A valid report file is mapped to MorningPrepResponse correctly."""
    c, reports = client
    prep_dir = reports / "morning_prep"
    prep_dir.mkdir()
    (prep_dir / "2026-06-06.json").write_text(json.dumps(_REPORT), encoding="utf-8")

    r = c.get("/api/morning-prep")
    assert r.status_code == 200
    data = r.json()

    assert data["generated_at"] == "2026-06-06T04:00:00-04:00"
    assert data["et_date"] == "2026-06-06"
    assert data["phase"] == "pre_open"
    assert data["what_changed_overnight"] == "3 new lessons; calibration: on-track"
    assert data["plan_for_open"] == "1 names armed; 1 high-conviction; 0 in earnings blackout."

    assert len(data["shortlist"]) == 1
    cand = data["shortlist"][0]
    assert cand["symbol"] == "NVDA"
    assert cand["score"] == pytest.approx(0.92)
    assert cand["setup"] == "breakout"
    assert cand["entry"] == pytest.approx(120.5)
    assert cand["stop"] == pytest.approx(115.0)
    assert cand["target"] == pytest.approx(135.0)
    assert cand["rr"] == pytest.approx(2.636)
    assert cand["conviction"] == "high"
    assert cand["catalysts"] == {"earnings_blackout": False, "days_to_earnings": 45}
    assert cand["warnings"] == []


def test_picks_most_recent_file(client):
    """When multiple date files exist, the lexicographically latest is used."""
    c, reports = client
    prep_dir = reports / "morning_prep"
    prep_dir.mkdir()

    older = {"generated_at": "OLD", "et_date": "2026-06-05", "phase": "overnight",
             "shortlist": [], "what_changed_overnight": "", "plan_for_open": ""}
    newer = {"generated_at": "NEW", "et_date": "2026-06-06", "phase": "pre_open",
             "shortlist": [], "what_changed_overnight": "", "plan_for_open": ""}

    (prep_dir / "2026-06-05.json").write_text(json.dumps(older), encoding="utf-8")
    (prep_dir / "2026-06-06.json").write_text(json.dumps(newer), encoding="utf-8")

    r = c.get("/api/morning-prep")
    assert r.status_code == 200
    data = r.json()
    assert data["generated_at"] == "NEW"
    assert data["et_date"] == "2026-06-06"


def test_partial_candidate_fields_degrade_gracefully(client):
    """Candidate missing optional fields still validates — no 500."""
    c, reports = client
    prep_dir = reports / "morning_prep"
    prep_dir.mkdir()

    sparse_report = {
        "generated_at": "2026-06-06T04:00:00-04:00",
        "et_date": "2026-06-06",
        "phase": "pre_open",
        "shortlist": [
            {"symbol": "AAPL", "score": 0.7, "setup": "pullback",
             "conviction": "medium", "catalysts": {}, "warnings": ["earnings blackout"]}
            # entry/stop/target/rr absent
        ],
        "what_changed_overnight": "",
        "plan_for_open": "",
    }
    (prep_dir / "2026-06-06.json").write_text(json.dumps(sparse_report), encoding="utf-8")

    r = c.get("/api/morning-prep")
    assert r.status_code == 200
    data = r.json()
    cand = data["shortlist"][0]
    assert cand["symbol"] == "AAPL"
    assert cand["entry"] is None
    assert cand["stop"] is None
    assert cand["target"] is None
    assert cand["rr"] is None
    assert "earnings blackout" in cand["warnings"]
