from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ScoredStock:
    symbol: str
    scanned_at: str
    final_score: float
    setup_category: str
    tags: list[str]
    universe_role: str
    name: str
    sector: str
    industry: str
    demo_profile: str
    notes: str
    candidate_summary: str
    trend_score: float
    momentum_score: float
    volume_score: float
    risk_score: float
    setup_quality_score: float
    latest_close: float
    avg_volume_20: float
    dollar_volume_20: float
    return_5d: float
    return_10d: float
    return_20d: float
    atr_14: float
    atr_percent: float
    volatility_20d: float
    relative_volume: float
    suggested_entry: float
    suggested_stop: float
    suggested_target_1: float
    risk_reward_ratio: float
    trade_plan_valid: bool
    trade_plan_status: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a serializable dictionary."""
        return asdict(self)
