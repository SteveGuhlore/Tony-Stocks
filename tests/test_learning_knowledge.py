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
