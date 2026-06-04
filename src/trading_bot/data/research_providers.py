"""Research-enrichment provider adapters for the Research Funnel (FMP / Finnhub /
Twelve Data) plus ``gather_funnel_signals`` that assembles ``SymbolSignals``.

These feeds are **advisory enrichment only** — never the scoring price feed (that
stays Alpaca/Twelve in market_data.py). Every call is defensive: any HTTP/parse
failure returns None/empty and is logged, never raised, so a flaky free-tier API
degrades the funnel instead of breaking the watch loop.

HTTP is injected via a ``get_json`` callable so tests run with zero network calls.
Keys come from the environment (FMP_API_KEY / FINNHUB_API_KEY / TWELVE_DATA_API_KEY);
a provider with no key is inert (its methods return None/empty).
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Callable

import requests

from trading_bot.data.research_funnel import SymbolSignals

LOGGER = logging.getLogger(__name__)

GetJson = Callable[[str, dict[str, Any]], Any]


def _default_get_json(url: str, params: dict[str, Any], timeout: int = 12) -> Any:
    """Defensive GET -> parsed JSON, or None on any failure."""
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if not resp.ok:
            LOGGER.warning("research provider HTTP %s for %s", resp.status_code, url)
            return None
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        LOGGER.warning("research provider request failed for %s: %s", url, exc)
        return None


def _safe_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "")).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


class FmpProvider:
    """Financial Modeling Prep: wide screener, earnings calendar, revenue growth.

    Uses the current ``/stable`` API (the legacy ``/api/v3`` paths 403 for newer keys).
    Verified working on free tier: earnings-calendar, quote, income-statement-growth.
    company-screener is paid-tier (402) — degrades to [] so the funnel falls back to
    its curated universe rather than the screener-sourced one.
    """

    BASE = "https://financialmodelingprep.com/stable"

    def __init__(self, api_key: str = "", get_json: GetJson | None = None) -> None:
        self.api_key = api_key
        self._get = get_json or _default_get_json

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def screen(
        self,
        *,
        price_more_than: float = 5.0,
        volume_more_than: int = 500_000,
        market_cap_more_than: int = 1_000_000_000,
        exchanges: str = "NASDAQ,NYSE,AMEX",
        limit: int = 1500,
    ) -> list[str]:
        """Stage-1 wide universe pull. Returns uppercase tickers (empty on failure)."""
        if not self.available:
            return []
        body = self._get(
            f"{self.BASE}/company-screener",
            {
                "priceMoreThan": price_more_than,
                "volumeMoreThan": volume_more_than,
                "marketCapMoreThan": market_cap_more_than,
                "exchange": exchanges,
                "isActivelyTrading": "true",
                "limit": limit,
                "apikey": self.api_key,
            },
        )
        if not isinstance(body, list):
            return []
        out: list[str] = []
        for row in body:
            if isinstance(row, dict) and row.get("symbol"):
                out.append(str(row["symbol"]).upper())
        return out

    def earnings_calendar(self, from_date: date, to_date: date) -> dict[str, date]:
        """Map symbol -> next earnings date within the window (one bulk call)."""
        if not self.available:
            return {}
        body = self._get(
            f"{self.BASE}/earnings-calendar",
            {"from": from_date.isoformat(), "to": to_date.isoformat(), "apikey": self.api_key},
        )
        if not isinstance(body, list):
            return {}
        out: dict[str, date] = {}
        for row in body:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol", "")).upper()
            d = _parse_date(row.get("date"))
            if sym and d and (sym not in out or d < out[sym]):
                out[sym] = d
        return out

    def revenue_growth(self, symbol: str) -> float | None:
        """Latest YoY revenue growth fraction for one symbol (per-symbol call)."""
        if not self.available:
            return None
        body = self._get(
            f"{self.BASE}/income-statement-growth",
            {"symbol": symbol.upper(), "limit": 1, "apikey": self.api_key},
        )
        if isinstance(body, list) and body and isinstance(body[0], dict):
            return _safe_float(body[0].get("growthRevenue"))
        return None


class FinnhubProvider:
    """Finnhub: news sentiment + analyst recommendation trend."""

    BASE = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str = "", get_json: GetJson | None = None) -> None:
        self.api_key = api_key
        self._get = get_json or _default_get_json

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def news_sentiment(self, symbol: str) -> float | None:
        """Normalized -1..1 sentiment from companyNewsScore / bullish percent."""
        if not self.available:
            return None
        body = self._get(f"{self.BASE}/news-sentiment", {"symbol": symbol.upper(), "token": self.api_key})
        if not isinstance(body, dict):
            return None
        score = _safe_float(body.get("companyNewsScore"))
        if score is not None:
            return max(-1.0, min(1.0, (score - 0.5) * 2))  # 0..1 -> -1..1
        sent = body.get("sentiment")
        if isinstance(sent, dict):
            bull = _safe_float(sent.get("bullishPercent"))
            if bull is not None:
                return max(-1.0, min(1.0, (bull - 0.5) * 2))
        return None

    def recommendation(self, symbol: str) -> float | None:
        """Latest analyst recommendation as -1..1 (buy bias)."""
        if not self.available:
            return None
        body = self._get(f"{self.BASE}/stock/recommendation", {"symbol": symbol.upper(), "token": self.api_key})
        if not isinstance(body, list) or not body or not isinstance(body[0], dict):
            return None
        row = body[0]  # most recent period first
        sb = _safe_float(row.get("strongBuy")) or 0.0
        b = _safe_float(row.get("buy")) or 0.0
        h = _safe_float(row.get("hold")) or 0.0
        s = _safe_float(row.get("sell")) or 0.0
        ss = _safe_float(row.get("strongSell")) or 0.0
        total = sb + b + h + s + ss
        if total <= 0:
            return None
        return (sb * 1.0 + b * 0.5 - s * 0.5 - ss * 1.0) / total


class TwelveDataProvider:
    """Twelve Data: breadth / fallback quote source (price + volume)."""

    BASE = "https://api.twelvedata.com"

    def __init__(self, api_key: str = "", get_json: GetJson | None = None) -> None:
        self.api_key = api_key
        self._get = get_json or _default_get_json

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def quote(self, symbol: str) -> dict[str, float] | None:
        """Return {'price', 'volume'} or None."""
        if not self.available:
            return None
        body = self._get(f"{self.BASE}/quote", {"symbol": symbol.upper(), "apikey": self.api_key})
        if not isinstance(body, dict) or body.get("status") == "error":
            return None
        price = _safe_float(body.get("close"))
        volume = _safe_float(body.get("volume"))
        if price is None and volume is None:
            return None
        return {"price": price or 0.0, "volume": volume or 0.0}


def build_providers_from_env(get_json: GetJson | None = None) -> dict[str, Any]:
    """Construct providers from environment keys. Each is inert without its key."""
    return {
        "fmp": FmpProvider(os.getenv("FMP_API_KEY", ""), get_json),
        "finnhub": FinnhubProvider(os.getenv("FINNHUB_API_KEY", ""), get_json),
        "twelve": TwelveDataProvider(os.getenv("TWELVE_DATA_API_KEY", ""), get_json),
    }


def gather_funnel_signals(
    symbols: list[str],
    *,
    today: date,
    base_metrics: dict[str, dict[str, float]] | None = None,
    fmp: FmpProvider | None = None,
    finnhub: FinnhubProvider | None = None,
    enrich_limit: int = 150,
    earnings_blackout_days: int = 10,
) -> dict[str, SymbolSignals]:
    """Assemble per-symbol SymbolSignals.

    ``base_metrics`` (symbol -> {price, dollar_volume, relative_strength}) comes from
    the caller's already-cached Alpaca scan data — that is the consistent feed and
    needs no API call. Provider enrichment (earnings/sentiment/recommendation) is
    layered on top: one bulk FMP earnings call for the whole window, plus per-symbol
    Finnhub calls capped at ``enrich_limit`` to respect free-tier rate limits.
    Symbols beyond the cap still get base metrics (price/volume/RS) — just no catalyst.
    """
    base_metrics = base_metrics or {}
    upper = [s.upper() for s in symbols]

    earnings: dict[str, date] = {}
    if fmp is not None and fmp.available and earnings_blackout_days > 0:
        earnings = fmp.earnings_calendar(today, today + timedelta(days=earnings_blackout_days + 1))

    signals: dict[str, SymbolSignals] = {}
    enriched = 0
    for sym in upper:
        base = base_metrics.get(sym, {})
        sentiment = recommendation = None
        if finnhub is not None and finnhub.available and enriched < enrich_limit:
            sentiment = finnhub.news_sentiment(sym)
            recommendation = finnhub.recommendation(sym)
            enriched += 1
        signals[sym] = SymbolSignals(
            symbol=sym,
            price=_safe_float(base.get("price")),
            dollar_volume=_safe_float(base.get("dollar_volume")),
            relative_strength=_safe_float(base.get("relative_strength")),
            news_sentiment=sentiment,
            recommendation_score=recommendation,
            earnings_date=earnings.get(sym),
        )
    return signals
