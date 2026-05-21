"""Shared pytest configuration for stable Windows temp cleanup.

Keeps pytest basetemp outside the repo by default so IDE sync, WSL mounts,
and stale project .pytest_tmp folders do not block teardown.
"""

from __future__ import annotations

import gc
import os
from datetime import datetime
from pathlib import Path

import pytest


def _default_basetemp_root() -> Path:
    """Return a user-writable basetemp root (never inside the repo tree)."""
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        return Path(local_app) / "TradingBotTests" / "pytest"
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if temp:
        return Path(temp) / "TradingBotTests" / "pytest"
    return Path.cwd() / ".pytest_tmp_sessions" / "pytest"


def pytest_configure(config: pytest.Config) -> None:
    """Set basetemp when pytest is launched without --basetemp (IDE, ad-hoc CLI)."""
    if config.option.basetemp:
        return
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    basetemp = _default_basetemp_root() / f"run_{session_id}_{os.getpid()}"
    basetemp.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(basetemp)


@pytest.fixture(autouse=True)
def _release_sqlite_file_handles() -> None:
    """Encourage SQLite and other handles to close before tmp_path teardown on Windows."""
    yield
    gc.collect()
