"""Divergence-driven scanner weight calibration.

Spec: ``docs/superpowers/specs/2026-06-05-divergence-calibration-design.md``.

Pure + deterministic: no I/O, no LLM, no trading side effects. This module joins two
independent signals and only acts when they agree:

1. **Per-component attribution** — across resolved picks, does a high ``momentum_score``
   actually predict a win, or does it predict a stop-out? A component whose winners barely
   outscore its losers is not earning its weight.
2. **Per-cohort divergence confirmation** — did Tony (layer 2) systematically override a
   cohort *and was he proven right* by resolved outcomes (``cc_overrode_saved`` >> missed)?

A weight nudge fires only when BOTH agree: Tony correctly overrode the cohort a component
inflates AND that component is independently non-predictive. Each nudge is tiny, bounded,
clamped, renormalized, and reversible. Research only — never auto-applied to the scanner;
the CLI/gate layers handle persistence and the two-key human approval flow.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from trading_bot.analytics.nightly_learning import confidence_for

_COMPONENTS = ("trend", "momentum", "volume", "risk", "setup_quality")
_WEIGHT_KEYS = {c: f"{c}_weight" for c in _COMPONENTS}
_WIN_RESULTS = {"target_hit"}
_LOSS_RESULTS = {"stop_hit", "failed_setup"}
_CONF_ORDER = {"insufficient": 0, "low": 1, "med": 2, "high": 3}
_CONF_TO_GATE = {"insufficient": "low", "low": "low", "med": "medium", "high": "high"}
_GATE_TO_INTERNAL = {"low": "low", "medium": "med", "high": "high"}
_WEIGHT_FLOOR, _WEIGHT_CEIL = 0.05, 0.50


# --------------------------------------------------------------------------- #
# Inputs                                                                       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PickRecord:
    """A resolved (or pending) pick joined with its scanner sub-scores."""

    symbol: str
    pick_date: str
    result: str | None
    return_pct: float | None
    setup_category: str
    score_band: str
    trend_score: float
    momentum_score: float
    volume_score: float
    risk_score: float
    setup_quality_score: float

    def component_score(self, component: str) -> float:
        return float(getattr(self, f"{component}_score"))


def _to_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def _outcome_is_win(pick: PickRecord) -> bool | None:
    """True/False for a resolved win/loss, else None (unresolved / undecidable)."""
    result = str(pick.result or "").lower()
    if result in _WIN_RESULTS:
        return True
    if result in _LOSS_RESULTS:
        return False
    ret = _to_float(pick.return_pct)
    if result == "closed" and ret is not None:
        return ret > 0
    return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _min_conf(a: str, b: str) -> str:
    """Lower of two gate-vocabulary confidences (low < medium < high)."""
    return a if _CONF_ORDER[_GATE_TO_INTERNAL[a]] <= _CONF_ORDER[_GATE_TO_INTERNAL[b]] else b


# --------------------------------------------------------------------------- #
# Step 1 — per-component attribution                                           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ComponentAttribution:
    component: str
    n: int
    win_mean: float | None
    loss_mean: float | None
    separation: float | None
    predictive: bool | None  # None when insufficient sample
    confidence: str


def attribution(
    picks: list[PickRecord], *, sep_eps: float = 3.0, min_sample: int = 5
) -> list[ComponentAttribution]:
    """For each sub-score, measure how well it separates winners from losers."""
    resolved = [(p, _outcome_is_win(p)) for p in picks]
    resolved = [(p, w) for p, w in resolved if w is not None]
    n = len(resolved)
    conf = confidence_for(n, min_sample=min_sample)
    out: list[ComponentAttribution] = []
    for c in _COMPONENTS:
        wins = [p.component_score(c) for p, w in resolved if w]
        losses = [p.component_score(c) for p, w in resolved if not w]
        wm = round(sum(wins) / len(wins), 4) if wins else None
        lm = round(sum(losses) / len(losses), 4) if losses else None
        sep = round(wm - lm, 4) if wm is not None and lm is not None else None
        predictive: bool | None = None
        if sep is not None and conf != "insufficient":
            predictive = sep >= sep_eps
        out.append(ComponentAttribution(c, n, wm, lm, sep, predictive, conf))
    return out


# --------------------------------------------------------------------------- #
# Step 2 — per-cohort divergence confirmation                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CohortOverride:
    dimension: str  # "setup_category" | "score_band"
    cohort: str
    saved: int
    missed: int
    agreed_right: int
    agreed_wrong: int
    net_override: int
    confidence: str
    tony_correctly_overrode: bool
    tony_correctly_kept: bool


def cohort_overrides(
    ledger: dict[str, Any],
    picks: list[PickRecord],
    *,
    min_net_override: int = 2,
    min_sample: int = 5,
) -> list[CohortOverride]:
    """Tally the ledger's graded classifications per cohort (setup_category + score_band)."""
    pick_map = {(p.symbol.upper(), p.pick_date): p for p in picks}
    tally: dict[tuple[str, str], dict[str, int]] = {}
    for rec in (ledger or {}).get("records", []) or []:
        key = (str(rec.get("symbol") or "").upper(), str(rec.get("pick_date") or ""))
        cls = str(rec.get("classification") or "")
        pick = pick_map.get(key)
        if pick is None or cls in ("", "pending"):
            continue
        for dim, val in (("setup_category", pick.setup_category), ("score_band", pick.score_band)):
            if not val:
                continue
            d = tally.setdefault((dim, val), {})
            d[cls] = d.get(cls, 0) + 1

    out: list[CohortOverride] = []
    for (dim, cohort), d in tally.items():
        saved = d.get("cc_overrode_saved", 0)
        missed = d.get("cc_overrode_missed", 0)
        ar = d.get("agreed_right", 0)
        aw = d.get("agreed_wrong", 0)
        net = saved - missed
        override_conf = confidence_for(saved + missed, min_sample=min_sample)
        kept_conf = confidence_for(ar + aw, min_sample=min_sample)
        out.append(
            CohortOverride(
                dimension=dim,
                cohort=cohort,
                saved=saved,
                missed=missed,
                agreed_right=ar,
                agreed_wrong=aw,
                net_override=net,
                confidence=override_conf,
                tony_correctly_overrode=(net >= min_net_override and override_conf != "insufficient"),
                tony_correctly_kept=((ar - aw) >= min_net_override and kept_conf != "insufficient"),
            )
        )
    return sorted(out, key=lambda c: (c.dimension, c.cohort))


# --------------------------------------------------------------------------- #
# Step 3 — cohort -> component bridge                                          #
# --------------------------------------------------------------------------- #
def cohort_component_elevation(
    picks: list[PickRecord], dimension: str, cohort: str
) -> list[tuple[str, float]]:
    """Rank components by how elevated they are inside a cohort vs the global mean."""
    resolved = [p for p in picks if _outcome_is_win(p) is not None]
    pool = resolved or list(picks)
    if not pool:
        return [(c, 0.0) for c in _COMPONENTS]

    def _dim_value(p: PickRecord) -> str:
        return p.setup_category if dimension == "setup_category" else p.score_band

    in_cohort = [p for p in pool if _dim_value(p) == cohort]
    if not in_cohort:
        return [(c, 0.0) for c in _COMPONENTS]

    ranked: list[tuple[str, float]] = []
    for c in _COMPONENTS:
        global_mean = sum(p.component_score(c) for p in pool) / len(pool)
        cohort_mean = sum(p.component_score(c) for p in in_cohort) / len(in_cohort)
        ranked.append((c, round(cohort_mean - global_mean, 4)))
    return sorted(ranked, key=lambda t: (-t[1], t[0]))


# --------------------------------------------------------------------------- #
# Step 5 — bounded nudge math                                                  #
# --------------------------------------------------------------------------- #
def apply_nudge(
    current_weights: dict[str, float],
    component: str,
    direction: str,
    *,
    max_delta_pts: float = 3.0,
) -> tuple[dict[str, float], float]:
    """Return (new_weights, applied_delta_pts). Bounded, clamped, renormalized to sum 1.0."""
    key = _WEIGHT_KEYS[component]
    w = {k: float(v) for k, v in current_weights.items()}
    target = w[key]
    signed = (max_delta_pts / 100.0) * (1 if direction == "up" else -1)
    moved = _clamp(target + signed, _WEIGHT_FLOOR, _WEIGHT_CEIL)
    applied = moved - target  # actual signed delta after clamp
    w[key] = moved

    # Distribute -applied across the other weights *proportional to their available room*
    # in the needed direction, so no weight is ever pushed past [floor, ceil]. Iterating a
    # few times absorbs any capacity a single pass could not (e.g. a weight near a bound).
    others = [k for k in w if k != key]
    to_distribute = -applied  # added to the others; keeps the total constant
    for _ in range(16):
        if abs(to_distribute) <= 1e-12:
            break
        if to_distribute < 0:
            capacity = {k: w[k] - _WEIGHT_FLOOR for k in others}  # room to decrease
        else:
            capacity = {k: _WEIGHT_CEIL - w[k] for k in others}  # room to increase
        total_cap = sum(c for c in capacity.values() if c > 0)
        if total_cap <= 1e-12:
            break
        moved_any = False
        for k in others:
            cap = capacity[k]
            if cap <= 0:
                continue
            share = to_distribute * (cap / total_cap)
            share = max(share, -cap) if to_distribute < 0 else min(share, cap)
            w[k] += share
            to_distribute -= share
            moved_any = True
        if not moved_any:
            break

    w = {k: round(v, 4) for k, v in w.items()}
    # Absorb residual rounding drift onto the first weight that still has bounded room.
    drift = round(1.0 - sum(w.values()), 4)
    if abs(drift) >= 1e-9:
        for k in sorted(others, key=lambda k: -w[k]):
            if _WEIGHT_FLOOR <= round(w[k] + drift, 4) <= _WEIGHT_CEIL:
                w[k] = round(w[k] + drift, 4)
                break
    return w, round(abs(applied) * 100.0, 4)


# --------------------------------------------------------------------------- #
# Step 4 + 6 — AND-gate + report                                              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CalibrationProposal:
    target_component: str
    direction: str  # "down" | "up"
    applied_delta_pts: float
    old_weights: dict[str, float]
    new_weights: dict[str, float]
    cohort_dimension: str
    cohort: str
    attribution_evidence: dict[str, Any]
    divergence_evidence: dict[str, Any]
    confidence: str  # low | medium | high
    rationale: str
    strategy_version: str
    suggestion: str  # == rationale (the approval gate keys on this string)
    kind: str = "weight_calibration"
    status: str = "needs_review"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationReport:
    proposals: list[CalibrationProposal]
    attributions: list[ComponentAttribution]
    cohort_overrides_: list[CohortOverride]
    headline: str
    research_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "research_only": self.research_only,
            "weight_proposals": [p.to_dict() for p in self.proposals],
            "attributions": [asdict(a) for a in self.attributions],
            "cohort_overrides": [asdict(c) for c in self.cohort_overrides_],
        }


def _keep_best(
    store: dict[str, tuple[CohortOverride, str]],
    component: str,
    cohort: CohortOverride,
    conf: str,
) -> None:
    prev = store.get(component)
    if prev is None or _better((cohort, conf), prev):
        store[component] = (cohort, conf)


def _better(a: tuple[CohortOverride, str], b: tuple[CohortOverride, str]) -> bool:
    co_a, conf_a = a
    co_b, conf_b = b
    return (_CONF_ORDER[_GATE_TO_INTERNAL[conf_a]], co_a.net_override) > (
        _CONF_ORDER[_GATE_TO_INTERNAL[conf_b]],
        co_b.net_override,
    )


def _select_one(
    store: dict[str, tuple[CohortOverride, str]], *, exclude: str | None = None
) -> tuple[str, tuple[CohortOverride, str]] | None:
    items = [(c, v) for c, v in store.items() if c != exclude]
    if not items:
        return None
    items.sort(
        key=lambda kv: (
            -_CONF_ORDER[_GATE_TO_INTERNAL[kv[1][1]]],
            -kv[1][0].net_override,
            kv[0],
        )
    )
    return items[0]


def _rationale(component: str, direction: str, co: CohortOverride, a: ComponentAttribution) -> str:
    verb = "lower" if direction == "down" else "raise"
    return (
        f"Calibration: {verb} the {component} weight. Tony's overrides on "
        f"{co.dimension}='{co.cohort}' net {co.net_override:+d} (proven, {co.confidence}); "
        f"{component} separates winners from losers by only {a.separation} pts "
        f"(n={a.n}, {a.confidence})."
    )


def _headline(proposals: list[CalibrationProposal]) -> str:
    parts = [f"{p.direction} {p.target_component} ({p.confidence})" for p in proposals]
    return "Calibration proposal(s): " + "; ".join(parts)


def build_divergence_calibration(
    picks: list[PickRecord],
    ledger: dict[str, Any],
    current_weights: dict[str, float],
    *,
    max_delta_pts: float = 3.0,
    sep_eps: float = 3.0,
    min_net_override: int = 2,
    min_sample: int = 5,
    strategy_version: str = "v1",
) -> CalibrationReport:
    """Join attribution + divergence; emit at most one down and one up bounded nudge."""
    attrs = attribution(picks, sep_eps=sep_eps, min_sample=min_sample)
    attr_map = {a.component: a for a in attrs}
    cohorts = cohort_overrides(
        ledger, picks, min_net_override=min_net_override, min_sample=min_sample
    )

    down_candidates: dict[str, tuple[CohortOverride, str]] = {}
    up_candidates: dict[str, tuple[CohortOverride, str]] = {}

    for co in cohorts:
        ranked = cohort_component_elevation(picks, co.dimension, co.cohort)
        top = ranked[0][0] if ranked and ranked[0][1] > 0 else None
        if top is None:
            continue
        a = attr_map.get(top)
        if a is None or a.predictive is None:
            continue
        conf = _min_conf(_CONF_TO_GATE[a.confidence], _CONF_TO_GATE[co.confidence])
        if co.tony_correctly_overrode and a.predictive is False:
            _keep_best(down_candidates, top, co, conf)
        if co.tony_correctly_kept and a.predictive is True:
            _keep_best(up_candidates, top, co, conf)

    down = _select_one(down_candidates)
    up = _select_one(up_candidates, exclude=down[0] if down else None)

    proposals: list[CalibrationProposal] = []
    for selection, direction in ((down, "down"), (up, "up")):
        if selection is None:
            continue
        component, (co, conf) = selection
        a = attr_map[component]
        new_w, applied = apply_nudge(
            current_weights, component, direction, max_delta_pts=max_delta_pts
        )
        rationale = _rationale(component, direction, co, a)
        proposals.append(
            CalibrationProposal(
                target_component=component,
                direction=direction,
                applied_delta_pts=applied,
                old_weights={k: round(float(v), 4) for k, v in current_weights.items()},
                new_weights=new_w,
                cohort_dimension=co.dimension,
                cohort=co.cohort,
                attribution_evidence={
                    "win_mean": a.win_mean,
                    "loss_mean": a.loss_mean,
                    "separation": a.separation,
                    "n": a.n,
                    "confidence": a.confidence,
                },
                divergence_evidence={
                    "saved": co.saved,
                    "missed": co.missed,
                    "net_override": co.net_override,
                    "agreed_right": co.agreed_right,
                    "agreed_wrong": co.agreed_wrong,
                    "confidence": co.confidence,
                },
                confidence=conf,
                rationale=rationale,
                strategy_version=strategy_version,
                suggestion=rationale,
            )
        )

    headline = _headline(proposals) if proposals else "No calibration yet — evidence has not converged."
    return CalibrationReport(proposals, attrs, cohorts, headline)
