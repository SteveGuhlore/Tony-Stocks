"""Personalization endpoints for the Kinetic Tape dashboard (pins / notes / presets /
journal / call ratings / price alerts). Operator-only convenience state; not money-adjacent,
so no env-fence — but additive and minimal. Backed by the additive SQLite tables created in
``storage/database.py``."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from trading_bot.api.deps import get_repo
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["personalize"], prefix="/personalize")


# ── pins ────────────────────────────────────────────────────────────────────────

class PinBody(BaseModel):
    symbol: str
    pinned: bool = True


@router.get("/pins")
def get_pins(repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    return {"pins": repo.list_pins()}


@router.post("/pins")
def set_pin(body: PinBody, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    if body.pinned:
        repo.add_pin(body.symbol)
    else:
        repo.remove_pin(body.symbol)
    return {"ok": True, "symbol": body.symbol.upper(), "pinned": body.pinned}


# ── notes ─────────────────────────────────────────────────────────────────────

class NoteBody(BaseModel):
    symbol: str
    body: str


@router.get("/notes")
def get_notes(symbol: str | None = None, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    return {"notes": repo.list_notes(symbol=symbol)}


@router.post("/notes")
def add_note(body: NoteBody, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    note_id = repo.add_note(symbol=body.symbol, body=body.body)
    return {"ok": True, "id": note_id}


# ── presets ─────────────────────────────────────────────────────────────────────

class PresetBody(BaseModel):
    name: str
    payload: dict[str, Any] = {}


@router.get("/presets")
def get_presets(repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    out = []
    for p in repo.list_presets():
        try:
            payload = json.loads(p.get("payload_json") or "{}")
        except (ValueError, TypeError):
            payload = {}
        out.append({"name": p.get("name"), "payload": payload,
                    "updated_at": p.get("updated_at")})
    return {"presets": out}


@router.post("/presets")
def save_preset(body: PresetBody, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    repo.upsert_preset(name=body.name, payload_json=json.dumps(body.payload, default=str))
    return {"ok": True, "name": body.name}


# ── journal ─────────────────────────────────────────────────────────────────────

class JournalBody(BaseModel):
    symbol: str | None = None
    entry: str


@router.get("/journal")
def get_journal(repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    return {"journal": repo.list_journal()}


@router.post("/journal")
def add_journal(body: JournalBody, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    entry_id = repo.add_journal_entry(symbol=body.symbol, entry=body.entry)
    return {"ok": True, "id": entry_id}


# ── call ratings ─────────────────────────────────────────────────────────────────

class RatingBody(BaseModel):
    symbol: str
    rating: int
    note: str | None = None


@router.get("/call-ratings")
def get_ratings(symbol: str | None = None, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    return {"ratings": repo.list_call_ratings(symbol=symbol)}


@router.post("/call-ratings")
def add_rating(body: RatingBody, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    rating_id = repo.add_call_rating(symbol=body.symbol, rating=body.rating, note=body.note)
    return {"ok": True, "id": rating_id}


# ── price alerts ─────────────────────────────────────────────────────────────────

class PriceAlertBody(BaseModel):
    symbol: str
    target_price: float
    direction: str = "above"  # above | below


@router.get("/price-alerts")
def get_alerts(active_only: bool = False, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    return {"alerts": repo.list_price_alerts(active_only=active_only)}


@router.post("/price-alerts")
def add_alert(body: PriceAlertBody, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    alert_id = repo.add_price_alert(symbol=body.symbol, target_price=body.target_price, direction=body.direction)
    return {"ok": True, "id": alert_id}


@router.post("/price-alerts/{alert_id}/deactivate")
def deactivate_alert(alert_id: int, repo: ScannerRepository = Depends(get_repo)) -> dict[str, Any]:
    repo.deactivate_price_alert(alert_id)
    return {"ok": True, "id": alert_id}
