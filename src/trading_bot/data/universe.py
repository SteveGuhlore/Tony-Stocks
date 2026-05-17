from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from trading_bot.settings import load_yaml


@dataclass(frozen=True)
class UniverseSymbol:
    symbol: str
    name: str = ""
    tags: tuple[str, ...] = ()
    sector: str = ""
    industry: str = ""
    universe_role: str = "primary_candidate"
    demo_profile: str = ""
    notes: str = ""


@dataclass(frozen=True)
class UniverseFilters:
    min_price: float = 5.0
    max_price: float = 500.0
    min_avg_volume: int = 500_000
    exclude_otc: bool = True
    exclude_missing_data: bool = True
    max_universe_size: int = 100


@dataclass(frozen=True)
class UniverseConfig:
    symbols: tuple[str, ...]
    metadata_by_symbol: dict[str, UniverseSymbol]
    tags_by_symbol: dict[str, tuple[str, ...]]
    csv_path: Path | None
    filters: UniverseFilters


def normalize_symbol(symbol: str) -> str:
    """Return a clean uppercase ticker symbol."""
    return symbol.strip().upper()


def load_universe_config(path: str | Path) -> UniverseConfig:
    """Load universe symbols and filters from YAML."""
    raw = load_yaml(path)
    symbols: list[str] = []
    metadata_by_symbol: dict[str, UniverseSymbol] = {}
    tags_by_symbol: dict[str, tuple[str, ...]] = {}
    for item in raw.get("symbols", []):
        if isinstance(item, dict):
            symbol = normalize_symbol(str(item.get("symbol", "")))
            tags = tuple(normalize_symbol(str(tag)).lower() for tag in item.get("tags", []) if str(tag).strip())
            metadata = UniverseSymbol(
                symbol=symbol,
                name=str(item.get("name", "") or ""),
                tags=tags,
                sector=str(item.get("sector", "") or "").lower(),
                industry=str(item.get("industry", "") or "").lower(),
                universe_role=str(item.get("universe_role", "primary_candidate") or "primary_candidate").lower(),
                demo_profile=str(item.get("demo_profile", "") or "").lower(),
                notes=str(item.get("notes", "") or ""),
            )
        else:
            symbol = normalize_symbol(str(item))
            tags = ()
            metadata = UniverseSymbol(symbol=symbol)
        if symbol:
            symbols.append(symbol)
            metadata_by_symbol[symbol] = metadata
            tags_by_symbol[symbol] = tags
    csv_path = Path(raw["csv_path"]) if raw.get("csv_path") else None
    filters_raw = raw.get("filters", {}) or {}
    if not isinstance(filters_raw, dict):
        raise ValueError("universe filters must be a mapping.")
    return UniverseConfig(
        symbols=tuple(symbols),
        metadata_by_symbol=metadata_by_symbol,
        tags_by_symbol=tags_by_symbol,
        csv_path=csv_path,
        filters=UniverseFilters(**filters_raw),
    )


def load_symbols_from_csv(path: str | Path) -> list[str]:
    """Load ticker symbols from a CSV with symbol/ticker or first column."""
    df = pd.read_csv(path)
    if df.empty:
        return []
    lower_columns = {str(col).lower(): col for col in df.columns}
    column = lower_columns.get("symbol") or lower_columns.get("ticker") or df.columns[0]
    return [normalize_symbol(str(value)) for value in df[column].dropna()]


def load_universe(path: str | Path, manual_symbols: Iterable[str] | None = None) -> list[str]:
    """Load a de-duplicated universe from config, optional CSV, and manual symbols."""
    config = load_universe_config(path)
    symbols: list[str] = list(config.symbols)
    if config.csv_path:
        symbols.extend(load_symbols_from_csv(config.csv_path))
    if manual_symbols:
        symbols.extend(normalize_symbol(symbol) for symbol in manual_symbols)
    seen: set[str] = set()
    result: list[str] = []
    for symbol in symbols:
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return result[: config.filters.max_universe_size]


def load_universe_tags(path: str | Path) -> dict[str, tuple[str, ...]]:
    """Load optional tags for symbols in the configured universe."""
    return load_universe_config(path).tags_by_symbol


def load_universe_metadata(path: str | Path) -> dict[str, UniverseSymbol]:
    """Load full optional metadata for symbols in the configured universe."""
    return load_universe_config(path).metadata_by_symbol
