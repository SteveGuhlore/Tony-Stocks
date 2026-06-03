"""Intraday bridge scheduling.

The bot hands Tony's picks to the Command Center several times a day so the CC can
re-analyze and adjust during the session, not just at EOD. Checkpoints (America/
New_York): 10:30 (1h post-open), 13:00 (post-lunch), 15:30 (pre-close adjust), and
16:00 (EOD close). Intraday slots write a timestamped file so they never overwrite
the canonical daily bridge; the CC dedups on the timestamp.
"""
from __future__ import annotations

from datetime import datetime, time

#: (slot label, checkpoint time ET). "eod" is the canonical daily drop.
BRIDGE_CHECKPOINTS: list[tuple[str, time]] = [
    ("1030", time(10, 30)),
    ("1300", time(13, 0)),
    ("1530", time(15, 30)),
    ("eod", time(16, 0)),
]


def due_bridge_slots(now_et: datetime, emitted: set[str]) -> list[str]:
    """Return checkpoint slot labels whose time has passed and not yet emitted today.

    ``now_et`` must be an America/New_York datetime. Weekends return nothing
    (no market day). Pure: the caller tracks ``emitted`` and idempotency.
    """
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return []
    current = now_et.time()
    return [label for label, checkpoint in BRIDGE_CHECKPOINTS if current >= checkpoint and label not in emitted]
