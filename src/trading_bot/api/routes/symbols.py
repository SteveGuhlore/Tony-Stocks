from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import SymbolDetailResponse, CandidateSnapshotRow, ScanResultRow
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["symbols"])

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

@router.get("/symbols/{symbol}/chart")
def get_symbol_chart(symbol: str, days: int = 60):
    try:
        import yfinance as yf
        df = yf.download(symbol.upper(), period=f"{days}d", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            return JSONResponse({"bars": []})
        bars = [{"date": str(d.date()), "open": float(r["Open"]), "high": float(r["High"]),
                 "low": float(r["Low"]), "close": float(r["Close"]), "volume": float(r["Volume"])}
                for d, r in df.iterrows()]
        return JSONResponse({"bars": bars})
    except Exception:
        return JSONResponse({"bars": []})
