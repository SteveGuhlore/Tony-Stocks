"""Paper-trading API: open/closed positions + a research P/L summary.

Degrades cleanly when paper_trading is disabled (enabled=false, empty lists). Reads
stored paper_positions only — no broker/network call in the request path.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

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


def _to_position(row: dict[str, Any]) -> PaperPosition:
    return PaperPosition(
        symbol=row.get("symbol", ""),
        qty=int(row.get("qty") or 0),
        entry_price=row.get("entry_price"),
        stop=row.get("stop"),
        target=row.get("target"),
        status=row.get("status", ""),
        result=row.get("result"),
        exit_price=row.get("exit_price"),
        realized_pl=row.get("realized_pl"),
        account_label=row.get("account_label"),
        opened_at=row.get("opened_at"),
        closed_at=row.get("closed_at"),
    )


@router.get("/paper/positions", response_model=PaperResponse)
def get_paper_positions(repo: ScannerRepository = Depends(get_repo)) -> PaperResponse:
    enabled, reason, label = _paper_config()
    rows = repo.list_paper_positions(limit=500)
    open_rows = [r for r in rows if r.get("status") == "open"]
    closed_rows = [r for r in rows if r.get("status") == "closed"]

    target_hits = sum(1 for r in closed_rows if r.get("result") == "target_hit")
    stop_hits = sum(1 for r in closed_rows if r.get("result") == "stop_hit")
    realized = sum(float(r["realized_pl"]) for r in closed_rows if r.get("realized_pl") is not None)
    conclusive = target_hits + stop_hits
    win_rate = round(target_hits / conclusive, 4) if conclusive else None

    return PaperResponse(
        enabled=enabled,
        disabled_reason=reason,
        account_label=label,
        open=[_to_position(r) for r in open_rows],
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
