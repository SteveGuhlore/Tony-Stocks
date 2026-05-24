from __future__ import annotations
import json
from fastapi import APIRouter, Depends, Query
from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import LatestScanResponse, ScanOverviewResponse, ScanResultRow, ScanRunInfo
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["scan"])

def _jl(v):
    if isinstance(v, str):
        try: return json.loads(v)
        except: return []
    return v or []

def _result(r):
    return ScanResultRow(
        symbol=r["symbol"], score=float(r.get("final_score",0)),
        setup_category=r.get("setup_category",""), tags=_jl(r.get("tags_json")),
        universe_role=r.get("universe_role",""), name=r.get("name",""), sector=r.get("sector",""),
        close=float(r.get("latest_close",0)), entry=float(r.get("suggested_entry",0)),
        stop=float(r.get("suggested_stop",0)), target=float(r.get("suggested_target_1",0)),
        rr=float(r.get("risk_reward_ratio",0)), trade_plan_valid=bool(r.get("trade_plan_valid",1)),
        trend_score=float(r.get("trend_score",0)), momentum_score=float(r.get("momentum_score",0)),
        volume_score=float(r.get("volume_score",0)), risk_score=float(r.get("risk_score",0)),
        setup_quality_score=float(r.get("setup_quality_score",0)),
        reasons=_jl(r.get("reasons_json")), warnings=_jl(r.get("warnings_json")))

@router.get("/scan/latest", response_model=LatestScanResponse)
def get_latest_scan(min_score: float = Query(0.0), category: str | None = Query(None),
                    role: str | None = Query(None), repo: ScannerRepository = Depends(get_repo)):
    run = repo.latest_scan_run()
    if not run:
        return LatestScanResponse(run=None, results=[], total=0)
    df = repo.latest_scan_results()
    run_info = ScanRunInfo(id=run["id"], created_at=run["created_at"],
                           universe_count=run["universe_count"], provider=run["provider"])
    if df.empty:
        return LatestScanResponse(run=run_info, results=[], total=0)
    if min_score > 0:
        df = df[df["final_score"] >= min_score]
    if category:
        df = df[df["setup_category"] == category]
    if role:
        df = df[df["universe_role"] == role]
    records = df.to_dict("records")
    return LatestScanResponse(run=run_info, results=[_result(r) for r in records], total=len(records))

@router.get("/scan/overview", response_model=ScanOverviewResponse)
def get_scan_overview(repo: ScannerRepository = Depends(get_repo)):
    run = repo.latest_scan_run()
    df = repo.latest_scan_results()
    picks_df = repo.manual_picks()
    return ScanOverviewResponse(
        scanned=int(run["universe_count"]) if run else 0,
        candidates=len(df) if not df.empty else 0,
        picks=len(picks_df) if not picks_df.empty else 0,
        last_scan_at=run["created_at"] if run else None)
