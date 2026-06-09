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
import re
from pathlib import Path
from typing import Any

_DEFAULT_VERDICTS_PATH = "reports/tony_stocks_verdicts.json"
_EXIT_TOKENS = frozenset({
    "close", "closed", "sell", "sold", "selling", "exit", "exited",
    "get_out", "getout", "flatten", "liquidate",
})
_NEGATORS = frozenset({"no", "not", "dont", "don", "t", "never", "without", "avoid", "hold"})


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


def _is_exit_text(text: str) -> bool:
    """Word-boundary exit detection with a small negation guard.

    The old substring scan flattened positions on phrases that merely *contain* an exit
    word — "disclosed" contains "close", "do not sell yet" contains "sell". This trades
    money for grep. Tokenize instead, treat "get out" as a bigram, and skip an exit word
    when one of the two preceding tokens negates it ("not sell", "don't exit", "hold —
    don't close"). Verdict fields are short enums in practice; this is a guardrail for
    when the CC writes prose into them.
    """
    tokens = [t for t in re.split(r"[^a-z0-9_]+", text.lower()) if t]
    for i, tok in enumerate(tokens):
        if tok == "out" and i > 0 and tokens[i - 1] == "get":
            anchor = i - 1  # negation window sits before "get"
        elif tok in _EXIT_TOKENS:
            anchor = i
        else:
            continue
        if any(t in _NEGATORS for t in tokens[max(0, anchor - 2):anchor]):
            continue
        return True
    return False


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
        )
        if _is_exit_text(signals):
            out.add(symbol)
    return out
