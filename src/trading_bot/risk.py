from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    quantity: int
    reason: str


@dataclass
class RiskManager:
    starting_cash: float = 10_000.0
    max_position_fraction: float = 0.10
    max_risk_per_trade_fraction: float = 0.02
    max_drawdown_fraction: float = 0.15
    allow_shorting: bool = False
    allow_margin: bool = False
    live_trading_enabled: bool = False

    def max_position_value(self, equity: float) -> float:
        return max(0.0, equity * self.max_position_fraction)

    def calculate_quantity(self, equity: float, price: float) -> int:
        if price <= 0:
            raise ValueError("price must be greater than 0")
        max_value = self.max_position_value(equity)
        return int(max_value // price)

    def approve_order(self, side: str, equity: float, price: float, current_position: int = 0) -> RiskDecision:
        normalized_side = side.lower().strip()
        if normalized_side not in {"buy", "sell"}:
            return RiskDecision(False, 0, f"Unsupported side: {side}")

        if normalized_side == "sell" and current_position <= 0 and not self.allow_shorting:
            return RiskDecision(False, 0, "Shorting is disabled.")

        quantity = self.calculate_quantity(equity=equity, price=price)
        if quantity <= 0:
            return RiskDecision(False, 0, "Calculated quantity is 0. Equity or price is too small.")

        return RiskDecision(True, quantity, "Approved by risk manager.")

    def drawdown_breached(self, peak_equity: float, current_equity: float) -> bool:
        if peak_equity <= 0:
            return False
        drawdown = (peak_equity - current_equity) / peak_equity
        return drawdown >= self.max_drawdown_fraction
