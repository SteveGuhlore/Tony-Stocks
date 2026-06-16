"""Tests for GET /api/command-center and its pure mappers.

Covers the three contract mismatches the endpoint bridges: win-rate 0–100 → 0–1,
agreement override_* → cc_overrode_*, and verbatim (non-enum) verdict passthrough.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from trading_bot.api.main import app
from trading_bot.api.routes.command_center import (
    build_agreement,
    build_agreement_from_teaching,
    build_picks,
    build_record,
)

_VERDICTS = [
    {
        "date": "2026-06-03",
        "symbol": "DAL",
        "tony_score": 45.0,
        "verdict": "override",
        "thesis": "Overriding to CLOSE. Falling volume on the breakout.",
        "target": 79.5,
        "stop": 75.49,
    },
    {
        "date": "2026-06-03",
        "symbol": "hood",  # lower-case to prove uppercasing
        "tony_score": 85.0,
        "verdict": "reaffirm",
        "thesis": "Reaffirming the momentum continuation.",
        "target": None,
        "stop": None,
    },
    {
        "date": "2026-06-03",
        "symbol": "MARA",
        "tony_score": 35.0,
        "verdict": "pass",  # not in the dashboard enum — must survive verbatim
        "thesis": "Passing; fundamentals too weak.",
        "target": None,
        "stop": None,
    },
]

_RECORD = {
    "status": "scored",
    "verdicts": 7,
    "graded": 6,
    "tony_win_rate": 33.3,
    "agreement": {
        "agreed_right": 0,
        "agreed_wrong": 0,
        "override_saved": 2,
        "override_missed": 4,
    },
    "calibration": {"low": 50.0, "medium": 0.0, "high": None},
}


# ── Pure mappers ──────────────────────────────────────────────────────────────


def test_build_picks_uppercases_keys_and_maps_fields():
    picks = build_picks(_VERDICTS)
    assert set(picks) == {"DAL", "HOOD", "MARA"}
    hood = picks["HOOD"]
    assert hood.symbol == "HOOD"
    assert hood.score == 85.0
    assert hood.verdict == "reaffirm"
    assert hood.reasoning == "Reaffirming the momentum continuation."
    assert hood.returned_at == "2026-06-03T00:00:00Z"


def test_build_picks_passes_through_non_enum_verdict():
    picks = build_picks(_VERDICTS)
    assert picks["MARA"].verdict == "pass"


def test_build_picks_handles_garbage():
    assert build_picks(None) == {}
    assert build_picks("nope") == {}
    assert build_picks([{"no_symbol": 1}, 42, None]) == {}


def test_build_record_normalizes_win_rate_to_fraction():
    rec = build_record(_RECORD)
    assert rec is not None
    assert rec.win_rate == pytest.approx(0.333)
    # absent fields degrade to None / empty, never crash
    assert rec.avg_pl_per_trade is None
    assert rec.target_hits is None
    assert rec.stop_hits is None
    assert rec.equity_curve == []


def test_build_record_none_when_missing():
    assert build_record(None) is None
    assert build_record("not a dict") is None


def test_build_agreement_renames_override_keys():
    agr = build_agreement(_RECORD)
    assert agr is not None
    assert agr.cc_overrode_saved == 2
    assert agr.cc_overrode_missed == 4
    assert agr.agreed_right == 0
    assert agr.agreed_wrong == 0


def test_build_agreement_accepts_cc_overrode_spelling():
    agr = build_agreement(
        {"agreement": {"cc_overrode_saved": 3, "cc_overrode_missed": 1}}
    )
    assert agr is not None
    assert agr.cc_overrode_saved == 3
    assert agr.cc_overrode_missed == 1


def test_build_agreement_none_when_no_agreement_block():
    assert build_agreement({"tony_win_rate": 50}) is None
    assert build_agreement(None) is None


def test_build_agreement_from_teaching_reads_quadrants():
    teaching = {
        "agreement": {
            "agreed_right": 3,
            "agreed_wrong": 1,
            "cc_overrode_saved": 2,
            "cc_overrode_missed": 4,
        }
    }
    agr = build_agreement_from_teaching(teaching)
    assert agr is not None
    assert (
        agr.agreed_right,
        agr.agreed_wrong,
        agr.cc_overrode_saved,
        agr.cc_overrode_missed,
    ) == (3, 1, 2, 4)


def test_build_agreement_from_teaching_none_when_missing():
    assert build_agreement_from_teaching(None) is None
    assert build_agreement_from_teaching({"records": []}) is None


# ── Endpoint ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setenv("REPORTS_DIR", str(reports))
    # Don't let a developer's real env-var overrides leak into the test.
    monkeypatch.delenv("TONY_VERDICTS_FILE", raising=False)
    monkeypatch.delenv("TONY_RECORD_FILE", raising=False)
    monkeypatch.delenv("TONY_TEACHING_FILE", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c, reports


def test_endpoint_empty_when_files_missing(client):
    c, _ = client
    r = c.get("/api/command-center")
    assert r.status_code == 200
    data = r.json()
    assert data["picks"] == {} and data["record"] is None and data["agreement"] is None
    assert "weights" in data


def test_endpoint_maps_full_payload(client):
    c, reports = client
    (reports / "tony_stocks_verdicts.json").write_text(
        json.dumps(_VERDICTS), encoding="utf-8"
    )
    (reports / "tony_stocks_record.json").write_text(
        json.dumps(_RECORD), encoding="utf-8"
    )

    data = c.get("/api/command-center").json()
    assert set(data["picks"]) == {"DAL", "HOOD", "MARA"}
    assert data["picks"]["MARA"]["verdict"] == "pass"
    assert data["record"]["win_rate"] == pytest.approx(0.333)
    assert data["agreement"]["cc_overrode_saved"] == 2
    assert data["agreement"]["cc_overrode_missed"] == 4


def test_endpoint_falls_back_to_teaching_agreement(client):
    # No CC record file -> agreement comes from the bot-side teaching ledger.
    c, reports = client
    teaching = {
        "agreement": {
            "agreed_right": 1,
            "agreed_wrong": 0,
            "cc_overrode_saved": 2,
            "cc_overrode_missed": 1,
        }
    }
    (reports / "tony_teaching_log.json").write_text(
        json.dumps(teaching), encoding="utf-8"
    )
    data = c.get("/api/command-center").json()
    assert data["record"] is None  # no CC record file
    assert data["agreement"]["cc_overrode_saved"] == 2
    assert data["agreement"]["agreed_right"] == 1


def test_richer_agreement_source_wins_cc_authoritative(client):
    # Both sources are monotonic; the panel shows whichever graded MORE. Here the CC record
    # (total 6) outweighs a thinner ledger (total 4), so the authoritative CC record wins.
    c, reports = client
    (reports / "tony_stocks_record.json").write_text(
        json.dumps(_RECORD), encoding="utf-8"
    )
    teaching = {
        "agreement": {
            "agreed_right": 1,
            "agreed_wrong": 1,
            "cc_overrode_saved": 1,
            "cc_overrode_missed": 1,
        }
    }
    (reports / "tony_teaching_log.json").write_text(
        json.dumps(teaching), encoding="utf-8"
    )
    data = c.get("/api/command-center").json()
    assert (
        data["agreement"]["cc_overrode_saved"] == 2
    )  # CC record (richer), not the ledger


def test_starved_cc_record_yields_to_richer_teaching(client):
    # The live bug: the outcomes file got wiped, so the CC record graded far fewer (2) than the
    # bot's monotonic teaching ledger (64). The panel must show the richer source, never regress.
    c, reports = client
    starved = {
        **_RECORD,
        "agreement": {
            "agreed_right": 0,
            "agreed_wrong": 1,
            "override_saved": 1,
            "override_missed": 0,
        },
    }  # total 2
    (reports / "tony_stocks_record.json").write_text(
        json.dumps(starved), encoding="utf-8"
    )
    teaching = {
        "agreement": {
            "agreed_right": 24,
            "agreed_wrong": 13,
            "cc_overrode_saved": 16,
            "cc_overrode_missed": 11,
        }
    }  # total 64
    (reports / "tony_teaching_log.json").write_text(
        json.dumps(teaching), encoding="utf-8"
    )
    data = c.get("/api/command-center").json()
    agr = data["agreement"]
    assert (
        agr["agreed_right"]
        + agr["agreed_wrong"]
        + agr["cc_overrode_saved"]
        + agr["cc_overrode_missed"]
        == 64
    )
    assert agr["agreed_right"] == 24  # the richer monotonic ledger, not the starved 2


def test_endpoint_survives_malformed_json(client):
    c, reports = client
    (reports / "tony_stocks_verdicts.json").write_text("{ not json", encoding="utf-8")
    (reports / "tony_stocks_record.json").write_text("[1,2,", encoding="utf-8")
    data = c.get("/api/command-center").json()
    # Malformed verdict/record files degrade to empty; weights come from scoring_config
    # (independent of those files), so they may still populate.
    assert data["picks"] == {}
    assert data["record"] is None
    assert data["agreement"] is None
    assert "weights" in data
