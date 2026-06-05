"""B1 experiment guard tests — keep the bot the falsifiable flat-1% control.

Contract: docs/CONTRACTS/execution-parity.md Section B.1. B1 introduces conviction-scaled
sizing in Tony's book ONLY. These tests lock the two bot-side invariants that keep the
head-to-head valid:

1. The bot's position sizing has NO conviction/confidence input (it stays flat-1%).
2. record.json ingestion tolerates an additive ``sizing_attribution`` key (ignore-if-unknown,
   never a strict-schema reject).

If either invariant breaks, the experiment measures nothing — hence these are guard tests.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from trading_bot.api.routes.command_center import build_record
from trading_bot.api.schemas import CommandCenterRecord
from trading_bot.execution.order_router import size_position


def _cfg(risk_pct: float = 1.0, max_notional: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(risk_per_trade_pct=risk_pct, max_notional_per_position=max_notional)


# --------------------------------------------------------------------------- #
# Invariant 1 — the bot is flat-1%, no conviction term                         #
# --------------------------------------------------------------------------- #
def test_size_position_takes_no_conviction_parameter():
    """The control-group sizing function must not grow a confidence/conviction knob."""
    params = set(inspect.signature(size_position).parameters)
    assert params == {"entry", "stop", "equity", "config"}
    assert not (params & {"confidence", "conviction", "tony_confidence", "score", "weight"})


def test_size_position_is_pure_flat_risk():
    """Same (entry, stop, equity, 1% config) always yields the same share count — no hidden
    conviction scaling. floor((100000 * 1%) / (100-95)) = floor(1000/5) = 200."""
    qty = size_position(entry=100.0, stop=95.0, equity=100_000.0, config=_cfg(1.0))
    assert qty == 200
    assert all(
        size_position(entry=100.0, stop=95.0, equity=100_000.0, config=_cfg(1.0)) == 200
        for _ in range(3)
    )


def test_size_position_scales_only_with_risk_policy_not_conviction():
    """Doubling the *risk policy* doubles size; there is no other lever (no conviction)."""
    one_pct = size_position(entry=100.0, stop=95.0, equity=100_000.0, config=_cfg(1.0))
    two_pct = size_position(entry=100.0, stop=95.0, equity=100_000.0, config=_cfg(2.0))
    assert two_pct == one_pct * 2  # 200 -> 400, purely from the risk %, not conviction


# --------------------------------------------------------------------------- #
# Invariant 2 — record.json tolerates an additive sizing_attribution key       #
# --------------------------------------------------------------------------- #
_RECORD_WITH_SIZING_ATTR = {
    "tony_win_rate": 55.0,  # build_record normalizes percent -> fraction (÷100)
    "avg_pl_per_trade": 1.2,
    "target_hits": 11,
    "stop_hits": 9,
    "equity_curve": [100.0, 101.5, 99.8],
    # B1-added optional block — must be ignored, never rejected:
    "sizing_attribution": {"picking_alpha_pct": 3.1, "sizing_alpha_pct": 1.4},
}


def test_build_record_ignores_unknown_sizing_attribution():
    rec = build_record(_RECORD_WITH_SIZING_ATTR)
    assert isinstance(rec, CommandCenterRecord)
    assert rec.win_rate == 0.55
    assert rec.equity_curve == [100.0, 101.5, 99.8]
    assert not hasattr(rec, "sizing_attribution")  # silently dropped, not surfaced


def test_command_center_record_model_tolerates_extra_keys():
    rec = CommandCenterRecord.model_validate(
        {
            "win_rate": 0.5,
            "avg_pl_per_trade": 0.0,
            "target_hits": 1,
            "stop_hits": 1,
            "equity_curve": [100.0],
            "sizing_attribution": {"picking_alpha_pct": 1.0},
        }
    )
    assert rec.win_rate == 0.5  # extra key accepted (ignored), no ValidationError
