from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RiskConfig:
    starting_cash: float = 10_000.0
    max_position_fraction: float = 0.10
    max_risk_per_trade_fraction: float = 0.02
    max_drawdown_fraction: float = 0.15
    allow_shorting: bool = False
    allow_margin: bool = False
    live_trading_enabled: bool = False


@dataclass(frozen=True)
class BacktestConfig:
    starting_cash: float = 10_000.0
    fee_per_trade: float = 0.0
    slippage_fraction: float = 0.0005
    default_ticker: str = "SPY"
    default_period: str = "1y"


@dataclass(frozen=True)
class StrategyConfig:
    name: str = "moving_average_crossover"
    fast_window: int = 20
    slow_window: int = 50


@dataclass(frozen=True)
class AppConfig:
    risk: RiskConfig
    backtest: BacktestConfig
    strategy: StrategyConfig


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{key}' must be a mapping.")
    return value


def load_config(path: str | Path = "configs/default_config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig(risk=RiskConfig(), backtest=BacktestConfig(), strategy=StrategyConfig())

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError("Config file must contain a YAML mapping at the top level.")

    return AppConfig(
        risk=RiskConfig(**_section(raw, "risk")),
        backtest=BacktestConfig(**_section(raw, "backtest")),
        strategy=StrategyConfig(**_section(raw, "strategy")),
    )
