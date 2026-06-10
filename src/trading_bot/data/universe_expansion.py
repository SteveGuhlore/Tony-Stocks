"""Quality-gated universe expansion (stage 4 — screened, not curated).

Prior expansions (scripts/expand_universe*.py) appended hardcoded curated lists.
This module discovers candidates from Alpaca's free ``/v2/assets`` endpoint, screens
them against the scanner's own liquidity floors using batch daily bars, classifies
sector via Finnhub profile2 (free tier) so the sector-exposure cap can see them, and
appends YAML blocks in the proven expansion-2/3 format (quoted symbols, additive only).

Design (docs/superpowers/specs/2026-06-10-universe-expansion-design.md):
  discover -> dedupe -> screen -> sector -> rank by dollar volume -> cap -> write.

Pure core + injected fetchers: every decision function below is side-effect free and
unit-tested offline; the three ``fetch_*`` helpers are the only network code and are
passed into ``run_expansion`` as callables so tests (and dry-runs) never need keys.
Research/scanning only — adding a symbol never places an order.
"""
from __future__ import annotations

import logging
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)

# Trading API (assets live here, NOT on the data API). Works with paper keys.
ALPACA_TRADING_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_DATA_BATCH_URL = "https://data.alpaca.markets/v2/stocks/bars"
FINNHUB_PROFILE_URL = "https://finnhub.io/api/v1/stock/profile2"

#: Exchanges we accept from /v2/assets (everything else — chiefly OTC — is dropped).
ALLOWED_EXCHANGES = frozenset({"NYSE", "NASDAQ", "ARCA", "AMEX", "NYSEMKT", "BATS"})

#: Name-substring heuristics for non-common-stock instruments the scanner shouldn't
#: hold (SPAC warrants/units/rights, preferreds, notes, depositary shares).
_NAME_EXCLUDE_TOKENS = (
    "warrant", " right", "rights", " unit", "units", "preferred", "pfd",
    " notes", "depositary", "% ",
)

#: ETF/fund name heuristics. /v2/assets lists ETFs as us_equity; without this the
#: most liquid "additions" are bond/leveraged/index funds (LQD, SOXL, TLT...) that
#: would be scored as regular stocks and paper-traded. Verified against a live
#: dry-run: the top unclassified survivors were all funds. ("trust" alone is NOT
#: excluded — REIT names legitimately carry it.)
_FUND_NAME_TOKENS = (
    "etf", "etn", " fund", "ishares", "spdr", "proshares", "direxion", "vanguard",
    "invesco", "wisdomtree", "global x", "vaneck", "xtrackers", "first trust",
    "index", "1x ", "2x ", "3x ",
)

#: Plain 1-5 letter tickers only: kills ".", "-", "/" share-class symbols outright.
_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")


# ---------------------------------------------------------------------------
# Screening thresholds (mirror the scanner's own floors — see default_config.yaml
# min_price/max_price/min_avg_volume and research_funnel.min_dollar_volume)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScreenThresholds:
    min_price: float = 5.0
    max_price: float = 500.0
    min_avg_volume: float = 300_000.0
    min_dollar_volume: float = 5_000_000.0
    min_bars: int = 20          # IEX data-availability gate (pre-empts quarantine churn)
    volume_window: int = 20

    #: dollar-volume floor above which an addition is a primary_candidate
    primary_dollar_volume: float = 25_000_000.0


@dataclass(frozen=True)
class ExpansionCandidate:
    symbol: str
    name: str = ""
    sector: str = ""            # canonical lowercase, "" = unclassified (uncapped by sector gate)
    last_close: float = 0.0
    avg_volume: float = 0.0
    dollar_volume: float = 0.0


@dataclass
class ExpansionReport:
    discovered: int = 0
    after_asset_filter: int = 0
    after_dedupe: int = 0
    screened_out: Counter = field(default_factory=Counter)
    survivors: int = 0
    added: list[ExpansionCandidate] = field(default_factory=list)
    unknown_sector: list[str] = field(default_factory=list)
    sector_distribution: Counter = field(default_factory=Counter)
    written: bool = False
    yaml_path: str = ""


# ---------------------------------------------------------------------------
# Pure: discovery filtering
# ---------------------------------------------------------------------------

def filter_assets(
    assets: Iterable[dict[str, Any]],
    existing_symbols: Iterable[str],
    quarantined_symbols: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], Counter]:
    """Keep tradable common-stock-shaped listings we don't already track.

    Returns (kept asset dicts, rejection-reason counter). Never raises on a
    malformed asset row — it just counts it out.
    """
    existing = {str(s).upper() for s in existing_symbols}
    quarantined = {str(s).upper() for s in quarantined_symbols}
    kept: list[dict[str, Any]] = []
    rejected: Counter = Counter()
    seen: set[str] = set()
    for a in assets:
        if not isinstance(a, dict):
            rejected["malformed"] += 1
            continue
        sym = str(a.get("symbol") or "").upper().strip()
        if not _SYMBOL_RE.match(sym):
            rejected["symbol_shape"] += 1
            continue
        if sym in seen:
            rejected["duplicate_listing"] += 1
            continue
        seen.add(sym)
        if sym in existing:
            rejected["already_in_universe"] += 1
            continue
        if sym in quarantined:
            rejected["quarantined"] += 1
            continue
        if not a.get("tradable", False):
            rejected["not_tradable"] += 1
            continue
        if str(a.get("exchange") or "").upper() not in ALLOWED_EXCHANGES:
            rejected["exchange"] += 1
            continue
        name_l = str(a.get("name") or "").lower()
        if any(tok in name_l for tok in _NAME_EXCLUDE_TOKENS):
            rejected["instrument_type"] += 1
            continue
        if any(tok in name_l for tok in _FUND_NAME_TOKENS):
            rejected["fund_etf"] += 1
            continue
        kept.append(a)
    return kept, rejected


# ---------------------------------------------------------------------------
# Pure: liquidity screen
# ---------------------------------------------------------------------------

def screen_candidate(
    closes: Sequence[float],
    volumes: Sequence[float],
    thresholds: ScreenThresholds,
) -> tuple[bool, str, dict[str, float]]:
    """Apply the scanner's own liquidity/price floors to a candidate's daily bars.

    Returns (passed, reject_reason, metrics). Missing/short data fails closed —
    a name IEX can't serve 20 daily bars for would just churn the quarantine list.
    """
    n = min(len(closes), len(volumes))
    if n < thresholds.min_bars:
        return False, "insufficient_bars", {}
    closes = [float(c) for c in closes[-thresholds.volume_window:]]
    volumes = [float(v) for v in volumes[-thresholds.volume_window:]]
    last_close = closes[-1]
    avg_volume = sum(volumes) / len(volumes)
    dollar_volume = sum(c * v for c, v in zip(closes, volumes)) / len(closes)
    metrics = {"last_close": last_close, "avg_volume": avg_volume, "dollar_volume": dollar_volume}
    if last_close < thresholds.min_price:
        return False, "price_below_min", metrics
    if last_close > thresholds.max_price:
        return False, "price_above_max", metrics
    if avg_volume < thresholds.min_avg_volume:
        return False, "avg_volume_below_min", metrics
    if dollar_volume < thresholds.min_dollar_volume:
        return False, "dollar_volume_below_min", metrics
    return True, "", metrics


# ---------------------------------------------------------------------------
# Pure: sector classification (Finnhub finnhubIndustry -> the YAML's canonical set)
# ---------------------------------------------------------------------------

_EXACT_INDUSTRY_MAP = {
    "technology": "technology",
    "semiconductors": "technology",
    "communications": "communication",
    "media": "communication",
    "telecommunication": "communication",
    "banking": "financials",
    "financial services": "financials",
    "insurance": "financials",
    "capital markets": "financials",
    "real estate": "real_estate",
    "health care": "healthcare",
    "pharmaceuticals": "healthcare",
    "biotechnology": "healthcare",
    "life sciences tools & services": "healthcare",
    "utilities": "utilities",
    "energy": "energy",
    "chemicals": "materials",
    "metals & mining": "materials",
    "packaging": "materials",
    "retail": "consumer",
    "beverages": "consumer",
    "food products": "consumer",
    "tobacco": "consumer",
    "automobiles": "consumer",
    "hotels restaurants & leisure": "consumer",
    "textiles apparel & luxury goods": "consumer",
    "consumer products": "consumer",
    "diversified consumer services": "consumer",
    "aerospace & defense": "industrials",
    "airlines": "industrials",
    "machinery": "industrials",
    "industrial conglomerates": "industrials",
    "road & rail": "industrials",
    "marine": "industrials",
    "logistics & transportation": "industrials",
    "electrical equipment": "industrials",
    "building": "industrials",
    "construction": "industrials",
    "commercial services & supplies": "industrials",
    "professional services": "industrials",
    "trading companies & distributors": "industrials",
}

_KEYWORD_SECTOR_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("bank", "insur", "financ", "capital", "asset manage", "mortgage"), "financials"),
    (("pharma", "biotech", "health", "medical", "life science", "diagnostic"), "healthcare"),
    (("semiconductor", "software", "technology", "computer", "electronic", "it service", "internet"), "technology"),
    (("media", "telecom", "communic", "entertain", "broadcast", "publish"), "communication"),
    (("real estate", "reit"), "real_estate"),
    (("util",), "utilities"),
    (("energy", "oil", "gas", "coal", "solar", "drilling", "pipeline"), "energy"),
    (("metal", "mining", "chemical", "paper", "packag", "steel", "material"), "materials"),
    (("retail", "consumer", "food", "beverage", "hotel", "restaurant", "leisure",
      "apparel", "auto", "textile", "tobacco", "household", "luxury"), "consumer"),
    (("aero", "defense", "airline", "machin", "industrial", "transport", "rail",
      "marine", "construct", "build", "electrical", "logistic", "commercial service",
      "professional service", "distribut"), "industrials"),
)


def map_industry_to_sector(industry: str | None) -> str:
    """Map a Finnhub ``finnhubIndustry`` string to the universe YAML's canonical
    lowercase sectors. Unknown -> "" (loader-safe; uncapped by the sector gate)."""
    text = str(industry or "").strip().lower()
    if not text:
        return ""
    if text in _EXACT_INDUSTRY_MAP:
        return _EXACT_INDUSTRY_MAP[text]
    for keywords, sector in _KEYWORD_SECTOR_RULES:
        if any(k in text for k in keywords):
            return sector
    return ""


# ---------------------------------------------------------------------------
# Pure: role assignment + YAML emission (expansion-2/3 proven format)
# ---------------------------------------------------------------------------

def assign_role(dollar_volume: float, thresholds: ScreenThresholds) -> tuple[str, str, str]:
    """(universe_role, demo_profile, cap_tag) by liquidity tier."""
    if dollar_volume >= thresholds.primary_dollar_volume:
        return "primary_candidate", "base_building", "mid_cap"
    return "speculative_candidate", "high_volatility_whipsaw", "small_cap"


def _yaml_safe_name(name: str) -> str:
    cleaned = str(name or "").replace('"', "'").strip()
    return cleaned[:80]


def build_yaml_blocks(
    candidates: Sequence[ExpansionCandidate],
    thresholds: ScreenThresholds,
    stage_comment: str = "Staged expansion 4 (2026-06-10): screened liquid additions",
) -> str:
    """Emit YAML entries in the expansion-2/3 format. Symbols are ALWAYS quoted so
    YAML-1.1 boolean tickers (ON/NO/OFF/YES/...) stay strings; names double-quoted."""
    if not candidates:
        return ""
    lines = [
        f"  # ── {stage_comment} —\n",
        "  #    Alpaca /v2/assets discovery -> liquidity screen (price/volume/dollar-volume\n",
        "  #    floors mirror the scanner) -> Finnhub sector. Research/scanning only.\n",
    ]
    for c in candidates:
        role, profile, cap_tag = assign_role(c.dollar_volume, thresholds)
        tags = [cap_tag] + ([c.sector] if c.sector else []) + ["discovery_screened"]
        lines.append(f'  - symbol: "{c.symbol}"\n')
        lines.append(f'    name: "{_yaml_safe_name(c.name)}"\n')
        lines.append(f"    tags: [{', '.join(tags)}]\n")
        if c.sector:
            lines.append(f"    sector: {c.sector}\n")
        lines.append(f"    universe_role: {role}\n")
        lines.append(f"    demo_profile: {profile}\n")
        # Provenance for later pruning: how it got in + its screened liquidity.
        lines.append(f"    notes: \"Screened expansion; ~${int(c.dollar_volume):,}/day dollar vol.\"\n")
    return "".join(lines)


def insert_blocks_into_yaml(text: str, blocks: str) -> str:
    """Insert new symbol blocks at the END of the top-level ``symbols:`` list —
    immediately before the first top-level key that follows it (``csv_path:`` in
    the live file, ``filters:`` in older fixtures). Anchoring on ``filters:``
    specifically corrupted the live file: blocks landed between ``csv_path:``
    (null value) and ``filters:``, so YAML parsed them as the VALUE of csv_path.
    Raises if no anchor is found rather than guessing — additive-only safety."""
    if not blocks:
        return text
    lines = text.splitlines(keepends=True)
    in_symbols = False
    for i, line in enumerate(lines):
        if line.startswith("symbols:"):
            in_symbols = True
            continue
        # First top-level key after the symbols block = insertion anchor.
        if in_symbols and re.match(r"^[A-Za-z_][\w]*:", line):
            return "".join(lines[:i]) + blocks + "\n" + "".join(lines[i:])
    if in_symbols:
        # symbols: is the last top-level block — append at end of file.
        return text + ("" if text.endswith("\n") else "\n") + blocks
    raise ValueError("universe YAML missing top-level 'symbols:' anchor; refusing to append blind")


def bump_max_universe_size(text: str, required: int) -> str:
    """Raise filters.max_universe_size if it would truncate the grown universe
    (universe.py slices the loaded list to this value)."""
    # Anchor to the start of a (possibly indented) line so a comment that happens to
    # contain "max_universe_size: N" can't be matched/corrupted ahead of the real key.
    m = re.search(r"^(\s*max_universe_size:\s*)(\d+)", text, re.MULTILINE)
    if not m:
        return text
    current = int(m.group(2))
    if current >= required:
        return text
    return text[: m.start()] + f"{m.group(1)}{required}" + text[m.end():]


# ---------------------------------------------------------------------------
# Impure: fetchers (injected into run_expansion; the only network code here)
# ---------------------------------------------------------------------------

def fetch_active_assets(
    api_key: str, secret_key: str, *, base_url: str = ALPACA_TRADING_BASE_URL, timeout: int = 60,
) -> list[dict[str, Any]]:
    """All active US-equity assets from Alpaca's free /v2/assets (trading API)."""
    resp = requests.get(
        f"{base_url}/v2/assets",
        headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key},
        params={"status": "active", "asset_class": "us_equity"},
        timeout=timeout,
    )
    if not resp.ok:
        raise OSError(f"Alpaca /v2/assets HTTP {resp.status_code}: {resp.text[:200]}")
    body = resp.json()
    return body if isinstance(body, list) else []


def fetch_daily_closes_volumes(
    symbols: Sequence[str],
    api_key: str,
    secret_key: str,
    *,
    lookback_days: int = 45,
    feed: str = "iex",
    batch_size: int = 175,
    timeout: int = 60,
    sleep_seconds: float = 0.3,
) -> dict[str, tuple[list[float], list[float]]]:
    """Batch daily bars -> {SYMBOL: (closes, volumes)}. Mirrors market_data.py's
    batch pattern (175/batch, pagination, 429 backoff). ~4k candidates ≈ 23 requests."""
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    end = datetime.now(UTC).date()
    start = end - timedelta(days=lookback_days)
    out: dict[str, tuple[list[float], list[float]]] = {}
    syms = [s.upper() for s in symbols]
    for i in range(0, len(syms), batch_size):
        chunk = syms[i : i + batch_size]
        params: dict[str, Any] = {
            "symbols": ",".join(chunk), "timeframe": "1Day",
            "start": start.isoformat(), "end": end.isoformat(),
            "feed": feed, "adjustment": "split", "limit": 10000,
        }
        page_token: str | None = None
        while True:
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(
                ALPACA_DATA_BATCH_URL,
                headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key},
                params=params, timeout=timeout,
            )
            if resp.status_code == 429:
                LOGGER.warning("Alpaca batch rate limit (429); sleeping 61s")
                time.sleep(61)
                continue
            if not resp.ok:
                LOGGER.warning("Alpaca batch HTTP %s for chunk %d; skipping chunk", resp.status_code, i // batch_size)
                break
            body = resp.json()
            for sym, bars in (body.get("bars") or {}).items():
                closes, volumes = out.setdefault(sym.upper(), ([], []))
                for bar in bars or []:
                    closes.append(float(bar.get("c", 0) or 0))
                    volumes.append(float(bar.get("v", 0) or 0))
            page_token = body.get("next_page_token")
            if not page_token:
                break
        time.sleep(sleep_seconds)
    return out


def fetch_finnhub_industry(
    symbol: str, finnhub_key: str, *, timeout: int = 10,
) -> str:
    """finnhubIndustry for one symbol via /stock/profile2 (free tier). "" on any error."""
    try:
        resp = requests.get(
            FINNHUB_PROFILE_URL,
            params={"symbol": symbol.upper(), "token": finnhub_key},
            timeout=timeout,
        )
        if resp.status_code == 429:
            time.sleep(2.0)
            return ""
        if not resp.ok:
            return ""
        return str((resp.json() or {}).get("finnhubIndustry") or "")
    except (requests.RequestException, ValueError):
        return ""


# ---------------------------------------------------------------------------
# Orchestrator (fetchers injected — fully testable offline)
# ---------------------------------------------------------------------------

def run_expansion(
    *,
    universe_path: str | Path,
    existing_symbols: Iterable[str],
    quarantined_symbols: Iterable[str],
    assets: list[dict[str, Any]],
    bars_fetcher: Callable[[list[str]], dict[str, tuple[list[float], list[float]]]],
    sector_fetcher: Callable[[str], str] | None,
    thresholds: ScreenThresholds | None = None,
    max_add: int = 1000,
    execute: bool = False,
    sector_sleep_seconds: float = 1.1,   # Finnhub free ~60/min
) -> ExpansionReport:
    """Discover -> dedupe -> screen -> sector -> rank -> cap -> (optionally) write.

    ``sector_fetcher`` None skips classification (sector="" -> uncapped, flagged in
    report). ``execute=False`` is a full dry-run: everything but the YAML write.
    """
    th = thresholds or ScreenThresholds()
    report = ExpansionReport(discovered=len(assets), yaml_path=str(universe_path))

    kept_assets, rejected = filter_assets(assets, existing_symbols, quarantined_symbols)
    report.after_asset_filter = len(kept_assets)
    report.after_dedupe = len(kept_assets)
    report.screened_out.update(rejected)

    names = {str(a["symbol"]).upper(): str(a.get("name") or "") for a in kept_assets}
    bars = bars_fetcher(sorted(names))

    survivors: list[ExpansionCandidate] = []
    for sym in sorted(names):
        closes, volumes = bars.get(sym, ([], []))
        ok, reason, metrics = screen_candidate(closes, volumes, th)
        if not ok:
            report.screened_out[reason] += 1
            continue
        survivors.append(ExpansionCandidate(
            symbol=sym, name=names[sym],
            last_close=metrics["last_close"], avg_volume=metrics["avg_volume"],
            dollar_volume=metrics["dollar_volume"],
        ))
    report.survivors = len(survivors)

    # Rank by liquidity, cap, THEN classify sector (so we only spend Finnhub budget
    # on names we're actually adding).
    survivors.sort(key=lambda c: c.dollar_volume, reverse=True)
    chosen = survivors[: max(0, max_add)]
    classified: list[ExpansionCandidate] = []
    for c in chosen:
        sector = ""
        if sector_fetcher is not None:
            sector = map_industry_to_sector(sector_fetcher(c.symbol))
            time.sleep(sector_sleep_seconds)
        if not sector:
            report.unknown_sector.append(c.symbol)
        classified.append(ExpansionCandidate(
            symbol=c.symbol, name=c.name, sector=sector,
            last_close=c.last_close, avg_volume=c.avg_volume, dollar_volume=c.dollar_volume,
        ))
    report.added = classified
    report.sector_distribution.update(c.sector or "unclassified" for c in classified)

    if execute and classified:
        path = Path(universe_path)
        text = path.read_text(encoding="utf-8")
        blocks = build_yaml_blocks(classified, th)
        text = insert_blocks_into_yaml(text, blocks)
        required = len({str(s).upper() for s in existing_symbols}) + len(classified) + 100
        text = bump_max_universe_size(text, required)
        path.write_text(text, encoding="utf-8")
        report.written = True
    return report
