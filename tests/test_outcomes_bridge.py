"""Tests for vault/outcomes_bridge.py — resolved-outcome emitter for the Command Center.

Emits reports/tony_stocks_outcomes.json so the Command Center can grade Tony's
verdicts. Research only: reads resolved outcome records, writes JSON. No trading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_bot.vault.outcomes_bridge import build_tony_outcomes, write_tony_outcomes

EOD = "2026-06-02"

# Output schema keys required on every emitted object.
SCHEMA_KEYS = {
    "symbol",
    "pick_date",
    "result",
    "entry",
    "exit",
    "return_pct",
    "days_held",
    "resolved_date",
}


class TestBuildSchema:
    def test_emits_one_object_per_resolved_record_with_full_schema(self):
        records = [
            {
                "symbol": "ORCL",
                "result": "target_hit",
                "pick_date": "2026-05-30",
                "entry": 120.0,
                "exit": 126.0,
                "return_pct": 5.0,
                "days_held": 3,
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert len(out) == 1
        assert set(out[0].keys()) == SCHEMA_KEYS
        assert out[0]["symbol"] == "ORCL"
        assert out[0]["result"] == "target_hit"
        assert out[0]["entry"] == 120.0
        assert out[0]["exit"] == 126.0
        assert out[0]["return_pct"] == 5.0
        assert out[0]["days_held"] == 3

    def test_empty_records_returns_empty_list(self):
        assert build_tony_outcomes([], eod_date=EOD) == []

    def test_resolved_date_defaults_to_eod_date(self):
        records = [{"symbol": "AAA", "result": "target_hit", "pick_date": "2026-06-01"}]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["resolved_date"] == EOD

    def test_explicit_resolved_date_is_preserved(self):
        records = [
            {
                "symbol": "AAA",
                "result": "stop_hit",
                "pick_date": "2026-06-01",
                "resolved_date": "2026-06-01",
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["resolved_date"] == "2026-06-01"


class TestResultNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("target_hit", "target_hit"),
            ("target_before_stop", "target_hit"),
            ("stop_hit", "stop_hit"),
            ("stop_before_target", "stop_hit"),
            ("failed_setup", "stop_hit"),
            ("expired_no_trigger", "expired"),
            ("entry_not_triggered", "expired"),
            ("partial_move", "closed"),
            ("invalidated", "closed"),
            ("closed", "closed"),
        ],
    )
    def test_result_maps_to_one_of_four_terminal_buckets(self, raw, expected):
        records = [{"symbol": "AAA", "result": raw, "pick_date": "2026-06-01"}]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert len(out) == 1
        assert out[0]["result"] == expected

    @pytest.mark.parametrize(
        "raw",
        ["still_open", "insufficient_future_data", "active", "missing_real_data", ""],
    )
    def test_non_terminal_records_are_skipped(self, raw):
        records = [{"symbol": "AAA", "result": raw, "pick_date": "2026-06-01"}]
        assert build_tony_outcomes(records, eod_date=EOD) == []

    def test_result_read_from_outcome_label_when_result_absent(self):
        records = [
            {"symbol": "AAA", "outcome_label": "target_hit", "pick_date": "2026-06-01"}
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["result"] == "target_hit"

    def test_result_read_from_tracking_status_fallback(self):
        records = [
            {"symbol": "AAA", "tracking_status": "stop_hit", "pick_date": "2026-06-01"}
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["result"] == "stop_hit"


class TestFieldFallbacks:
    def test_return_pct_falls_back_to_pl_pct(self):
        records = [
            {
                "symbol": "AAA",
                "result": "target_hit",
                "pick_date": "2026-06-01",
                "pl_pct": 3.3,
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["return_pct"] == 3.3

    def test_return_pct_falls_back_to_terminal_research_pl_pct(self):
        records = [
            {
                "symbol": "AAA",
                "result": "stop_hit",
                "pick_date": "2026-06-01",
                "terminal_research_pl_pct": -2.1,
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["return_pct"] == -2.1

    def test_entry_falls_back_to_original_then_actual_entry_price(self):
        records = [
            {
                "symbol": "AAA",
                "result": "target_hit",
                "pick_date": "2026-06-01",
                "original_entry_price": 50.0,
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["entry"] == 50.0

    def test_exit_falls_back_to_terminal_exit_price(self):
        records = [
            {
                "symbol": "AAA",
                "result": "target_hit",
                "pick_date": "2026-06-01",
                "terminal_exit_price": 55.0,
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["exit"] == 55.0

    def test_missing_numeric_fields_become_none(self):
        records = [{"symbol": "AAA", "result": "closed", "pick_date": "2026-06-01"}]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["entry"] is None
        assert out[0]["exit"] is None
        assert out[0]["return_pct"] is None
        assert out[0]["days_held"] is None

    def test_symbol_is_uppercased(self):
        records = [{"symbol": "aaa", "result": "target_hit", "pick_date": "2026-06-01"}]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["symbol"] == "AAA"


class TestPickDateDerivation:
    """pick_date MUST be the originating bridge date (day-1 of days_active), never entry_date."""

    def test_explicit_pick_date_wins(self):
        records = [
            {
                "symbol": "AAA",
                "result": "target_hit",
                "pick_date": "2026-05-28",
                "entry_date": "2026-05-30",
                "days_active": 3,
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["pick_date"] == "2026-05-28"

    def test_pick_id_supplies_date_when_pick_date_absent(self):
        records = [
            {
                "symbol": "AAA",
                "result": "target_hit",
                "pick_id": "AAA-2026-05-27",
                "entry_date": "2026-05-30",
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["pick_date"] == "2026-05-27"

    def test_first_seen_used_when_no_pick_date_or_id(self):
        records = [
            {
                "symbol": "AAA",
                "result": "target_hit",
                "first_seen": "2026-05-26T14:30:00+00:00",
                "entry_date": "2026-05-30",
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["pick_date"] == "2026-05-26"

    def test_derived_from_entry_date_minus_days_active(self):
        # entry on the 30th, active for 3 distinct days => first appeared on the 28th.
        records = [
            {
                "symbol": "AAA",
                "result": "target_hit",
                "entry_date": "2026-05-30",
                "days_active": 3,
            }
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["pick_date"] == "2026-05-28"

    def test_falls_back_to_entry_date_when_nothing_else_available(self):
        records = [
            {"symbol": "AAA", "result": "target_hit", "entry_date": "2026-05-30"}
        ]
        out = build_tony_outcomes(records, eod_date=EOD)
        assert out[0]["pick_date"] == "2026-05-30"


class TestWriteTonyOutcomes:
    def test_writes_explicit_path_as_json_list(self, tmp_path):
        built = [
            {
                "symbol": "ORCL",
                "pick_date": "2026-05-30",
                "result": "target_hit",
                "entry": 120.0,
                "exit": 126.0,
                "return_pct": 5.0,
                "days_held": 3,
                "resolved_date": EOD,
            }
        ]
        out_path = tmp_path / "custom_outcomes.json"
        written = write_tony_outcomes(built, path=out_path)
        assert Path(written) == out_path
        loaded = json.loads(out_path.read_text(encoding="utf-8"))
        assert loaded == built

    def test_default_path_is_reports_tony_stocks_outcomes(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TONY_OUTCOMES_FILE", raising=False)
        monkeypatch.chdir(tmp_path)
        written = write_tony_outcomes([])
        assert Path(written) == tmp_path / "reports" / "tony_stocks_outcomes.json"
        assert (tmp_path / "reports" / "tony_stocks_outcomes.json").exists()

    def test_env_var_overrides_default_path(self, tmp_path, monkeypatch):
        target = tmp_path / "env_dir" / "outcomes.json"
        monkeypatch.setenv("TONY_OUTCOMES_FILE", str(target))
        written = write_tony_outcomes([{"symbol": "AAA"}])
        assert Path(written) == target
        assert json.loads(target.read_text(encoding="utf-8")) == [{"symbol": "AAA"}]

    def test_explicit_path_overrides_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TONY_OUTCOMES_FILE", str(tmp_path / "env.json"))
        explicit = tmp_path / "explicit.json"
        write_tony_outcomes([], path=explicit)
        assert explicit.exists()
        assert not (tmp_path / "env.json").exists()

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c" / "outcomes.json"
        write_tony_outcomes([], path=nested)
        assert nested.exists()


class TestAccumulation:
    """write_tony_outcomes accumulates by default so a thin/empty emit never wipes history."""

    def _built(self, symbol, pick_date, result, ret):
        return build_tony_outcomes(
            [
                {
                    "symbol": symbol,
                    "result": result,
                    "pick_date": pick_date,
                    "return_pct": ret,
                }
            ],
            eod_date=EOD,
        )

    def test_thin_emit_never_wipes_existing(self, tmp_path):
        p = tmp_path / "outcomes.json"
        write_tony_outcomes(
            self._built("AAA", "2026-06-01", "target_hit", 5.0)
            + self._built("BBB", "2026-06-02", "stop_hit", -3.0),
            path=p,
        )
        write_tony_outcomes(
            [], path=p
        )  # a run that resolved nothing must NOT wipe the file
        kept = {
            (o["symbol"], o["pick_date"])
            for o in json.loads(p.read_text(encoding="utf-8"))
        }
        assert kept == {("AAA", "2026-06-01"), ("BBB", "2026-06-02")}

    def test_union_adds_new_and_newer_resolution_wins(self, tmp_path):
        p = tmp_path / "outcomes.json"
        write_tony_outcomes(self._built("AAA", "2026-06-01", "stop_hit", -2.0), path=p)
        write_tony_outcomes(
            self._built(
                "AAA", "2026-06-01", "target_hit", 6.0
            )  # same pick, corrected outcome
            + self._built("CCC", "2026-06-03", "target_hit", 4.0),
            path=p,
        )
        kept = {
            (o["symbol"], o["pick_date"]): o
            for o in json.loads(p.read_text(encoding="utf-8"))
        }
        assert set(kept) == {("AAA", "2026-06-01"), ("CCC", "2026-06-03")}
        assert kept[("AAA", "2026-06-01")]["result"] == "target_hit"  # newer wins
        assert kept[("AAA", "2026-06-01")]["return_pct"] == 6.0

    def test_merge_false_overwrites_exactly(self, tmp_path):
        p = tmp_path / "outcomes.json"
        write_tony_outcomes(self._built("AAA", "2026-06-01", "target_hit", 5.0), path=p)
        write_tony_outcomes([], path=p, merge=False)
        assert json.loads(p.read_text(encoding="utf-8")) == []
