"""LLM narration layer for the nightly learner (design §5.3).

Turns VERIFIED NightlyFacts + the evolving KnowledgeBase into prose lessons and a
short list of dashboard insight lines. The model only ever sees computed facts —
never raw trade rows it could miscount. Any failure (or missing key / use_llm=False)
falls back to deterministic templates so the 1:30am run always completes.
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any

from trading_bot.analytics.nightly_learning import NightlyFacts
from trading_bot.analytics.learning_knowledge import KnowledgeBase


@dataclass(frozen=True)
class NarrationResult:
    narrative: str
    insights: list[dict[str, Any]]      # agent_insights rows (no date/status yet)
    template_fallback: bool
    model: str | None = None


_SYSTEM = (
    "You are the trading bot's nightly self-learning analyst. You receive VERIFIED, "
    "pre-computed statistics (win rates, R-multiples, streaks) — never raw trades. "
    "NEVER invent or recompute numbers; cite only figures present in the input. "
    "Write a concise, honest 'lessons learned' note: what worked, what didn't, what "
    "changed since last night, and what to watch. Compare against prior knowledge. "
    "Research only — never recommend bypassing risk rules. "
    "Return STRICT JSON: {\"narrative\": str, \"insights\": "
    "[{\"category\": str, \"insight\": str, \"confidence\": \"low|med|high\", "
    "\"symbols\": [str]}]}."
)


def _confident_dims(facts: NightlyFacts) -> list:
    return [d for d in facts.dimensions if d.confidence != "insufficient"]


def _pct(v: float | None) -> str:
    return f"{round(v * 100)}%" if v is not None else "n/a"


def _templated(facts: NightlyFacts, kb: KnowledgeBase) -> NarrationResult:
    dims = _confident_dims(facts)
    lines = [f"# Nightly lessons — {facts.as_of}", "",
             f"Graded {facts.summary.get('trades', 0)} resolved trades; "
             f"win rate {_pct(facts.summary.get('win_rate'))}.", ""]
    for d in dims:
        lines.append(f"- **{d.title}** ({d.confidence}): {d.headline}")
    confirmed = [i for i in kb.items if i.status == "confirmed"]
    decaying = [i for i in kb.items if i.status in {"decaying", "rejected"}]
    if confirmed:
        lines += ["", "**Confirmed edges:** " + ", ".join(i.claim for i in confirmed)]
    if decaying:
        lines += ["**Fading/abandoned:** " + ", ".join(f"{i.claim} ({i.trend})" for i in decaying)]
    insights = [{"category": d.key, "insight": d.headline, "confidence": d.confidence,
                 "symbols": []} for d in dims]
    return NarrationResult("\n".join(lines), insights, template_fallback=True)


def _build_user_payload(facts: NightlyFacts, kb: KnowledgeBase, prior_note: str | None) -> str:
    return _json.dumps({
        "as_of": facts.as_of,
        "summary": facts.summary,
        "dimensions": [d.to_dict() for d in _confident_dims(facts)],
        "knowledge": kb.to_dict(),
        "prior_note": prior_note or "",
    }, default=str)


def _parse_llm(text: str) -> tuple[str, list[dict[str, Any]]]:
    start, end = text.find("{"), text.rfind("}")
    data = _json.loads(text[start:end + 1])
    narrative = str(data.get("narrative") or "").strip()
    insights = []
    for it in data.get("insights") or []:
        if it.get("insight"):
            insights.append({
                "category": str(it.get("category") or "general"),
                "insight": str(it["insight"]),
                "confidence": str(it.get("confidence") or "low"),
                "symbols": list(it.get("symbols") or []),
            })
    if not narrative:
        raise ValueError("empty narrative")
    return narrative, insights


def narrate(facts: NightlyFacts, knowledge: KnowledgeBase, prior_note: str | None,
            *, client: Any = None, use_llm: bool = True,
            model: str = "claude-sonnet-4-6") -> NarrationResult:
    """Grounded narration. Falls back to deterministic templates on use_llm=False,
    no client, or any client error — the nightly run never fails on the LLM."""
    if not use_llm or client is None:
        return _templated(facts, knowledge)
    try:
        msg = client.messages.create(
            model=model, max_tokens=1500, system=_SYSTEM,
            messages=[{"role": "user",
                       "content": _build_user_payload(facts, knowledge, prior_note)}],
        )
        text = msg.content[0].text
        narrative, insights = _parse_llm(text)
        return NarrationResult(narrative, insights, template_fallback=False, model=model)
    except Exception:
        return _templated(facts, knowledge)
