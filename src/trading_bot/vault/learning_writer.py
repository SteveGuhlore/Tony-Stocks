"""Render the nightly learner's Obsidian artifacts + the CC bridge (design §5.5, §6).

Dated lessons note, the living _knowledge.md, and the one-way bridge brief the
Command Center's 2am script consumes. Takes computed objects and target dirs, writes
markdown. No analysis here. Research only.
"""
from __future__ import annotations

from pathlib import Path

from trading_bot.analytics.learning_knowledge import KnowledgeBase
from trading_bot.analytics.learning_narrator import NarrationResult
from trading_bot.analytics.nightly_learning import NightlyFacts

_STATUS_ICON = {"confirmed": "✅", "emerging": "🌱", "decaying": "⚠️", "rejected": "❌"}


def _learning_dir(vault_dir: str | Path) -> Path:
    d = Path(vault_dir) / "learning"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_learning_note(vault_dir: str | Path, facts: NightlyFacts,
                        narration: NarrationResult) -> Path:
    d = _learning_dir(vault_dir)
    out = d / f"{facts.as_of}.md"
    fm = ["---", f"as_of: {facts.as_of}", "type: nightly-learning",
          "research_only: true",
          f"template_fallback: {str(narration.template_fallback).lower()}", "---", ""]
    tables = []
    for dim in facts.dimensions:
        if dim.confidence == "insufficient":
            continue
        tables.append(f"\n### {dim.title} ({dim.confidence})\n\n- {dim.headline}")
    body = "\n".join(fm) + narration.narrative + "\n" + "\n".join(tables) + "\n"
    out.write_text(body, encoding="utf-8")
    return out


def write_knowledge_page(vault_dir: str | Path, kb: KnowledgeBase) -> Path:
    d = _learning_dir(vault_dir)
    out = d / "_knowledge.md"
    lines = ["---", f"as_of: {kb.as_of}", "type: learning-knowledge",
             "research_only: true", "---", "", "# What the bot has learned", ""]
    for it in sorted(kb.items, key=lambda i: (i.status, i.key)):
        icon = _STATUS_ICON.get(it.status, "·")
        wr = f"{round(it.win_rate * 100)}%" if it.win_rate is not None else "n/a"
        lines.append(f"- {icon} **{it.claim}** — {it.status}, {wr} win "
                     f"(n={it.sample_size}, {it.confidence}, trend {it.trend}) "
                     f"· since {it.first_seen}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def write_cc_learning_bridge(command_center_dir: str | Path, facts: NightlyFacts,
                             kb: KnowledgeBase, narration: NarrationResult) -> Path:
    """Push the night's brief to {cc}/bridge/tony-stocks/learning/<date>.md for CC's
    2am script. Disk-idempotent: skips rewriting if the dated file already exists."""
    bridge_dir = Path(command_center_dir) / "bridge" / "tony-stocks" / "learning"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    out = bridge_dir / f"{facts.as_of}.md"
    if out.exists():
        return out
    confirmed = [i for i in kb.items if i.status == "confirmed"]
    decaying = [i for i in kb.items if i.status in {"decaying", "rejected"}]
    lines = ["---", "export_type: bot-self-learning", "source: trading-bot",
             f"as_of: {facts.as_of}", "research_only: true", "---", "",
             f"# Trading bot — nightly self-assessment ({facts.as_of})", "",
             narration.narrative, "", "## Confirmed edges"]
    lines += ([f"- {i.claim}: {round((i.win_rate or 0) * 100)}% (n={i.sample_size})"
               for i in confirmed] or ["- (none yet)"])
    lines += ["", "## Fading / abandoned"]
    lines += ([f"- {i.claim} ({i.trend})" for i in decaying] or ["- (none)"])
    lines += [""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
