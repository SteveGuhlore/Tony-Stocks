"""Lightweight pre-screener funnel for the watch-mode universe.

Filters the symbol universe ONCE per watch cycle before the discovery
rotation picks symbols for full scoring.  Uses cached scan_results data
(avg_volume_20, latest_close) from recent scan runs — no extra API calls.

Design rules:
- Called once before WatchUniverseRotator is initialized; rotator only
  sees quality-eligible symbols in its discovery pool.
- Missing-data symbols PASS THROUGH (fail naturally in scoring).
- When the filtered pool is too small, fall back to the full list.
- Returns the full list unchanged when enabled=False.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

LOGGER = logging.getLogger(__name__)

# Default config values used when the pre_screener block is absent or partial.
_DEFAULT_ENABLED = True
_DEFAULT_MIN_SYMBOLS = 50
_DEFAULT_MAX_CACHE_AGE_DAYS = 7


@dataclass
class PreScreenResult:
    """Result of a pre-screening pass."""

    symbols: list[str]
    """The filtered (or fallback) symbol list to use for rotation."""

    original_count: int
    """Number of symbols before filtering."""

    filtered_count: int
    """Number of symbols that passed all filters."""

    screened_out_count: int
    """Number of symbols removed by cheap filters."""

    no_cache_data_count: int
    """Number of symbols that had no recent cached data (passed through)."""

    fallback_used: bool
    """True when the filtered pool was too small and we reverted to the full list."""

    reasons: dict[str, int]
    """Per-reason counts for symbols that were screened out."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_count": self.original_count,
            "filtered_count": self.filtered_count,
            "screened_out_count": self.screened_out_count,
            "no_cache_data_count": self.no_cache_data_count,
            "fallback_used": self.fallback_used,
            "reasons": self.reasons,
        }


def pre_screen_universe(
    symbols: list[str],
    *,
    recent_metrics: dict[str, dict[str, Any]],
    min_price: float,
    max_price: float,
    min_avg_volume: float,
    min_symbols_after_filter: int = _DEFAULT_MIN_SYMBOLS,
) -> PreScreenResult:
    """Apply cheap price/volume filters to the universe using cached scan data.

    Parameters
    ----------
    symbols:
        Full symbol list to filter.
    recent_metrics:
        Mapping of symbol -> {'latest_close': float, 'avg_volume_20': float}.
        Built from recent scan_results rows.  Symbols absent from this mapping
        have no cached data and are passed through unconditionally.
    min_price, max_price:
        Price bounds from config (same thresholds used in run_scan).
    min_avg_volume:
        Average 20-day share volume minimum from config.
    min_symbols_after_filter:
        If fewer symbols pass the filter, fall back to the full list.

    Returns
    -------
    PreScreenResult
        Contains the final symbol list plus diagnostic counts.
    """
    passed: list[str] = []
    no_data_symbols: list[str] = []
    reasons: dict[str, int] = {
        "price_below_min": 0,
        "price_above_max": 0,
        "avg_volume_below_minimum": 0,
    }

    for symbol in symbols:
        metrics = recent_metrics.get(symbol.upper())
        if metrics is None:
            # No cached data — pass through; will fail naturally in scoring if bad.
            no_data_symbols.append(symbol)
            passed.append(symbol)
            continue

        close = metrics.get("latest_close")
        avg_vol = metrics.get("avg_volume_20")

        # Price filter (only when we have a close price)
        if close is not None:
            try:
                close_f = float(close)
            except (TypeError, ValueError):
                close_f = None
            if close_f is not None:
                if close_f < min_price:
                    reasons["price_below_min"] += 1
                    continue
                if close_f > max_price:
                    reasons["price_above_max"] += 1
                    continue

        # Volume filter (only when we have avg volume)
        if avg_vol is not None:
            try:
                avg_vol_f = float(avg_vol)
            except (TypeError, ValueError):
                avg_vol_f = None
            if avg_vol_f is not None and avg_vol_f < min_avg_volume:
                reasons["avg_volume_below_minimum"] += 1
                continue

        passed.append(symbol)

    screened_out = len(symbols) - len(passed)
    fallback_used = False
    final_symbols = passed

    if len(passed) < min_symbols_after_filter:
        LOGGER.warning(
            "Pre-screener filtered pool too small (%d < %d); falling back to full list (%d symbols).",
            len(passed),
            min_symbols_after_filter,
            len(symbols),
        )
        final_symbols = list(symbols)
        fallback_used = True

    LOGGER.info(
        "Pre-screener: %d → %d symbols (screened_out=%d no_data=%d fallback=%s)",
        len(symbols),
        len(final_symbols),
        screened_out,
        len(no_data_symbols),
        fallback_used,
    )

    return PreScreenResult(
        symbols=final_symbols,
        original_count=len(symbols),
        filtered_count=len(passed),
        screened_out_count=screened_out,
        no_cache_data_count=len(no_data_symbols),
        fallback_used=fallback_used,
        reasons=reasons,
    )


def build_recent_symbol_metrics(
    scan_result_rows: list[dict[str, Any]],
    *,
    max_cache_age_days: int = _DEFAULT_MAX_CACHE_AGE_DAYS,
) -> dict[str, dict[str, Any]]:
    """Build a per-symbol metrics dict from recent scan_results rows.

    Takes the MOST RECENT row per symbol within the cache age window.
    Older rows are ignored.  The result is used by ``pre_screen_universe()``.

    Parameters
    ----------
    scan_result_rows:
        List of dicts from the scan_results table.  Each must have at least
        'symbol' and 'created_at'.  Rows with 'latest_close' and
        'avg_volume_20' are used; missing fields pass through.
    max_cache_age_days:
        Rows older than this many days are ignored.

    Returns
    -------
    dict[str, dict]
        ``{'AAPL': {'latest_close': 190.5, 'avg_volume_20': 55_000_000}, ...}``
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_cache_age_days)
    # symbol -> (created_at, metrics_dict)
    best: dict[str, tuple[datetime, dict[str, Any]]] = {}

    for row in scan_result_rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue

        created_at_raw = row.get("created_at")
        if created_at_raw is None:
            continue
        try:
            if isinstance(created_at_raw, datetime):
                created_at = created_at_raw
            else:
                created_at_str = str(created_at_raw)
                # Handle both 'Z' suffix and '+00:00' style
                created_at_str = created_at_str.replace("Z", "+00:00")
                created_at = datetime.fromisoformat(created_at_str)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            continue

        if created_at < cutoff:
            continue

        existing = best.get(symbol)
        if existing is None or created_at > existing[0]:
            metrics: dict[str, Any] = {}
            if row.get("latest_close") is not None:
                metrics["latest_close"] = row["latest_close"]
            if row.get("avg_volume_20") is not None:
                metrics["avg_volume_20"] = row["avg_volume_20"]
            best[symbol] = (created_at, metrics)

    return {symbol: metrics for symbol, (_, metrics) in best.items()}


def load_pre_screener_config(settings_dict: dict[str, Any] | None) -> dict[str, Any]:
    """Return a normalized pre_screener config dict with defaults filled in."""
    cfg = dict(settings_dict or {})
    cfg.setdefault("enabled", _DEFAULT_ENABLED)
    cfg.setdefault("min_symbols_after_filter", _DEFAULT_MIN_SYMBOLS)
    cfg.setdefault("use_snapshot_cache", True)
    cfg.setdefault("max_cache_age_days", _DEFAULT_MAX_CACHE_AGE_DAYS)
    return cfg
