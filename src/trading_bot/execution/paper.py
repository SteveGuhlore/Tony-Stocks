from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PaperOrder:
    symbol: str
    side: str
    quantity: int
    price: float
    created_at: datetime


class PaperBroker:
    """Simple in-memory paper broker for tests and early experiments."""

    def __init__(self) -> None:
        self.orders: list[PaperOrder] = []

    def submit_order(self, symbol: str, side: str, quantity: int, price: float) -> PaperOrder:
        if quantity <= 0:
            raise ValueError("quantity must be greater than 0")
        if price <= 0:
            raise ValueError("price must be greater than 0")
        order = PaperOrder(
            symbol=symbol.upper(),
            side=side.lower(),
            quantity=quantity,
            price=price,
            created_at=datetime.now(timezone.utc),
        )
        self.orders.append(order)
        return order
