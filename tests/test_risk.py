from trading_bot.risk import RiskManager


def test_quantity_respects_max_position_fraction():
    manager = RiskManager(max_position_fraction=0.10)
    assert manager.calculate_quantity(equity=10_000, price=100) == 10


def test_shorting_disabled_blocks_sell_without_position():
    manager = RiskManager(allow_shorting=False)
    decision = manager.approve_order("sell", equity=10_000, price=100, current_position=0)
    assert not decision.allowed
    assert decision.quantity == 0


def test_drawdown_breached():
    manager = RiskManager(max_drawdown_fraction=0.15)
    assert manager.drawdown_breached(peak_equity=10_000, current_equity=8_500)
