from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_market_calendars as mcal


def market_status(now: datetime | None = None) -> dict:
    """Return NYSE market status relative to `now` (UTC).

    Returns dict with keys: open (bool), next_open (ISO str | None),
    next_close (ISO str | None), timezone (str).
    """
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    cal = mcal.get_calendar("NYSE")
    ts_pd = pd.Timestamp(ts)

    start = (ts - timedelta(days=1)).strftime("%Y-%m-%d")
    end = (ts + timedelta(days=14)).strftime("%Y-%m-%d")
    schedule = cal.schedule(start_date=start, end_date=end)

    is_open = False
    next_open_ts: pd.Timestamp | None = None
    next_close_ts: pd.Timestamp | None = None

    for _, row in schedule.iterrows():
        open_ts: pd.Timestamp = row["market_open"]
        close_ts: pd.Timestamp = row["market_close"]

        if open_ts <= ts_pd < close_ts:
            is_open = True
            next_close_ts = close_ts
            future = schedule[schedule["market_open"] > close_ts]
            next_open_ts = future.iloc[0]["market_open"] if not future.empty else None
            break
        elif open_ts > ts_pd:
            next_open_ts = open_ts
            next_close_ts = close_ts
            break

    return {
        "open": is_open,
        "next_open": next_open_ts.isoformat() if next_open_ts is not None else None,
        "next_close": next_close_ts.isoformat() if next_close_ts is not None else None,
        "timezone": "America/New_York",
    }


def is_market_open(now: datetime | None = None) -> bool:
    return market_status(now)["open"]
