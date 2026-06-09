"""Evolving knowledge base for the nightly learner (design §5.2).

Deterministic merge of nightly facts into a long-lived set of claims that get
promoted/demoted as evidence accumulates. The markdown view is rendered elsewhere;
this module is pure + JSON-serializable so it can be persisted and re-read nightly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trading_bot.analytics.nightly_learning import NightlyFacts, confidence_for

_CONFIRM_MIN_N = 12
_CONFIRM_WR = 0.55
_REJECT_WR = 0.40


@dataclass(frozen=True)
class KnowledgeItem:
    key: str
    claim: str
    status: str                 # emerging | confirmed | decaying | rejected
    win_rate: float | None
    sample_size: int
    confidence: str
    first_seen: str
    last_updated: str
    trend: str                  # up | down | flat
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__}


@dataclass(frozen=True)
class KnowledgeBase:
    items: list[KnowledgeItem]
    as_of: str

    def item(self, key: str) -> KnowledgeItem | None:
        return next((i for i in self.items if i.key == key), None)

    def to_dict(self) -> dict[str, Any]:
        return {"as_of": self.as_of, "research_only": True,
                "items": [i.to_dict() for i in self.items]}


_ITEM_DEFAULTS: dict[str, Any] = {
    "claim": "", "status": "emerging", "win_rate": None, "sample_size": 0,
    "confidence": "insufficient", "first_seen": "", "last_updated": "",
    "trend": "flat", "history": [],
}


def knowledge_from_dict(data: dict[str, Any] | None) -> KnowledgeBase:
    """Rehydrate the running knowledge from its persisted JSON. Tolerant by design:
    this reads LAST night's file, so it must survive schema drift (a field we added
    since it was written) and a partially-corrupt row without killing tonight's whole
    learning run. An item with no ``key`` is unusable and dropped; missing fields fall
    back to defaults; unknown fields are ignored."""
    data = data if isinstance(data, dict) else {}
    items: list[KnowledgeItem] = []
    for it in data.get("items", []) or []:
        if not isinstance(it, dict) or not it.get("key"):
            continue
        fields = {k: it.get(k, default) for k, default in _ITEM_DEFAULTS.items()}
        history = fields["history"]
        fields["history"] = history if isinstance(history, list) else []
        items.append(KnowledgeItem(key=str(it["key"]), **fields))
    return KnowledgeBase(items=items, as_of=str(data.get("as_of") or ""))


def _candidates(facts: NightlyFacts) -> list[dict[str, Any]]:
    """Flatten the dimensions into mergeable (key, claim, win_rate, n) candidates.
    setup_edge + sector_signal carry per-group edges worth remembering."""
    out: list[dict[str, Any]] = []
    se = facts.dimension("setup_edge")
    if se:
        for r in se.rows:
            if r.get("win_rate") is not None:
                out.append({"key": f"setup:{r['setup_category'].lower()}",
                            "claim": f"{r['setup_category']} setups",
                            "win_rate": r["win_rate"], "n": r["n"]})
    ss = facts.dimension("sector_signal")
    if ss:
        for r in ss.rows:
            if r.get("win_rate") is not None:
                out.append({"key": f"sector:{r['sector'].lower()}",
                            "claim": f"{r['sector']} sector",
                            "win_rate": r["win_rate"], "n": r["n"]})
    return out


def _status(latest_wr: float | None, cum_n: int, prior: str | None) -> str:
    """Grade a claim from the LATEST win-rate against CUMULATIVE evidence (cum_n is
    the summed sample across the item's history) — so a sustained edge promotes and a
    collapse demotes, while a single thin night can't flip a verdict."""
    if latest_wr is None:
        return prior or "emerging"
    if cum_n < _CONFIRM_MIN_N:
        # not enough cumulative evidence to confirm/reject a fresh claim
        return prior if prior in {"confirmed", "decaying"} else "emerging"
    if latest_wr <= _REJECT_WR:
        return "rejected"
    if latest_wr >= _CONFIRM_WR:
        return "confirmed"
    # mediocre middle band
    return "decaying" if prior in {"confirmed", "decaying"} else "emerging"


def _trend(history: list[dict[str, Any]]) -> str:
    rated = [h["win_rate"] for h in history if h.get("win_rate") is not None]
    if len(rated) < 2:
        return "flat"
    delta = rated[-1] - rated[0]
    return "up" if delta > 0.03 else "down" if delta < -0.03 else "flat"


def update_knowledge(prior: KnowledgeBase | None, facts: NightlyFacts,
                     *, history_cap: int = 30) -> KnowledgeBase:
    """Merge tonight's facts into the running knowledge. Deterministic: promote on a
    sustained edge + sample growth, demote on win-rate erosion, set trend from history.
    Lessons compound across nights instead of resetting."""
    prior_items = {i.key: i for i in (prior.items if prior else [])}
    seen: dict[str, KnowledgeItem] = {}
    for c in _candidates(facts):
        old = prior_items.get(c["key"])
        # drop any prior point for tonight's date so re-running a date is idempotent
        # (and a re-grade overwrites rather than duplicates)
        history = [h for h in (old.history if old else []) if h.get("date") != facts.as_of]
        history = history + [{"date": facts.as_of, "win_rate": c["win_rate"], "n": c["n"]}]
        history = history[-history_cap:]
        cum_n = sum(int(h.get("n") or 0) for h in history)
        seen[c["key"]] = KnowledgeItem(
            key=c["key"], claim=c["claim"],
            status=_status(c["win_rate"], cum_n, old.status if old else None),
            win_rate=c["win_rate"], sample_size=c["n"],
            confidence=confidence_for(c["n"], min_sample=5),
            first_seen=old.first_seen if old else facts.as_of,
            last_updated=facts.as_of, trend=_trend(history), history=history,
        )
    # carry forward prior items not seen tonight (no new evidence => unchanged)
    merged = list(seen.values()) + [it for k, it in prior_items.items() if k not in seen]
    merged.sort(key=lambda i: i.key)
    return KnowledgeBase(items=merged, as_of=facts.as_of)
