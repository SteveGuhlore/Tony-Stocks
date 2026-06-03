"""AlpacaPaperBroker — Broker implementation over alpaca-py (paper=True).

Submits long-equity bracket orders (entry + stop + target) to an Alpaca PAPER
account and reads back account/positions. The base URL is asserted to be a paper
endpoint at construction so an order can never reach the live API.

A trading client may be injected (tests); otherwise one is built lazily from keys
so importing this module never requires alpaca-py or network. The account identity
(label + keys) is explicit, leaving room for a second (Command Center) account.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from trading_bot.execution.broker import BracketOrderResult, BrokerAccount, BrokerPosition
from trading_bot.execution.paper_config import PAPER_BASE_URL, PaperTradingConfig, assert_paper_base_url


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class AlpacaPaperBroker:
    """Broker over alpaca-py's TradingClient(paper=True)."""

    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        account_label: str = "tony",
        base_url: str = PAPER_BASE_URL,
        client: Any | None = None,
    ) -> None:
        assert_paper_base_url(base_url)  # never allow a live endpoint
        self.api_key = api_key
        self.secret_key = secret_key
        self.account_label = account_label
        self.base_url = base_url
        if client is not None:
            self._client = client
        else:
            from alpaca.trading.client import TradingClient  # noqa: PLC0415

            self._client = TradingClient(api_key, secret_key, paper=True)

    def submit_bracket(
        self, *, symbol: str, qty: int, entry: float, stop: float, target: float,
        time_in_force: str = "day",
    ) -> BracketOrderResult:
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce  # noqa: PLC0415
        from alpaca.trading.requests import (  # noqa: PLC0415
            MarketOrderRequest,
            StopLossRequest,
            TakeProfitRequest,
        )

        tif = TimeInForce.GTC if str(time_in_force).lower() == "gtc" else TimeInForce.DAY
        request = MarketOrderRequest(
            symbol=str(symbol).upper(),
            qty=int(qty),
            side=OrderSide.BUY,
            time_in_force=tif,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(float(target), 2)),
            stop_loss=StopLossRequest(stop_price=round(float(stop), 2)),
        )
        order = self._client.submit_order(request)
        return BracketOrderResult(
            order_id=str(getattr(order, "id", "")),
            symbol=str(getattr(order, "symbol", symbol)).upper(),
            qty=int(_f(getattr(order, "qty", qty), qty)),
            status=str(getattr(order, "status", "accepted")),
            submitted_at=_now_iso(),
            entry=float(entry), stop=float(stop), target=float(target),
        )

    def account(self) -> BrokerAccount:
        a = self._client.get_account()
        return BrokerAccount(
            equity=_f(getattr(a, "equity", 0.0)),
            cash=_f(getattr(a, "cash", 0.0)),
            buying_power=_f(getattr(a, "buying_power", 0.0)),
            account_label=self.account_label,
            account_number=str(getattr(a, "account_number", "") or ""),
        )

    def list_positions(self) -> list[BrokerPosition]:
        positions = []
        for p in self._client.get_all_positions():
            positions.append(
                BrokerPosition(
                    symbol=str(getattr(p, "symbol", "")).upper(),
                    qty=int(_f(getattr(p, "qty", 0))),
                    avg_entry_price=_f(getattr(p, "avg_entry_price", 0.0)),
                    market_value=_f(getattr(p, "market_value", 0.0)),
                    unrealized_pl=_f(getattr(p, "unrealized_pl", 0.0)),
                )
            )
        return positions

    def get_position(self, symbol: str) -> BrokerPosition | None:
        sym = str(symbol).upper()
        for p in self.list_positions():
            if p.symbol == sym:
                return p
        return None

    def closed_positions(self) -> list[dict[str, Any]]:
        """Recently filled closing (SELL) orders, for reconciling exits.

        Best-effort: returns {symbol, exit, result, realized_pl} per filled sell. The
        engine refines ``result`` against the position's stored target/stop. Returns
        [] on any error so a reconciliation pass never breaks the watch loop. Needs
        live verification against real bracket fills.
        """
        try:
            from alpaca.trading.enums import OrderSide, QueryOrderStatus  # noqa: PLC0415
            from alpaca.trading.requests import GetOrdersRequest  # noqa: PLC0415

            req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=100)
            out: list[dict[str, Any]] = []
            for order in self._client.get_orders(filter=req):
                if str(getattr(order, "status", "")).lower().endswith("filled") is False and \
                        str(getattr(order, "status", "")).lower() != "filled":
                    continue
                if getattr(order, "side", None) not in (OrderSide.SELL, "sell"):
                    continue
                filled = getattr(order, "filled_avg_price", None)
                if filled is None:
                    continue
                out.append({
                    "symbol": str(getattr(order, "symbol", "")).upper(),
                    "exit": _f(filled),
                    "result": None,
                    "realized_pl": None,
                })
            return out
        except Exception:
            return []

    def close_position(self, symbol: str, *, price: float | None = None) -> BracketOrderResult | None:
        sym = str(symbol).upper()
        try:
            order = self._client.close_position(sym)
        except Exception:
            return None
        if order is None:
            return None
        return BracketOrderResult(
            order_id=str(getattr(order, "id", "")),
            symbol=sym,
            qty=int(_f(getattr(order, "qty", 0))),
            status=str(getattr(order, "status", "accepted")),
            submitted_at=_now_iso(),
        )


def build_alpaca_paper_broker(
    config: PaperTradingConfig,
    *,
    env: dict[str, str] | None = None,
    client: Any | None = None,
) -> AlpacaPaperBroker:
    """Build an AlpacaPaperBroker from config + env keys.

    Prefers dedicated ``ALPACA_PAPER_API_KEY`` / ``ALPACA_PAPER_SECRET_KEY``, falling
    back to ``ALPACA_API_KEY`` / ``ALPACA_SECRET_KEY``. Raises if keys are missing or
    the configured base URL is not a paper endpoint.
    """
    environ = os.environ if env is None else env
    assert_paper_base_url(config.base_url)
    api_key = environ.get("ALPACA_PAPER_API_KEY") or environ.get("ALPACA_API_KEY")
    secret = environ.get("ALPACA_PAPER_SECRET_KEY") or environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret:
        raise RuntimeError(
            "Alpaca paper API keys not set. Set ALPACA_API_KEY/ALPACA_SECRET_KEY "
            "(or ALPACA_PAPER_API_KEY/ALPACA_PAPER_SECRET_KEY)."
        )
    return AlpacaPaperBroker(
        api_key=api_key, secret_key=secret,
        account_label=config.account_label, base_url=config.base_url, client=client,
    )
