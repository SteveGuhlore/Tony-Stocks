"""Broker interface + in-memory FakeBroker for paper trading (phase 3).

The ``Broker`` protocol is the seam between the trading logic and Alpaca. The real
implementation is ``AlpacaPaperBroker`` (alpaca-py, paper=True); ``FakeBroker`` is a
deterministic in-memory stand-in for tests and for driving full position lifecycles.

Research/paper only — long equity bracket orders. Exit prices for stop/target use
the tracked stop/target levels, mirroring how Alpaca bracket legs fill.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class BrokerAccount:
    equity: float
    cash: float
    buying_power: float
    account_label: str


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    qty: int
    avg_entry_price: float
    market_value: float
    unrealized_pl: float


@dataclass(frozen=True)
class BracketOrderResult:
    order_id: str
    symbol: str
    qty: int
    status: str
    submitted_at: str
    entry: float | None = None
    stop: float | None = None
    target: float | None = None


class Broker(Protocol):
    """Minimal brokerage surface used by the paper-trading subsystem."""

    def account(self) -> BrokerAccount: ...

    def submit_bracket(
        self, *, symbol: str, qty: int, entry: float, stop: float, target: float,
        time_in_force: str = "day",
    ) -> BracketOrderResult: ...

    def get_position(self, symbol: str) -> BrokerPosition | None: ...

    def list_positions(self) -> list[BrokerPosition]: ...

    def close_position(self, symbol: str, *, price: float | None = None) -> BracketOrderResult | None: ...

    def closed_positions(self) -> list[dict[str, Any]]: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeBroker:
    """Deterministic in-memory broker. Use ``simulate_price`` to resolve positions."""

    def __init__(self, *, equity: float = 100_000.0, account_label: str = "tony") -> None:
        self._equity = float(equity)
        self._label = account_label
        self._positions: dict[str, dict[str, Any]] = {}
        self._closed: list[dict[str, Any]] = []
        self._seq = 0

    def account(self) -> BrokerAccount:
        unrealized = sum(
            (p["last"] - p["entry"]) * p["qty"] for p in self._positions.values()
        )
        return BrokerAccount(
            equity=self._equity + unrealized,
            cash=self._equity,
            buying_power=self._equity,
            account_label=self._label,
        )

    def submit_bracket(
        self, *, symbol: str, qty: int, entry: float, stop: float, target: float,
        time_in_force: str = "day",
    ) -> BracketOrderResult:
        sym = str(symbol).upper()
        self._seq += 1
        order_id = f"fake-{self._seq}"
        self._positions[sym] = {
            "qty": int(qty), "entry": float(entry), "stop": float(stop),
            "target": float(target), "last": float(entry), "order_id": order_id,
        }
        return BracketOrderResult(
            order_id=order_id, symbol=sym, qty=int(qty), status="accepted",
            submitted_at=_now_iso(), entry=float(entry), stop=float(stop), target=float(target),
        )

    def _to_position(self, sym: str, p: dict[str, Any]) -> BrokerPosition:
        return BrokerPosition(
            symbol=sym, qty=p["qty"], avg_entry_price=p["entry"],
            market_value=p["last"] * p["qty"],
            unrealized_pl=(p["last"] - p["entry"]) * p["qty"],
        )

    def get_position(self, symbol: str) -> BrokerPosition | None:
        sym = str(symbol).upper()
        p = self._positions.get(sym)
        return self._to_position(sym, p) if p else None

    def list_positions(self) -> list[BrokerPosition]:
        return [self._to_position(sym, p) for sym, p in self._positions.items()]

    def _close(self, sym: str, exit_price: float, result: str) -> BracketOrderResult:
        p = self._positions.pop(sym)
        self._closed.append({
            "symbol": sym, "qty": p["qty"], "entry": p["entry"], "exit": exit_price,
            "result": result, "order_id": p["order_id"], "closed_at": _now_iso(),
            "realized_pl": (exit_price - p["entry"]) * p["qty"],
        })
        self._seq += 1
        return BracketOrderResult(
            order_id=f"fake-close-{self._seq}", symbol=sym, qty=p["qty"], status="filled",
            submitted_at=_now_iso(), entry=p["entry"], stop=p["stop"], target=p["target"],
        )

    def close_position(self, symbol: str, *, price: float | None = None) -> BracketOrderResult | None:
        sym = str(symbol).upper()
        p = self._positions.get(sym)
        if not p:
            return None
        exit_price = float(price) if price is not None else p["last"]
        return self._close(sym, exit_price, "closed")

    def simulate_price(self, symbol: str, price: float) -> None:
        """Mark the position to ``price``; auto-close at the target/stop level if crossed."""
        sym = str(symbol).upper()
        p = self._positions.get(sym)
        if not p:
            return
        p["last"] = float(price)
        if price >= p["target"]:
            self._close(sym, p["target"], "target_hit")
        elif price <= p["stop"]:
            self._close(sym, p["stop"], "stop_hit")

    def closed_positions(self) -> list[dict[str, Any]]:
        return list(self._closed)
