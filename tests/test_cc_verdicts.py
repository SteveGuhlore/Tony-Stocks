"""Tests for reading Command Center verdicts (the bot side of the CC-exit loop).

The CC writes reports/tony_stocks_verdicts.json; the bot reads it and feeds 'close'
verdicts into the paper engine's CC-exit hook. Tolerant of a few JSON shapes.
"""
from __future__ import annotations

import json

from trading_bot.execution.cc_verdicts import cc_exit_symbols, load_cc_verdicts


def _write(tmp_path, payload):
    p = tmp_path / "tony_stocks_verdicts.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class TestLoad:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_cc_verdicts(tmp_path / "nope.json") == []

    def test_list_of_verdicts(self, tmp_path):
        p = _write(tmp_path, [{"symbol": "ZETA", "verdict": "close"}, {"symbol": "NVDA", "verdict": "reaffirm"}])
        rows = load_cc_verdicts(p)
        assert {r["symbol"] for r in rows} == {"ZETA", "NVDA"}

    def test_wrapped_verdicts_key(self, tmp_path):
        p = _write(tmp_path, {"verdicts": [{"symbol": "ZETA", "verdict": "close"}]})
        assert load_cc_verdicts(p)[0]["symbol"] == "ZETA"

    def test_dict_keyed_by_symbol(self, tmp_path):
        p = _write(tmp_path, {"ZETA": {"verdict": "close"}, "NVDA": {"verdict": "adjust"}})
        rows = load_cc_verdicts(p)
        assert {r["symbol"] for r in rows} == {"ZETA", "NVDA"}

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        assert load_cc_verdicts(p) == []


class TestExitSymbols:
    def test_close_verdict_is_exit(self):
        assert cc_exit_symbols([{"symbol": "ZETA", "verdict": "close"}]) == {"ZETA"}

    def test_reaffirm_and_adjust_are_not_exits(self):
        verdicts = [{"symbol": "ZETA", "verdict": "reaffirm"}, {"symbol": "NVDA", "verdict": "adjust"}]
        assert cc_exit_symbols(verdicts) == set()

    def test_sell_or_exit_action_counts(self):
        verdicts = [{"symbol": "AAA", "recommended_action": "sell now"},
                    {"symbol": "BBB", "action": "exit"}]
        assert cc_exit_symbols(verdicts) == {"AAA", "BBB"}

    def test_explicit_exit_flag(self):
        assert cc_exit_symbols([{"symbol": "ZETA", "verdict": "override", "exit": True}]) == {"ZETA"}

    def test_symbol_uppercased_and_blank_skipped(self):
        assert cc_exit_symbols([{"symbol": "zeta", "verdict": "close"}, {"verdict": "close"}]) == {"ZETA"}

    def test_empty_input(self):
        assert cc_exit_symbols([]) == set()
        assert cc_exit_symbols(None) == set()


class TestExitTextEdges:
    """Word-boundary + negation guard: prose in a verdict field must not flatten a
    position it didn't ask to flatten (substring matching did: 'disclosed' ⊃ 'close')."""

    def test_substring_inside_word_is_not_exit(self):
        verdicts = [{"symbol": "AAA", "action": "risk disclosed in 10-K"},
                    {"symbol": "BBB", "decision": "florexit catalyst watch"}]
        assert cc_exit_symbols(verdicts) == set()

    def test_negated_exit_is_not_exit(self):
        verdicts = [{"symbol": "AAA", "action": "do not sell"},
                    {"symbol": "BBB", "action": "don't exit yet"},
                    {"symbol": "CCC", "recommended_action": "hold, never close early"},
                    {"symbol": "DDD", "decision": "avoid selling here"}]
        assert cc_exit_symbols(verdicts) == set()

    def test_plain_exit_words_still_count(self):
        verdicts = [{"symbol": "AAA", "action": "sell now"},
                    {"symbol": "BBB", "verdict": "close"},
                    {"symbol": "CCC", "action": "flatten the position"},
                    {"symbol": "DDD", "recommended_action": "liquidate"},
                    {"symbol": "EEE", "verdict": "closed"}]
        assert cc_exit_symbols(verdicts) == {"AAA", "BBB", "CCC", "DDD", "EEE"}

    def test_get_out_bigram(self):
        assert cc_exit_symbols([{"symbol": "AAA", "action": "get out now"}]) == {"AAA"}
        assert cc_exit_symbols([{"symbol": "AAA", "action": "don't get out"}]) == set()
        assert cc_exit_symbols([{"symbol": "AAA", "verdict": "get_out"}]) == {"AAA"}

    def test_explicit_exit_flag_beats_negated_text(self):
        # The boolean channel is unambiguous — text never overrides it.
        verdicts = [{"symbol": "AAA", "exit": True, "action": "do not sell"}]
        assert cc_exit_symbols(verdicts) == {"AAA"}
