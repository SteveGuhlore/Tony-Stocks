from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import TonyEventsResponse, TonyEventRow
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["events"])

def _nan(v):
    return v if isinstance(v, str) else None

def _evt(r):
    return TonyEventRow(id=r["id"], event_type=r.get("event_type",""), severity=r.get("severity",""),
        symbol=_nan(r.get("symbol")), title=r.get("title",""), message=r.get("message",""),
        created_at=r.get("created_at",""), acknowledged=bool(r.get("acknowledged",0)))

@router.get("/events", response_model=TonyEventsResponse)
def list_events(severity: str | None = Query(None), event_type: str | None = Query(None),
                symbol: str | None = Query(None), limit: int = Query(50, le=200),
                unacked_only: bool = Query(False), repo: ScannerRepository = Depends(get_repo)):
    df = repo.list_tony_events(limit=limit, severity=severity, event_type=event_type,
                                symbol=symbol, unacknowledged=unacked_only)
    events = [_evt(r) for r in df.to_dict("records")] if not df.empty else []
    total = repo.count_tony_events()
    unacked = repo.count_tony_events(severity="warning") + repo.count_tony_events(severity="error")
    return TonyEventsResponse(events=events, total=total, unacknowledged_count=unacked)

@router.get("/events/stream")
async def event_stream(request: Request):
    db_path = request.app.state.db_path

    async def generate():
        repo = ScannerRepository(db_path)
        last_id = None
        while True:
            if await request.is_disconnected():
                break
            try:
                scan = repo.latest_scan_run()
                watch = repo.latest_watch_run()
                age = None
                if scan and scan.get("created_at"):
                    try:
                        created = datetime.fromisoformat(scan["created_at"].replace("Z", "+00:00"))
                        age = int((datetime.now(timezone.utc) - created).total_seconds())
                    except Exception:
                        pass
                hb = {
                    "type": "heartbeat",
                    "watch_status": watch.get("status") if watch else "unknown",
                    "last_scan_age_seconds": age,
                    "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
                }
                yield "data: " + json.dumps(hb) + "\n\n"
                edf = repo.list_tony_events(limit=5)
                if not edf.empty:
                    nid = int(edf.iloc[0]["id"])
                    if last_id is None:
                        last_id = nid
                    elif nid > last_id:
                        for _, row in edf[edf["id"] > last_id].iterrows():
                            p = {
                                "type": "event",
                                "event_type": row.get("event_type", ""),
                                "severity": row.get("severity", ""),
                                "symbol": _nan(row.get("symbol")),
                                "title": row.get("title", ""),
                                "message": row.get("message", ""),
                                "created_at": row.get("created_at", ""),
                            }
                            yield "data: " + json.dumps(p) + "\n\n"
                        last_id = nid
            except Exception as exc:
                err = {"type": "error", "message": str(exc)}
                yield "data: " + json.dumps(err) + "\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
