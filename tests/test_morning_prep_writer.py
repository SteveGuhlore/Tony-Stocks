"""Tests for vault/morning_prep_writer.py — TDD Step 1 (failing tests).

Tests verify:
- render_morning_prep_markdown produces PLANNED disclaimer + wikilinks + table
- write_morning_prep_note writes morning_prep/<date>.md under vault_dir
- write_morning_prep_report writes <date>.json and <date>.md under reports_dir/morning_prep/
- write_morning_prep_bridge writes under bridge/tony-stocks/morning-prep/<date>.md or returns None
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from trading_bot.analytics.morning_prep import MorningPrep, build_morning_prep
from trading_bot.vault.morning_prep_writer import (
    render_morning_prep_markdown,
    write_morning_prep_note,
    write_morning_prep_bridge,
    write_morning_prep_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ET = timezone(timedelta(hours=-4))  # EDT (June is daylight time in ET)


def _make_prep(date_str: str = "2026-06-07", n_candidates: int = 2) -> MorningPrep:
    """Build a MorningPrep with deterministic data."""
    rows = []
    if n_candidates > 0:
        rows = [
            {
                "symbol": "AAPL",
                "total_score": 85.0,
                "setup_category": "Momentum / Buy",
                "planned_entry_price": 190.0,
                "stop_price": 185.0,
                "target_price": 200.0,
            },
            {
                "symbol": "MSTR",
                "total_score": 72.0,
                "setup_category": "Breakout",
                "planned_entry_price": 300.0,
                "stop_price": 290.0,
                "target_price": 320.0,
            },
        ][:n_candidates]

    # naive datetime in ET
    dt = datetime(2026, 6, 7, 4, 30, 0, tzinfo=_ET)
    return build_morning_prep(
        scored_rows=rows,
        catalyst_tags={},
        now_et=dt,
        phase="pre_open",
    )


def _make_prep_empty() -> MorningPrep:
    """Build a MorningPrep with no shortlist candidates."""
    dt = datetime(2026, 6, 7, 4, 30, 0, tzinfo=_ET)
    return build_morning_prep(
        scored_rows=[],
        catalyst_tags={},
        now_et=dt,
        phase="overnight",
    )


# ---------------------------------------------------------------------------
# render_morning_prep_markdown
# ---------------------------------------------------------------------------

class TestRenderMorningPrepMarkdown:
    def test_contains_planned_disclaimer(self):
        prep = _make_prep()
        md = render_morning_prep_markdown(prep)
        # Must contain "PLANNED" (case-insensitive partial match)
        assert "PLANNED" in md.upper()

    def test_disclaimer_is_explicit_no_orders(self):
        """Disclaimer must reinforce no off-hours execution."""
        prep = _make_prep()
        md = render_morning_prep_markdown(prep)
        # Must mention both "PLANNED" and something about no orders / off-hours
        upper = md.upper()
        assert "PLANNED" in upper
        assert "ORDER" in upper or "OFF-HOURS" in upper or "NO ORDERS" in upper

    def test_contains_et_date_in_header(self):
        prep = _make_prep()
        md = render_morning_prep_markdown(prep)
        assert prep.et_date in md

    def test_contains_phase_in_header(self):
        prep = _make_prep()
        md = render_morning_prep_markdown(prep)
        assert prep.phase in md

    def test_symbols_as_obsidian_wikilinks(self):
        prep = _make_prep()
        md = render_morning_prep_markdown(prep)
        assert "[[AAPL]]" in md
        assert "[[MSTR]]" in md

    def test_shortlist_table_columns_present(self):
        prep = _make_prep()
        md = render_morning_prep_markdown(prep)
        # Table should have these column headers
        for col in ("symbol", "score", "setup", "entry", "stop", "target", "rr",
                    "conviction", "catalysts"):
            assert col.lower() in md.lower(), f"Column '{col}' not found in markdown"

    def test_what_changed_overnight_section(self):
        prep = _make_prep()
        md = render_morning_prep_markdown(prep)
        assert prep.what_changed_overnight in md

    def test_plan_for_open_section(self):
        prep = _make_prep()
        md = render_morning_prep_markdown(prep)
        assert prep.plan_for_open in md

    def test_narrative_appended_when_provided(self):
        prep = _make_prep()
        narrative = "This is my custom narrative analysis."
        md = render_morning_prep_markdown(prep, narrative=narrative)
        assert narrative in md

    def test_narrative_absent_when_none(self):
        prep = _make_prep()
        md = render_morning_prep_markdown(prep, narrative=None)
        # No narrative block at all — just check there's no crash and it's a string
        assert isinstance(md, str)

    def test_empty_shortlist_handled_gracefully(self):
        prep = _make_prep_empty()
        md = render_morning_prep_markdown(prep)
        assert isinstance(md, str)
        # Should still have disclaimer and header
        assert "PLANNED" in md.upper()
        assert prep.et_date in md


# ---------------------------------------------------------------------------
# write_morning_prep_note
# ---------------------------------------------------------------------------

class TestWriteMorningPrepNote:
    def test_writes_to_correct_path(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_note(prep, vault_dir=tmp_path)
        expected = tmp_path / "morning_prep" / f"{prep.et_date}.md"
        assert p == expected

    def test_file_exists_and_nonempty(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_note(prep, vault_dir=tmp_path)
        assert p.exists()
        assert p.stat().st_size > 0

    def test_file_is_utf8_and_contains_date(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_note(prep, vault_dir=tmp_path)
        body = p.read_text(encoding="utf-8")
        assert prep.et_date in body

    def test_returns_path_object(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_note(prep, vault_dir=tmp_path)
        assert isinstance(p, Path)

    def test_creates_parent_dirs(self, tmp_path):
        prep = _make_prep()
        vault = tmp_path / "deep" / "vault"
        p = write_morning_prep_note(prep, vault_dir=vault)
        assert p.exists()

    def test_narrative_passed_through(self, tmp_path):
        prep = _make_prep()
        narrative = "Unique narrative token XYZZY99"
        p = write_morning_prep_note(prep, vault_dir=tmp_path, narrative=narrative)
        body = p.read_text(encoding="utf-8")
        assert "XYZZY99" in body


# ---------------------------------------------------------------------------
# write_morning_prep_report
# ---------------------------------------------------------------------------

class TestWriteMorningPrepReport:
    def test_returns_path_to_json(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_report(prep, reports_dir=tmp_path)
        assert isinstance(p, Path)
        assert p.suffix == ".json"

    def test_json_path_correct(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_report(prep, reports_dir=tmp_path)
        expected = tmp_path / "morning_prep" / f"{prep.et_date}.json"
        assert p == expected

    def test_json_is_valid_and_matches_to_dict(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_report(prep, reports_dir=tmp_path)
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert data == prep.to_dict()

    def test_md_file_also_written(self, tmp_path):
        prep = _make_prep()
        write_morning_prep_report(prep, reports_dir=tmp_path)
        md_path = tmp_path / "morning_prep" / f"{prep.et_date}.md"
        assert md_path.exists()
        body = md_path.read_text(encoding="utf-8")
        assert "PLANNED" in body.upper()

    def test_creates_parent_dirs(self, tmp_path):
        prep = _make_prep()
        reports = tmp_path / "nested" / "reports"
        p = write_morning_prep_report(prep, reports_dir=reports)
        assert p.exists()

    def test_json_is_utf8(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_report(prep, reports_dir=tmp_path)
        # Should read as UTF-8 without error
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "et_date" in data


# ---------------------------------------------------------------------------
# write_morning_prep_bridge
# ---------------------------------------------------------------------------

class TestWriteMorningPrepBridge:
    def test_returns_none_when_command_center_dir_is_none(self):
        prep = _make_prep()
        result = write_morning_prep_bridge(prep, command_center_dir=None)
        assert result is None

    def test_writes_to_correct_path(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_bridge(prep, command_center_dir=tmp_path)
        expected = (tmp_path / "bridge" / "tony-stocks" / "morning-prep"
                    / f"{prep.et_date}.md")
        assert p == expected

    def test_file_exists_and_contains_disclaimer(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_bridge(prep, command_center_dir=tmp_path)
        assert p.exists()
        body = p.read_text(encoding="utf-8")
        assert "PLANNED" in body.upper()

    def test_returns_path_object(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_bridge(prep, command_center_dir=tmp_path)
        assert isinstance(p, Path)

    def test_creates_parent_dirs(self, tmp_path):
        prep = _make_prep()
        cc = tmp_path / "deep" / "cc"
        p = write_morning_prep_bridge(prep, command_center_dir=cc)
        assert p.exists()

    def test_narrative_included_in_bridge(self, tmp_path):
        prep = _make_prep()
        narrative = "Bridge narrative token BRIDGE42"
        p = write_morning_prep_bridge(prep, command_center_dir=tmp_path,
                                      narrative=narrative)
        body = p.read_text(encoding="utf-8")
        assert "BRIDGE42" in body

    def test_symbols_wikilinked_in_bridge(self, tmp_path):
        prep = _make_prep()
        p = write_morning_prep_bridge(prep, command_center_dir=tmp_path)
        body = p.read_text(encoding="utf-8")
        assert "[[AAPL]]" in body
        assert "[[MSTR]]" in body
