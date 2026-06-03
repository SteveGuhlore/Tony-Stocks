"""Read Command Center verdicts — the bot side of the CC-exit loop.

The Command Center writes ``reports/tony_stocks_verdicts.json`` (override with
``TONY_VERDICTS_FILE``); the bot reads it each paper cycle and flattens any position
the CC verdict says to close/sell. Verdict enum: reaffirm | adjust | override | close.
Tolerant of a list, a ``{"verdicts": [...]}`` wrapper, or a dict keyed by symbol.
Pure/IO-light: never raises on a missing or malformed file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_DEFAULT_VERDICTS_PATH = "reports/tony_stocks_verdicts.json"
_EXIT_TOKENS = ("close", "sell", "exit", "get out", "get_out", "getout", "flatten")


def load_cc_verdicts(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return the CC verdict records, or [] if absent/malformed."""
    if path is None:
        path = os.environ.get("TONY_VERDICTS_FILE") or _DEFAULT_VERDICTS_PATH
    file_path = Path(path)
    if not file_path.exists():
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        if isinstance(data.get("verdicts"), list):
            return [r for r in data["verdicts"] if isinstance(r, dict)]
        rows: list[dict[str, Any]] = []
        for key, value in data.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("symbol", key)
                rows.append(row)
        return rows
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def cc_exit_symbols(verdicts: list[dict[str, Any]] | None) -> set[str]:
    """Symbols whose verdict/action says to close (sell/exit/flatten)."""
    out: set[str] = set()
    for verdict in verdicts or []:
        symbol = str(verdict.get("symbol") or "").upper()
        if not symbol:
            continue
        if verdict.get("exit") is True or verdict.get("should_close") is True:
            out.add(symbol)
            continue
        signals = " ".join(
            str(verdict.get(key) or "")
            for key in ("verdict", "action", "recommended_action", "decision")
        ).lower()
        if any(token in signals for token in _EXIT_TOKENS):
            out.add(symbol)
    return out
