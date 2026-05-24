from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import TodayResponse, TodayKPIs, WatchStatus, TonyEventRow, CandidateSnapshotRow
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["today"])

def _nan(v):
    return v if isinstance(v, str) else None

def _watch(repo):
    run = repo.latest_watch_run()
    scan = repo.latest_scan_run()
    age = None
    if scan and scan.get("created_at"):
        try:
            created = datetime.fromisoformat(scan["created_at"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - created).total_seconds()
        except Exception:
            pass
    r = run or {}
    return WatchStatus(
        status=r.get("status"), started_at=r.get("started_at"),
        last_heartbeat_at=r.get("last_heartbeat_at"),
        cycles_completed=int(r.get("cycles_completed") or 0),
        api_requests=int(r.get("latest_api_requests_used") or 0),
        symbols_scanned=int(r.get("latest_symbols_scored") or 0),
        last_scan_age_seconds=age,
    )

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
        entry_triggered=bool(r.get("entry_triggered", 0)), entry_triggered_at=_nan(r.get("entry_triggered_at")),
    )

def _evt(r):
    return TonyEventRow(
        id=r["id"], event_type=r.get("event_type", ""), severity=r.get("severity", ""),
        symbol=_nan(r.get("symbol")), title=r.get("title", ""), message=r.get("message", ""),
        created_at=r.get("created_at", ""), acknowledged=bool(r.get("acknowledged", 0)),
    )

@router.get("/today", response_model=TodayResponse)
def get_today(repo: ScannerRepository = Depends(get_repo)):
    watch = _watch(repo)
    events_df = repo.list_tony_events(limit=15)
    events = [_evt(r) for r in events_df.to_dict("records")] if not events_df.empty else []
    snaps_df = repo.list_candidate_snapshots(limit=20)
    snaps = [_snap(r) for r in snaps_df.to_dict("records")] if not snaps_df.empty else []
    scan = repo.latest_scan_run()
    kpis = TodayKPIs(
        watching=repo.count_open_candidate_snapshots(),
        triggered=repo.count_triggered_candidate_snapshots(),
        win_rate=None, last_scan_at=scan["created_at"] if scan else None,
    )
    return TodayResponse(kpis=kpis, watch=watch, recent_events=events, active_snapshots=snaps)
