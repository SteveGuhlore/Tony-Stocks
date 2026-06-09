"""Tests for the Tony teaching / divergence memory layer (roadmap item 4).

Pure + deterministic: synthetic (verdict, outcome) pairs -> correct quadrant tallies.
Research only; reasoning is preserved verbatim and graded against real outcomes.
"""
from __future__ import annotations

import json

from trading_bot.analytics.tony_divergence import (
    TeachingRecord,
    build_tony_divergence,
    teaching_log_path,
    write_divergence_ledger,
)


def _verdict(symbol, date, verdict, thesis="because reasons", score=70.0):
    return {"symbol": symbol, "date": date, "verdict": verdict, "thesis": thesis, "tony_score": score}


def _outcome(symbol, pick_date, result, return_pct=None):
    return {"symbol": symbol, "pick_date": pick_date, "result": result, "return_pct": return_pct}


def _by_symbol(ledger):
    return {r.symbol: r for r in ledger.records}


class TestClassification:
    def test_reaffirm_win_is_agreed_right(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "reaffirm")],
            [_outcome("AAA", "2026-06-01", "target_hit", 8.0)],
        )
        assert _by_symbol(led)["AAA"].classification == "agreed_right"

    def test_reaffirm_loss_is_agreed_wrong(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "reaffirm")],
            [_outcome("AAA", "2026-06-01", "stop_hit", -3.0)],
        )
        assert _by_symbol(led)["AAA"].classification == "agreed_wrong"

    def test_override_on_loser_is_cc_overrode_saved(self):
        # Tony said get out; the bot held and lost -> Tony's override would have saved us.
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "override")],
            [_outcome("AAA", "2026-06-01", "stop_hit", -4.0)],
        )
        assert _by_symbol(led)["AAA"].classification == "cc_overrode_saved"

    def test_override_on_winner_is_cc_overrode_missed(self):
        # Tony said get out; the bot held and won -> Tony's override would have missed it.
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "override")],
            [_outcome("AAA", "2026-06-01", "target_hit", 9.0)],
        )
        assert _by_symbol(led)["AAA"].classification == "cc_overrode_missed"

    def test_close_and_adjust_are_divergent(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "close"), _verdict("BBB", "2026-06-01", "adjust")],
            [_outcome("AAA", "2026-06-01", "stop_hit", -2.0),
             _outcome("BBB", "2026-06-01", "target_hit", 5.0)],
        )
        by = _by_symbol(led)
        assert by["AAA"].classification == "cc_overrode_saved"   # diverge + loss
        assert by["BBB"].classification == "cc_overrode_missed"  # diverge + win

    def test_unknown_verdict_defaults_to_agreement(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "pass")],
            [_outcome("AAA", "2026-06-01", "target_hit", 4.0)],
        )
        assert _by_symbol(led)["AAA"].classification == "agreed_right"

    def test_closed_outcome_uses_return_sign(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "reaffirm"), _verdict("BBB", "2026-06-01", "reaffirm")],
            [_outcome("AAA", "2026-06-01", "closed", 1.5),
             _outcome("BBB", "2026-06-01", "closed", -1.5)],
        )
        by = _by_symbol(led)
        assert by["AAA"].classification == "agreed_right"
        assert by["BBB"].classification == "agreed_wrong"


class TestJoinAndPending:
    def test_verdict_without_outcome_is_pending(self):
        led = build_tony_divergence([_verdict("AAA", "2026-06-01", "reaffirm")], [])
        assert _by_symbol(led)["AAA"].classification == "pending"

    def test_join_is_on_symbol_and_pick_date(self):
        # Outcome date doesn't match the verdict date -> no join -> pending.
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "reaffirm")],
            [_outcome("AAA", "2026-06-02", "target_hit", 8.0)],
        )
        assert _by_symbol(led)["AAA"].classification == "pending"

    def test_unresolved_outcome_without_return_is_pending(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "reaffirm")],
            [_outcome("AAA", "2026-06-01", "still_open", None)],
        )
        assert _by_symbol(led)["AAA"].classification == "pending"


class TestReasoningAndIds:
    def test_reasoning_preserved_verbatim(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "override", thesis="momentum fading into earnings")],
            [_outcome("AAA", "2026-06-01", "stop_hit", -2.0)],
        )
        rec = _by_symbol(led)["AAA"]
        assert rec.tony_reasoning == "momentum fading into earnings"
        assert rec.verdict == "override"
        assert rec.return_pct == -2.0

    def test_pick_id_is_symbol_and_date(self):
        led = build_tony_divergence(
            [_verdict("aaa", "2026-06-01", "reaffirm")],
            [_outcome("AAA", "2026-06-01", "target_hit", 3.0)],
        )
        assert _by_symbol(led)["AAA"].pick_id == "AAA-2026-06-01"

    def test_bot_action_from_bot_picks(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "reaffirm")],
            [_outcome("AAA", "2026-06-01", "target_hit", 3.0)],
            bot_picks=[{"symbol": "AAA", "pick_date": "2026-06-01", "action": "entered",
                        "rationale": "breakout"}],
        )
        rec = _by_symbol(led)["AAA"]
        assert rec.bot_action == "entered"
        assert rec.bot_rationale == "breakout"


class TestLedgerTallies:
    def test_agreement_dict_counts_quadrants(self):
        verdicts = [
            _verdict("AR", "2026-06-01", "reaffirm"), _verdict("AW", "2026-06-01", "reaffirm"),
            _verdict("OS", "2026-06-01", "override"), _verdict("OM", "2026-06-01", "override"),
            _verdict("PEND", "2026-06-01", "reaffirm"),
        ]
        outcomes = [
            _outcome("AR", "2026-06-01", "target_hit", 5.0),
            _outcome("AW", "2026-06-01", "stop_hit", -5.0),
            _outcome("OS", "2026-06-01", "stop_hit", -5.0),
            _outcome("OM", "2026-06-01", "target_hit", 5.0),
        ]
        led = build_tony_divergence(verdicts, outcomes)
        agr = led.agreement_dict()
        assert agr == {
            "agreed_right": 1, "agreed_wrong": 1,
            "cc_overrode_saved": 1, "cc_overrode_missed": 1,
        }
        assert led.tallies["pending"] == 1

    def test_to_dict_is_research_only_and_lists_records(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "reaffirm")],
            [_outcome("AAA", "2026-06-01", "target_hit", 5.0)],
        )
        d = led.to_dict()
        assert d["research_only"] is True
        assert d["tallies"]["agreed_right"] == 1
        assert len(d["records"]) == 1
        assert d["records"][0]["symbol"] == "AAA"


class TestPersistence:
    def test_write_round_trips_agreement_and_records(self, tmp_path):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-01", "override", thesis="overbought")],
            [_outcome("AAA", "2026-06-01", "stop_hit", -3.0)],
        )
        path = tmp_path / "teaching.json"
        write_divergence_ledger(led, path)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["research_only"] is True
        assert data["agreement"]["cc_overrode_saved"] == 1
        assert data["records"][0]["tony_reasoning"] == "overbought"

    def test_teaching_log_path_honors_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TONY_TEACHING_FILE", str(tmp_path / "custom.json"))
        assert teaching_log_path() == tmp_path / "custom.json"
        monkeypatch.delenv("TONY_TEACHING_FILE")
        assert teaching_log_path().name == "tony_teaching_log.json"


# --- regression: verdict REVIEW-date vs outcome PICK-date join (was all-pending) ---

def test_join_grades_verdict_against_prior_pick_date():
    """Verdicts carry Tony's REVIEW date; outcomes a (different, earlier) pick_date. The
    join must match by symbol + latest pick on-or-before the verdict, not require equal
    dates — a date-equality join falsely marked every verdict 'pending'."""
    verdicts = [_verdict("AAPL", "2026-06-05", "reaffirm")]
    outcomes = [{"symbol": "AAPL", "pick_date": "2026-05-18", "result": "target_hit", "return_pct": 9.0}]
    rec = build_tony_divergence(verdicts, outcomes).records[0]
    assert rec.classification == "agreed_right"  # reaffirm + a win
    assert rec.result == "target_hit"
    assert rec.pick_date == "2026-05-18"  # matched the reviewed pick


def test_join_ignores_outcomes_after_the_verdict():
    verdicts = [_verdict("MSFT", "2026-06-01", "reaffirm")]
    outcomes = [{"symbol": "MSFT", "pick_date": "2026-06-10", "result": "target_hit"}]
    assert build_tony_divergence(verdicts, outcomes).records[0].classification == "pending"


def test_latest_verdict_per_symbol_graded_once():
    verdicts = [_verdict("NVDA", "2026-06-01", "reaffirm"), _verdict("NVDA", "2026-06-05", "override")]
    outcomes = [{"symbol": "NVDA", "pick_date": "2026-05-20", "result": "target_hit"}]
    recs = build_tony_divergence(verdicts, outcomes).records
    assert len(recs) == 1                                 # one record per symbol (latest stance)
    assert recs[0].verdict == "override"
    assert recs[0].classification == "cc_overrode_missed"  # overrode a winner -> missed


class TestMalformedInputs:
    """Error/edge: the verdicts file is written by the CC and the outcomes come from the
    DB — junk rows must be skipped or held pending, never crash the nightly regrade."""

    def test_rows_missing_symbol_or_date_are_skipped(self):
        led = build_tony_divergence(
            [{"verdict": "close"}, {"symbol": "", "date": "2026-06-01", "verdict": "close"},
             {"symbol": "AAA", "verdict": "close"}, _verdict("BBB", "2026-06-01", "reaffirm")],
            [{"pick_date": "2026-06-01", "result": "target_hit"},      # no symbol
             {"symbol": "BBB", "result": "target_hit"},                 # no pick_date
             _outcome("BBB", "2026-06-01", "target_hit", 5.0)],
        )
        assert {r.symbol for r in led.records} == {"BBB"}
        assert _by_symbol(led)["BBB"].classification == "agreed_right"

    def test_nan_return_pct_stays_pending(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-02", "reaffirm")],
            [_outcome("AAA", "2026-06-01", "still_open", float("nan"))],
        )
        assert _by_symbol(led)["AAA"].classification == "pending"
        assert _by_symbol(led)["AAA"].return_pct is None

    def test_unknown_result_with_signed_return_grades_by_return(self):
        led = build_tony_divergence(
            [_verdict("AAA", "2026-06-02", "reaffirm"), _verdict("BBB", "2026-06-02", "override")],
            [_outcome("AAA", "2026-06-01", "time_exit", 3.5),
             _outcome("BBB", "2026-06-01", "time_exit", -2.0)],
        )
        assert _by_symbol(led)["AAA"].classification == "agreed_right"
        assert _by_symbol(led)["BBB"].classification == "cc_overrode_saved"

    def test_verdict_before_any_outcome_is_pending(self):
        # Tony reviewed the name BEFORE the bot ever picked it — nothing to grade against.
        led = build_tony_divergence(
            [_verdict("AAA", "2026-05-01", "reaffirm")],
            [_outcome("AAA", "2026-06-01", "target_hit", 5.0)],
        )
        assert _by_symbol(led)["AAA"].classification == "pending"

    def test_empty_and_none_inputs(self):
        assert build_tony_divergence([], []).records == []
        assert build_tony_divergence(None, None).records == []
