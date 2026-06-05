import json
import types

from trading_bot.analytics.nightly_learning import build_nightly_facts
from trading_bot.analytics.learning_knowledge import update_knowledge
from trading_bot.analytics.learning_narrator import narrate, NarrationResult


def _fixture():
    outcomes = [{"symbol": "MARA", "pick_date": "2026-06-01", "result": "target_hit",
                 "return_pct": 12, "setup_category": "Momentum / Buy", "total_score": 80,
                 "days_held": 4, "entry": 13.7, "stop": 12.2, "exit": 16.3}]
    facts = build_nightly_facts(outcomes, None, None, None, as_of="2026-06-01", min_sample=1)
    kb = update_knowledge(None, facts)
    return facts, kb


def _make_fake_client(text, captured):
    client = types.SimpleNamespace()

    def create(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=text)])

    client.messages = types.SimpleNamespace(create=create)
    return client


def test_templated_fallback_when_no_client():
    facts, kb = _fixture()
    res = narrate(facts, kb, prior_note=None, client=None, use_llm=False)
    assert isinstance(res, NarrationResult)
    assert res.template_fallback is True
    assert facts.as_of in res.narrative
    assert len(res.insights) >= 1
    assert all({"category", "insight", "confidence"} <= set(i) for i in res.insights)


def test_insights_skip_insufficient_dimensions():
    facts, kb = _fixture()
    res = narrate(facts, kb, prior_note=None, client=None, use_llm=False)
    cats = {i["category"] for i in res.insights}
    assert "tony_divergence" not in cats  # no teaching data in fixture


def test_llm_path_parses_json_and_only_sees_facts():
    facts, kb = _fixture()
    captured = {}
    payload = json.dumps({
        "narrative": "Momentum is working; keep leaning in.",
        "insights": [{"category": "setup_edge", "insight": "Momentum edge holding",
                      "confidence": "high", "symbols": ["MARA"]}],
    })
    client = _make_fake_client(payload, captured)
    res = narrate(facts, kb, prior_note="last night text", client=client, use_llm=True)
    assert res.template_fallback is False
    assert "Momentum is working" in res.narrative
    assert res.insights[0]["category"] == "setup_edge"
    sent = json.dumps(captured)
    assert "setup_edge" in sent and "build_nightly_facts" not in sent


def test_llm_failure_falls_back_to_templates():
    facts, kb = _fixture()

    def boom(**kwargs):
        raise RuntimeError("api down")

    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=boom))
    res = narrate(facts, kb, prior_note=None, client=client, use_llm=True)
    assert res.template_fallback is True
    assert facts.as_of in res.narrative
