"""Funnel evaluation harness (roadmap item 3) — *does each funnel stage help?*

Pure, deterministic replay over stored picks. For each funnel stage we split the
picks into the names the stage would KEEP vs DROP (using the same thresholds as the
live :class:`~trading_bot.data.research_funnel.FunnelStageConfig`) and compare their
realized outcomes. If the dropped names did worse than the kept names, the stage is
separating losers from winners ("helps"); if better, it is throwing away winners
("hurts").

Advisory semantics mirror the live funnel:
  * Threshold-keep stages (price / dollar-volume / relative-strength / recommendation)
    only classify a pick when the datum is present; absent data is EXCLUDED from that
    stage's comparison (we can't say whether the screen would have acted).
  * The condition-drop stage (earnings blackout) drops a name only when it has a known
    report inside the window; absent or out-of-window names are KEPT.

Research only. This measures historical separation, not edge or profitability — a
positive delta on a small sample is not a trading claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from trading_bot.data.research_funnel import FunnelStageConfig

_KEEP, _DROP, _EXCLUDE = "keep", "drop", "exclude"


@dataclass(frozen=True)
class EvaluatedPick:
    """One historical pick: its realized outcome plus the funnel signals at pick time.

    Any signal may be ``None`` (not captured) — the harness excludes that pick from
    the affected stage rather than guessing.
    """

    symbol: str
    win: bool
    r_multiple: float | None = None
    price: float | None = None
    dollar_volume: float | None = None
    relative_strength: float | None = None
    recommendation_score: float | None = None
    days_to_earnings: int | None = None


@dataclass
class StageResult:
    stage: str
    configured: bool
    kept_n: int
    dropped_n: int
    kept_win_rate: float | None
    dropped_win_rate: float | None
    kept_avg_r: float | None
    dropped_avg_r: float | None
    win_rate_delta: float | None
    avg_r_delta: float | None
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "configured": self.configured,
            "kept_n": self.kept_n,
            "dropped_n": self.dropped_n,
            "kept_win_rate": self.kept_win_rate,
            "dropped_win_rate": self.dropped_win_rate,
            "kept_avg_r": self.kept_avg_r,
            "dropped_avg_r": self.dropped_avg_r,
            "win_rate_delta": self.win_rate_delta,
            "avg_r_delta": self.avg_r_delta,
            "verdict": self.verdict,
        }


@dataclass
class FunnelEvalReport:
    total_picks: int
    stages: list[StageResult]
    research_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_only": self.research_only,
            "total_picks": self.total_picks,
            "stages": [s.to_dict() for s in self.stages],
            "note": (
                "Per-stage win-rate of names the stage KEEPS vs DROPS over stored "
                "outcomes. Positive win_rate_delta = the stage drops the worse names. "
                "Research only; small samples are not evidence of edge."
            ),
        }


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
    return None if f is None else int(f)


def _outcome_is_win(record: dict[str, Any]) -> bool | None:
    """True/False for a resolved win/loss, or None when the record is not evaluable."""
    result = str(record.get("result") or "").lower()
    if result in _WIN_RESULTS:
        return True
    if result in _LOSS_RESULTS:
        return False
    ret = _to_float(record.get("return_pct"))
    if ret is not None:
        return ret > 0
    return None  # closed/expired without a return -> ambiguous, skip


def _asof_signal(series: list[Any], pick_date: str) -> dict[str, Any]:
    """Point-in-time join: the latest snapshot dated on/before ``pick_date``.

    ``series`` is a list of (date_str, signal_dict). Falls back to the earliest
    snapshot when the pick predates all of them (better than no signal at all).
    """
    ordered = sorted(series, key=lambda kv: str(kv[0]))
    chosen: dict[str, Any] | None = None
    for d, sig in ordered:
        if str(d) <= str(pick_date):
            chosen = sig
        else:
            break
    if chosen is None and ordered:
        chosen = ordered[0][1]
    return chosen or {}


def build_evaluated_picks(
    outcomes: list[dict[str, Any]],
    signals_by_symbol: dict[str, dict[str, Any]] | None = None,
    signals_history: dict[str, list[Any]] | None = None,
) -> list[EvaluatedPick]:
    """Join resolved outcome records with per-symbol funnel signals into picks.

    ``outcomes`` are ``tony_stocks_outcomes.json`` records ({symbol, result,
    return_pct, pick_date, ...}). ``signals_by_symbol`` maps SYMBOL -> a single
    signal dict (back-compat). ``signals_history`` maps SYMBOL -> [(date, signal), ...]
    and, when given, is AS-OF joined per pick by ``pick_date`` so the same ticker
    picked on different dates is matched to ITS pick-time signals rather than one
    shared snapshot. Records not yet resolved into a win/loss are skipped.
    """
    signals_by_symbol = signals_by_symbol or {}
    signals_history = signals_history or {}
    picks: list[EvaluatedPick] = []
    for record in outcomes:
        symbol = str(record.get("symbol") or "").upper()
        if not symbol:
            continue
        win = _outcome_is_win(record)
        if win is None:
            continue
        if symbol in signals_history:
            sig = _asof_signal(signals_history[symbol], str(record.get("pick_date") or ""))
        else:
            sig = signals_by_symbol.get(symbol, {})
        picks.append(EvaluatedPick(
            symbol=symbol,
            win=win,
            r_multiple=_to_float(record.get("return_pct")),
            price=_to_float(sig.get("price")),
            dollar_volume=_to_float(sig.get("dollar_volume")),
            relative_strength=_to_float(sig.get("relative_strength")),
            recommendation_score=_to_float(sig.get("recommendation_score")),
            days_to_earnings=_to_int(sig.get("days_to_earnings")),
        ))
    return picks


def _classify_price(p: EvaluatedPick, cfg: FunnelStageConfig) -> str:
    if p.price is None:
        return _EXCLUDE
    return _KEEP if cfg.min_price <= p.price <= cfg.max_price else _DROP


def _classify_dollar_volume(p: EvaluatedPick, cfg: FunnelStageConfig) -> str:
    if p.dollar_volume is None:
        return _EXCLUDE
    return _KEEP if p.dollar_volume >= cfg.min_dollar_volume else _DROP


def _classify_relative_strength(p: EvaluatedPick, cfg: FunnelStageConfig) -> str:
    if p.relative_strength is None or cfg.min_relative_strength is None:
        return _EXCLUDE
    return _KEEP if p.relative_strength >= cfg.min_relative_strength else _DROP


def _classify_earnings(p: EvaluatedPick, cfg: FunnelStageConfig) -> str:
    d = p.days_to_earnings
    if d is not None and 0 <= d <= cfg.earnings_blackout_days:
        return _DROP
    return _KEEP  # absent or outside the blackout window -> kept (advisory)


def _classify_recommendation(p: EvaluatedPick, cfg: FunnelStageConfig) -> str:
    if p.recommendation_score is None:
        return _EXCLUDE
    if cfg.min_recommendation is not None:
        return _KEEP if p.recommendation_score >= cfg.min_recommendation else _DROP
    # No explicit threshold: treat a positive analyst bias as the keep signal so the
    # rank's discriminative value can still be measured.
    return _KEEP if p.recommendation_score > 0.0 else _DROP


def _win_rate(picks: list[EvaluatedPick]) -> float | None:
    if not picks:
        return None
    return sum(1 for p in picks if p.win) / len(picks)


def _avg_r(picks: list[EvaluatedPick]) -> float | None:
    rs = [p.r_multiple for p in picks if p.r_multiple is not None]
    if not rs:
        return None
    return sum(rs) / len(rs)


def _verdict(kept_n: int, dropped_n: int, wr_delta: float | None,
             min_sample: int, delta_threshold: float) -> str:
    if kept_n < min_sample or dropped_n < min_sample or wr_delta is None:
        return "insufficient_data"
    if wr_delta > delta_threshold:
        return "helps"
    if wr_delta < -delta_threshold:
        return "hurts"
    return "neutral"


_StageSpec = tuple[str, bool, Callable[[EvaluatedPick, FunnelStageConfig], str]]


def evaluate_funnel_stages(
    picks: list[EvaluatedPick],
    config: FunnelStageConfig,
    *,
    min_sample: int = 5,
    delta_threshold: float = 0.05,
) -> FunnelEvalReport:
    """Evaluate every funnel stage against the realized outcomes in ``picks``."""
    specs: list[_StageSpec] = [
        ("price_screen", True, _classify_price),
        ("dollar_volume_screen", True, _classify_dollar_volume),
        ("relative_strength_screen", config.min_relative_strength is not None, _classify_relative_strength),
        ("earnings_blackout", config.earnings_blackout_days > 0, _classify_earnings),
        ("recommendation_rank", True, _classify_recommendation),
    ]
    results: list[StageResult] = []
    for name, configured, classify in specs:
        if not configured:
            results.append(StageResult(
                stage=name, configured=False, kept_n=0, dropped_n=0,
                kept_win_rate=None, dropped_win_rate=None, kept_avg_r=None,
                dropped_avg_r=None, win_rate_delta=None, avg_r_delta=None,
                verdict="not_configured",
            ))
            continue
        kept: list[EvaluatedPick] = []
        dropped: list[EvaluatedPick] = []
        for p in picks:
            verdict = classify(p, config)
            if verdict == _KEEP:
                kept.append(p)
            elif verdict == _DROP:
                dropped.append(p)
        kept_wr, dropped_wr = _win_rate(kept), _win_rate(dropped)
        kept_ar, dropped_ar = _avg_r(kept), _avg_r(dropped)
        wr_delta = (
            kept_wr - dropped_wr if kept_wr is not None and dropped_wr is not None else None
        )
        ar_delta = (
            kept_ar - dropped_ar if kept_ar is not None and dropped_ar is not None else None
        )
        results.append(StageResult(
            stage=name, configured=True, kept_n=len(kept), dropped_n=len(dropped),
            kept_win_rate=kept_wr, dropped_win_rate=dropped_wr,
            kept_avg_r=kept_ar, dropped_avg_r=dropped_ar,
            win_rate_delta=wr_delta, avg_r_delta=ar_delta,
            verdict=_verdict(len(kept), len(dropped), wr_delta, min_sample, delta_threshold),
        ))
    return FunnelEvalReport(total_picks=len(picks), stages=results)
