from __future__ import annotations


def calculate_trade_pnl(entry_price: float, exit_price: float, shares: float) -> tuple[float, float]:
    """Calculate paper trade P&L and percent return."""
    if entry_price <= 0:
        raise ValueError("entry_price must be greater than 0")
    pnl = (exit_price - entry_price) * shares
    pnl_pct = (exit_price / entry_price - 1) * 100
    return round(pnl, 2), round(pnl_pct, 2)

