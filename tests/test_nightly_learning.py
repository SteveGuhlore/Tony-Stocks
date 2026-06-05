from trading_bot.analytics.nightly_learning import (
    Dimension, NightlyFacts, confidence_for, _to_float, _outcome_is_win,
    _win_rate, _avg_return, build_nightly_facts,
    dim_setup_edge, dim_sector_signal, dim_score_calibration, dim_r_multiple,
    dim_hold_time, dim_exit_mix, dim_regime, dim_funnel_value, dim_tony_divergence,
)


def _o(sym, result, ret, setup="Momentum / Buy", days=3, pick="2026-05-18"):
    return {"symbol": sym, "pick_date": pick, "result": result,
            "return_pct": ret, "days_held": days, "setup_category": setup}


# --- Task 1: helpers + gating --------------------------------------------- #
def test_to_float_handles_garbage():
    assert _to_float("3.5") == 3.5
    assert _to_float(None) is None
    assert _to_float("nope") is None
    assert _to_float(float("nan")) is None


def test_outcome_is_win_by_result_then_return():
    assert _outcome_is_win({"result": "target_hit"}) is True
    assert _outcome_is_win({"result": "stop_hit"}) is False
    assert _outcome_is_win({"result": "closed", "return_pct": 2.0}) is True
    assert _outcome_is_win({"result": "closed", "return_pct": -2.0}) is False
    assert _outcome_is_win({"result": "expired"}) is None


def test_win_rate_and_avg_return():
    rows = [{"result": "target_hit", "return_pct": 10.0},
            {"result": "stop_hit", "return_pct": -5.0}]
    assert _win_rate(rows) == 0.5
    assert _avg_return(rows) == 2.5


def test_confidence_for_is_sample_gated():
    assert confidence_for(0) == "insufficient"
    assert confidence_for(4, min_sample=5) == "insufficient"
    assert confidence_for(5, min_sample=5) == "low"
    assert confidence_for(12, min_sample=5) == "med"
    assert confidence_for(30, min_sample=5) == "high"


def test_dimension_to_dict_roundtrips():
    d = Dimension(key="setup_edge", title="Setup edge", rows=[{"k": 1}],
                  headline="x", confidence="low", sample_size=5)
    assert d.to_dict()["key"] == "setup_edge"
    assert d.to_dict()["sample_size"] == 5


# --- Task 2: NightlyFacts -------------------------------------------------- #
def test_nightly_facts_to_dict_and_summary():
    facts = NightlyFacts(
        as_of="2026-06-04",
        dimensions=[Dimension("setup_edge", "Setup edge", [], "x", "low", 5)],
        summary={"trades": 10, "win_rate": 0.6},
    )
    d = facts.to_dict()
    assert d["as_of"] == "2026-06-04"
    assert d["research_only"] is True
    assert d["summary"]["trades"] == 10
    assert d["dimensions"][0]["key"] == "setup_edge"
    assert facts.dimension("setup_edge").title == "Setup edge"
    assert facts.dimension("missing") is None


# --- Task 3: setup_edge + sector_signal ----------------------------------- #
def test_setup_edge_dimension_groups_and_gates():
    rows = [_o("A", "target_hit", 10), _o("B", "target_hit", 8), _o("C", "stop_hit", -4),
            _o("D", "target_hit", 6, setup="Pullback / Buy")]
    d = dim_setup_edge(rows, min_sample=2)
    mom = next(r for r in d.rows if r["setup_category"] == "Momentum / Buy")
    assert mom["wins"] == 2 and mom["losses"] == 1
    assert mom["win_rate"] == round(2 / 3, 4)
    assert d.key == "setup_edge"
    assert d.confidence in {"low", "med", "high"}


def test_sector_signal_uses_sector_map_and_flags_streak():
    # NVDA + AMD are Technology in sector_map; MU is Unknown (excluded)
    rows = [{"symbol": "NVDA", "pick_date": "2026-05-18", "result": "stop_hit", "return_pct": -3},
            {"symbol": "AMD", "pick_date": "2026-05-19", "result": "stop_hit", "return_pct": -2},
            {"symbol": "MU", "pick_date": "2026-05-20", "result": "stop_hit", "return_pct": -1}]
    d = dim_sector_signal(rows, min_sample=2)
    assert d.key == "sector_signal"
    tech = next(r for r in d.rows if r["sector"] == "Technology")
    assert tech["loss_streak"] >= 2
    assert all(r["sector"].lower() != "unknown" for r in d.rows)


# --- Task 4: score_calibration + r_multiple ------------------------------- #
def test_score_calibration_buckets_by_total_score():
    rows = [{"symbol": "A", "result": "target_hit", "return_pct": 9, "total_score": 82},
            {"symbol": "B", "result": "target_hit", "return_pct": 5, "total_score": 76},
            {"symbol": "C", "result": "stop_hit", "return_pct": -4, "total_score": 41},
            {"symbol": "D", "result": "stop_hit", "return_pct": -3, "total_score": 55}]
    d = dim_score_calibration(rows, min_sample=2)
    hi = next(r for r in d.rows if r["bucket"] == "80-100")
    assert hi["win_rate"] == 1.0
    assert d.key == "score_calibration"
    assert d.headline


def test_r_multiple_expectancy():
    rows = [{"symbol": "A", "result": "target_hit", "entry": 100, "stop": 95, "exit": 110},
            {"symbol": "B", "result": "stop_hit", "entry": 50, "stop": 48, "exit": 48}]
    d = dim_r_multiple(rows, min_sample=2)
    body = d.rows[0]
    assert body["avg_winner_r"] == 2.0
    assert body["avg_loser_r"] == -1.0
    assert body["expectancy_r"] == 0.5


# --- Task 5: hold_time + exit_mix + regime -------------------------------- #
def test_hold_time_splits_winners_losers():
    rows = [{"symbol": "A", "result": "target_hit", "return_pct": 9, "days_held": 6},
            {"symbol": "B", "result": "stop_hit", "return_pct": -4, "days_held": 2}]
    d = dim_hold_time(rows, min_sample=2)
    body = d.rows[0]
    assert body["avg_days_winners"] == 6.0
    assert body["avg_days_losers"] == 2.0


def test_exit_mix_counts_results():
    rows = [{"result": "target_hit"}, {"result": "target_hit"}, {"result": "stop_hit"},
            {"result": "expired"}, {"result": "closed", "return_pct": 1}]
    d = dim_exit_mix(rows, min_sample=2)
    counts = {r["result"]: r["n"] for r in d.rows}
    assert counts["target_hit"] == 2 and counts["expired"] == 1


def test_regime_trailing_streak():
    rows = [{"symbol": "A", "pick_date": "2026-05-18", "result": "target_hit", "return_pct": 5},
            {"symbol": "B", "pick_date": "2026-05-19", "result": "target_hit", "return_pct": 4}]
    d = dim_regime(rows, min_sample=2)
    body = d.rows[0]
    assert body["current_streak"] == 2 and body["streak_kind"] == "win"


# --- Task 6: funnel_value + tony_divergence ------------------------------- #
def test_funnel_value_dimension_from_report_dict():
    report = {"stages": [
        {"stage": "recommendation", "verdict": "helps", "kept_win_rate": 0.6, "dropped_win_rate": 0.3},
        {"stage": "earnings", "verdict": "neutral", "kept_win_rate": 0.5, "dropped_win_rate": 0.5},
    ]}
    d = dim_funnel_value(report, min_sample=5)
    assert d.key == "funnel_value"
    assert any(r["verdict"] == "helps" for r in d.rows)


def test_tony_divergence_dimension_from_teaching_dict():
    teaching = {"agreement": {"agreed_right": 3, "agreed_wrong": 1,
                              "cc_overrode_saved": 2, "cc_overrode_missed": 1}}
    d = dim_tony_divergence(teaching, min_sample=2)
    body = d.rows[0]
    assert body["net_override"] == 1
    assert d.key == "tony_divergence"


def test_dimension_wrappers_handle_none():
    assert dim_funnel_value(None).confidence == "insufficient"
    assert dim_tony_divergence(None).confidence == "insufficient"


# --- Task 7: build_nightly_facts ------------------------------------------ #
def test_build_nightly_facts_assembles_all_dimensions():
    outcomes = [_o("A", "target_hit", 10), _o("B", "stop_hit", -4)]
    facts = build_nightly_facts(outcomes, teaching=None, funnel_report=None,
                                closed_paper=None, as_of="2026-06-04", min_sample=1)
    keys = {d.key for d in facts.dimensions}
    assert {"setup_edge", "sector_signal", "score_calibration", "r_multiple",
            "hold_time", "exit_mix", "regime", "funnel_value", "tony_divergence"} <= keys
    assert facts.as_of == "2026-06-04"
    assert facts.summary["trades"] == 2
    assert facts.summary["win_rate"] == 0.5


def test_build_nightly_facts_empty_is_safe():
    facts = build_nightly_facts([], None, None, None, as_of="2026-06-04")
    assert facts.summary["trades"] == 0
    assert all(d.confidence == "insufficient" for d in facts.dimensions)
