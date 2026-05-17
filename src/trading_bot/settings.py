from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


API_KEY_ENV_VARS = (
    "POLYGON_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "FINNHUB_API_KEY",
    "FMP_API_KEY",
    "TWELVE_DATA_API_KEY",
)


@dataclass(frozen=True)
class ScannerSettings:
    provider: str = "demo_generated"
    database_path: Path = Path("data/trading_bot.db")
    outputs_dir: Path = Path("outputs")
    cache_dir: Path = Path("data/cache")
    log_dir: Path = Path("logs")
    lookback_days: int = 120
    timeframe: str = "daily"
    max_symbols: int = 100
    min_price: float = 5.0
    max_price: float = 500.0
    min_avg_volume: int = 500_000
    min_dollar_volume: float = 5_000_000
    score_threshold_watchlist: float = 70.0
    score_threshold_high_quality: float = 80.0
    live_trading_enabled: bool = False
    scoring_config_path: Path = Path("config/scoring_config.yaml")
    universe_config_path: Path = Path("config/universe_config.yaml")
    candidate_snapshots: dict[str, Any] | None = None
    snapshot_followup: dict[str, Any] | None = None
    demo_snapshot_seed: dict[str, Any] | None = None
    scheduled_watch: dict[str, Any] | None = None
    tony_stocks: dict[str, Any] | None = None


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping from disk."""
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Config file not found: {yaml_path}")
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {yaml_path}")
    return data


def load_dotenv_if_present(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE pairs from .env without overwriting OS env vars."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_scanner_settings(path: str | Path = "config/default_config.yaml") -> ScannerSettings:
    """Load scanner settings from YAML and environment."""
    load_dotenv_if_present()
    raw = load_yaml(path)
    allowed = set(ScannerSettings.__dataclass_fields__)
    values = {key: value for key, value in raw.items() if key in allowed}
    for key in ("database_path", "outputs_dir", "cache_dir", "log_dir", "scoring_config_path", "universe_config_path"):
        if key in values:
            values[key] = Path(values[key])
    settings = ScannerSettings(**values)
    if settings.live_trading_enabled:
        raise ValueError("live_trading_enabled must remain false for V1 scanner mode.")
    return settings


def configured_api_keys() -> dict[str, bool]:
    """Return which supported provider key environment variables are present."""
    load_dotenv_if_present()
    return {name: bool(os.getenv(name)) for name in API_KEY_ENV_VARS}
