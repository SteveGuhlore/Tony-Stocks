from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import SymbolDetailResponse, CandidateSnapshotRow, ScanResultRow
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["symbols"])

# A symbol's stored bars are "stale" if the newest bar is older than this.
CHART_STALE_AFTER_HOURS = 26  # one trading day + slack (covers an overnight gap)

def _nan(v):
    return v if isinstance(v, str) else None

def _jl(v):
    if isinstance(v, str):
        try: return json.loads(v)
        except: return []
    return v or []

def _snap(r):
    return CandidateSnapshotRow(id=r["id"], symbol=r["symbol"], status=r.get("status",""),
        setup_category=r.get("setup_category",""), universe_role=r.get("universe_role",""),
        total_score=r.get("total_score"), close=r.get("close"), entry=r.get("entry"),
        stop=r.get("stop"), target=r.get("target"), risk_reward=r.get("risk_reward"),
        snapshot_time=r.get("snapshot_time",""), outcome_label=_nan(r.get("outcome_label")),
        notes=_nan(r.get("notes")), tony_priority_label=_nan(r.get("tony_priority_label")),
        tony_recommended_action=_nan(r.get("tony_recommended_action")),
        tony_setup_read=_nan(r.get("tony_setup_read")), tony_hypothesis=_nan(r.get("tony_hypothesis")),
        entry_triggered=bool(r.get("entry_triggered",0)), entry_triggered_at=_nan(r.get("entry_triggered_at")))

def _scan_result(r):
    return ScanResultRow(symbol=r["symbol"], score=float(r.get("final_score",0)),
        setup_category=r.get("setup_category",""), tags=_jl(r.get("tags_json")),
        universe_role=r.get("universe_role",""), name=r.get("name",""), sector=r.get("sector",""),
        close=float(r.get("latest_close",0)), entry=float(r.get("suggested_entry",0)),
        stop=float(r.get("suggested_stop",0)), target=float(r.get("suggested_target_1",0)),
        rr=float(r.get("risk_reward_ratio",0)), trade_plan_valid=bool(r.get("trade_plan_valid",1)),
        trend_score=float(r.get("trend_score",0)), momentum_score=float(r.get("momentum_score",0)),
        volume_score=float(r.get("volume_score",0)), risk_score=float(r.get("risk_score",0)),
        setup_quality_score=float(r.get("setup_quality_score",0)),
        reasons=_jl(r.get("reasons_json")), warnings=_jl(r.get("warnings_json")))

@router.get("/symbols/{symbol}/detail", response_model=SymbolDetailResponse)
def get_symbol_detail(symbol: str, repo: ScannerRepository = Depends(get_repo)):
    symbol = symbol.upper()
    snaps_df = repo.list_candidate_snapshots(limit=500)
    sym_snaps = []
    if not snaps_df.empty:
        sym_snaps = [_snap(r) for r in snaps_df[snaps_df["symbol"]==symbol].to_dict("records")]
    scan_df = repo.latest_scan_results()
    latest_scan = None
    if not scan_df.empty:
        m = scan_df[scan_df["symbol"]==symbol]
        if not m.empty:
            latest_scan = _scan_result(m.iloc[0].to_dict())
    return SymbolDetailResponse(symbol=symbol, latest_snapshot=sym_snaps[0] if sym_snaps else None,
        recent_snapshots=sym_snaps[:5], latest_scan_result=latest_scan, chart_bars=[])

def _plan_for_symbol(repo: ScannerRepository, symbol: str) -> dict:
    """Latest plan levels (entry/stop/target) from the newest snapshot. Awaiting-safe."""
    plan = {"entry": None, "stop": None, "target": None}
    try:
        df = repo.list_candidate_snapshots(limit=500)
        if not df.empty:
            m = df[df["symbol"] == symbol]
            if not m.empty:
                r = m.iloc[0].to_dict()
                def _fl(v):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None
                plan = {
                    "entry": _fl(r.get("original_entry_price") if r.get("original_entry_price") is not None else r.get("entry")),
                    "stop": _fl(r.get("original_stop_price") if r.get("original_stop_price") is not None else r.get("stop")),
                    "target": _fl(r.get("original_target_price") if r.get("original_target_price") is not None else r.get("target")),
                }
    except Exception:
        pass
    return plan


@router.get("/symbols/{symbol}/chart")
def get_symbol_chart(symbol: str, timeframe: str = "intraday", repo: ScannerRepository = Depends(get_repo)):
    """First-party chart endpoint. Reads ONLY stored intraday_bars (fed by the price-poll
    cycle) — never on-request yfinance in the hot path. Returns an explicit status so the
    UI shows a labeled empty/stale state instead of a broken axis. Never crashes on a
    symbol with no bars (status='unavailable')."""
    symbol = symbol.upper()
    plan = _plan_for_symbol(repo, symbol)

    try:
        stored = repo.list_intraday_bars(symbol, limit=5000)
    except Exception:
        stored = []

    if not stored:
        return JSONResponse({"symbol": symbol, "timeframe": timeframe, "status": "unavailable",
                             "bars": [], "plan": plan})

    bars = []
    for b in stored:
        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        bars.append({"t": b.get("ts"), "o": _f(b.get("open")), "h": _f(b.get("high")),
                     "l": _f(b.get("low")), "c": _f(b.get("close")), "v": _f(b.get("volume"))})

    status = "ok"
    last_ts = bars[-1]["t"]
    try:
        last_dt = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last_dt > timedelta(hours=CHART_STALE_AFTER_HOURS):
            status = "stale"
    except Exception:
        status = "stale"

    return JSONResponse({"symbol": symbol, "timeframe": timeframe, "status": status,
                         "bars": bars, "plan": plan})
