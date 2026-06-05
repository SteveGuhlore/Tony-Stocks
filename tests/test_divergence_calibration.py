"""Unit tests for the pure divergence-calibration core.

Spec: docs/superpowers/specs/2026-06-05-divergence-calibration-design.md (test matrix T1-T9).
Pure module — synthetic PickRecord + ledger dicts only, no I/O.
"""
from __future__ import annotations

import pytest

from trading_bot.analytics.divergence_calibration import (
    PickRecord,
    _COMPONENTS,
    _outcome_is_win,
    apply_nudge,
    attribution,
    build_divergence_calibration,
    cohort_component_elevation,
    cohort_overrides,
)

_W = {
    "trend_weight": 0.22,
    "momentum_weight": 0.28,
    "volume_weight": 0.18,
    "risk_weight": 0.14,
    "setup_quality_weight": 0.18,
}


def _pick(**kw) -> PickRecord:
    base = dict(
        symbol="AAA",
        pick_date="2026-05-01",
        result="target_hit",
        return_pct=5.0,
        setup_category="Breakout Watch",
        score_band="80-89",
        trend_score=70.0,
        momentum_score=80.0,
        volume_score=60.0,
        risk_score=55.0,
        setup_quality_score=65.0,
    )
    base.update(kw)
    return PickRecord(**base)


# --------------------------------------------------------------------------- #
# Task 1 — scaffolding                                                         #
# --------------------------------------------------------------------------- #
def test_outcome_is_win_semantics():
    assert _outcome_is_win(_pick(result="target_hit")) is True
    assert _outcome_is_win(_pick(result="stop_hit")) is False
    assert _outcome_is_win(_pick(result="failed_setup")) is False
    assert _outcome_is_win(_pick(result="closed", return_pct=2.0)) is True
    assert _outcome_is_win(_pick(result="closed", return_pct=-2.0)) is False
    assert _outcome_is_win(_pick(result="expired", return_pct=None)) is None
    assert _outcome_is_win(_pick(result=None, return_pct=None)) is None


def test_components_constant():
    assert _COMPONENTS == ("trend", "momentum", "volume", "risk", "setup_quality")


# --------------------------------------------------------------------------- #
# Task 2 — attribution                                                         #
# --------------------------------------------------------------------------- #
def test_attribution_separation_and_predictive():
    picks = []
    for i in range(6):
        picks.append(_pick(symbol=f"W{i}", result="target_hit", momentum_score=80.0, trend_score=75.0))
        picks.append(_pick(symbol=f"L{i}", result="stop_hit", momentum_score=78.0, trend_score=55.0))
    attrs = {a.component: a for a in attribution(picks)}
    assert attrs["trend"].predictive is True
    assert attrs["trend"].separation == 20.0
    assert attrs["momentum"].predictive is False  # +2 <= sep_eps(3)
    assert attrs["momentum"].confidence == "med"  # 12 resolved -> med (high needs n>=30)


def test_attribution_insufficient_sample_is_none():
    picks = [_pick(symbol="A", result="target_hit"), _pick(symbol="B", result="stop_hit")]
    attrs = {a.component: a for a in attribution(picks)}
    assert attrs["momentum"].predictive is None
    assert attrs["momentum"].confidence == "insufficient"


# --------------------------------------------------------------------------- #
# Task 3 — cohort overrides                                                    #
# --------------------------------------------------------------------------- #
def test_cohort_overrides_flags_proven_overrides():
    ledger = {
        "records": [
            {"symbol": f"S{i}", "pick_date": "2026-05-01", "classification": "cc_overrode_saved"}
            for i in range(5)
        ]
        + [{"symbol": "M0", "pick_date": "2026-05-01", "classification": "cc_overrode_missed"}]
    }
    picks = [_pick(symbol=f"S{i}", setup_category="Breakout Watch") for i in range(5)] + [
        _pick(symbol="M0", setup_category="Breakout Watch")
    ]
    by = {(c.dimension, c.cohort): c for c in cohort_overrides(ledger, picks)}
    bw = by[("setup_category", "Breakout Watch")]
    assert bw.saved == 5 and bw.missed == 1 and bw.net_override == 4
    assert bw.tony_correctly_overrode is True


def test_cohort_overrides_ignores_pending_and_unmatched():
    ledger = {
        "records": [
            {"symbol": "AAA", "pick_date": "2026-05-01", "classification": "pending"},
            {"symbol": "ZZZ", "pick_date": "2026-05-01", "classification": "cc_overrode_saved"},
        ]
    }
    picks = [_pick(symbol="AAA")]
    assert cohort_overrides(ledger, picks) == []


# --------------------------------------------------------------------------- #
# Task 4 — bridge                                                              #
# --------------------------------------------------------------------------- #
def test_elevation_picks_most_inflated_component():
    picks = [
        _pick(
            symbol=f"C{i}",
            setup_category="Momentum Continuation",
            momentum_score=95.0,
            trend_score=50.0,
            volume_score=50.0,
            risk_score=50.0,
            setup_quality_score=50.0,
        )
        for i in range(4)
    ] + [
        _pick(
            symbol=f"O{i}",
            setup_category="Pullback Watch",
            momentum_score=40.0,
            trend_score=50.0,
            volume_score=50.0,
            risk_score=50.0,
            setup_quality_score=50.0,
        )
        for i in range(6)
    ]
    ranked = cohort_component_elevation(picks, "setup_category", "Momentum Continuation")
    assert ranked[0][0] == "momentum"
    assert ranked[0][1] > 0


# --------------------------------------------------------------------------- #
# Task 5 — nudge math (T1 invariants + T6 clamp)                               #
# --------------------------------------------------------------------------- #
def test_apply_nudge_down_keeps_sum_and_bounds():
    new, applied = apply_nudge(_W, "momentum", "down", max_delta_pts=3.0)
    assert abs(sum(new.values()) - 1.0) < 1e-9
    assert new["momentum_weight"] < _W["momentum_weight"]
    assert applied == 3.0
    assert all(0.05 <= v <= 0.50 for v in new.values())


def test_apply_nudge_up_keeps_sum():
    new, applied = apply_nudge(_W, "risk", "up", max_delta_pts=3.0)
    assert abs(sum(new.values()) - 1.0) < 1e-9
    assert new["risk_weight"] > _W["risk_weight"]
    assert applied == 3.0


def test_apply_nudge_clamps_at_floor():
    w = {
        "trend_weight": 0.06,
        "momentum_weight": 0.40,
        "volume_weight": 0.18,
        "risk_weight": 0.18,
        "setup_quality_weight": 0.18,
    }
    new, applied = apply_nudge(w, "trend", "down", max_delta_pts=3.0)  # 0.06 -> floor 0.05
    assert new["trend_weight"] >= 0.05 - 1e-9
    assert applied <= 1.0 + 1e-9  # only 1 pt of room before the floor
    assert abs(sum(new.values()) - 1.0) < 1e-9


# --------------------------------------------------------------------------- #
# Task 6 — AND-gate + report                                                   #
# --------------------------------------------------------------------------- #
def _converging_inputs():
    """momentum non-predictive (sep +2) AND Momentum Continuation overridden+proven."""
    picks, records = [], []
    for i in range(6):
        picks.append(
            _pick(symbol=f"W{i}", result="target_hit", setup_category="Pullback Watch", momentum_score=78.0)
        )
        picks.append(
            _pick(symbol=f"M{i}", result="stop_hit", setup_category="Momentum Continuation", momentum_score=92.0)
        )
        records.append({"symbol": f"M{i}", "pick_date": "2026-05-01", "classification": "cc_overrode_saved"})
    return picks, {"records": records}


def test_down_proposal_fires_on_convergence():
    picks, ledger = _converging_inputs()
    rep = build_divergence_calibration(picks, ledger, dict(_W))
    downs = [p for p in rep.proposals if p.direction == "down"]
    assert len(downs) == 1
    assert downs[0].target_component == "momentum"
    assert downs[0].confidence in {"low", "medium", "high"}
    assert abs(sum(downs[0].new_weights.values()) - 1.0) < 1e-9
    assert downs[0].new_weights["momentum_weight"] < _W["momentum_weight"]
    assert downs[0].kind == "weight_calibration"
    assert downs[0].suggestion == downs[0].rationale


def test_no_proposal_when_attribution_disagrees():
    # momentum strongly predictive -> Tony's override is cohort noise, not a weighting fault.
    picks, records = [], []
    for i in range(6):
        picks.append(
            _pick(symbol=f"W{i}", result="target_hit", setup_category="Momentum Continuation", momentum_score=95.0)
        )
        picks.append(
            _pick(symbol=f"L{i}", result="stop_hit", setup_category="Pullback Watch", momentum_score=40.0)
        )
        records.append({"symbol": f"W{i}", "pick_date": "2026-05-01", "classification": "cc_overrode_saved"})
    rep = build_divergence_calibration(picks, {"records": records}, dict(_W))
    assert all(p.target_component != "momentum" for p in rep.proposals if p.direction == "down")


def test_no_proposal_when_no_override():
    # Attribution alone (momentum non-predictive) must not move a weight without a confirmed override.
    picks = []
    for i in range(6):
        picks.append(_pick(symbol=f"W{i}", result="target_hit", momentum_score=80.0))
        picks.append(_pick(symbol=f"L{i}", result="stop_hit", momentum_score=78.0))
    rep = build_divergence_calibration(picks, {"records": []}, dict(_W))
    assert rep.proposals == []


def test_insufficient_sample_no_proposal():
    picks = [_pick(symbol="A", result="target_hit"), _pick(symbol="B", result="stop_hit")]
    rep = build_divergence_calibration(picks, {"records": []}, dict(_W))
    assert rep.proposals == []
    assert "converged" in rep.headline.lower() or "no calibration" in rep.headline.lower()


def test_up_proposal_from_agreed_right_cohort():
    # trend strongly predictive AND Breakout Watch reaffirmed-and-won -> raise trend.
    picks, records = [], []
    for i in range(6):
        picks.append(
            _pick(symbol=f"W{i}", result="target_hit", setup_category="Breakout Watch", trend_score=95.0)
        )
        picks.append(
            _pick(symbol=f"L{i}", result="stop_hit", setup_category="Pullback Watch", trend_score=45.0)
        )
        records.append({"symbol": f"W{i}", "pick_date": "2026-05-01", "classification": "agreed_right"})
    rep = build_divergence_calibration(picks, {"records": records}, dict(_W))
    ups = [p for p in rep.proposals if p.direction == "up"]
    assert len(ups) == 1
    assert ups[0].target_component == "trend"
    assert ups[0].new_weights["trend_weight"] > _W["trend_weight"]


def test_single_component_invariant_and_determinism():
    picks, ledger = _converging_inputs()
    a = build_divergence_calibration(picks, ledger, dict(_W))
    b = build_divergence_calibration(picks, ledger, dict(_W))
    comps = [p.target_component for p in a.proposals]
    assert len(comps) == len(set(comps))  # never two proposals on one component
    assert [p.to_dict() for p in a.proposals] == [p.to_dict() for p in b.proposals]


def test_confidence_mapping_uses_gate_vocab():
    picks, ledger = _converging_inputs()
    rep = build_divergence_calibration(picks, ledger, dict(_W))
    for p in rep.proposals:
        assert p.confidence in {"low", "medium", "high"}  # never "med"/"insufficient"


@pytest.mark.parametrize("direction", ["up", "down"])
def test_report_to_dict_shape(direction):
    picks, ledger = _converging_inputs()
    rep = build_divergence_calibration(picks, ledger, dict(_W))
    d = rep.to_dict()
    assert set(d) >= {"headline", "research_only", "weight_proposals", "attributions", "cohort_overrides"}
    assert d["research_only"] is True
