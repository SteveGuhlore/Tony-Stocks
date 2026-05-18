"""Deterministic candidate analysis for Tony Stocks analyst mode.

Produces structured reads for each scanned candidate:
  - technical setup
  - volume and liquidity
  - risk / trade plan
  - market context relative to SPY / QQQ / IWM / DIA
  - data quality
  - outcome context from historical snapshots

Allowed recommended_actions:
  snapshot_only | watch_only | avoid | needs_more_data | reference_only

Safety constraints (must never be relaxed in this module):
  - No LLM calls.
  - No broker execution.
  - No paper trades.
  - No live trades.
  - No order placement.
  - Seeded demo fixtures excluded from outcome learning by default.
  - Alpaca IEX single-exchange notice always included in IEX data quality reads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from trading_bot.analytics.outcomes import OutcomeAnalytics, score_bucket
from trading_bot.scoring.score_models import ScoredStock


# ── Setup read labels ─────────────────────────────────────────────────────────
SETUP_BREAKOUT = "breakout_candidate"
SETUP_PULLBACK = "pullback_candidate"
SETUP_MOMENTUM = "momentum_continuation"
SETUP_OVEREXTENDED = "overextended"
SETUP_WEAK = "weak_downtrend"
SETUP_REFERENCE = "reference_only"
SETUP_INSUFFICIENT = "insufficient_data"

# ── Volume read labels ────────────────────────────────────────────────────────
VOL_CONFIRMATION = "volume_confirmation"
VOL_LOW_LIQUIDITY = "low_liquidity_concern"
VOL_LOW_DOLLAR = "dollar_volume_concern"
VOL_RELATIVE_STRENGTH = "relative_volume_strength"
VOL_SPECULATIVE_RISK = "speculative_volume_risk"

# ── Risk read labels ──────────────────────────────────────────────────────────
RISK_ACCEPTABLE = "acceptable_risk"
RISK_STRONG_RR = "strong_risk_reward"
RISK_INVALID_PLAN = "avoid_invalid_plan"
RISK_WIDE_ATR = "wide_atr_concern"
RISK_HIGH_VOLATILITY = "high_volatility_concern"

# ── Market context labels ─────────────────────────────────────────────────────
MKT_SUPPORTIVE = "market_supportive"
MKT_MIXED = "market_mixed"
MKT_WEAK = "market_weak"
MKT_MISSING = "benchmark_data_missing"

# ── Data quality labels ───────────────────────────────────────────────────────
DQ_ALPACA_IEX = "alpaca_iex_real_data"
DQ_DEMO = "demo_data"
DQ_FALLBACK = "fallback_data"
DQ_STALE = "stale_data"
DQ_SEEDED = "seeded_demo_fixture"

# ── Outcome context labels ────────────────────────────────────────────────────
OC_NOT_ENOUGH = "not_enough_history"
OC_POSITIVE = "historically_positive"
OC_NEGATIVE = "historically_negative"
OC_MIXED = "historically_mixed"

# ── Priority labels ───────────────────────────────────────────────────────────
PRI_HIGH = "high_priority"
PRI_WATCH = "watch"
PRI_LOW = "low_priority"
PRI_AVOID = "avoid"
PRI_REFERENCE = "reference_only"

# ── Analysis versioning ───────────────────────────────────────────────────────
TONY_ANALYSIS_VERSION = "v1"

# ── Recommended actions (exhaustive — no paper_trade or live_trade) ───────────
ACTION_SNAPSHOT = "snapshot_only"
ACTION_WATCH = "watch_only"
ACTION_AVOID = "avoid"
ACTION_NEEDS_DATA = "needs_more_data"
ACTION_REFERENCE = "reference_only"

ALLOWED_ACTIONS = frozenset({ACTION_SNAPSHOT, ACTION_WATCH, ACTION_AVOID, ACTION_NEEDS_DATA, ACTION_REFERENCE})

# ── Internal thresholds ───────────────────────────────────────────────────────
_MIN_AVG_VOLUME = 500_000
_MIN_DOLLAR_VOLUME = 5_000_000
_HIGH_SCORE_THRESHOLD = 80.0
_WATCH_SCORE_THRESHOLD = 65.0
_STRONG_RR_THRESHOLD = 2.5
_MIN_RR_THRESHOLD = 1.5
_WIDE_ATR_THRESHOLD = 0.07
_HIGH_VOLATILITY_THRESHOLD = 0.07
_OUTCOME_MIN_SNAPSHOTS = 5
_OUTCOME_POSITIVE_RATE = 0.45
_OUTCOME_NEGATIVE_RATE = 0.45


@dataclass(frozen=True)
class CandidateAnalysis:
    """One analyst read for a single scanned candidate.

    Tony is analyzing, not trading. No paper trades or orders are created.
    """

    symbol: str
    priority_label: str
    setup_read: str
    technical_read: str
    volume_read: str
    risk_read: str
    market_context_read: str
    data_quality_read: str
    tony_hypothesis: str
    outcome_context: str
    reasons: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    recommended_action: str = ACTION_WATCH

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "priority_label": self.priority_label,
            "setup_read": self.setup_read,
            "technical_read": self.technical_read,
            "volume_read": self.volume_read,
            "risk_read": self.risk_read,
            "market_context_read": self.market_context_read,
            "data_quality_read": self.data_quality_read,
            "tony_hypothesis": self.tony_hypothesis,
            "outcome_context": self.outcome_context,
            "reasons": list(self.reasons),
            "concerns": list(self.concerns),
            "recommended_action": self.recommended_action,
        }


class MarketContext:
    """Lightweight market direction read derived from benchmark scan rows.

    Uses 20-day return of SPY / QQQ / IWM / DIA when available.
    Never fetches additional data — only uses what the scanner already produced.
    """

    def __init__(self, benchmark_rows: list[ScoredStock] | None = None) -> None:
        self._rows: dict[str, ScoredStock] = {}
        for row in (benchmark_rows or []):
            if row.universe_role in ("benchmark", "reference") or "benchmark" in row.tags or "etf" in row.tags:
                self._rows[row.symbol] = row

    def context_label(self) -> str:
        benchmarks = [self._rows.get(s) for s in ("SPY", "QQQ", "IWM", "DIA") if s in self._rows]
        if not benchmarks:
            return MKT_MISSING
        returns = [b.return_20d for b in benchmarks]
        positive = sum(1 for r in returns if r > 0)
        negative = sum(1 for r in returns if r < 0)
        total = len(returns)
        if positive > total // 2:
            return MKT_SUPPORTIVE
        if negative > total // 2:
            return MKT_WEAK
        return MKT_MIXED

    def description(self) -> str:
        label = self.context_label()
        spy = self._rows.get("SPY")
        spy_note = f"SPY {spy.return_20d * 100:+.1f}% 20d" if spy else "SPY not in scan"
        if label == MKT_SUPPORTIVE:
            return f"Market context is supportive ({spy_note}). Broad benchmarks trending higher."
        if label == MKT_WEAK:
            return f"Market context is weak ({spy_note}). Benchmarks under pressure."
        if label == MKT_MIXED:
            return f"Market context is mixed ({spy_note}). Benchmarks sending conflicting signals."
        return "No benchmark data in scan results — market direction unknown."


def analyze_candidates(
    candidates: list[ScoredStock],
    benchmark_rows: list[ScoredStock] | None = None,
    provider_name: str = "demo_generated",
    fallback_symbols: list[str] | None = None,
    stale_symbols: list[str] | None = None,
    outcome_snapshots: pd.DataFrame | None = None,
    include_seeded_demo: bool = False,
) -> list[CandidateAnalysis]:
    """Return one CandidateAnalysis per candidate.

    Benchmark / reference symbols receive a reference_only analysis.
    Outcome learning uses existing snapshots only; seeded fixtures excluded by default.
    No LLMs, no paper trades, no orders.
    """
    market = MarketContext(benchmark_rows)
    ctx_label = market.context_label()
    ctx_desc = market.description()
    fallback_set = set(fallback_symbols or [])
    stale_set = set(stale_symbols or [])
    outcome_cache: dict[tuple[str, str, str], str] = {}

    results: list[CandidateAnalysis] = []
    for stock in candidates:
        analysis = _analyze_one(
            stock=stock,
            ctx_label=ctx_label,
            ctx_desc=ctx_desc,
            provider_name=provider_name,
            fallback_set=fallback_set,
            stale_set=stale_set,
            outcome_snapshots=outcome_snapshots,
            outcome_cache=outcome_cache,
            include_seeded_demo=include_seeded_demo,
        )
        results.append(analysis)
    return results


# ── Private helpers ───────────────────────────────────────────────────────────

def _analyze_one(
    stock: ScoredStock,
    ctx_label: str,
    ctx_desc: str,
    provider_name: str,
    fallback_set: set[str],
    stale_set: set[str],
    outcome_snapshots: pd.DataFrame | None,
    outcome_cache: dict[tuple[str, str, str], str],
    include_seeded_demo: bool,
) -> CandidateAnalysis:
    reasons: list[str] = []
    concerns: list[str] = []

    dq_label, dq_text = _data_quality(stock, provider_name, fallback_set, stale_set)
    setup_label, technical_text = _setup_read(stock)
    vol_label, vol_text = _volume_read(stock)
    risk_label, risk_text = _risk_read(stock)

    bucket = score_bucket(stock.final_score)
    cache_key = (stock.setup_category, bucket, stock.universe_role)
    if cache_key not in outcome_cache:
        outcome_cache[cache_key] = _outcome_context(
            stock.setup_category,
            bucket,
            stock.universe_role,
            outcome_snapshots,
            include_seeded_demo,
        )
    oc_label = outcome_cache[cache_key]

    priority, action = _priority_and_action(stock, setup_label, risk_label, dq_label)

    # build reasons from scorer output + analysis
    reasons.extend(stock.reasons[:5])
    if risk_label in (RISK_STRONG_RR, RISK_ACCEPTABLE):
        reasons.append(f"Risk/reward is {stock.risk_reward_ratio:.1f}x — trade plan is {stock.trade_plan_status}.")
    if vol_label == VOL_CONFIRMATION:
        reasons.append("Volume is confirming the move; liquidity is adequate.")
    if ctx_label == MKT_SUPPORTIVE:
        reasons.append("Broad market is supportive.")

    # build concerns from scanner warnings + analysis
    for w in stock.warnings[:4]:
        concerns.append(w)
    if dq_label in (DQ_FALLBACK, DQ_STALE, DQ_SEEDED):
        concerns.append(f"Data quality flag: {dq_label}. Signals may not reflect real market prices.")
    if ctx_label == MKT_WEAK:
        concerns.append("Broad market is weak; setup faces headwinds.")
    if oc_label == OC_NEGATIVE:
        concerns.append("Historical outcomes have been negative for similar setups.")

    hypothesis = _build_hypothesis(stock, setup_label, vol_label, risk_label, ctx_label, oc_label, dq_label, priority)

    return CandidateAnalysis(
        symbol=stock.symbol,
        priority_label=priority,
        setup_read=setup_label,
        technical_read=technical_text,
        volume_read=vol_label,
        risk_read=risk_label,
        market_context_read=ctx_label,
        data_quality_read=dq_label,
        tony_hypothesis=hypothesis,
        outcome_context=oc_label,
        reasons=reasons,
        concerns=concerns,
        recommended_action=action,
    )


def _setup_read(stock: ScoredStock) -> tuple[str, str]:
    role = stock.universe_role
    category = stock.setup_category

    if role in ("benchmark", "reference"):
        return SETUP_REFERENCE, (
            f"{stock.symbol} is a {role} symbol used for market context, not a primary swing candidate."
        )
    if category == "ETF / Benchmark Reference":
        return SETUP_REFERENCE, (
            f"{stock.symbol} is tagged as an ETF or benchmark — use for context only, not a directional setup."
        )
    if category == "Invalid Trade Plan":
        return SETUP_INSUFFICIENT, (
            f"{stock.symbol} scored {stock.final_score:.0f} but the trade plan is invalid ({stock.trade_plan_status}). "
            "Entry, stop, or target levels need resolution before this can be treated as a signal."
        )
    if category == "Overextended / Wait":
        return SETUP_OVEREXTENDED, (
            f"{stock.symbol} has moved significantly above near-term support and is extended. "
            "The setup favors patience — a pullback or base-building phase would improve the entry."
        )
    if category == "Weak / Avoid":
        direction = "downtrend" if stock.return_20d < 0 else "sideways/flat"
        return SETUP_WEAK, (
            f"{stock.symbol} is in a {direction} with trend score {stock.trend_score:.0f} "
            f"and momentum score {stock.momentum_score:.0f} below swing minimums. "
            "Not a clean setup under current rules."
        )
    if category == "Speculative Watchlist":
        return SETUP_MOMENTUM, (
            f"{stock.symbol} is a speculative candidate with momentum "
            f"({stock.return_5d * 100:+.1f}% 5-day, {stock.return_20d * 100:+.1f}% 20-day). "
            "Requires extra scrutiny: liquidity, volatility, and news risk must be manually reviewed."
        )
    if category == "Breakout Watch":
        return SETUP_BREAKOUT, (
            f"{stock.symbol} is setting up near a recent high with positive price momentum. "
            f"5-day return {stock.return_5d * 100:+.1f}%, trend score {stock.trend_score:.0f}. "
            "A confirmed break above resistance on volume would validate the entry."
        )
    if category == "Pullback Watch":
        return SETUP_PULLBACK, (
            f"{stock.symbol} has pulled back toward moving average support within an uptrend. "
            f"Trend score {stock.trend_score:.0f}, 20-day return {stock.return_20d * 100:+.1f}%. "
            "Look for stabilization or a reversal candle near support before acting."
        )
    if category == "Momentum Continuation":
        return SETUP_MOMENTUM, (
            f"{stock.symbol} is in active momentum with positive short and intermediate returns "
            f"({stock.return_5d * 100:+.1f}% 5-day, {stock.return_20d * 100:+.1f}% 20-day). "
            "Continuation setups require monitoring for reversal signs."
        )
    return SETUP_INSUFFICIENT, (
        f"{stock.symbol} setup category '{category}' is unclear or borderline. "
        "More data or a cleaner trend needed before acting."
    )


def _volume_read(stock: ScoredStock) -> tuple[str, str]:
    tags = set(stock.tags)
    is_speculative = "speculative" in tags or stock.universe_role == "speculative_candidate"

    low_avg = stock.avg_volume_20 < _MIN_AVG_VOLUME
    low_dollar = stock.dollar_volume_20 < _MIN_DOLLAR_VOLUME
    high_rel_vol = stock.relative_volume >= 1.2
    low_rel_vol = stock.relative_volume < 0.75

    if (low_avg or low_dollar) and is_speculative:
        return VOL_SPECULATIVE_RISK, (
            f"{stock.symbol} has thin liquidity for a speculative name: "
            f"${stock.dollar_volume_20 / 1_000_000:.1f}M dollar volume, "
            f"{stock.avg_volume_20 / 1_000:.0f}K average volume. "
            "Thin markets increase spread and slippage risk significantly."
        )
    if low_dollar:
        return VOL_LOW_DOLLAR, (
            f"{stock.symbol} dollar volume ${stock.dollar_volume_20 / 1_000_000:.1f}M is below the configured minimum. "
            "Lower dollar volume limits practical position sizing and increases slippage risk."
        )
    if low_avg:
        return VOL_LOW_LIQUIDITY, (
            f"{stock.symbol} average volume {stock.avg_volume_20 / 1_000:.0f}K is below the configured minimum. "
            "Lower share liquidity may make clean entry and exit more difficult."
        )
    if high_rel_vol:
        label = VOL_RELATIVE_STRENGTH if low_rel_vol else VOL_CONFIRMATION
        return label, (
            f"{stock.symbol} shows elevated relative volume ({stock.relative_volume:.2f}x normal). "
            f"Dollar volume ${stock.dollar_volume_20 / 1_000_000:.1f}M, "
            f"average volume {stock.avg_volume_20 / 1_000:.0f}K. "
            "Volume expansion can confirm a setup if price moves cleanly."
        )
    if low_rel_vol:
        return VOL_LOW_LIQUIDITY, (
            f"{stock.symbol} relative volume is below normal ({stock.relative_volume:.2f}x). "
            f"Dollar volume ${stock.dollar_volume_20 / 1_000_000:.1f}M. "
            "Low relative volume during a move is a concern."
        )
    return VOL_CONFIRMATION, (
        f"{stock.symbol} volume is adequate: ${stock.dollar_volume_20 / 1_000_000:.1f}M dollar volume, "
        f"{stock.avg_volume_20 / 1_000:.0f}K average, {stock.relative_volume:.2f}x relative."
    )


def _risk_read(stock: ScoredStock) -> tuple[str, str]:
    if not stock.trade_plan_valid:
        return RISK_INVALID_PLAN, (
            f"{stock.symbol} trade plan is invalid ({stock.trade_plan_status}). "
            "Do not act on this signal until entry/stop/target levels are validated. "
            "No recommended action beyond reviewing the setup."
        )

    stop_pct = abs(stock.suggested_entry - stock.suggested_stop) / stock.suggested_entry if stock.suggested_entry else 0
    parts: list[str] = [
        f"risk/reward {stock.risk_reward_ratio:.1f}x",
        f"stop distance {stop_pct * 100:.1f}%",
        f"ATR {stock.atr_percent * 100:.1f}%",
    ]

    label = RISK_ACCEPTABLE
    if stock.risk_reward_ratio >= _STRONG_RR_THRESHOLD:
        label = RISK_STRONG_RR
    elif stock.risk_reward_ratio < _MIN_RR_THRESHOLD:
        label = RISK_WIDE_ATR

    if stock.atr_percent > _WIDE_ATR_THRESHOLD:
        label = RISK_WIDE_ATR
        parts.append("ATR is wide for swing timeframe")
    if stock.volatility_20d > _HIGH_VOLATILITY_THRESHOLD:
        label = RISK_HIGH_VOLATILITY
        parts.append(f"20-day volatility {stock.volatility_20d * 100:.1f}% is elevated")

    return label, f"{stock.symbol}: {', '.join(parts)}. Trade plan: {stock.trade_plan_status}."


def _data_quality(
    stock: ScoredStock,
    provider_name: str,
    fallback_set: set[str],
    stale_set: set[str],
) -> tuple[str, str]:
    is_seeded = (
        "demo_seeded" in stock.tags
        or "outcome_fixture" in stock.tags
        or "seeded demo" in stock.notes.lower()
        or "demo seeded snapshot" in stock.notes.lower()
    )
    if is_seeded:
        return DQ_SEEDED, (
            f"{stock.symbol} is a seeded demo fixture. Results are for testing and research only. "
            "Not a real market signal."
        )
    if stock.symbol in stale_set:
        return DQ_STALE, (
            f"{stock.symbol} returned stale data from {provider_name}. "
            "The most recent bar may be older than the configured freshness threshold. "
            "Signals may not reflect current market conditions."
        )
    if stock.symbol in fallback_set:
        return DQ_FALLBACK, (
            f"{stock.symbol} data fell back from {provider_name} to demo-generated prices. "
            "This is a synthetic approximation — not real market data. "
            "Do not act on this signal until real data is confirmed."
        )
    is_demo = any("demo data only" in w.lower() for w in stock.warnings) or provider_name == "demo_generated"
    if is_demo:
        return DQ_DEMO, (
            f"{stock.symbol} is using demo-generated price data. "
            "Signals are deterministic approximations for research and testing, "
            "not real market prices. Do not use for real trade decisions."
        )
    if "alpaca_iex" in provider_name:
        return DQ_ALPACA_IEX, (
            f"{stock.symbol} data is from Alpaca IEX ({provider_name}). "
            "IEX is a single-exchange feed — not full SIP consolidated tape. "
            "Prices may differ from other venues. For research and scanning only."
        )
    return DQ_DEMO, f"{stock.symbol} data quality is unconfirmed (provider: {provider_name})."


def _outcome_context(
    setup_category: str,
    bucket: str,
    universe_role: str,
    outcome_snapshots: pd.DataFrame | None,
    include_seeded_demo: bool,
) -> str:
    if outcome_snapshots is None or outcome_snapshots.empty:
        return OC_NOT_ENOUGH

    analytics = OutcomeAnalytics(outcome_snapshots, include_seeded_demo=include_seeded_demo)
    by_category = analytics.grouped_by("setup_category")
    if by_category.empty:
        return OC_NOT_ENOUGH

    row = by_category[by_category["setup_category"] == setup_category]
    if row.empty:
        return OC_NOT_ENOUGH

    n = int(row.iloc[0].get("total_snapshots", 0))
    if n < _OUTCOME_MIN_SNAPSHOTS:
        return OC_NOT_ENOUGH

    target_rate = float(row.iloc[0].get("target_hit_rate", 0))
    failure_rate = float(row.iloc[0].get("failure_rate", 0))

    if target_rate >= _OUTCOME_POSITIVE_RATE:
        return OC_POSITIVE
    if failure_rate >= _OUTCOME_NEGATIVE_RATE:
        return OC_NEGATIVE
    return OC_MIXED


def _priority_and_action(
    stock: ScoredStock,
    setup_label: str,
    risk_label: str,
    dq_label: str,
) -> tuple[str, str]:
    role = stock.universe_role

    if role in ("benchmark", "reference"):
        return PRI_REFERENCE, ACTION_REFERENCE

    if not stock.trade_plan_valid:
        return PRI_AVOID, ACTION_AVOID

    if setup_label in (SETUP_OVEREXTENDED, SETUP_WEAK, SETUP_INSUFFICIENT, SETUP_REFERENCE):
        return PRI_AVOID, ACTION_AVOID

    if dq_label in (DQ_FALLBACK, DQ_STALE):
        return PRI_LOW, ACTION_NEEDS_DATA

    if dq_label == DQ_SEEDED:
        return PRI_LOW, ACTION_AVOID

    is_risk_concern = risk_label in (RISK_WIDE_ATR, RISK_HIGH_VOLATILITY)

    if stock.final_score >= _HIGH_SCORE_THRESHOLD and not is_risk_concern:
        return PRI_HIGH, ACTION_SNAPSHOT

    if stock.final_score >= _WATCH_SCORE_THRESHOLD:
        return PRI_WATCH, ACTION_WATCH

    return PRI_LOW, ACTION_WATCH


def _build_hypothesis(
    stock: ScoredStock,
    setup_label: str,
    vol_label: str,
    risk_label: str,
    ctx_label: str,
    oc_label: str,
    dq_label: str,
    priority: str,
) -> str:
    if priority == PRI_REFERENCE:
        return (
            f"{stock.symbol} is a {stock.universe_role} symbol providing market context. "
            "No directional trade hypothesis — use for benchmark comparison only."
        )
    if priority == PRI_AVOID:
        if not stock.trade_plan_valid:
            return (
                f"{stock.symbol}: Trade plan is invalid ({stock.trade_plan_status}). "
                "Avoid until entry/stop/target levels are resolved. Tony is analyzing, not trading."
            )
        return (
            f"{stock.symbol} (score {stock.final_score:.0f}): Setup '{stock.setup_category}' does not meet "
            "swing entry criteria. Current conditions favor waiting."
        )

    setup_phrases = {
        SETUP_BREAKOUT: "is approaching a potential breakout",
        SETUP_PULLBACK: "has pulled back to support in an uptrend",
        SETUP_MOMENTUM: "is in active momentum",
    }
    setup_phrase = setup_phrases.get(setup_label, f"is in a {stock.setup_category} setup")
    parts = [f"{stock.symbol} (score {stock.final_score:.0f}) {setup_phrase}."]

    vol_notes = {
        VOL_CONFIRMATION: "Volume is confirming.",
        VOL_RELATIVE_STRENGTH: f"Relative volume elevated ({stock.relative_volume:.2f}x).",
        VOL_LOW_LIQUIDITY: "Thin share liquidity — watch execution.",
        VOL_LOW_DOLLAR: "Dollar volume below minimum.",
        VOL_SPECULATIVE_RISK: "Speculative liquidity risk.",
    }
    if vol_label in vol_notes:
        parts.append(vol_notes[vol_label])

    risk_notes = {
        RISK_STRONG_RR: f"Risk/reward strong ({stock.risk_reward_ratio:.1f}x).",
        RISK_ACCEPTABLE: f"Risk/reward acceptable ({stock.risk_reward_ratio:.1f}x).",
        RISK_WIDE_ATR: f"ATR is wide ({stock.atr_percent * 100:.1f}%) — tighter sizing warranted.",
        RISK_HIGH_VOLATILITY: f"Elevated volatility ({stock.volatility_20d * 100:.1f}% 20d) — reduce size.",
    }
    if risk_label in risk_notes:
        parts.append(risk_notes[risk_label])

    ctx_notes = {
        MKT_SUPPORTIVE: "Broad market is supportive.",
        MKT_MIXED: "Market context is mixed.",
        MKT_WEAK: "Broad market is weak — heightened caution.",
        MKT_MISSING: "No benchmark data for market context.",
    }
    if ctx_label in ctx_notes:
        parts.append(ctx_notes[ctx_label])

    oc_notes = {
        OC_NOT_ENOUGH: "Not enough outcome history for this setup.",
        OC_POSITIVE: "Historical outcomes are positive for this setup category.",
        OC_NEGATIVE: "Historical outcomes have been negative for similar setups — extra scrutiny needed.",
        OC_MIXED: "Historical outcomes are mixed.",
    }
    if oc_label in oc_notes:
        parts.append(oc_notes[oc_label])

    dq_notes = {
        DQ_DEMO: "Note: demo-generated data — not real market prices.",
        DQ_FALLBACK: "Caution: data fell back to demo this cycle.",
        DQ_STALE: "Caution: data may be stale.",
        DQ_SEEDED: "Seeded fixture only — not a real market signal.",
        DQ_ALPACA_IEX: "Data: Alpaca IEX (single-exchange feed, not full SIP tape).",
    }
    if dq_label in dq_notes:
        parts.append(dq_notes[dq_label])

    parts.append("Tony is analyzing, not trading.")
    return " ".join(parts)
