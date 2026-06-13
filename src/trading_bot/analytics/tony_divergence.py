"""Tony teaching / divergence memory layer (roadmap item 4).

Execution is *pure separation*: the bot trades its own picks and ignores Tony's
verdicts on its book. But Tony's second-pass reasoning is signal we keep as memory —
"Tony said X because Y; the outcome proved him right/wrong." This module joins Tony's
verdicts with the bot's resolved outcomes on ``(symbol, pick_date)`` and grades each
into the agreement quadrants the dashboard already understands:

    agreed_right        Tony reaffirmed + the bot's pick won
    agreed_wrong        Tony reaffirmed + the bot's pick lost
    cc_overrode_saved   Tony said get out/adjust + the pick lost  (his override would have saved us)
    cc_overrode_missed  Tony said get out/adjust + the pick won   (his override would have missed it)
    pending             outcome not yet resolved

Tony's reasoning is preserved verbatim so the ledger *teaches why*, not just who won.
Pure + deterministic (this module does no I/O); persistence + the API surface live in
the CLI / route layers. Research only — no profitability claim, and nothing here ever
touches the bot's paper book.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_TEACHING_PATH = "reports/tony_teaching_log.json"

# Verdicts that mean "Tony wanted a different path than the bot's hold".
_DIVERGE_VERDICTS = {
    "override", "close", "adjust", "sell", "exit", "reduce", "avoid", "trim", "get_out",
}
_WIN_RESULTS = {"target_hit"}
_LOSS_RESULTS = {"stop_hit", "failed_setup"}

AGREED_RIGHT = "agreed_right"
AGREED_WRONG = "agreed_wrong"
CC_OVERRODE_SAVED = "cc_overrode_saved"
CC_OVERRODE_MISSED = "cc_overrode_missed"
PENDING = "pending"
_CLASSES = (AGREED_RIGHT, AGREED_WRONG, CC_OVERRODE_SAVED, CC_OVERRODE_MISSED, PENDING)
_AGREEMENT_KEYS = (AGREED_RIGHT, AGREED_WRONG, CC_OVERRODE_SAVED, CC_OVERRODE_MISSED)


@dataclass(frozen=True)
class TeachingRecord:
    pick_id: str
    symbol: str
    pick_date: str
    verdict: str
    tony_reasoning: str
    bot_action: str
    bot_rationale: str
    result: str | None
    return_pct: float | None
    classification: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pick_id": self.pick_id,
            "symbol": self.symbol,
            "pick_date": self.pick_date,
            "verdict": self.verdict,
            "tony_reasoning": self.tony_reasoning,
            "bot_action": self.bot_action,
            "bot_rationale": self.bot_rationale,
            "result": self.result,
            "return_pct": self.return_pct,
            "classification": self.classification,
        }


@dataclass
class DivergenceLedger:
    records: list[TeachingRecord] = field(default_factory=list)
    research_only: bool = True

    @property
    def tallies(self) -> dict[str, int]:
        counts = {c: 0 for c in _CLASSES}
        for r in self.records:
            counts[r.classification] = counts.get(r.classification, 0) + 1
        return counts

    def agreement_dict(self) -> dict[str, int]:
        """The 4 quadrants in the shape ``/api/command-center`` agreement expects."""
        t = self.tallies
        return {k: t[k] for k in _AGREEMENT_KEYS}

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_only": self.research_only,
            "tallies": self.tallies,
            "agreement": self.agreement_dict(),
            "records": [r.to_dict() for r in self.records],
            "note": (
                "Tony-vs-bot divergence graded against resolved outcomes; reasoning "
                "preserved verbatim. Research only — never auto-applied to the bot's book."
            ),
        }


def teaching_log_path() -> Path:
    """Resolve the teaching-ledger path: ``TONY_TEACHING_FILE`` env or the default."""
    env = os.environ.get("TONY_TEACHING_FILE")
    return Path(env) if env else Path(_DEFAULT_TEACHING_PATH)


def write_divergence_ledger(ledger: "DivergenceLedger", path: str | Path | None = None) -> Path:
    """Persist the recomputed ledger as JSON (overwrite — re-grading is deterministic
    from current verdicts+outcomes, so the latest snapshot is the source of truth)."""
    out = Path(path) if path is not None else teaching_log_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger.to_dict(), indent=2), encoding="utf-8")
    return out


def _to_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def _outcome_is_win(record: dict[str, Any] | None) -> bool | None:
    """True/False for a resolved win/loss, or None when not yet resolved."""
    if not record:
        return None
    result = str(record.get("result") or "").lower()
    if result in _WIN_RESULTS:
        return True
    if result in _LOSS_RESULTS:
        return False
    ret = _to_float(record.get("return_pct"))
    if ret is not None:
        return ret > 0
    return None


def _is_divergent(verdict: str) -> bool:
    return verdict.strip().lower() in _DIVERGE_VERDICTS


def _classify(verdict: str, win: bool | None) -> str:
    if win is None:
        return PENDING
    if _is_divergent(verdict):
        return CC_OVERRODE_SAVED if win is False else CC_OVERRODE_MISSED
    return AGREED_RIGHT if win else AGREED_WRONG


def build_tony_divergence(
    verdicts: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    *,
    bot_picks: list[dict[str, Any]] | None = None,
) -> DivergenceLedger:
    """Join Tony verdicts with resolved outcomes (and optional bot picks) on
    ``(symbol, pick_date)`` and grade each into a :class:`TeachingRecord`.

    One record per verdict. A verdict with no matching resolved outcome is ``pending``
    and is re-graded automatically on a later run once the outcome resolves.
    """
    from collections import defaultdict  # noqa: PLC0415

    # Outcomes per symbol, sorted by pick_date. A Tony verdict carries his REVIEW date, not
    # the snapshot's pick_date, so an exact-date join never matches (every record would be a
    # false "pending"). Instead, match a verdict to the pick it was reviewing: the symbol's
    # latest outcome with pick_date <= the verdict date. It grades once that pick resolves.
    by_symbol: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for o in outcomes or []:
        sym = str(o.get("symbol") or "").upper()
        pd = str(o.get("pick_date") or "")
        if sym and pd:
            by_symbol[sym].append((pd, o))
    for lst in by_symbol.values():
        lst.sort(key=lambda x: x[0])

    def _match(sym: str, vdate: str) -> dict[str, Any] | None:
        chosen: dict[str, Any] | None = None
        for pd, o in by_symbol.get(sym, []):
            if pd <= vdate:
                chosen = o
            else:
                break
        return chosen

    bot_map: dict[str, dict[str, Any]] = {}
    for b in bot_picks or []:
        sym = str(b.get("symbol") or "").upper()
        if sym:
            bot_map[sym] = b

    # One graded record per distinct PICK (symbol, pick_date), NOT per symbol. A verdict
    # reviews the pick that existed at review time (the symbol's latest outcome with
    # pick_date <= the verdict's date); we keep the latest verdict per pick (Tony's final
    # stance on it). This makes the ledger a per-pick history that ACCUMULATES as picks
    # resolve, instead of a one-row-per-name snapshot that shrinks when verdicts rotate.
    # Re-issued verdicts on the same pick still collapse to a single record.
    per_pick: dict[tuple[str, str], dict[str, Any]] = {}
    for v in verdicts or []:
        sym = str(v.get("symbol") or "").upper()
        vdate = str(v.get("date") or v.get("pick_date") or "")
        if not sym or not vdate:
            continue
        outcome = _match(sym, vdate)
        pick_date = str(outcome.get("pick_date")) if outcome else vdate
        key = (sym, pick_date)
        prev = per_pick.get(key)
        if prev is None or vdate >= str(prev.get("date") or prev.get("pick_date") or ""):
            per_pick[key] = v

    records: list[TeachingRecord] = []
    for (sym, pick_date), v in per_pick.items():
        vdate = str(v.get("date") or v.get("pick_date") or "")
        verdict = str(v.get("verdict") or "")
        outcome = _match(sym, vdate)
        win = _outcome_is_win(outcome)
        bot = bot_map.get(sym, {})
        records.append(TeachingRecord(
            pick_id=f"{sym}-{pick_date}",
            symbol=sym,
            pick_date=pick_date,
            verdict=verdict,
            tony_reasoning=str(v.get("thesis") or v.get("reasoning") or ""),
            bot_action=str(bot.get("action") or ""),
            bot_rationale=str(bot.get("rationale") or bot.get("notes") or ""),
            result=(str(outcome.get("result")) if outcome and outcome.get("result") is not None else None),
            return_pct=_to_float(outcome.get("return_pct")) if outcome else None,
            classification=_classify(verdict, win),
        ))
    return DivergenceLedger(records=records)


_TERMINAL_CLASSES = {AGREED_RIGHT, AGREED_WRONG, CC_OVERRODE_SAVED, CC_OVERRODE_MISSED}


def read_divergence_ledger(path: str | Path | None = None) -> DivergenceLedger:
    """Load an existing ledger so re-grading can ACCUMULATE (merge) rather than overwrite.
    Returns an empty ledger when the file is missing or malformed."""
    src = Path(path) if path is not None else teaching_log_path()
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DivergenceLedger(records=[])
    raw = data.get("records") if isinstance(data, dict) else None
    records: list[TeachingRecord] = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        records.append(TeachingRecord(
            pick_id=str(r.get("pick_id") or ""),
            symbol=str(r.get("symbol") or "").upper(),
            pick_date=str(r.get("pick_date") or ""),
            verdict=str(r.get("verdict") or ""),
            tony_reasoning=str(r.get("tony_reasoning") or ""),
            bot_action=str(r.get("bot_action") or ""),
            bot_rationale=str(r.get("bot_rationale") or ""),
            result=(str(r["result"]) if r.get("result") is not None else None),
            return_pct=_to_float(r.get("return_pct")),
            classification=str(r.get("classification") or PENDING),
        ))
    return DivergenceLedger(records=records)


def merge_ledgers(existing: DivergenceLedger, fresh: DivergenceLedger) -> DivergenceLedger:
    """Cumulative merge keyed by (symbol, pick_date). A pick that has resolved to a TERMINAL
    classification is permanent — carried forward and never downgraded/re-flipped — so the
    4-quadrant "2nd pass" tally is MONOTONIC even when the source verdicts file is a
    daily-rotated snapshot. Pending picks do NOT accumulate: they come only from ``fresh``,
    so transient/phantom pending rows don't pile up — pending reflects the current state."""
    merged: dict[tuple[str, str], TeachingRecord] = {}
    # 1. Lock in every resolved pick from the existing ledger.
    for r in existing.records:
        if r.classification in _TERMINAL_CLASSES:
            merged[(r.symbol, r.pick_date)] = r
    # 2. Apply the fresh grading (current pending + any newly-resolved), never overwriting
    #    a locked terminal record.
    for r in fresh.records:
        key = (r.symbol, r.pick_date)
        if key in merged:
            continue
        merged[key] = r
    return DivergenceLedger(records=list(merged.values()))
