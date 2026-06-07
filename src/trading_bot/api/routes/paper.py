"""Paper-trading API: open/closed positions + a research P/L summary.

Degrades cleanly when paper_trading is disabled (enabled=false, empty lists). Reads
stored paper_positions only — no broker/network call in the request path.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from trading_bot.analytics.equity_curve import build_paper_equity_curve
from trading_bot.api.deps import get_repo
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["paper"])


class PaperPosition(BaseModel):
    symbol: str
    qty: int
    entry_price: float | None = None
    stop: float | None = None
    target: float | None = None
    status: str
    result: str | None = None
    exit_price: float | None = None
    realized_pl: float | None = None
    account_label: str | None = None
    opened_at: str | None = None
    closed_at: str | None = None
    # Kinetic Tape (Codex #4): marked-to-live unrealized P/L + protection status.
    # All None when no keys / market closed / position closed — fail-quiet.
    last_price: float | None = None
    unrealized_pl: float | None = None
    unrealized_pl_pct: float | None = None
    protection_status: str = "unknown"  # "armed" | "unknown"


class PaperSummary(BaseModel):
    open_count: int
    closed_count: int
    target_hits: int
    stop_hits: int
    realized_pl: float
    win_rate: float | None = None


class PaperResponse(BaseModel):
    enabled: bool
    disabled_reason: str | None = None
    account_label: str
    open: list[PaperPosition]
    closed: list[PaperPosition]
    summary: PaperSummary


def _paper_config() -> tuple[bool, str | None, str]:
    """Return (enabled, disabled_reason, account_label) from config; safe on error."""
    try:
        from trading_bot.execution import load_paper_trading_config
        from trading_bot.settings import load_scanner_settings

        settings = load_scanner_settings("config/default_config.yaml")
        cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
        return cfg.enabled, cfg.disabled_reason, cfg.account_label
    except Exception:
        return False, None, "tony"


def _to_position(row: dict[str, Any], live_price: float | None = None) -> PaperPosition:
    status = row.get("status", "")
    entry = row.get("entry_price")
    qty = int(row.get("qty") or 0)

    last_price = None
    unrealized_pl = None
    unrealized_pl_pct = None
    # Mark OPEN positions to live (Codex #4). Closed positions keep realized P/L only.
    if status == "open" and live_price is not None and entry not in (None, "", 0):
        try:
            entry_f = float(entry)
            last_price = float(live_price)
            if entry_f:
                unrealized_pl = round((last_price - entry_f) * qty, 2)
                unrealized_pl_pct = round((last_price / entry_f - 1.0) * 100.0, 3)
        except (TypeError, ValueError, ZeroDivisionError):
            last_price = unrealized_pl = unrealized_pl_pct = None

    # Protection (OCO bracket) is armed when the position carries a stop AND target.
    protection_status = "armed" if (status == "open" and row.get("stop") and row.get("target")) else "unknown"

    return PaperPosition(
        symbol=row.get("symbol", ""),
        qty=qty,
        entry_price=entry,
        stop=row.get("stop"),
        target=row.get("target"),
        status=status,
        result=row.get("result"),
        exit_price=row.get("exit_price"),
        realized_pl=row.get("realized_pl"),
        account_label=row.get("account_label"),
        opened_at=row.get("opened_at"),
        closed_at=row.get("closed_at"),
        last_price=last_price,
        unrealized_pl=unrealized_pl,
        unrealized_pl_pct=unrealized_pl_pct,
        protection_status=protection_status,
    )


@router.get("/paper/positions", response_model=PaperResponse)
def get_paper_positions(request: Request, repo: ScannerRepository = Depends(get_repo)) -> PaperResponse:
    enabled, reason, label = _paper_config()
    rows = repo.list_paper_positions(limit=500)
    open_rows = [r for r in rows if r.get("status") == "open"]
    closed_rows = [r for r in rows if r.get("status") == "closed"]
    live_prices = _live_prices_for(request, open_rows)

    target_hits = sum(1 for r in closed_rows if r.get("result") == "target_hit")
    stop_hits = sum(1 for r in closed_rows if r.get("result") == "stop_hit")
    realized = sum(float(r["realized_pl"]) for r in closed_rows if r.get("realized_pl") is not None)
    conclusive = target_hits + stop_hits
    win_rate = round(target_hits / conclusive, 4) if conclusive else None

    return PaperResponse(
        enabled=enabled,
        disabled_reason=reason,
        account_label=label,
        open=[_to_position(r, live_prices.get(str(r.get("symbol", "")).upper())) for r in open_rows],
        closed=[_to_position(r) for r in closed_rows],
        summary=PaperSummary(
            open_count=len(open_rows),
            closed_count=len(closed_rows),
            target_hits=target_hits,
            stop_hits=stop_hits,
            realized_pl=round(realized, 2),
            win_rate=win_rate,
        ),
    )


class EquityPointSchema(BaseModel):
    t: str
    equity: float
    index: float


class PaperEquityResponse(BaseModel):
    enabled: bool
    label: str
    base_equity: float
    return_pct: float
    points: list[EquityPointSchema]
    research_only: bool = True


def _live_prices_for(request: Request, open_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Best-effort live price map for the open paper symbols, from the PriceCache.

    Fail-quiet: returns {} when there is no cache, no keys, or no quotes (no keys /
    market closed / not yet polled) so the curve degrades to realized-only.
    """
    try:
        cache = request.app.state.price_cache
        if cache is None or not cache.has_keys():
            return {}
        prices: dict[str, float] = {}
        for r in open_rows:
            symbol = str(r.get("symbol", "")).upper()
            if not symbol or symbol in prices:
                continue
            quote = cache.get(symbol)
            if quote is not None and quote.price:
                prices[symbol] = float(quote.price)
        return prices
    except Exception:
        return {}


@router.get("/paper/equity-curve", response_model=PaperEquityResponse)
def get_paper_equity_curve(
    request: Request,
    base_equity: float = Query(100_000.0, gt=0, description="Paper account base equity to index to 100."),
    repo: ScannerRepository = Depends(get_repo),
) -> PaperEquityResponse:
    """The bot's paper-equity series, indexed to 100 for a normalized head-to-head
    against the Command Center's Tony curve. Read-only.

    Realized closed-trade series, plus — when live prices are available from the
    PriceCache — the unrealized P/L of OPEN positions (marked to live) folded into the
    latest point so both sides compare like-for-like. Fails quiet to realized-only when
    prices are unavailable (no keys / market closed).
    """
    enabled, _reason, label = _paper_config()
    rows = repo.list_paper_positions(limit=1000)
    closed_rows = [r for r in rows if r.get("status") == "closed"]
    open_rows = [r for r in rows if r.get("status") == "open"]
    live_prices = _live_prices_for(request, open_rows)
    curve = build_paper_equity_curve(
        closed_rows,
        base_equity=base_equity,
        label=label or "bot",
        open_positions=open_rows,
        live_prices=live_prices,
    )
    return PaperEquityResponse(
        enabled=enabled,
        label=curve.label,
        base_equity=curve.base_equity,
        return_pct=curve.return_pct,
        points=[EquityPointSchema(**p.to_dict()) for p in curve.points],
    )
