from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import SystemHealthResponse, WatchStatus, ScanRunInfo
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["system"])

@router.get("/system/health", response_model=SystemHealthResponse)
def get_system_health(repo: ScannerRepository = Depends(get_repo)):
    wr = repo.latest_watch_run()
    sr = repo.latest_scan_run()
    age = None
    if sr and sr.get("created_at"):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                sr["created_at"].replace("Z", "+00:00"))).total_seconds()
        except Exception:
            pass
    r = wr or {}
    watch = WatchStatus(
        status=r.get("status"), started_at=r.get("started_at"),
        last_heartbeat_at=r.get("last_heartbeat_at"),
        cycles_completed=int(r.get("cycles_completed") or 0),
        api_requests=int(r.get("latest_api_requests_used") or 0),
        symbols_scanned=int(r.get("latest_symbols_scored") or 0),
        last_scan_age_seconds=age)
    scan_info = ScanRunInfo(id=sr["id"], created_at=sr["created_at"],
        universe_count=sr["universe_count"], provider=sr["provider"]) if sr else None
    total = repo.count_tony_events()
    unacked = repo.count_tony_events(severity="warning") + repo.count_tony_events(severity="error")
    return SystemHealthResponse(watch=watch, last_scan_run=scan_info,
        open_snapshots=repo.count_open_candidate_snapshots(),
        triggered_snapshots=repo.count_triggered_candidate_snapshots(),
        tony_events_total=total, unacknowledged_warnings=unacked)
