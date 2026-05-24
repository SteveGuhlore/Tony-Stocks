from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request
from trading_bot.api.schemas import VaultBridgeSummary

router = APIRouter(tags=["vault"])

@router.get("/vault/bridge", response_model=VaultBridgeSummary)
def get_vault_bridge(request: Request):
    vault_dir = Path(getattr(request.app.state, "vault_dir", "vault"))
    bridge_dir = vault_dir / "bridge" / "tony-stocks"
    if not bridge_dir.exists():
        return VaultBridgeSummary(available=False, latest_date=None, content=None)
    md_files = sorted(bridge_dir.glob("*.md"), reverse=True)
    if not md_files:
        return VaultBridgeSummary(available=False, latest_date=None, content=None)
    latest = md_files[0]
    return VaultBridgeSummary(available=True, latest_date=latest.stem, content=latest.read_text(encoding="utf-8"))

@router.get("/insights")
def get_insights(request: Request, limit: int = 10):
    vault_dir = Path(getattr(request.app.state, "vault_dir", "vault"))
    notes_dir = vault_dir / "daily-notes"
    if not notes_dir.exists():
        return {"insights": []}
    notes = sorted(notes_dir.glob("*.md"), reverse=True)[:limit]
    return {"insights": [{"date": n.stem, "content": n.read_text(encoding="utf-8")} for n in notes]}
