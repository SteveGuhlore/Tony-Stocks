from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from trading_bot.indicators import (
    average_true_range,
    dollar_volume,
    percent_return,
    relative_volume,
    rolling_high,
    rolling_volatility,
    simple_moving_average,
)
from trading_bot.scoring.score_models import ScoredStock
from trading_bot.settings import load_yaml
from trading_bot.utils.time_utils import utc_now_iso


@dataclass(frozen=True)
class ScoreWeights:
    trend_weight: float = 0.30
    momentum_weight: float = 0.25
    volume_weight: float = 0.20
    risk_weight: float = 0.15
    setup_quality_weight: float = 0.10


@dataclass(frozen=True)
class ScoreThresholds:
    min_avg_volume: float = 500_000
    min_dollar_volume: float = 5_000_000
    max_volatility_20d: float = 0.08
    min_volatility_20d: float = 0.006
    max_atr_pct: float = 0.08
    min_atr_pct: float = 0.012
    extended_from_sma20_pct: float = 0.12
    near_high_lookback: int = 60
    breakout_lookback: int = 20
    near_high_pct: float = 0.10
    pullback_to_sma20_pct: float = 0.035
    min_risk_reward: float = 1.5
    minimum_risk_reward: float = 1.5
    dead_return_20d_abs: float = 0.015
    suggested_stop_atr_multiple: float = 1.5
    suggested_target_r_multiple: float = 2.0
    stop_atr_multiplier: float = 1.5
    target_atr_multiplier: float = 3.0
    invalid_trade_plan_score_cap: float = 40.0
    etf_score_penalty: float = 8.0
    mega_cap_score_penalty: float = 5.0


@dataclass(frozen=True)
class TradePlanValidation:
    """Validated long-only trade plan values."""

    valid: bool
    entry: float
    stop: float
    target: float
    risk_reward: float
    status: str
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoleScoreAdjustments:
    benchmark: float = -15.0
    reference: float = -10.0
    primary_candidate: float = 4.0
    speculative_candidate: float = -2.0
    excluded_by_default: float = -25.0


@dataclass(frozen=True)
class ScoringConfig:
    weights: ScoreWeights
    thresholds: ScoreThresholds
    role_score_adjustments: RoleScoreAdjustments = field(default_factory=RoleScoreAdjustments)
    mode: str = "swing"


def load_scoring_config(path: str | Path) -> ScoringConfig:
    """Load scoring weights and thresholds."""
    raw = load_yaml(path)
    mode = str(raw.get("mode", "swing")).lower()
    weights = raw.get("weights", {}) or {}
    thresholds = raw.get("thresholds", {}) or {}
    role_adjustments = raw.get("role_score_adjustments", {}) or {}
    return ScoringConfig(
        weights=ScoreWeights(**weights),
        thresholds=ScoreThresholds(**thresholds),
        role_score_adjustments=RoleScoreAdjustments(**role_adjustments),
        mode=mode,
    )


def _latest(series: pd.Series, default: float = 0.0) -> float:
    value = series.dropna().iloc[-1] if not series.dropna().empty else default
    return float(value)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def validate_long_trade_plan(
    entry: float,
    stop: float,
    target: float,
    atr: float = 0.0,
    stop_atr_multiplier: float = 1.5,
    target_atr_multiplier: float = 3.0,
    minimum_risk_reward: float = 1.5,
) -> TradePlanValidation:
    """Validate and, when explainable, repair a long-only entry/stop/target plan."""
    warnings: list[str] = []
    reasons: list[str] = []
    entry = float(entry or 0.0)
    stop = float(stop or 0.0)
    target = float(target or 0.0)
    atr = max(float(atr or 0.0), 0.0)

    if entry <= 0:
        return TradePlanValidation(
            valid=False,
            entry=entry,
            stop=stop,
            target=target,
            risk_reward=0.0,
            status="invalid_entry",
            warnings=["Invalid long trade plan: entry must be greater than zero."],
        )

    stop_distance = max(atr * stop_atr_multiplier, entry * 0.03, 0.01)
    if stop <= 0 or stop >= entry:
        warnings.append("Invalid long trade plan: stop is not below entry. Applied ATR fallback stop.")
        stop = max(entry - stop_distance, 0.01)
        reasons.append("Stop uses configured ATR fallback below entry.")

    risk = entry - stop
    if risk <= 0:
        return TradePlanValidation(
            valid=False,
            entry=entry,
            stop=stop,
            target=target,
            risk_reward=0.0,
            status="invalid_stop",
            warnings=warnings + ["Invalid long trade plan: risk is not greater than zero."],
            reasons=reasons,
        )

    target_distance = max(atr * target_atr_multiplier, risk * minimum_risk_reward, entry * 0.03, 0.01)
    if target <= entry:
        warnings.append("Invalid long trade plan: target is not above entry. Applied ATR/risk fallback target.")
        target = entry + target_distance
        reasons.append("Target uses configured ATR/risk fallback above entry.")

    reward = target - entry
    if reward <= 0:
        return TradePlanValidation(
            valid=False,
            entry=entry,
            stop=stop,
            target=target,
            risk_reward=0.0,
            status="invalid_target",
            warnings=warnings + ["Invalid long trade plan: reward is not greater than zero."],
            reasons=reasons,
        )

    risk_reward = reward / risk
    if risk_reward <= 0:
        return TradePlanValidation(
            valid=False,
            entry=entry,
            stop=stop,
            target=target,
            risk_reward=0.0,
            status="invalid_risk_reward",
            warnings=warnings + ["Invalid long trade plan: risk/reward unavailable."],
            reasons=reasons,
        )

    status = "valid"
    if warnings:
        status = "valid_after_fallback"
    return TradePlanValidation(
        valid=True,
        entry=entry,
        stop=stop,
        target=target,
        risk_reward=risk_reward,
        status=status,
        warnings=warnings,
        reasons=reasons,
    )


class ScoreEngine:
    """Transparent, config-weighted stock scoring engine."""

    def __init__(self, config: ScoringConfig) -> None:
        self.config = config

    def score(
        self,
        symbol: str,
        data: pd.DataFrame,
        spy_data: pd.DataFrame | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        metadata: Any | None = None,
    ) -> ScoredStock:
        """Score one stock from recent OHLCV data."""
        if len(data) < 60:
            raise ValueError(f"{symbol} needs at least 60 rows for V1 scoring.")
        clean_tags = sorted({tag.lower() for tag in (tags or [])})
        universe_role = str(getattr(metadata, "universe_role", "primary_candidate") or "primary_candidate").lower()
        name = str(getattr(metadata, "name", "") or "")
        sector = str(getattr(metadata, "sector", "") or "")
        industry = str(getattr(metadata, "industry", "") or "")
        demo_profile = str(getattr(metadata, "demo_profile", "") or "")
        notes = str(getattr(metadata, "notes", "") or "")
        enriched = self._with_indicators(data)
        row = enriched.iloc[-1]
        close = float(row["close"])
        sma20 = float(row["sma20"])
        sma50 = float(row["sma50"])
        high_lookback = float(row["rolling_high"])
        avg_volume_20 = float(row["avg_volume_20"])
        dollar_volume_20 = float(row["dollar_volume_20"])
        return_5d = float(row["return_5d"])
        return_10d = float(row["return_10d"])
        return_20d = float(row["return_20d"])
        atr_14 = float(row["atr_14"])
        volatility_20d = float(row["volatility_20d"])
        rel_volume = float(row["relative_volume"])
        breakout_high = float(row["breakout_high"])

        reasons: list[str] = []
        warnings: list[str] = []
        if "etf" in clean_tags or "benchmark" in clean_tags:
            warnings.append("ETF/reference symbol, not an individual stock setup.")
        if universe_role in {"benchmark", "reference"}:
            warnings.append(f"Universe role is {universe_role}; use as context, not a primary buy-opportunity ranking.")
        if "mega_cap" in clean_tags:
            warnings.append("Mega-cap quality name may rank high due to liquidity/trend.")
        if universe_role == "speculative_candidate" or "speculative" in clean_tags:
            warnings.append("Speculative candidate; manually review liquidity, volatility, and news risk.")
        if universe_role == "excluded_by_default":
            warnings.append("Excluded-by-default research name; hidden from the primary dashboard view.")
        if self.config.mode == "swing":
            warnings.append("Demo data only; do not use for real trade decisions.")

        trend_score = 0.0
        if close > sma20 and close > sma50:
            trend_score += 35
            reasons.append("Price above 20-day and 50-day trend.")
        elif close > sma20 or close > sma50:
            trend_score += 18
            reasons.append("Price is above one key moving average.")
        if sma20 > sma50:
            trend_score += 30
            reasons.append("20-day trend is above 50-day trend.")
        if high_lookback > 0 and close >= high_lookback * (1 - self.config.thresholds.near_high_pct):
            trend_score += 20
            reasons.append("Near recent highs without needing a long-term quality bias.")
        if sma20 > 0 and abs(close / sma20 - 1) <= self.config.thresholds.pullback_to_sma20_pct:
            trend_score += 15
            reasons.append("Pullback near moving average support.")

        momentum_score = _clamp(45 + return_5d * 420 + return_10d * 300 + return_20d * 180)
        if return_5d > 0:
            reasons.append("Five-day momentum is positive.")
        if return_10d > 0:
            reasons.append("Ten-day momentum is positive.")
        if return_20d > 0:
            reasons.append("Twenty-day momentum is positive.")
        if abs(return_20d) < self.config.thresholds.dead_return_20d_abs and rel_volume < 0.95:
            momentum_score -= 18
            warnings.append("Price action is too flat for the swing timeframe.")
        if spy_data is not None and len(spy_data) >= 21:
            spy_return = float(spy_data["close"].pct_change(20).dropna().iloc[-1])
            relative_strength = return_20d - spy_return
            momentum_score = _clamp(momentum_score + relative_strength * 200)
            if relative_strength > 0:
                reasons.append("Twenty-day return is stronger than SPY.")

        volume_score = 0.0
        if avg_volume_20 >= self.config.thresholds.min_avg_volume:
            volume_score += 35
        else:
            warnings.append("Average volume is below configured minimum.")
        if dollar_volume_20 >= self.config.thresholds.min_dollar_volume:
            volume_score += 35
        else:
            warnings.append("Dollar volume is below configured minimum.")
        volume_score += _clamp((rel_volume - 0.8) * 50, 0, 30)
        if rel_volume >= 1.15:
            reasons.append("Relative volume above normal.")
            if universe_role in {"primary_candidate", "speculative_candidate"}:
                volume_score += 8
        elif rel_volume < 0.75:
            warnings.append("Relative volume is below normal.")

        atr_pct = atr_14 / close if close else 0.0
        risk_score = 100.0
        risk_score -= _clamp(volatility_20d / self.config.thresholds.max_volatility_20d * 45, 0, 55)
        risk_score -= _clamp(atr_pct / self.config.thresholds.max_atr_pct * 35, 0, 45)
        if volatility_20d > self.config.thresholds.max_volatility_20d:
            warnings.append("Volatility is above configured comfort range.")
        if atr_pct > self.config.thresholds.max_atr_pct:
            warnings.append("ATR risk is wide for swing timeframe.")
        if self.config.thresholds.min_atr_pct <= atr_pct <= self.config.thresholds.max_atr_pct:
            reasons.append("ATR percent is in the configured swing-trading range.")
            risk_score += 8
        if volatility_20d < self.config.thresholds.min_volatility_20d or atr_pct < self.config.thresholds.min_atr_pct:
            risk_score -= 15
            warnings.append("Volatility is low; setup may be too dead/flat.")
        risk_score = _clamp(risk_score)

        extension = (close / sma20 - 1) if sma20 else 0.0
        setup_quality_score = 45.0
        if close > sma20 > sma50:
            setup_quality_score += 18
        near_breakout = breakout_high > 0 and close >= breakout_high * (1 - self.config.thresholds.near_high_pct)
        pullback_quality = sma20 > 0 and abs(close / sma20 - 1) <= self.config.thresholds.pullback_to_sma20_pct and sma20 > sma50
        if 0 <= extension <= self.config.thresholds.extended_from_sma20_pct and near_breakout:
            setup_quality_score += 18
            reasons.append("Near 20-day high but not too extended.")
        elif pullback_quality:
            setup_quality_score += 18
            reasons.append("Pullback/retest quality is acceptable.")
        elif extension > self.config.thresholds.extended_from_sma20_pct:
            setup_quality_score -= 20
            warnings.append("Extended above short-term moving average.")
        if avg_volume_20 >= self.config.thresholds.min_avg_volume and risk_score >= 45:
            setup_quality_score += 10
        recent_range = data["close"].tail(20)
        base_range_pct = (float(recent_range.max()) - float(recent_range.min())) / close if close else 0
        base_building_quality = (
            sma20 > sma50
            and base_range_pct <= self.config.thresholds.extended_from_sma20_pct
            and abs(return_20d) <= self.config.thresholds.near_high_pct
        )
        if base_building_quality:
            setup_quality_score += 10
            reasons.append("Recent range suggests base-building rather than a chaotic move.")
        setup_quality_score = _clamp(setup_quality_score)

        minimum_risk_reward = max(self.config.thresholds.minimum_risk_reward, self.config.thresholds.min_risk_reward)
        stop_distance = max(atr_14 * self.config.thresholds.stop_atr_multiplier, close * 0.03)
        suggested_entry = close
        suggested_stop = max(close - stop_distance, 0.01)
        suggested_target = close + max(
            atr_14 * self.config.thresholds.target_atr_multiplier,
            (suggested_entry - suggested_stop) * self.config.thresholds.suggested_target_r_multiple,
        )
        trade_plan = validate_long_trade_plan(
            entry=suggested_entry,
            stop=suggested_stop,
            target=suggested_target,
            atr=atr_14,
            stop_atr_multiplier=self.config.thresholds.stop_atr_multiplier,
            target_atr_multiplier=self.config.thresholds.target_atr_multiplier,
            minimum_risk_reward=minimum_risk_reward,
        )
        suggested_entry = trade_plan.entry
        suggested_stop = trade_plan.stop
        suggested_target = trade_plan.target
        risk_reward_ratio = trade_plan.risk_reward
        reasons.extend(trade_plan.reasons)
        warnings.extend(trade_plan.warnings)
        if risk_reward_ratio >= minimum_risk_reward:
            reasons.append("Risk/reward above configured minimum.")
        else:
            warnings.append("Risk/reward is below configured minimum.")

        weights = self.config.weights
        final_score = (
            trend_score * weights.trend_weight
            + momentum_score * weights.momentum_weight
            + volume_score * weights.volume_weight
            + risk_score * weights.risk_weight
            + setup_quality_score * weights.setup_quality_weight
        )
        setup_category = self._setup_category(
            tags=clean_tags,
            trend_score=trend_score,
            momentum_score=momentum_score,
            setup_quality_score=setup_quality_score,
            risk_score=risk_score,
            extension=extension,
            near_breakout=near_breakout,
            pullback_quality=pullback_quality,
            return_5d=return_5d,
            return_20d=return_20d,
        )
        if "etf" in clean_tags or "benchmark" in clean_tags:
            final_score -= self.config.thresholds.etf_score_penalty
        if "mega_cap" in clean_tags:
            final_score -= self.config.thresholds.mega_cap_score_penalty
        final_score += self._role_score_adjustment(universe_role)
        if not trade_plan.valid:
            setup_category = "Invalid Trade Plan"
            setup_quality_score = min(setup_quality_score, 20)
            final_score = min(final_score, self.config.thresholds.invalid_trade_plan_score_cap)
        candidate_summary = self._candidate_summary(
            universe_role=universe_role,
            setup_category=setup_category,
            warnings=warnings,
            risk_reward_ratio=risk_reward_ratio,
            clean_tags=clean_tags,
        )

        return ScoredStock(
            symbol=symbol,
            scanned_at=utc_now_iso(),
            final_score=round(_clamp(final_score), 2),
            setup_category=setup_category,
            tags=clean_tags,
            universe_role=universe_role,
            name=name,
            sector=sector,
            industry=industry,
            demo_profile=demo_profile,
            notes=notes,
            candidate_summary=candidate_summary,
            trend_score=round(_clamp(trend_score), 2),
            momentum_score=round(_clamp(momentum_score), 2),
            volume_score=round(_clamp(volume_score), 2),
            risk_score=round(_clamp(risk_score), 2),
            setup_quality_score=round(_clamp(setup_quality_score), 2),
            latest_close=round(close, 4),
            avg_volume_20=round(avg_volume_20, 2),
            dollar_volume_20=round(dollar_volume_20, 2),
            return_5d=round(return_5d, 6),
            return_10d=round(return_10d, 6),
            return_20d=round(return_20d, 6),
            atr_14=round(atr_14, 4),
            atr_percent=round(atr_pct, 6),
            volatility_20d=round(volatility_20d, 6),
            relative_volume=round(rel_volume, 4),
            suggested_entry=round(suggested_entry, 4),
            suggested_stop=round(suggested_stop, 4),
            suggested_target_1=round(suggested_target, 4),
            risk_reward_ratio=round(risk_reward_ratio, 2),
            trade_plan_valid=trade_plan.valid,
            trade_plan_status=trade_plan.status,
            reasons=reasons,
            warnings=warnings,
        )

    def _with_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        df["sma20"] = simple_moving_average(df["close"], 20)
        df["sma50"] = simple_moving_average(df["close"], 50)
        df["avg_volume_20"] = df["volume"].rolling(20, min_periods=20).mean()
        df["dollar_volume_20"] = dollar_volume(df["close"], df["volume"], 20)
        df["return_5d"] = percent_return(df["close"], 5)
        df["return_10d"] = percent_return(df["close"], 10)
        df["return_20d"] = percent_return(df["close"], 20)
        df["atr_14"] = average_true_range(df, 14)
        df["volatility_20d"] = rolling_volatility(df["close"], 20)
        df["relative_volume"] = relative_volume(df["volume"], 20)
        df["rolling_high"] = rolling_high(df["close"], self.config.thresholds.near_high_lookback)
        df["breakout_high"] = rolling_high(df["close"], self.config.thresholds.breakout_lookback)
        return df.dropna()

    def _setup_category(
        self,
        tags: list[str],
        trend_score: float,
        momentum_score: float,
        setup_quality_score: float,
        risk_score: float,
        extension: float,
        near_breakout: bool,
        pullback_quality: bool,
        return_5d: float,
        return_20d: float,
    ) -> str:
        """Classify a swing setup into a review bucket."""
        if "etf" in tags or "benchmark" in tags:
            return "ETF / Benchmark Reference"
        if extension > self.config.thresholds.extended_from_sma20_pct:
            return "Overextended / Wait"
        if trend_score < 35 or momentum_score < 35 or risk_score < 35:
            return "Weak / Avoid"
        if "speculative" in tags and risk_score >= 35 and momentum_score >= 50:
            return "Speculative Watchlist"
        if near_breakout and setup_quality_score >= 65:
            return "Breakout Watch"
        if pullback_quality and trend_score >= 55:
            return "Pullback Watch"
        if return_5d > 0 and return_20d > 0 and momentum_score >= 60:
            return "Momentum Continuation"
        return "Weak / Avoid"

    def _role_score_adjustment(self, universe_role: str) -> float:
        """Return the configured score adjustment for a symbol role."""
        return float(getattr(self.config.role_score_adjustments, universe_role, 0.0))

    def _candidate_summary(
        self,
        universe_role: str,
        setup_category: str,
        warnings: list[str],
        risk_reward_ratio: float,
        clean_tags: list[str],
    ) -> str:
        """Explain whether the symbol belongs in the main opportunity list."""
        if universe_role in {"benchmark", "reference"}:
            return "Context/reference symbol; review separately from primary buy-opportunity candidates."
        if universe_role == "excluded_by_default":
            return "Excluded from the default opportunity list; inspect only when explicitly researching weak or risky names."
        if setup_category in {"Weak / Avoid", "Overextended / Wait", "Invalid Trade Plan", "Insufficient Data"}:
            return "Not a clean buy-opportunity candidate under current swing rules."
        if "speculative" in clean_tags or universe_role == "speculative_candidate":
            return "Speculative watchlist candidate; requires stricter manual review before any paper-trade plan."
        if risk_reward_ratio >= self.config.thresholds.min_risk_reward and not any("below configured minimum" in warning for warning in warnings):
            return "Primary candidate worth manual review under the configured swing rules."
        return "Candidate needs manual review because one or more setup checks are borderline."
