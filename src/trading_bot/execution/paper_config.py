"""Paper-trading configuration loading with fail-closed safety (phase 1).

The paper-trading subsystem auto-submits Tony's triggered picks as Alpaca PAPER
bracket orders. It is OFF by default and gated behind ``paper_trading.enabled``,
which is **independent** of ``live_trading_enabled`` (that stays false and blocks
any real-money path).

Safety posture: a block that requests ``enabled: true`` but is misconfigured
(bad sizing, zero limits, or a non-paper base URL) fails CLOSED — the loader
returns a disabled config with a ``disabled_reason`` rather than trading on bad
settings. The broker base URL must always be Alpaca's PAPER endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Alpaca paper-trading base URL. The live endpoint (api.alpaca.markets) is rejected.
PAPER_BASE_URL = "https://paper-api.alpaca.markets"

_VALID_TIF = {"day", "gtc"}


@dataclass(frozen=True)
class PaperTradingConfig:
    """Normalized, validated paper-trading settings.

    ``enabled`` is the master switch for this subsystem only. When a requested
    ``enabled: true`` fails validation, ``enabled`` is forced False and
    ``disabled_reason`` explains why (fail-closed).
    """

    enabled: bool = False
    risk_per_trade_pct: float = 1.0
    max_open_positions: int = 8
    max_notional_per_position: float = 5000.0
    max_daily_orders: int = 20
    # Portfolio concentration gate: max concurrent open positions in any one sector.
    # 0 = disabled (no sector cap). Per-position risk caps don't protect against a
    # correlated cohort (e.g. 15 regional banks) gapping together on one headline.
    max_positions_per_sector: int = 0
    bracket: bool = True
    # GTC by default: the entry is a market order (fills immediately, never rests), so
    # the only effect of "day" would be to expire the protective take-profit/stop-loss
    # legs at the close — leaving overnight positions UNPROTECTED. GTC keeps the bracket
    # protection persistent; only a never-resting market entry is involved either way.
    time_in_force: str = "gtc"
    gate_on_command_center: bool = False
    close_on_command_center_exit: bool = True
    # Block re-buying a symbol the same day it was already exited (esp. after a stop-out).
    # The duplicate gate only blocks CURRENTLY-open names; without this, a stop fill closes
    # the position and the next cycle immediately re-enters the loser. Default on.
    block_same_day_reentry: bool = True
    account_label: str = "tony"
    base_url: str = PAPER_BASE_URL
    disabled_reason: str | None = None


def is_paper_base_url(url: str | None) -> bool:
    """True only for an Alpaca paper-trading base URL."""
    return bool(url) and "paper-api.alpaca" in str(url).lower()


def assert_paper_base_url(url: str | None) -> None:
    """Raise ValueError unless ``url`` is an Alpaca paper endpoint.

    Called at broker startup so an order is never placed against a live base URL.
    """
    if not is_paper_base_url(url):
        raise ValueError(
            f"Refusing to use non-paper base URL for paper trading: {url!r}. "
            f"Expected an Alpaca paper endpoint like {PAPER_BASE_URL}."
        )


def _coerce_float(val: Any, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _coerce_int(val: Any, default: int) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def load_paper_trading_config(raw: dict[str, Any] | None) -> PaperTradingConfig:
    """Build a validated PaperTradingConfig from a raw config mapping.

    Missing/None/empty -> safe disabled defaults. A requested ``enabled: true``
    that fails validation -> disabled with a ``disabled_reason`` (fail-closed).
    """
    data = raw or {}
    requested_enabled = bool(data.get("enabled", False))

    risk = _coerce_float(data.get("risk_per_trade_pct", 1.0), 1.0)
    max_open = _coerce_int(data.get("max_open_positions", 8), 8)
    max_notional = _coerce_float(data.get("max_notional_per_position", 5000.0), 5000.0)
    max_daily = _coerce_int(data.get("max_daily_orders", 20), 20)
    # Sector cap: clamp negatives to 0 (disabled). 0 = no cap; >0 = max open per sector.
    max_per_sector = max(0, _coerce_int(data.get("max_positions_per_sector", 0), 0))
    base_url = str(data.get("base_url", PAPER_BASE_URL) or PAPER_BASE_URL)

    tif = str(data.get("time_in_force", "gtc")).strip().lower()
    if tif not in _VALID_TIF:
        tif = "gtc"  # safe default: persistent bracket protection, never silently day-expired

    defaults = PaperTradingConfig()
    common = {
        "risk_per_trade_pct": risk,
        "max_open_positions": max_open,
        "max_notional_per_position": max_notional,
        "max_daily_orders": max_daily,
        "max_positions_per_sector": max_per_sector,
        "bracket": bool(data.get("bracket", True)),
        "time_in_force": tif,
        "gate_on_command_center": bool(data.get("gate_on_command_center", False)),
        "close_on_command_center_exit": bool(
            data.get("close_on_command_center_exit", defaults.close_on_command_center_exit)
        ),
        "block_same_day_reentry": bool(
            data.get("block_same_day_reentry", defaults.block_same_day_reentry)
        ),
        "account_label": str(data.get("account_label", defaults.account_label)),
        "base_url": base_url,
    }

    if not requested_enabled:
        return PaperTradingConfig(enabled=False, disabled_reason=None, **common)

    # Validate the safety-critical gates; any failure disables trading.
    reason: str | None = None
    if not (0 < risk <= 100):
        reason = f"risk_per_trade_pct must be in (0, 100]; got {risk}"
    elif max_open < 1:
        reason = f"max_open_positions must be >= 1; got {max_open}"
    elif max_notional <= 0:
        reason = f"max_notional_per_position must be > 0; got {max_notional}"
    elif max_daily < 1:
        reason = f"max_daily_orders must be >= 1; got {max_daily}"
    elif not is_paper_base_url(base_url):
        reason = f"base_url must be an Alpaca paper endpoint; got {base_url!r}"

    if reason is not None:
        return PaperTradingConfig(enabled=False, disabled_reason=reason, **common)

    return PaperTradingConfig(enabled=True, disabled_reason=None, **common)
