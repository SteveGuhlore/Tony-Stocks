from __future__ import annotations

from fastapi import APIRouter, Depends

from trading_bot.api.deps import get_repo
from trading_bot.api.schemas import HealthResponse
from trading_bot.storage.repositories import ScannerRepository

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(repo: ScannerRepository = Depends(get_repo)) -> HealthResponse:
    return HealthResponse(status="ok", db_path=str(repo.database_path))
