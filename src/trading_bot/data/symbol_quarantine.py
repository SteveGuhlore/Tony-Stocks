"""Non-destructive symbol quarantine for real-data-only scan/watch runs.

Quarantined symbols remain in universe YAML files. They are excluded from
fetching, scoring, snapshots, and Tony learning during real-data-only runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_bot.settings import ScannerSettings, real_data_only_enabled


@dataclass(frozen=True)
class QuarantineEntry:
    """One quarantined symbol with a human-readable reason."""

    symbol: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"symbol": self.symbol, "reason": self.reason}


@dataclass(frozen=True)
class SymbolQuarantineConfig:
    """Runtime quarantine configuration loaded from scanner YAML."""

    enabled: bool
    apply_during_real_data_only: bool
    entries: tuple[QuarantineEntry, ...]
    replacement_symbols: tuple[str, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(entry.symbol for entry in self.entries)

    def symbol_set(self) -> set[str]:
        return {entry.symbol for entry in self.entries}


def load_symbol_quarantine_config(settings: ScannerSettings) -> SymbolQuarantineConfig:
    """Load symbol quarantine settings from scanner config."""
    raw = settings.symbol_quarantine or {}
    entries: list[QuarantineEntry] = []
    for item in raw.get("symbols", []) or []:
        if isinstance(item, dict):
            symbol = str(item.get("symbol", "")).strip().upper()
            reason = str(item.get("reason", "") or "Quarantined for repeated missing real data.").strip()
        else:
            symbol = str(item).strip().upper()
            reason = "Quarantined for repeated missing real data."
        if symbol:
            entries.append(QuarantineEntry(symbol=symbol, reason=reason))
    replacements = tuple(
        str(item).strip().upper()
        for item in (raw.get("replacement_symbols") or [])
        if str(item).strip()
    )
    return SymbolQuarantineConfig(
        enabled=bool(raw.get("enabled", False)),
        apply_during_real_data_only=bool(raw.get("apply_during_real_data_only", True)),
        entries=tuple(entries),
        replacement_symbols=replacements,
    )


def quarantine_active(settings: ScannerSettings, real_data_only: bool | None = None) -> bool:
    """Return whether quarantine filtering should run for this scan/watch cycle."""
    cfg = load_symbol_quarantine_config(settings)
    if not cfg.enabled or not cfg.entries:
        return False
    if cfg.apply_during_real_data_only:
        return real_data_only_enabled(settings) if real_data_only is None else bool(real_data_only)
    return True


def apply_symbol_quarantine(
    symbols: list[str],
    settings: ScannerSettings,
    real_data_only: bool | None = None,
) -> tuple[list[str], list[QuarantineEntry]]:
    """Remove quarantined symbols from an active scan/watch symbol list."""
    cfg = load_symbol_quarantine_config(settings)
    real_only = real_data_only_enabled(settings) if real_data_only is None else bool(real_data_only)
    if not quarantine_active(settings, real_only):
        return list(symbols), []

    blocked = cfg.symbol_set()
    excluded = [entry for entry in cfg.entries if entry.symbol in {s.upper() for s in symbols}]
    kept = [symbol for symbol in symbols if symbol.upper() not in blocked]
    return kept, excluded


def configured_quarantine_entries(settings: ScannerSettings) -> list[QuarantineEntry]:
    """Return configured quarantine entries regardless of active filtering."""
    return list(load_symbol_quarantine_config(settings).entries)


def format_quarantine_symbols(entries: list[QuarantineEntry] | None = None, settings: ScannerSettings | None = None) -> str:
    """Format quarantine symbols for console or dashboard display."""
    if entries is None:
        if settings is None:
            return "none"
        entries = configured_quarantine_entries(settings)
    if not entries:
        return "none"
    return ", ".join(entry.symbol for entry in entries)
