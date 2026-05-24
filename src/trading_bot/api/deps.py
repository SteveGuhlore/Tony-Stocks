from __future__ import annotations

from fastapi import Request

from trading_bot.storage.repositories import ScannerRepository


def get_repo(request: Request) -> ScannerRepository:
    return ScannerRepository(request.app.state.db_path)
