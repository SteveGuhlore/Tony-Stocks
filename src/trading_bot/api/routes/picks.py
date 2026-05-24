from __future__ import annotations
from fastapi import APIRouter, Depends
from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import PicksResponse, ManualPickRow, TrackingResponse, CandidateSnapshotRow
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["picks"])

def _nan(v):
    return v if isinstance(v, str) else None

def _pick(r):
    return ManualPickRow(id=r["id"], symbol=r["symbol"], status=r.get("status", ""),
        planned_entry=r.get("planned_entry"), planned_stop=r.get("planned_stop"),
        planned_target=r.get("planned_target"), notes=_nan(r.get("notes")), picked_at=r.get("picked_at", ""))

def _snap(r):
    return CandidateSnapshotRow(
        id=r["id"], symbol=r["symbol"], status=r.get("status", ""),
        setup_category=r.get("setup_category", ""), universe_role=r.get("universe_role", ""),
        total_score=r.get("total_score"), close=r.get("close"), entry=r.get("entry"),
        stop=r.get("stop"), target=r.get("target"), risk_reward=r.get("risk_reward"),
        snapshot_time=r.get("snapshot_time", ""), outcome_label=_nan(r.get("outcome_label")),
        notes=_nan(r.get("notes")), tony_priority_label=_nan(r.get("tony_priority_label")),
        tony_recommended_action=_nan(r.get("tony_recommended_action")),
        tony_setup_read=_nan(r.get("tony_setup_read")), tony_hypothesis=_nan(r.get("tony_hypothesis")),
        entry_triggered=bool(r.get("entry_triggered", 0)), entry_triggered_at=_nan(r.get("entry_triggered_at")))

@router.get("/picks", response_model=PicksResponse)
def get_picks(repo: ScannerRepository = Depends(get_repo)):
    df = repo.manual_picks()
    return PicksResponse(picks=[_pick(r) for r in df.to_dict("records")] if not df.empty else [])

@router.get("/tracking", response_model=TrackingResponse)
def get_tracking(repo: ScannerRepository = Depends(get_repo)):
    df = repo.list_candidate_snapshots(limit=200)
    all_s = df.to_dict("records") if not df.empty else []
    return TrackingResponse(
        active=[_snap(r) for r in all_s if r.get("status") in {"open/watch","active","triggered"}],
        watching=[_snap(r) for r in all_s if r.get("status") in {"watching","pending"}],
        open_count=repo.count_open_candidate_snapshots(),
        triggered_count=repo.count_triggered_candidate_snapshots())
