"""Research Funnel v2 — pure multi-stage pre-Tony shortlisting logic.

The funnel turns a large candidate universe into a ranked shortlist *before* the
expensive technical scoring + Tony hand-off. It is deliberately split into:

- this module: a **pure** ``build_funnel`` that takes pre-fetched per-symbol signals
  and applies the stages (cheap screen -> catalyst/quality -> rank/shortlist). No
  network, no clock, no files — trivially unit-testable and deterministic.
- ``research_providers.gather_funnel_signals``: the impure layer that calls FMP /
  Finnhub / Twelve Data and assembles the ``SymbolSignals`` this module consumes.

Design rules (see docs/superpowers/specs/2026-06-03-research-funnel-design.md):
- Enrichment feeds are **advisory**: a missing signal never drops a symbol unless a
  filter is explicitly configured AND the datum is present. We never reject on
  absence — that would let a flaky API silently shrink the universe.
- Every stage records a count and a per-symbol drop reason for EOD diagnostics.
- Research only; no profitability claims.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class SymbolSignals:
    """Pre-fetched, provider-agnostic signals for one symbol. All optional."""

    symbol: str
    price: float | None = None
    dollar_volume: float | None = None
    relative_strength: float | None = None  # symbol return minus SPY return over window
    news_sentiment: float | None = None      # normalized -1..1 (bullish positive)
    recommendation_score: float | None = None  # -1..1 (analyst buy bias)
    revenue_growth: float | None = None      # YoY fraction, e.g. 0.20 = +20%
    earnings_date: date | None = None        # next scheduled report, if known


@dataclass(frozen=True)
class FunnelStageConfig:
    """Tunable funnel thresholds. Conservative defaults; everything off-by-default
    that could drop a symbol on enrichment data, so enabling the funnel without
    tuning behaves like a price/liquidity screen only."""

    # Stage 2 — cheap screen
    min_price: float = 5.0
    max_price: float = 500.0
    min_dollar_volume: float = 5_000_000.0
    min_relative_strength: float | None = None  # None = off
    earnings_blackout_days: int = 0              # 0 = off; N drops names reporting within N days
    # Stage 3 — catalyst / quality (advisory unless a threshold is set)
    sentiment_mode: str = "annotate"             # "annotate" | "filter"
    min_news_sentiment: float = -1.0             # used only when sentiment_mode == "filter"
    min_recommendation: float | None = None      # None = off
    min_revenue_growth: float | None = None      # None = off (e.g. -0.5 drops >50% revenue decline)
    # Stage 4 — rank / shortlist
    shortlist_size: int = 350
    weight_relative_strength: float = 1.0
    weight_sentiment: float = 0.5
    weight_recommendation: float = 0.5

    @classmethod
    def from_dict(cls, cfg: dict | None) -> "FunnelStageConfig":
        cfg = cfg or {}
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in cfg.items() if k in known})


@dataclass
class FunnelResult:
    """Outcome of a funnel run, with per-stage counts for EOD diagnostics."""

    universe_count: int
    after_screen: int
    after_catalyst: int
    shortlist: list[str]
    dropped: dict[str, str] = field(default_factory=dict)  # symbol -> stage:reason
    ranked_scores: dict[str, float] = field(default_factory=dict)

    @property
    def shortlist_count(self) -> int:
        return len(self.shortlist)

    def to_dict(self) -> dict:
        return {
            "universe_count": self.universe_count,
            "after_screen": self.after_screen,
            "after_catalyst": self.after_catalyst,
            "shortlist_count": self.shortlist_count,
            "dropped_count": len(self.dropped),
            "stage_counts": {
                "universe": self.universe_count,
                "screened": self.after_screen,
                "catalyst_passed": self.after_catalyst,
                "shortlist": self.shortlist_count,
            },
        }


def _passes_cheap_screen(
    sig: SymbolSignals, cfg: FunnelStageConfig, today: date
) -> tuple[bool, str]:
    """Stage 2: price / dollar-volume / relative-strength / earnings blackout.
    Returns (passed, reason_if_dropped). Missing data is never a drop reason."""
    if sig.price is not None and not (cfg.min_price <= sig.price <= cfg.max_price):
        return False, f"screen:price_out_of_band({sig.price:.2f})"
    if sig.dollar_volume is not None and sig.dollar_volume < cfg.min_dollar_volume:
        return False, f"screen:dollar_volume_below_floor({sig.dollar_volume:.0f})"
    if (
        cfg.min_relative_strength is not None
        and sig.relative_strength is not None
        and sig.relative_strength < cfg.min_relative_strength
    ):
        return False, f"screen:weak_relative_strength({sig.relative_strength:.3f})"
    if cfg.earnings_blackout_days > 0 and sig.earnings_date is not None:
        days_to_earnings = (sig.earnings_date - today).days
        if 0 <= days_to_earnings <= cfg.earnings_blackout_days:
            return False, f"screen:earnings_blackout(in_{days_to_earnings}d)"
    return True, ""


def _passes_catalyst(sig: SymbolSignals, cfg: FunnelStageConfig) -> tuple[bool, str]:
    """Stage 3: catalyst/quality gate. Only drops when a threshold is configured
    AND the datum is present (advisory-by-default)."""
    if (
        cfg.sentiment_mode == "filter"
        and sig.news_sentiment is not None
        and sig.news_sentiment < cfg.min_news_sentiment
    ):
        return False, f"catalyst:bearish_news({sig.news_sentiment:.2f})"
    if (
        cfg.min_recommendation is not None
        and sig.recommendation_score is not None
        and sig.recommendation_score < cfg.min_recommendation
    ):
        return False, f"catalyst:weak_recommendation({sig.recommendation_score:.2f})"
    if (
        cfg.min_revenue_growth is not None
        and sig.revenue_growth is not None
        and sig.revenue_growth < cfg.min_revenue_growth
    ):
        return False, f"catalyst:negative_growth({sig.revenue_growth:.2f})"
    return True, ""


def _rank_score(sig: SymbolSignals, cfg: FunnelStageConfig) -> float:
    """Composite rank score from advisory signals (missing -> 0 contribution)."""
    return (
        cfg.weight_relative_strength * (sig.relative_strength or 0.0)
        + cfg.weight_sentiment * (sig.news_sentiment or 0.0)
        + cfg.weight_recommendation * (sig.recommendation_score or 0.0)
    )


def build_funnel(
    universe: list[str],
    signals: dict[str, SymbolSignals],
    config: FunnelStageConfig,
    today: date,
    *,
    always_include: set[str] | None = None,
) -> FunnelResult:
    """Run the pure funnel stages over ``universe`` using pre-fetched ``signals``.

    ``always_include`` symbols (e.g. core benchmarks or currently-open positions)
    bypass the screen/catalyst drops and are guaranteed into the shortlist — the
    funnel must never silently drop a name the rest of the system depends on.
    Order within the shortlist is by descending rank score, then ticker for
    determinism. The shortlist is capped at ``config.shortlist_size`` but
    always-include names are added back even if that would exceed the cap.
    """
    always_include = {s.upper() for s in (always_include or set())}
    # De-dup while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for s in universe:
        u = s.upper()
        if u and u not in seen:
            seen.add(u)
            ordered.append(u)

    dropped: dict[str, str] = {}
    screened: list[str] = []
    for sym in ordered:
        if sym in always_include:
            screened.append(sym)
            continue
        sig = signals.get(sym, SymbolSignals(symbol=sym))
        ok, reason = _passes_cheap_screen(sig, config, today)
        if ok:
            screened.append(sym)
        else:
            dropped[sym] = reason

    catalyst_passed: list[str] = []
    for sym in screened:
        if sym in always_include:
            catalyst_passed.append(sym)
            continue
        sig = signals.get(sym, SymbolSignals(symbol=sym))
        ok, reason = _passes_catalyst(sig, config)
        if ok:
            catalyst_passed.append(sym)
        else:
            dropped[sym] = reason

    ranked_scores = {
        sym: _rank_score(signals.get(sym, SymbolSignals(symbol=sym)), config)
        for sym in catalyst_passed
    }
    ranked = sorted(catalyst_passed, key=lambda s: (-ranked_scores[s], s))

    shortlist = ranked[: max(0, config.shortlist_size)]
    # Guarantee always-include names survive the cap.
    shortlist_set = set(shortlist)
    for sym in catalyst_passed:
        if sym in always_include and sym not in shortlist_set:
            shortlist.append(sym)
            shortlist_set.add(sym)

    return FunnelResult(
        universe_count=len(ordered),
        after_screen=len(screened),
        after_catalyst=len(catalyst_passed),
        shortlist=shortlist,
        dropped=dropped,
        ranked_scores=ranked_scores,
    )
