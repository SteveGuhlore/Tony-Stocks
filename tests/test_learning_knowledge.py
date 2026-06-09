from trading_bot.analytics.learning_knowledge import (
    knowledge_from_dict, update_knowledge,
)
from trading_bot.analytics.nightly_learning import build_nightly_facts


def _facts(as_of, wr_rows):
    # wr_rows: list of (result, return_pct) for a single "Momentum / Buy" setup
    outcomes = [{"symbol": f"S{i}", "pick_date": as_of, "result": res,
                 "return_pct": ret, "setup_category": "Momentum / Buy", "total_score": 75}
                for i, (res, ret) in enumerate(wr_rows)]
    return build_nightly_facts(outcomes, None, None, None, as_of=as_of, min_sample=1)


def test_first_night_creates_emerging_items():
    facts = _facts("2026-06-01", [("target_hit", 8)] * 6 + [("stop_hit", -3)] * 2)
    kb = update_knowledge(None, facts)
    item = next(i for i in kb.items if i.key == "setup:momentum / buy")
    assert item.status in {"emerging", "confirmed"}
    assert item.first_seen == "2026-06-01"
    assert item.sample_size == 8


def test_sustained_edge_promotes_to_confirmed():
    kb = None
    for d in ("2026-06-01", "2026-06-02", "2026-06-03"):
        kb = update_knowledge(kb, _facts(d, [("target_hit", 8)] * 8 + [("stop_hit", -3)] * 2))
    item = next(i for i in kb.items if i.key == "setup:momentum / buy")
    assert item.status == "confirmed"
    assert item.first_seen == "2026-06-01"
    assert item.last_updated == "2026-06-03"


def test_eroding_edge_demotes_and_trends_down():
    kb = update_knowledge(None, _facts("2026-06-01", [("target_hit", 8)] * 9 + [("stop_hit", -3)]))
    kb = update_knowledge(kb, _facts("2026-06-08", [("stop_hit", -4)] * 8 + [("target_hit", 5)] * 2))
    item = next(i for i in kb.items if i.key == "setup:momentum / buy")
    assert item.status in {"decaying", "rejected"}
    assert item.trend == "down"


def test_history_capped_and_roundtrips():
    kb = None
    for i in range(40):
        kb = update_knowledge(kb, _facts(f"2026-06-{(i % 28) + 1:02d}",
                                         [("target_hit", 5)] * 5 + [("stop_hit", -2)] * 5),
                              history_cap=10)
    item = next(i for i in kb.items if i.key == "setup:momentum / buy")
    assert len(item.history) <= 10
    restored = knowledge_from_dict(kb.to_dict())
    assert {i.key for i in restored.items} == {i.key for i in kb.items}


# ── error/edge: the persistence READ path must survive a corrupt prior file ────────
# knowledge_from_dict reads LAST night's JSON; if it crashes, tonight's grading is lost
# too. These pin "degrade, don't crash" on the file that compounds the bot's memory.

def test_from_dict_tolerates_non_dict_and_empty():
    for bad in (None, [], "nope", {"items": None}, {"items": "x"}):
        assert knowledge_from_dict(bad).items == []  # type: ignore[arg-type]


def test_from_dict_drops_rows_without_a_key():
    kb = knowledge_from_dict({"items": [
        {"claim": "orphan"},                                  # no key -> dropped
        "not even a dict",                                    # junk -> dropped
        {"key": "setup:momentum", "claim": "kept", "win_rate": 0.6},
    ]})
    assert [i.key for i in kb.items] == ["setup:momentum"]


def test_from_dict_fills_missing_fields_with_defaults():
    # Schema drift: a row written by an OLDER build is missing fields we read today.
    kb = knowledge_from_dict({"as_of": "2026-06-09",
                              "items": [{"key": "setup:breakout", "win_rate": 0.7}]})
    it = kb.items[0]
    assert it.status == "emerging" and it.trend == "flat"
    assert it.sample_size == 0 and it.history == []
    assert it.confidence == "insufficient"


def test_from_dict_ignores_unknown_fields():
    # Forward drift: a row written by a NEWER build carries a field we don't model yet.
    kb = knowledge_from_dict({"items": [
        {"key": "setup:vwap", "claim": "x", "status": "confirmed",
         "win_rate": 0.6, "sample_size": 20, "confidence": "high",
         "first_seen": "2026-06-01", "last_updated": "2026-06-09",
         "trend": "up", "history": [], "future_field_we_dont_know": 123},
    ]})
    assert kb.items[0].status == "confirmed"


def test_corrupt_row_survives_round_trip_into_next_night():
    # A drifted prior file rehydrates, then tonight's facts merge on top without error.
    prior = knowledge_from_dict({"as_of": "2026-06-08",
                                 "items": [{"key": "setup:momentum / buy", "win_rate": 0.6,
                                            "history": [{"date": "2026-06-08", "win_rate": 0.6, "n": 5}]}]})
    kb = update_knowledge(prior, _facts("2026-06-09", [("target_hit", 6)] * 8 + [("stop_hit", -2)] * 2))
    item = next(i for i in kb.items if i.key == "setup:momentum / buy")
    assert item.last_updated == "2026-06-09"       # merge ran cleanly on the drifted prior
    assert len(item.history) == 2                  # tonight compounded onto the prior point


def test_nan_win_rate_in_facts_does_not_poison_status():
    # A NaN return slipping into the grader must not flip a claim or crash _status/_trend.
    facts = _facts("2026-06-09", [("closed", float("nan"))] * 5)
    kb = update_knowledge(None, facts)
    # NaN returns are undecidable -> the setup has no win_rate -> no item emitted (or emerging)
    item = next((i for i in kb.items if i.key == "setup:momentum / buy"), None)
    assert item is None or item.status == "emerging"
