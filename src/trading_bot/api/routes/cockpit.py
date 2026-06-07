"""GET /api/cockpit — the read-optimized aggregate that powers "The Tape".

Codex review #6: the tape needs scan score + 5 sub-scores + setup + levels +
live tracking + day-change + Tony's verdict/score + status + RVOL in ONE row,
instead of the frontend doing a six-way join across /picks, /tracking, /scan,
/prices, /command-center. This endpoint assembles that single symbol view-model.

``build_cockpit_rows`` is PURE (all inputs injected) so it is unit-tested without
a DB, broker, or network. The route wires the repo + price cache + CC files and
degrades every field to a safe default ("awaiting") when a source is missing.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from trading_bot.api.deps import get_repo
from trading_bot.api.routes.command_center import _load_json, _verdicts_path, build_picks
from trading_bot.api.schemas import MarketStatus
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["cockpit"])


# ── Response models ───────────────────────────────────────────────────────────

class SubScores(BaseModel):
    trend: float | None = None
    momentum: float | None = None
    volume: float | None = None
    risk: float | None = None
    setup: float | None = None


class TonyRead(BaseModel):
    score: float | None = None
    verdict: str = ""          # transport string; frontend normalizes/degrades unknowns
    reasoning: str = ""
    returned_at: str = ""


class CockpitRow(BaseModel):
    symbol: str
    name: str = ""
    sector: str = ""
    universe_role: str = ""
    setup_category: str = ""
    score: float | None = None
    sub_scores: SubScores = SubScores()
    close: float | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rr: float | None = None
    trade_plan_valid: bool = True
    # live price (Codex #8: explicit status so the UI never collapses on a 503)
    last_price: float | None = None
    day_change_pct: float | None = None
    price_status: str = "unavailable"   # live | delayed | stale | unavailable
    rvol: float | None = None
    sparkline: list[float] = []          # populated once intraday_bars lands (Codex #5)
    # tracking overlay
    status: str = "watching"             # watching | near | triggered
    entry_triggered: bool = False
    distance_to_entry_pct: float | None = None
    current_price: float | None = None
    research_unrealized_pl_pct: float | None = None
    reassessment_label: str | None = None
    time_active_minutes: float | None = None
    original_entry: float | None = None
    original_stop: float | None = None
    original_target: float | None = None
    # second pass
    tony: TonyRead | None = None


class CockpitResponse(BaseModel):
    generated_at: str
    market: MarketStatus | None = None
    counts: dict[str, int] = {}
    rows: list[CockpitRow] = []


# ── Coercion ────────────────────────────────────────────────────────────────

def _f(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _s(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def _dedup_latest_by_symbol(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first (newest — repo orders snapshot_time DESC) row per symbol."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in snapshots:
        sym = _s(r.get("symbol")).upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(r)
    return out


# ── Pure assembler (unit-tested directly) ─────────────────────────────────────

def build_cockpit_rows(
    snapshots: list[dict[str, Any]],
    subscores_by_symbol: dict[str, dict[str, Any]],
    cc_picks: dict[str, Any],
    price_by_symbol: dict[str, dict[str, Any]],
    *,
    near_pct: float = 0.005,
) -> list[CockpitRow]:
    """Assemble one CockpitRow per (deduped, latest) snapshot symbol.

    - snapshots: candidate_snapshots rows (newest-first); carries score/levels/tracking.
    - subscores_by_symbol: symbol → {trend_score, momentum_score, ...} from scan_results.
    - cc_picks: symbol → object with .score/.verdict/.reasoning/.returned_at (CommandCenterPick).
    - price_by_symbol: symbol → {price, change_pct, status}.
    - near_pct: how close (fraction below entry) counts as "near".
    """
    rows: list[CockpitRow] = []
    for r in _dedup_latest_by_symbol(snapshots):
        sym = _s(r.get("symbol")).upper()
        sub = subscores_by_symbol.get(sym, {})
        price = price_by_symbol.get(sym, {})
        last_price = _f(price.get("price"))
        entry = _f(r.get("entry"))

        triggered = bool(r.get("entry_triggered")) or _s(r.get("entry_status")).lower() == "triggered"

        distance = None
        if last_price is not None and entry:
            distance = round((last_price / entry - 1.0) * 100.0, 3)

        near = (
            not triggered
            and last_price is not None
            and entry is not None
            and entry > 0
            and last_price >= entry * (1.0 - near_pct)
            and last_price <= entry * (1.0 + 0.002)
        )
        status = "triggered" if triggered else ("near" if near else "watching")

        pick = cc_picks.get(sym)
        tony = None
        if pick is not None:
            tony = TonyRead(
                score=_f(getattr(pick, "score", None)),
                verdict=_s(getattr(pick, "verdict", "")),
                reasoning=_s(getattr(pick, "reasoning", "")),
                returned_at=_s(getattr(pick, "returned_at", "")),
            )

        rows.append(CockpitRow(
            symbol=sym,
            name=_s(r.get("name")),
            sector=_s(r.get("sector")),
            universe_role=_s(r.get("universe_role")),
            setup_category=_s(r.get("setup_category")),
            score=_f(r.get("total_score")),
            sub_scores=SubScores(
                trend=_f(sub.get("trend_score")),
                momentum=_f(sub.get("momentum_score")),
                volume=_f(sub.get("volume_score")),
                risk=_f(sub.get("risk_score")),
                setup=_f(sub.get("setup_quality_score")),
            ),
            close=_f(r.get("close")),
            entry=entry,
            stop=_f(r.get("stop")),
            target=_f(r.get("target")),
            rr=_f(r.get("risk_reward")),
            trade_plan_valid=bool(r.get("trade_plan_valid", 1)),
            last_price=last_price,
            day_change_pct=_f(price.get("change_pct")),
            price_status=_s(price.get("status")) or "unavailable",
            rvol=_f(r.get("relative_volume")),
            sparkline=[],
            status=status,
            entry_triggered=triggered,
            distance_to_entry_pct=distance,
            current_price=_f(r.get("current_price")),
            research_unrealized_pl_pct=_f(r.get("research_unrealized_pl_pct")),
            reassessment_label=(_s(r.get("reassessment_label")) or None),
            time_active_minutes=_f(r.get("time_active_minutes")),
            original_entry=_f(r.get("original_entry_price")),
            original_stop=_f(r.get("original_stop_price")),
            original_target=_f(r.get("original_target_price")),
            tony=tony,
        ))
    return rows


# ── Route ─────────────────────────────────────────────────────────────────────

def _price_map_from_cache(request: Request, symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Best-effort live price map. Fail-quiet → {} (every row then shows 'unavailable')."""
    out: dict[str, dict[str, Any]] = {}
    try:
        cache = getattr(request.app.state, "price_cache", None)
        if cache is None or not cache.has_keys():
            return out
        for sym in symbols:
            quote = cache.get(sym)
            if quote is None:
                continue
            out[sym] = {
                "price": getattr(quote, "price", None),
                "change_pct": getattr(quote, "change_pct", None),
                "status": "live" if getattr(quote, "is_live", False) else "delayed",
            }
    except Exception:
        return out
    return out


def _market_status(request: Request) -> MarketStatus | None:
    try:
        cache = getattr(request.app.state, "price_cache", None)
        if cache is not None and hasattr(cache, "market_status"):
            ms = cache.market_status()
            return MarketStatus(**ms) if isinstance(ms, dict) else ms
    except Exception:
        pass
    return None


@router.get("/cockpit", response_model=CockpitResponse)
def get_cockpit(request: Request, repo: ScannerRepository = Depends(get_repo)) -> CockpitResponse:
    from trading_bot.utils.time_utils import utc_now_iso

    snap_df = repo.list_candidate_snapshots(limit=500)
    snapshots = snap_df.to_dict("records") if not snap_df.empty else []

    sub_df = repo.list_snapshot_subscores(limit=10000)
    subscores_by_symbol: dict[str, dict[str, Any]] = {}
    if not sub_df.empty:
        for rec in sub_df.to_dict("records"):
            sym = _s(rec.get("symbol")).upper()
            if sym and sym not in subscores_by_symbol:  # newest-first → first wins
                subscores_by_symbol[sym] = rec

    reports_dir = Path(getattr(request.app.state, "reports_dir", "reports"))
    cc_picks = build_picks(_load_json(_verdicts_path(reports_dir)))

    symbols = sorted({_s(r.get("symbol")).upper() for r in snapshots if r.get("symbol")})
    price_map = _price_map_from_cache(request, symbols)

    rows = build_cockpit_rows(snapshots, subscores_by_symbol, cc_picks, price_map)
    counts = {
        "total": len(rows),
        "near": sum(1 for r in rows if r.status == "near"),
        "triggered": sum(1 for r in rows if r.status == "triggered"),
        "watching": sum(1 for r in rows if r.status == "watching"),
    }
    return CockpitResponse(
        generated_at=utc_now_iso(),
        market=_market_status(request),
        counts=counts,
        rows=rows,
    )
