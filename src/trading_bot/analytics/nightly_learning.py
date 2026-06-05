"""Nightly self-learning facts core (design: specs/2026-06-04-nightly-self-learning-design.md).

Pure + deterministic: computes the *verified numbers* the learning loop rests on.
No I/O, no LLM, no trading side effects. The CLI/sink layer persists; the narrator
(learning_narrator.py) turns these facts into prose. Research only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_bot.vault.sector_map import get_sector

# result strings from the outcomes emitter
_WIN_RESULTS = {"target_hit"}
_LOSS_RESULTS = {"stop_hit", "failed_setup"}


def _to_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _outcome_is_win(record: dict[str, Any]) -> bool | None:
    """True/False for a resolved win/loss, else None (unresolved / undecidable)."""
    result = str(record.get("result") or "").lower()
    if result in _WIN_RESULTS:
        return True
    if result in _LOSS_RESULTS:
        return False
    ret = _to_float(record.get("return_pct"))
    if result == "closed" and ret is not None:
        return ret > 0
    return None


def _resolved(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if _outcome_is_win(r) is not None]


def _win_rate(rows: list[dict[str, Any]]) -> float | None:
    decided = [_outcome_is_win(r) for r in rows]
    decided = [w for w in decided if w is not None]
    if not decided:
        return None
    return round(sum(1 for w in decided if w) / len(decided), 4)


def _avg_return(rows: list[dict[str, Any]]) -> float | None:
    vals = [_to_float(r.get("return_pct")) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def confidence_for(n: int, *, min_sample: int = 5) -> str:
    """Sample-size gated confidence so we never overfit to a handful of trades."""
    if n < min_sample:
        return "insufficient"
    if n < 2 * min_sample:
        return "low"
    if n < 6 * min_sample:
        return "med"
    return "high"


@dataclass(frozen=True)
class Dimension:
    key: str
    title: str
    rows: list[dict[str, Any]]
    headline: str
    confidence: str
    sample_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "rows": self.rows,
            "headline": self.headline,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class NightlyFacts:
    as_of: str
    dimensions: list[Dimension]
    summary: dict[str, Any]
    research_only: bool = True

    def dimension(self, key: str) -> Dimension | None:
        return next((d for d in self.dimensions if d.key == key), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "research_only": self.research_only,
            "summary": self.summary,
            "dimensions": [d.to_dict() for d in self.dimensions],
        }


# --------------------------------------------------------------------------- #
# Dimensions                                                                   #
# --------------------------------------------------------------------------- #
def _group_rate_rows(rows: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        k = key_fn(r)
        if k:
            groups.setdefault(k, []).append(r)
    out = []
    for k, grp in groups.items():
        decided = [_outcome_is_win(r) for r in grp]
        decided = [w for w in decided if w is not None]
        out.append({
            "key": k,
            "n": len(grp),
            "wins": sum(1 for w in decided if w),
            "losses": sum(1 for w in decided if w is False),
            "win_rate": _win_rate(grp),
            "avg_return": _avg_return(grp),
        })
    return sorted(out, key=lambda r: (r["win_rate"] is None, -(r["win_rate"] or 0), -r["n"]))


def dim_setup_edge(rows: list[dict[str, Any]], *, min_sample: int = 5) -> Dimension:
    grouped = _group_rate_rows(rows, lambda r: str(r.get("setup_category") or "").strip() or None)
    for g in grouped:
        g["setup_category"] = g.pop("key")
    n = len(_resolved(rows))
    best = grouped[0] if grouped else None
    headline = (
        f"Best setup: {best['setup_category']} {round((best['win_rate'] or 0) * 100)}% win "
        f"(n={best['n']})" if best and best["win_rate"] is not None else "No setup edge yet"
    )
    return Dimension("setup_edge", "Win rate by setup", grouped, headline,
                     confidence_for(n, min_sample=min_sample), n)


def _loss_streak(grp: list[dict[str, Any]]) -> int:
    """Trailing consecutive losses, most-recent first (rows sorted by pick_date asc)."""
    ordered = sorted(grp, key=lambda r: str(r.get("pick_date") or ""))
    streak = 0
    for r in reversed(ordered):
        w = _outcome_is_win(r)
        if w is False:
            streak += 1
        elif w is True:
            break
    return streak


def dim_sector_signal(rows: list[dict[str, Any]], *, min_sample: int = 5) -> Dimension:
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        sec = get_sector(str(r.get("symbol") or ""))
        if sec and sec.lower() != "unknown":
            by_sector.setdefault(sec, []).append(r)
    out = []
    for sec, grp in by_sector.items():
        out.append({
            "sector": sec, "n": len(grp), "win_rate": _win_rate(grp),
            "avg_return": _avg_return(grp), "loss_streak": _loss_streak(grp),
        })
    out.sort(key=lambda r: (-r["loss_streak"], r["win_rate"] is None, r["win_rate"] or 0))
    n = sum(len(g) for g in by_sector.values())
    flagged = next((r for r in out if r["loss_streak"] >= 3), None)
    headline = (f"{flagged['sector']} on a {flagged['loss_streak']}-loss streak"
                if flagged else "No sector on a notable streak")
    return Dimension("sector_signal", "Sector signal & streaks", out, headline,
                     confidence_for(n, min_sample=min_sample), n)


_SCORE_BUCKETS = [(0, 40, "0-40"), (40, 60, "40-60"), (60, 80, "60-80"), (80, 101, "80-100")]


def dim_score_calibration(rows: list[dict[str, Any]], *, min_sample: int = 5) -> Dimension:
    buckets: dict[str, list[dict[str, Any]]] = {label: [] for _, _, label in _SCORE_BUCKETS}
    for r in rows:
        s = _to_float(r.get("total_score"))
        if s is None:
            continue
        for lo, hi, label in _SCORE_BUCKETS:
            if lo <= s < hi:
                buckets[label].append(r)
                break
    out = [{"bucket": label, "n": len(grp), "win_rate": _win_rate(grp),
            "avg_return": _avg_return(grp)} for label, grp in buckets.items() if grp]
    rated = [b for b in out if b["win_rate"] is not None]
    monotonic = all(
        rated[i]["win_rate"] <= rated[i + 1]["win_rate"] for i in range(len(rated) - 1)
    ) if len(rated) >= 2 else None
    n = len(_resolved([r for r in rows if _to_float(r.get("total_score")) is not None]))
    headline = ("Score IS predictive (higher buckets win more)" if monotonic
                else "Score is NOT cleanly predictive — review weighting" if monotonic is False
                else "Not enough graded picks to calibrate score")
    if out:
        out[0]["monotonic"] = monotonic
    return Dimension("score_calibration", "Score calibration", out, headline,
                     confidence_for(n, min_sample=min_sample), n)


def _r_multiple(r: dict[str, Any]) -> float | None:
    entry = _to_float(r.get("entry"))
    stop = _to_float(r.get("stop"))
    exit_ = _to_float(r.get("exit"))
    if None in (entry, stop, exit_) or entry == stop:
        return None
    risk = abs(entry - stop)
    return round((exit_ - entry) / risk, 4)


def dim_r_multiple(rows: list[dict[str, Any]], *, min_sample: int = 5) -> Dimension:
    rs = [(r, _r_multiple(r), _outcome_is_win(r)) for r in rows]
    rs = [(r, rm, w) for r, rm, w in rs if rm is not None and w is not None]
    winners = [rm for _, rm, w in rs if w]
    losers = [rm for _, rm, w in rs if w is False]
    avg_w = round(sum(winners) / len(winners), 4) if winners else None
    avg_l = round(sum(losers) / len(losers), 4) if losers else None
    n = len(rs)
    wr = (len(winners) / n) if n else None
    expectancy = (round(wr * (avg_w or 0) + (1 - wr) * (avg_l or 0), 4)
                  if wr is not None and (avg_w is not None or avg_l is not None) else None)
    body = [{"avg_winner_r": avg_w, "avg_loser_r": avg_l, "expectancy_r": expectancy, "n": n}]
    headline = (f"Expectancy {expectancy:+.2f}R (win {avg_w:+.1f}R / lose {avg_l:+.1f}R)"
                if expectancy is not None and avg_w is not None and avg_l is not None
                else "Not enough R-graded trades")
    return Dimension("r_multiple", "R-multiple & expectancy", body, headline,
                     confidence_for(n, min_sample=min_sample), n)


def dim_hold_time(rows: list[dict[str, Any]], *, min_sample: int = 5) -> Dimension:
    win_days = [_to_float(r.get("days_held")) for r in rows if _outcome_is_win(r) is True]
    loss_days = [_to_float(r.get("days_held")) for r in rows if _outcome_is_win(r) is False]
    win_days = [d for d in win_days if d is not None]
    loss_days = [d for d in loss_days if d is not None]
    aw = round(sum(win_days) / len(win_days), 2) if win_days else None
    al = round(sum(loss_days) / len(loss_days), 2) if loss_days else None
    body = [{"avg_days_winners": aw, "avg_days_losers": al}]
    n = len(win_days) + len(loss_days)
    headline = (f"Winners held {aw}d vs losers {al}d" if aw is not None and al is not None
                else "Not enough hold-time data")
    return Dimension("hold_time", "Hold-time analysis", body, headline,
                     confidence_for(n, min_sample=min_sample), n)


def dim_exit_mix(rows: list[dict[str, Any]], *, min_sample: int = 5) -> Dimension:
    counts: dict[str, int] = {}
    for r in rows:
        res = str(r.get("result") or "unknown").lower()
        counts[res] = counts.get(res, 0) + 1
    out = [{"result": k, "n": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    n = sum(counts.values())
    exp = counts.get("expired", 0)
    headline = (f"{exp}/{n} died by expiry — review time-stop" if n and exp / n > 0.3
                else "Exit mix nominal")
    return Dimension("exit_mix", "Exit reason mix", out, headline,
                     confidence_for(n, min_sample=min_sample), n)


def dim_regime(rows: list[dict[str, Any]], *, min_sample: int = 5) -> Dimension:
    ordered = sorted(rows, key=lambda r: str(r.get("pick_date") or ""))
    kind, streak = None, 0
    for r in reversed(ordered):
        w = _outcome_is_win(r)
        if w is None:
            continue
        this = "win" if w else "loss"
        if kind is None:
            kind, streak = this, 1
        elif this == kind:
            streak += 1
        else:
            break
    n = len(_resolved(rows))
    body = [{"current_streak": streak, "streak_kind": kind,
             "recent_win_rate": _win_rate(ordered[-10:])}]
    headline = (f"Currently on a {streak}-{kind} streak" if kind else "No resolved trades yet")
    return Dimension("regime", "Regime / streak", body, headline,
                     confidence_for(n, min_sample=min_sample), n)


def dim_funnel_value(funnel_report: dict[str, Any] | None, *, min_sample: int = 5) -> Dimension:
    stages = (funnel_report or {}).get("stages") or []
    rows = [{"stage": s.get("stage"), "verdict": s.get("verdict"),
             "kept_win_rate": s.get("kept_win_rate"),
             "dropped_win_rate": s.get("dropped_win_rate")} for s in stages]
    helps = [r["stage"] for r in rows if r["verdict"] == "helps"]
    n = len(rows)
    headline = (f"Funnel stages helping: {', '.join(str(s) for s in helps)}" if helps
                else "No funnel stage shows a clear edge yet")
    conf = "insufficient" if not rows else confidence_for(min_sample, min_sample=min_sample)
    return Dimension("funnel_value", "Funnel stage value", rows, headline, conf, n)


def dim_tony_divergence(teaching: dict[str, Any] | None, *, min_sample: int = 5) -> Dimension:
    agr = (teaching or {}).get("agreement") or {}
    saved = int(agr.get("cc_overrode_saved", 0) or 0)
    missed = int(agr.get("cc_overrode_missed", 0) or 0)
    right = int(agr.get("agreed_right", 0) or 0)
    wrong = int(agr.get("agreed_wrong", 0) or 0)
    n = saved + missed + right + wrong
    body = [{"agreed_right": right, "agreed_wrong": wrong, "cc_overrode_saved": saved,
             "cc_overrode_missed": missed, "net_override": saved - missed}]
    headline = (f"Tony's overrides net {saved - missed:+d} (saved {saved}, missed {missed})"
                if n else "No graded Tony divergences yet")
    return Dimension("tony_divergence", "Tony 2nd-pass divergence", body, headline,
                     confidence_for(n, min_sample=min_sample), n)


def build_nightly_facts(
    outcomes: list[dict[str, Any]],
    teaching: dict[str, Any] | None,
    funnel_report: dict[str, Any] | None,
    closed_paper: list[dict[str, Any]] | None,
    *,
    as_of: str,
    min_sample: int = 5,
) -> NightlyFacts:
    """Assemble every dimension into one NightlyFacts. Pure. ``outcomes`` is the spine;
    ``closed_paper`` (the bot's own book) is folded in when present so the bot grades its
    real fills alongside research outcomes."""
    rows = list(outcomes or [])
    if closed_paper:
        rows = rows + [c for c in closed_paper if c.get("result")]
    dims = [
        dim_setup_edge(rows, min_sample=min_sample),
        dim_sector_signal(rows, min_sample=min_sample),
        dim_score_calibration(rows, min_sample=min_sample),
        dim_r_multiple(rows, min_sample=min_sample),
        dim_hold_time(rows, min_sample=min_sample),
        dim_exit_mix(rows, min_sample=min_sample),
        dim_regime(rows, min_sample=min_sample),
        dim_funnel_value(funnel_report, min_sample=min_sample),
        dim_tony_divergence(teaching, min_sample=min_sample),
    ]
    resolved = _resolved(rows)
    summary = {
        "trades": len(resolved),
        "win_rate": _win_rate(rows),
        "avg_return": _avg_return(rows),
        "net_tony_divergence": dims[-1].rows[0]["net_override"] if dims[-1].rows else 0,
    }
    return NightlyFacts(as_of=as_of, dimensions=dims, summary=summary)
