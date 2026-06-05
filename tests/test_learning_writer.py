from trading_bot.analytics.nightly_learning import build_nightly_facts
from trading_bot.analytics.learning_knowledge import update_knowledge
from trading_bot.analytics.learning_narrator import narrate
from trading_bot.vault.learning_writer import (
    write_learning_note, write_knowledge_page, write_cc_learning_bridge,
)


def _bundle(as_of="2026-06-04"):
    outcomes = [{"symbol": "MARA", "pick_date": as_of, "result": "target_hit", "return_pct": 12,
                 "setup_category": "Momentum / Buy", "total_score": 80, "days_held": 4,
                 "entry": 13.7, "stop": 12.2, "exit": 16.3}]
    facts = build_nightly_facts(outcomes, None, None, None, as_of=as_of, min_sample=1)
    kb = update_knowledge(None, facts)
    res = narrate(facts, kb, None, client=None, use_llm=False)
    return facts, kb, res


def test_write_learning_note(tmp_path):
    facts, kb, res = _bundle()
    p = write_learning_note(tmp_path, facts, res)
    assert p == tmp_path / "learning" / "2026-06-04.md"
    body = p.read_text(encoding="utf-8")
    assert "2026-06-04" in body and "Nightly lessons" in body
    assert "research_only: true" in body


def test_write_knowledge_page(tmp_path):
    facts, kb, res = _bundle()
    p = write_knowledge_page(tmp_path, kb)
    assert p == tmp_path / "learning" / "_knowledge.md"
    body = p.read_text(encoding="utf-8")
    assert "Momentum / Buy" in body or "momentum" in body.lower()


def test_cc_learning_bridge_writes_contract_and_is_idempotent(tmp_path):
    facts, kb, res = _bundle("2026-06-05")
    cc = tmp_path / "CC"
    p = write_cc_learning_bridge(cc, facts, kb, res)
    assert p == cc / "bridge" / "tony-stocks" / "learning" / "2026-06-05.md"
    body = p.read_text(encoding="utf-8")
    assert "export_type: bot-self-learning" in body
    assert "source: trading-bot" in body
    assert "research_only: true" in body
    first_mtime = p.stat().st_mtime_ns
    p2 = write_cc_learning_bridge(cc, facts, kb, res)
    assert p2 == p and p2.stat().st_mtime_ns == first_mtime
