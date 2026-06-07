"""Tests for morning_prep assembler (Task 4 — Off-Hours Research Engine).

TDD: tests written first, implementation follows.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pytest

from trading_bot.analytics.morning_prep import (
    PrepCandidate,
    MorningPrep,
    build_morning_prep,
)
from trading_bot.analytics.catalyst_enrichment import CatalystTags

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

ET = ZoneInfo("America/New_York")


def _now_et() -> datetime:
    """Return a fixed aware ET datetime for deterministic tests."""
    return datetime(2026, 6, 6, 5, 30, 0, tzinfo=ET)


def _make_row(
    symbol: str,
    total_score: float,
    setup_category: str = "momentum_breakout",
    planned_entry_price: float | None = 100.0,
    stop_price: float | None = 95.0,
    target_price: float | None = 115.0,
) -> dict:
    return {
        "symbol": symbol,
        "total_score": total_score,
        "setup_category": setup_category,
        "planned_entry_price": planned_entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
    }


def _make_catalyst(symbol: str, *, earnings_blackout: bool = False) -> CatalystTags:
    return CatalystTags(
        symbol=symbol,
        upcoming_earnings_date="2026-06-10" if earnings_blackout else None,
        earnings_blackout=earnings_blackout,
        analyst_rec_trend="up",
        news_sentiment=0.5,
        revenue_growth=0.15,
    )


# 3 synthetic scored rows (spec requirement)
ROWS_3 = [
    _make_row("AAPL", 85.0),   # high conviction (0.85 → "high")
    _make_row("MSFT", 65.0),   # medium conviction (0.65 → "medium")
    _make_row("GOOG", 45.0),   # low conviction (0.45 → "low")
]

CATALYST_TAGS_BASIC = {
    "AAPL": _make_catalyst("AAPL"),
    "MSFT": _make_catalyst("MSFT"),
    "GOOG": _make_catalyst("GOOG"),
}


# ---------------------------------------------------------------------------
# Test: sort order — top-N sorted descending by score
# ---------------------------------------------------------------------------

class TestSortOrder:
    def test_sorted_descending_by_score(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="pre_open",
        )
        scores = [c.score for c in prep.shortlist]
        assert scores == sorted(scores, reverse=True)

    def test_shortlist_truncated_to_size(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="pre_open",
            shortlist_size=2,
        )
        assert len(prep.shortlist) == 2

    def test_top_symbol_is_highest_score(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].symbol == "AAPL"

    def test_dedupes_to_one_row_per_symbol_keeping_highest_score(self):
        # Several snapshot rows per symbol (as the live DB scan produces) must
        # collapse to one row per symbol — the highest-scored — not N duplicates.
        rows = [
            _make_row("CVS", 70.0),
            _make_row("CVS", 95.0),   # highest for CVS — this one should win
            _make_row("CVS", 80.0),
            _make_row("CSX", 90.0),
            _make_row("CSX", 60.0),
        ]
        prep = build_morning_prep(
            scored_rows=rows,
            catalyst_tags={},
            now_et=_now_et(),
            phase="weekend",
        )
        symbols = [c.symbol for c in prep.shortlist]
        assert symbols == ["CVS", "CSX"]          # 2 distinct names, deduped
        assert len(symbols) == len(set(symbols))  # no duplicates
        cvs = next(c for c in prep.shortlist if c.symbol == "CVS")
        assert cvs.score == pytest.approx(0.95)   # kept the highest-scored CVS row


# ---------------------------------------------------------------------------
# Test: conviction bands (score normalized /100)
# ---------------------------------------------------------------------------

class TestConvictionBands:
    def test_high_conviction_at_80(self):
        row = _make_row("X", 80.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].conviction == "high"

    def test_high_conviction_above_80(self):
        row = _make_row("X", 92.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].conviction == "high"

    def test_medium_conviction_at_60(self):
        row = _make_row("X", 60.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].conviction == "medium"

    def test_medium_conviction_between_60_and_80(self):
        row = _make_row("X", 70.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].conviction == "medium"

    def test_low_conviction_below_60(self):
        row = _make_row("X", 40.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].conviction == "low"

    def test_three_rows_correct_bands(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="pre_open",
        )
        convictions = {c.symbol: c.conviction for c in prep.shortlist}
        assert convictions["AAPL"] == "high"
        assert convictions["MSFT"] == "medium"
        assert convictions["GOOG"] == "low"


# ---------------------------------------------------------------------------
# Test: blackout downgrades conviction
# ---------------------------------------------------------------------------

class TestBlackoutDowngrade:
    def test_high_downgraded_to_medium_on_blackout(self):
        row = _make_row("EARN", 85.0)
        tags = {"EARN": _make_catalyst("EARN", earnings_blackout=True)}
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags=tags,
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].conviction == "medium"

    def test_medium_downgraded_to_low_on_blackout(self):
        row = _make_row("EARN", 65.0)
        tags = {"EARN": _make_catalyst("EARN", earnings_blackout=True)}
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags=tags,
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].conviction == "low"

    def test_low_stays_low_on_blackout(self):
        row = _make_row("EARN", 40.0)
        tags = {"EARN": _make_catalyst("EARN", earnings_blackout=True)}
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags=tags,
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].conviction == "low"

    def test_blackout_adds_warning(self):
        row = _make_row("EARN", 85.0)
        tags = {"EARN": _make_catalyst("EARN", earnings_blackout=True)}
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags=tags,
            now_et=_now_et(),
            phase="pre_open",
        )
        candidate = prep.shortlist[0]
        assert len(candidate.warnings) > 0
        assert any("blackout" in w.lower() for w in candidate.warnings)

    def test_no_blackout_no_warning(self):
        row = _make_row("SAFE", 85.0)
        tags = {"SAFE": _make_catalyst("SAFE", earnings_blackout=False)}
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags=tags,
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].warnings == []


# ---------------------------------------------------------------------------
# Test: rr computation
# ---------------------------------------------------------------------------

class TestRiskReward:
    def test_rr_computed(self):
        # entry=100, stop=95, target=115 → rr = (115-100)/(100-95) = 3.0
        row = _make_row("X", 75.0, planned_entry_price=100.0, stop_price=95.0, target_price=115.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].rr == pytest.approx(3.0)

    def test_rr_none_when_entry_missing(self):
        row = _make_row("X", 75.0, planned_entry_price=None, stop_price=95.0, target_price=115.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].rr is None

    def test_rr_none_when_stop_missing(self):
        row = _make_row("X", 75.0, planned_entry_price=100.0, stop_price=None, target_price=115.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].rr is None

    def test_rr_none_when_target_missing(self):
        row = _make_row("X", 75.0, planned_entry_price=100.0, stop_price=95.0, target_price=None)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].rr is None

    def test_rr_none_when_entry_equals_stop(self):
        row = _make_row("X", 75.0, planned_entry_price=100.0, stop_price=100.0, target_price=115.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].rr is None

    def test_rr_none_when_stop_above_entry(self):
        # stop above entry → negative risk → meaningless R:R, degrade to None
        row = _make_row("X", 75.0, planned_entry_price=100.0, stop_price=105.0, target_price=115.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].rr is None


# ---------------------------------------------------------------------------
# Test: to_dict round-trip
# ---------------------------------------------------------------------------

class TestToDict:
    def test_to_dict_keys(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="pre_open",
        )
        d = prep.to_dict()
        expected_keys = {"generated_at", "et_date", "phase", "shortlist",
                         "what_changed_overnight", "plan_for_open"}
        assert set(d.keys()) == expected_keys

    def test_shortlist_item_keys(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="pre_open",
        )
        d = prep.to_dict()
        assert len(d["shortlist"]) == 3
        item = d["shortlist"][0]
        expected_item_keys = {
            "symbol", "score", "setup", "entry", "stop", "target",
            "rr", "conviction", "catalysts", "warnings",
        }
        assert set(item.keys()) == expected_item_keys

    def test_to_dict_json_serializable(self):
        import json
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="pre_open",
        )
        # Must not raise
        result = json.dumps(prep.to_dict())
        assert isinstance(result, str)

    def test_to_dict_phase_preserved(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="overnight",
        )
        assert prep.to_dict()["phase"] == "overnight"

    def test_to_dict_et_date(self):
        now = _now_et()
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=now,
            phase="pre_open",
        )
        assert prep.to_dict()["et_date"] == "2026-06-06"

    def test_to_dict_generated_at_iso(self):
        now = _now_et()
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=now,
            phase="pre_open",
        )
        generated_at = prep.to_dict()["generated_at"]
        # Must be parseable as ISO-8601 with offset
        parsed = datetime.fromisoformat(generated_at)
        assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# Test: empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_rows_empty_shortlist(self):
        prep = build_morning_prep(
            scored_rows=[],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist == []

    def test_empty_rows_no_error(self):
        # Must not raise
        prep = build_morning_prep(
            scored_rows=[],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert isinstance(prep, MorningPrep)

    def test_empty_rows_to_dict_shortlist_empty(self):
        prep = build_morning_prep(
            scored_rows=[],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        d = prep.to_dict()
        assert d["shortlist"] == []


# ---------------------------------------------------------------------------
# Test: what_changed_overnight
# ---------------------------------------------------------------------------

class TestWhatChangedOvernight:
    def test_no_learning_facts_returns_default(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
            learning_facts=None,
        )
        assert prep.what_changed_overnight == "No overnight changes."

    def test_empty_learning_facts_returns_default(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
            learning_facts={},
        )
        assert prep.what_changed_overnight == "No overnight changes."

    def test_learning_facts_produces_summary(self):
        facts = {
            "dimensions": [{"key": "a"}, {"key": "b"}],
            "summary": {"win_rate": 0.55},
        }
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
            learning_facts=facts,
        )
        # Must not be the default "No overnight changes." string
        assert prep.what_changed_overnight != "No overnight changes."
        # Must be deterministic
        prep2 = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
            learning_facts=facts,
        )
        assert prep.what_changed_overnight == prep2.what_changed_overnight

    def test_learning_facts_mentions_lessons_count(self):
        facts = {
            "dimensions": [{"key": "x"}, {"key": "y"}, {"key": "z"}],
            "summary": {"win_rate": 0.6},
        }
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
            learning_facts=facts,
        )
        # Should contain a number (n new lessons)
        assert any(char.isdigit() for char in prep.what_changed_overnight)


# ---------------------------------------------------------------------------
# Test: plan_for_open
# ---------------------------------------------------------------------------

class TestPlanForOpen:
    def test_plan_for_open_format(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="pre_open",
        )
        plan = prep.plan_for_open
        # Should mention count of names
        assert "3 names armed" in plan or "names armed" in plan

    def test_plan_for_open_high_conviction_count(self):
        prep = build_morning_prep(
            scored_rows=ROWS_3,
            catalyst_tags=CATALYST_TAGS_BASIC,
            now_et=_now_et(),
            phase="pre_open",
        )
        plan = prep.plan_for_open
        assert "high-conviction" in plan

    def test_plan_for_open_blackout_count(self):
        rows = ROWS_3 + [_make_row("EARN", 85.0)]
        tags = {**CATALYST_TAGS_BASIC, "EARN": _make_catalyst("EARN", earnings_blackout=True)}
        prep = build_morning_prep(
            scored_rows=rows,
            catalyst_tags=tags,
            now_et=_now_et(),
            phase="pre_open",
        )
        plan = prep.plan_for_open
        assert "earnings blackout" in plan

    def test_plan_for_open_empty_shortlist(self):
        prep = build_morning_prep(
            scored_rows=[],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        plan = prep.plan_for_open
        assert "0 names armed" in plan


# ---------------------------------------------------------------------------
# Test: catalyst attachment
# ---------------------------------------------------------------------------

class TestCatalystAttachment:
    def test_catalyst_dict_attached_when_present(self):
        prep = build_morning_prep(
            scored_rows=[_make_row("AAPL", 80.0)],
            catalyst_tags={"AAPL": _make_catalyst("AAPL")},
            now_et=_now_et(),
            phase="pre_open",
        )
        c = prep.shortlist[0]
        assert isinstance(c.catalysts, dict)
        assert c.catalysts.get("symbol") == "AAPL"

    def test_empty_dict_when_no_catalyst(self):
        prep = build_morning_prep(
            scored_rows=[_make_row("AAPL", 80.0)],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].catalysts == {}


# ---------------------------------------------------------------------------
# Test: score stored normalized (0-1)
# ---------------------------------------------------------------------------

class TestScoreNormalization:
    def test_score_stored_as_0_to_1(self):
        row = _make_row("X", 75.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].score == pytest.approx(0.75)

    def test_score_boundary_100(self):
        row = _make_row("X", 100.0)
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test: missing/malformed fields degrade gracefully
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_missing_total_score_treated_as_zero(self):
        row = {"symbol": "X", "setup_category": "test"}  # no total_score
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        assert prep.shortlist[0].score == 0.0

    def test_missing_price_levels_rr_none(self):
        row = {"symbol": "X", "total_score": 75.0, "setup_category": "test"}
        prep = build_morning_prep(
            scored_rows=[row],
            catalyst_tags={},
            now_et=_now_et(),
            phase="pre_open",
        )
        c = prep.shortlist[0]
        assert c.entry is None
        assert c.stop is None
        assert c.target is None
        assert c.rr is None
