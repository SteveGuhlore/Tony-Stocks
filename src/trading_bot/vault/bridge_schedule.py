"""Intraday bridge scheduling.

The bot hands Tony's picks to the Command Center several times a day so the CC can
re-analyze and adjust during the session, not just at EOD. Checkpoints (America/
New_York): 10:30 (1h post-open), 13:00 (post-lunch), 15:30 (pre-close adjust), and
16:00 (post-close handoff). Every auto checkpoint — including 16:00 — writes a
timestamped file (YYYY-MM-DDTHHMM.md) so it never overwrites the canonical daily
bridge / morning anchor; the CC dedups on the timestamp.

NOTE: the 16:00 slot is labelled "1600", NOT "eod". An "eod" label reuses the
daily-anchor filename YYYY-MM-DD.md, which the watch loop's disk-idempotency guard
(``bridge_file.exists()``) then skips — so the post-close handoff was silently
never emitted. The canonical daily file is still produced by the daily anchor and
by manual ``export-to-vault --slot eod``.
"""
from __future__ import annotations

from datetime import datetime, time

#: (slot label, checkpoint time ET). All auto slots are timestamped intraday-style
#: drops; the 16:00 "1600" slot is the post-close handoff.
BRIDGE_CHECKPOINTS: list[tuple[str, time]] = [
    ("1030", time(10, 30)),
    ("1300", time(13, 0)),
    ("1530", time(15, 30)),
    ("1600", time(16, 0)),
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
