"""Live-like test doubles: fakes that mimic the REAL Alpaca quirks, not the happy path.

FakeBroker is deterministic and friendly — every close carries exit, result, and
realized_pl. The live AlpacaPaperBroker is not: closes arrive as bare SELL fills
(result=None, realized_pl=None), newest-first, with every fill in the recent order
window (so a re-entered symbol has SEVERAL records). Code that only ever met FakeBroker
can pass its tests and still mis-grade real closes. These doubles reproduce the live
contract so the engine seam is exercised the way production exercises it.

Also: canned Alpaca ``/v2/account/portfolio/history`` payloads with the real warts
(zero-padding before funding, nulls, string numerics) for the equity-compare tests.
"""
from __future__ import annotations

from typing import Any

from trading_bot.execution.broker import FakeBroker


class LiveLikeBroker(FakeBroker):
    """FakeBroker with the live AlpacaPaperBroker's reporting behavior.

    ``closed_positions()`` returns what the live broker actually returns: one record per
    SELL fill (NOT per position), newest-first, with ``result=None`` and
    ``realized_pl=None`` — the live API only sees the closing fill, never the entry.
    ``closed_at`` is carried like the live mapping does (from the order's filled_at).
    """

    def closed_positions(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in reversed(super().closed_positions()):  # live get_orders is newest-first
            out.append({
                "symbol": c["symbol"],
                "exit": c["exit"],
                "result": None,        # live broker cannot classify the close
                "realized_pl": None,   # live broker has the SELL fill only, no entry
                "closed_at": c.get("closed_at"),
            })
        return out


class AmnesiacBroker(FakeBroker):
    """A broker whose position vanished with NO close record in the window.

    Real failure mode: the closing fill aged out of the 100-order window (or the order
    query failed and returned []). Reconcile must still close the repo row — result
    "closed", exit/realized None — instead of leaving a phantom open position.
    """

    def closed_positions(self) -> list[dict[str, Any]]:
        return []


# ── Alpaca portfolio-history payloads, as the real API returns them ────────────────

def history_payload(timestamps: list[int], equity: list[Any]) -> dict[str, Any]:
    """Bare payload in Alpaca's shape (parallel arrays)."""
    return {"timestamp": timestamps, "equity": equity, "timeframe": "1D"}


def history_with_prefunding_zeros() -> dict[str, Any]:
    """Days of equity 0 before the account was funded — the phantom-plunge wart."""
    return history_payload(
        [1_700_000_000 + i * 86_400 for i in range(6)],
        [0, 0, 0, 100_000.0, 101_000.0, 99_500.0],
    )


def history_with_junk_entries() -> dict[str, Any]:
    """Nulls and string numerics interleaved with good bars (seen on flaky fetches)."""
    return history_payload(
        [1_700_000_000, 1_700_086_400, "1700172800", 1_700_259_200, 1_700_345_600],
        [100_000.0, None, "101000", "n/a", 102_000.0],
    )
