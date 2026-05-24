from __future__ import annotations
import math
from fastapi import APIRouter, Depends, Query
from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import OutcomesResponse, OutcomeKPIs, CandidateSnapshotRow
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["outcomes"])
_TARGET = {"target_hit", "target_before_stop"}
_STOP = {"stop_hit", "stop_before_target", "failed_setup"}

def _nan(v):
    return v if isinstance(v, str) else None

def _is_null(v):
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return False

def _snap(r):
    return CandidateSnapshotRow(
        id=r["id"], symbol=r["symbol"], status=r.get("status",""),
        setup_category=r.get("setup_category",""), universe_role=r.get("universe_role",""),
        total_score=r.get("total_score"), close=r.get("close"), entry=r.get("entry"),
        stop=r.get("stop"), target=r.get("target"), risk_reward=r.get("risk_reward"),
        snapshot_time=r.get("snapshot_time",""), outcome_label=_nan(r.get("outcome_label")),
        notes=_nan(r.get("notes")), tony_priority_label=_nan(r.get("tony_priority_label")),
        tony_recommended_action=_nan(r.get("tony_recommended_action")),
        tony_setup_read=_nan(r.get("tony_setup_read")), tony_hypothesis=_nan(r.get("tony_hypothesis")),
        entry_triggered=bool(r.get("entry_triggered",0)), entry_triggered_at=_nan(r.get("entry_triggered_at")))

@router.get("/outcomes", response_model=OutcomesResponse)
def get_outcomes(filter: str = Query("all", enum=["all","open","targets","stops"]),
                 repo: ScannerRepository = Depends(get_repo)):
    df = repo.list_snapshots_for_analytics(limit=500)
    records = df.to_dict("records") if not df.empty else []
    if filter == "open":
        records = [r for r in records if _is_null(r.get("outcome_label"))]
    elif filter == "targets":
        records = [r for r in records if r.get("outcome_label") in _TARGET]
    elif filter == "stops":
        records = [r for r in records if r.get("outcome_label") in _STOP]
    hits = sum(1 for r in records if r.get("outcome_label") in _TARGET)
    stops = sum(1 for r in records if r.get("outcome_label") in _STOP)
    closed = hits + stops
    return OutcomesResponse(
        kpis=OutcomeKPIs(active=sum(1 for r in records if _is_null(r.get("outcome_label"))),
                         closed=closed, target_hits=hits, stop_hits=stops,
                         win_rate=hits/closed if closed else None),
        snapshots=[_snap(r) for r in records[:200]])
