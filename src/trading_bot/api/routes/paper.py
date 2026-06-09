"""Paper-trading API: open/closed positions + a research P/L summary.

Degrades cleanly when paper_trading is disabled (enabled=false, empty lists). Reads
stored paper_positions only — no broker/network call in the request path.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from trading_bot.analytics.equity_compare import align_common, build_account_curve
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


# ── Bot-vs-Tony equity comparison (time-aligned, both Alpaca paper accounts) ─────

_PAPER_REST = "https://paper-api.alpaca.markets"


def _env_keys(env: dict[str, str]) -> tuple[str | None, str | None]:
    return (
        env.get("ALPACA_PAPER_API_KEY") or env.get("ALPACA_API_KEY"),
        env.get("ALPACA_PAPER_SECRET_KEY") or env.get("ALPACA_SECRET_KEY"),
    )


def _read_env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, _, v = ln.partition("=")
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _portfolio_history(key: str | None, secret: str | None, period: str, timeframe: str) -> dict[str, Any] | None:
    """Fetch one paper account's Alpaca portfolio history. Fail-quiet → None on any error."""
    if not (key and secret):
        return None
    from urllib.parse import quote  # noqa: PLC0415

    url = (f"{_PAPER_REST}/v2/account/portfolio/history"
           f"?period={quote(str(period))}&timeframe={quote(str(timeframe))}")
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed paper host
            return json.load(resp)
    except Exception:  # noqa: BLE001 - never break the dashboard on a broker hiccup
        return None


@router.get("/paper/equity-compare")
def get_equity_compare(
    period: str = Query("1M", description="Alpaca portfolio-history period, e.g. 1D/1W/1M/3M."),
    timeframe: str = Query("1D", description="Bar timeframe, e.g. 15Min/1H/1D."),
) -> dict[str, Any]:
    """Bot vs Tony equity on ONE shared time axis. Pulls Alpaca portfolio history for both
    paper accounts with the same period+timeframe (so timestamps align), indexes each to
    100, and trims to the common window. Read-only; degrades to whichever account(s) have
    keys. Tony's keys come from CC_ENV_FILE (default /opt/command-center/.env)."""
    bot_key, bot_secret = _env_keys(dict(os.environ))
    cc_env = _read_env_file(os.environ.get("CC_ENV_FILE", "/opt/command-center/.env"))
    tony_key, tony_secret = _env_keys(cc_env)

    bot = build_account_curve(_portfolio_history(bot_key, bot_secret, period, timeframe), "Bot")
    tony = build_account_curve(_portfolio_history(tony_key, tony_secret, period, timeframe), "Tony")
    bot, tony = align_common(bot, tony)
    return {
        "period": period,
        "timeframe": timeframe,
        "bot": bot,
        "tony": tony,
        "research_only": True,
    }
