"""Tier-3 contract-drift guard — freeze the cross-process schemas between the
trading bot and the Command Center ("Tony Stocks") agent.

These tests are intentionally STRUCTURAL: they assert the required keys + types
(and, for the bridge markdown, the required section headers) of every payload
that crosses the bot↔CC boundary. If a future code change renames or drops a
field that the Command Center parses, ONE of these tests fails with an explicit
"contract: key X of type Y is required" message — turning a silent 2nd-layer
integration break into a loud test failure.

Scope (one block per frozen schema):
  1. ``tony_stocks_outcomes.json`` records  (build_tony_outcomes)            — bot → CC
  2. The bridge markdown export sections     (write_bridge_export)            — bot → CC
  3. ``tony_stocks_verdicts.json``           (cc_verdicts + build_picks)      — CC → bot
  4. ``tony_stocks_record.json``             (build_record / build_agreement) — CC → bot
  5. The Tony divergence / teaching-log shape (build_tony_divergence)         — bot internal,
     consumed by the CC-agreement fallback mapper

We freeze to the CODE (current behavior), not the docs. Any doc discrepancy is
noted in a comment next to the relevant assertion.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from trading_bot.analytics.tony_divergence import build_tony_divergence
from trading_bot.api.routes.command_center import (
    build_agreement,
    build_agreement_from_teaching,
    build_picks,
    build_record,
)
from trading_bot.execution.cc_verdicts import cc_exit_symbols, load_cc_verdicts
from trading_bot.vault.bridge import write_bridge_export
from trading_bot.vault.outcomes_bridge import build_tony_outcomes


# ── Small structural assertion helpers ────────────────────────────────────────

def _assert_key(obj: dict[str, Any], key: str, types: type | tuple[type, ...],
                *, allow_none: bool = False) -> None:
    """Assert ``obj`` has ``key`` of the given type(s) — explicit contract failure."""
    assert key in obj, f"contract: key '{key}' is required (got keys {sorted(obj)})"
    val = obj[key]
    if val is None and allow_none:
        return
    expected = types if isinstance(types, tuple) else (types,)
    assert isinstance(val, expected), (
        f"contract: key '{key}' must be of type {expected} "
        f"(got {type(val).__name__} = {val!r})"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. tony_stocks_outcomes.json  —  bot → CC  (build_tony_outcomes)
# ══════════════════════════════════════════════════════════════════════════════

# The CC keys its (symbol, date) verdicts on these exact fields. Freeze them.
_OUTCOME_REQUIRED_KEYS = {
    "symbol",
    "pick_date",
    "result",
    "entry",
    "exit",
    "return_pct",
    "days_held",
    "resolved_date",
}
# result is normalized to exactly one of these four terminal buckets.
_OUTCOME_RESULT_BUCKETS = {"target_hit", "stop_hit", "closed", "expired"}


def _representative_outcome_records() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "orcl",  # lower-case proves uppercasing contract
            "result": "target_hit",
            "pick_date": "2026-05-30",
            "entry": 120.0,
            "exit": 126.0,
            "return_pct": 5.0,
            "days_held": 3,
            "resolved_date": "2026-06-02",
        },
        {
            "symbol": "AAA",
            "result": "stop_hit",
            "pick_date": "2026-05-31",
        },
    ]


class TestOutcomesJsonContract:
    def test_every_record_has_exactly_the_required_keys(self):
        out = build_tony_outcomes(_representative_outcome_records(), eod_date="2026-06-02")
        assert out, "contract: representative input must produce at least one outcome"
        for rec in out:
            assert set(rec.keys()) == _OUTCOME_REQUIRED_KEYS, (
                "contract: tony_stocks_outcomes record keys drifted; "
                f"expected {sorted(_OUTCOME_REQUIRED_KEYS)}, got {sorted(rec)}"
            )

    def test_key_types_are_frozen(self):
        out = build_tony_outcomes(_representative_outcome_records(), eod_date="2026-06-02")
        rec = out[0]
        _assert_key(rec, "symbol", str)
        _assert_key(rec, "pick_date", str, allow_none=True)
        _assert_key(rec, "result", str)
        _assert_key(rec, "entry", float, allow_none=True)
        _assert_key(rec, "exit", float, allow_none=True)
        _assert_key(rec, "return_pct", float, allow_none=True)
        _assert_key(rec, "days_held", int, allow_none=True)
        _assert_key(rec, "resolved_date", str, allow_none=True)

    def test_symbol_is_uppercased(self):
        out = build_tony_outcomes(_representative_outcome_records(), eod_date="2026-06-02")
        assert out[0]["symbol"] == "ORCL"

    def test_result_is_one_of_the_four_terminal_buckets(self):
        out = build_tony_outcomes(_representative_outcome_records(), eod_date="2026-06-02")
        for rec in out:
            assert rec["result"] in _OUTCOME_RESULT_BUCKETS, (
                f"contract: result '{rec['result']}' is not a frozen terminal bucket "
                f"{sorted(_OUTCOME_RESULT_BUCKETS)}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 2. Bridge markdown export  —  bot → CC  (write_bridge_export)
# ══════════════════════════════════════════════════════════════════════════════

# Front-matter keys + section headers the Command Center parser depends on.
_BRIDGE_FRONTMATTER_KEYS = ("date:", "source: TradingBotAgentProject", "export_type: eod-bridge")
_BRIDGE_REQUIRED_SECTIONS = (
    "## Scanner Summary",
    "## Tier 1",
    "## Tier 2",
    "## Tier 3",
    "## Sector ETF Snapshot",
    "## Cluster Risk Flags",
    "## Outcomes Since Last Brief",
    "## Signal Scorecard",
    "## Rule Suggestions",
    "## For Tony",
)


def _representative_eod_result() -> dict[str, Any]:
    return {
        "report_date": "2026-05-22",
        "scan_coverage": {"universe_size": 349, "scored_count": 175,
                          "coverage_pct": 50.1, "cycles_completed": 12},
        "strategy_version_report": {"current_version": "v1"},
        "tony_self_review": {
            "rule_suggestions": [{"confidence": "medium", "suggestion": "Prioritize Breakout Watch"}],
        },
        "terminal_outcome_summary": {"active_count": 7},
        "signal_scorecard": {
            "Breakout Watch": {"triggered": 14, "target_rate": 0.64, "stop_rate": 0.21},
        },
        "outcomes_since_last_brief": [
            {"symbol": "ORCL", "result": "target_hit", "entry_date": "2026-05-20",
             "days_held": 2, "pl_pct": 4.2},
        ],
    }


def _representative_snapshots() -> list[dict[str, Any]]:
    return [
        {"symbol": "GTLB", "score": 87, "setup_category": "Breakout Watch",
         "status": "active", "days_active": 4,
         "latest_close": 58.20, "target_price": 63.50, "stop_price": 55.80},
        {"symbol": "CVS", "score": 71, "setup_category": "Breakout Watch",
         "status": "waiting", "days_active": 2,
         "latest_close": 62.10, "target_price": 67.20, "stop_price": 58.90},
        {"symbol": "ANET", "score": 61, "setup_category": "Breakout Watch",
         "status": "watching", "days_active": 1,
         "latest_close": 312.40, "target_price": 340.0, "stop_price": 298.0},
    ]


class TestBridgeMarkdownContract:
    @pytest.fixture()
    def bridge_md(self, tmp_path: Path) -> str:
        write_bridge_export("2026-05-22", _representative_eod_result(), tmp_path,
                            snapshots=_representative_snapshots())
        out = tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md"
        assert out.exists(), "contract: eod bridge must write {date}.md"
        return out.read_text(encoding="utf-8")

    def test_frontmatter_keys_present(self, bridge_md: str):
        for key in _BRIDGE_FRONTMATTER_KEYS:
            assert key in bridge_md, f"contract: bridge front-matter must contain '{key}'"

    def test_all_required_sections_present(self, bridge_md: str):
        for header in _BRIDGE_REQUIRED_SECTIONS:
            assert header in bridge_md, (
                f"contract: bridge markdown must contain section header '{header}' "
                "(the Command Center parser keys off these)"
            )

    def test_title_and_backlink_present(self, bridge_md: str):
        # The CC index/backlink navigation depends on these wikilink anchors.
        assert "# Tony Stocks Bridge — 2026-05-22" in bridge_md
        assert "[[bridge/tony-stocks/index]]" in bridge_md


# ══════════════════════════════════════════════════════════════════════════════
# 3. tony_stocks_verdicts.json  —  CC → bot  (cc_verdicts + build_picks)
# ══════════════════════════════════════════════════════════════════════════════

def _representative_verdicts() -> list[dict[str, Any]]:
    """The shape the Command Center writes — fields the bot mappers read."""
    return [
        {
            "date": "2026-06-03",
            "symbol": "DAL",
            "tony_score": 45.0,
            "verdict": "close",  # an exit verdict — cc_exit_symbols must catch it
            "thesis": "Overriding to CLOSE. Falling volume on the breakout.",
        },
        {
            "date": "2026-06-03",
            "symbol": "hood",  # lower-case proves uppercasing contract
            "tony_score": 85.0,
            "verdict": "reaffirm",
            "thesis": "Reaffirming the momentum continuation.",
        },
    ]


class TestVerdictsJsonContract:
    def test_load_cc_verdicts_accepts_bare_list(self, tmp_path: Path):
        path = tmp_path / "verdicts.json"
        import json
        path.write_text(json.dumps(_representative_verdicts()), encoding="utf-8")
        rows = load_cc_verdicts(path)
        assert len(rows) == 2
        for row in rows:
            _assert_key(row, "symbol", str)
            _assert_key(row, "verdict", str)

    def test_load_cc_verdicts_accepts_wrapper_and_symbol_keyed_dict(self, tmp_path: Path):
        import json
        wrapped = tmp_path / "wrapped.json"
        wrapped.write_text(json.dumps({"verdicts": _representative_verdicts()}), encoding="utf-8")
        assert len(load_cc_verdicts(wrapped)) == 2

        keyed = tmp_path / "keyed.json"
        keyed.write_text(json.dumps({"DAL": {"verdict": "close"}}), encoding="utf-8")
        rows = load_cc_verdicts(keyed)
        # symbol is back-filled from the dict key — contract for the keyed form.
        assert rows[0]["symbol"] == "DAL"

    def test_exit_verdict_token_is_recognized(self):
        # Contract: a 'close' verdict on DAL must flatten DAL on the bot's book.
        symbols = cc_exit_symbols(_representative_verdicts())
        assert "DAL" in symbols
        assert "HOOD" not in symbols  # reaffirm is a hold

    def test_build_picks_maps_verdict_fields_to_expected_output_keys(self):
        picks = build_picks(_representative_verdicts())
        assert set(picks) == {"DAL", "HOOD"}, "contract: picks keyed by uppercase symbol"
        hood = picks["HOOD"]
        # CommandCenterPick output contract: symbol/score/verdict/reasoning/returned_at.
        assert hood.symbol == "HOOD"
        assert isinstance(hood.score, float) and hood.score == 85.0  # from tony_score
        assert hood.verdict == "reaffirm"
        assert hood.reasoning == "Reaffirming the momentum continuation."  # from thesis
        assert hood.returned_at == "2026-06-03T00:00:00Z"  # date → ISO instant


# ══════════════════════════════════════════════════════════════════════════════
# 4. tony_stocks_record.json  —  CC → bot  (build_record / build_agreement)
# ══════════════════════════════════════════════════════════════════════════════

def _representative_record() -> dict[str, Any]:
    """The graded scorecard the Command Center writes."""
    return {
        "status": "scored",
        "tony_win_rate": 33.3,  # 0–100 in the file; mapper normalizes to 0–1
        "avg_pl_per_trade": 1.4,
        "target_hits": 6,
        "stop_hits": 3,
        "equity_curve": [100.0, 101.2, 99.8],
        "agreement": {
            "agreed_right": 0,
            "agreed_wrong": 0,
            "override_saved": 2,   # producer spelling; mapper renames → cc_overrode_saved
            "override_missed": 4,
        },
    }


class TestRecordJsonContract:
    def test_build_record_maps_scorecard_fields(self):
        rec = build_record(_representative_record())
        assert rec is not None, "contract: a dict record must map to CommandCenterRecord"
        # win_rate input is 0–100, output contract is the 0–1 fraction.
        assert rec.win_rate == pytest.approx(0.333)
        assert isinstance(rec.avg_pl_per_trade, float)
        assert rec.target_hits == 6
        assert rec.stop_hits == 3
        assert isinstance(rec.equity_curve, list)
        assert rec.equity_curve == [100.0, 101.2, 99.8]

    def test_build_agreement_renames_override_to_cc_overrode(self):
        agr = build_agreement(_representative_record())
        assert agr is not None, "contract: record.agreement must map to CommandCenterAgreement"
        # The four frozen agreement quadrants the dashboard matrix consumes.
        assert agr.agreed_right == 0
        assert agr.agreed_wrong == 0
        assert agr.cc_overrode_saved == 2   # renamed from override_saved
        assert agr.cc_overrode_missed == 4  # renamed from override_missed

    def test_agreement_accepts_native_cc_overrode_spelling(self):
        agr = build_agreement(
            {"agreement": {"agreed_right": 1, "agreed_wrong": 2,
                           "cc_overrode_saved": 3, "cc_overrode_missed": 4}}
        )
        assert agr is not None
        assert (agr.agreed_right, agr.agreed_wrong,
                agr.cc_overrode_saved, agr.cc_overrode_missed) == (1, 2, 3, 4)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Tony divergence / teaching-log shape  (build_tony_divergence)
#    Consumed by build_agreement_from_teaching (the bot-side agreement fallback).
# ══════════════════════════════════════════════════════════════════════════════

_TEACHING_RECORD_KEYS = {
    "pick_id",
    "symbol",
    "pick_date",
    "verdict",
    "tony_reasoning",
    "bot_action",
    "bot_rationale",
    "result",
    "return_pct",
    "classification",
}
_AGREEMENT_QUADRANTS = {"agreed_right", "agreed_wrong", "cc_overrode_saved", "cc_overrode_missed"}
_CLASSIFICATIONS = _AGREEMENT_QUADRANTS | {"pending"}


class TestTeachingLogContract:
    def _ledger_dict(self) -> dict[str, Any]:
        verdicts = [
            {"symbol": "DAL", "date": "2026-06-03", "verdict": "close",
             "thesis": "Falling volume; get out."},
            {"symbol": "HOOD", "date": "2026-06-03", "verdict": "reaffirm",
             "thesis": "Momentum intact."},
        ]
        outcomes = [
            {"symbol": "DAL", "pick_date": "2026-06-03", "result": "stop_hit", "return_pct": -2.0},
            {"symbol": "HOOD", "pick_date": "2026-06-03", "result": "target_hit", "return_pct": 6.0},
        ]
        return build_tony_divergence(verdicts, outcomes).to_dict()

    def test_top_level_ledger_keys(self):
        d = self._ledger_dict()
        _assert_key(d, "research_only", bool)
        _assert_key(d, "tallies", dict)
        _assert_key(d, "agreement", dict)
        _assert_key(d, "records", list)

    def test_agreement_block_has_exactly_the_four_quadrants(self):
        d = self._ledger_dict()
        assert set(d["agreement"].keys()) == _AGREEMENT_QUADRANTS, (
            "contract: teaching-log agreement quadrants drifted; "
            f"expected {sorted(_AGREEMENT_QUADRANTS)}, got {sorted(d['agreement'])}"
        )
        for k, v in d["agreement"].items():
            assert isinstance(v, int), f"contract: agreement['{k}'] must be int"

    def test_record_keys_and_classification_frozen(self):
        d = self._ledger_dict()
        assert d["records"], "contract: representative input must produce records"
        for rec in d["records"]:
            assert set(rec.keys()) == _TEACHING_RECORD_KEYS, (
                "contract: teaching record keys drifted; "
                f"expected {sorted(_TEACHING_RECORD_KEYS)}, got {sorted(rec)}"
            )
            assert rec["classification"] in _CLASSIFICATIONS, (
                f"contract: classification '{rec['classification']}' not in "
                f"{sorted(_CLASSIFICATIONS)}"
            )

    def test_teaching_agreement_feeds_the_fallback_mapper(self):
        # End-to-end contract: the teaching-log agreement block must be consumable
        # by build_agreement_from_teaching (the bot-side CC-agreement fallback).
        d = self._ledger_dict()
        agr = build_agreement_from_teaching(d)
        assert agr is not None, (
            "contract: build_tony_divergence output must be accepted by "
            "build_agreement_from_teaching"
        )
        # DAL: Tony said close + pick lost => override would have saved us.
        assert agr.cc_overrode_saved == 1
        # HOOD: Tony reaffirmed + pick won => agreed_right.
        assert agr.agreed_right == 1
