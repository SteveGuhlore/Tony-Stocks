"""Pre-market data provider seam for the Off-Hours Research Engine.

Defines the ``PreMarketProvider`` Protocol and the ``PreMarketQuote`` value
object so that call sites are decoupled from any specific data source.
``NullPreMarketProvider`` is the live default: it always returns ``None``,
keeping the off-hours engine inert until a real provider is wired in.

Future real providers that implement the Protocol (drop-in replacements,
no call-site changes needed):

    AlpacaSipPreMarketProvider  — Alpaca SIP pre-market snapshot endpoint
                                   (requires ALPACA_API_KEY / ALPACA_SECRET_KEY)
    PolygonPreMarketProvider    — Polygon.io /v2/last/trade/{ticker} pre-market
                                   (requires POLYGON_API_KEY)

Both are sketched as placeholder classes below; uncomment and flesh out when
the upstream API contracts are confirmed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PreMarketQuote:
    """Immutable snapshot of a single symbol's pre-market price.

    ``gap_pct`` must be supplied by the caller/provider as
    ``(last - prev_close) / prev_close * 100``; this dataclass is a pure
    value object and performs no arithmetic.

    ``as_of`` is a plain ISO-8601 string with UTC offset, e.g.
    ``"2026-06-06T08:00:00-04:00"``.  It is not parsed or validated here
    so that providers can relay the string exactly as returned by the API.
    """

    symbol: str
    last: float
    prev_close: float
    gap_pct: float
    as_of: str  # ISO-8601 with offset, e.g. "2026-06-06T08:00:00-04:00"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class PreMarketProvider(Protocol):
    """Structural interface for pre-market quote providers.

    Any object that exposes ``get_premarket_quote`` with the matching
    signature satisfies this Protocol — no inheritance required.
    """

    def get_premarket_quote(self, symbol: str) -> PreMarketQuote | None:
        """Return a pre-market quote for *symbol*, or ``None`` if unavailable."""
        ...


# ---------------------------------------------------------------------------
# Null implementation (default)
# ---------------------------------------------------------------------------

class NullPreMarketProvider:
    """No-op provider; always returns ``None``.

    Used until a real pre-market data source is configured.  Satisfies the
    ``PreMarketProvider`` Protocol structurally, so it slots into any typed
    call site without change.
    """

    def get_premarket_quote(self, symbol: str) -> PreMarketQuote | None:  # noqa: ARG002
        return None


# ---------------------------------------------------------------------------
# Placeholder stubs (future real providers — NOT yet implemented)
# ---------------------------------------------------------------------------

# class AlpacaSipPreMarketProvider:
#     """Pre-market snapshots via Alpaca SIP data (IEX or SIP feed).
#
#     Requires env vars: ALPACA_API_KEY, ALPACA_SECRET_KEY.
#     Endpoint: GET https://data.alpaca.markets/v2/stocks/{symbol}/snapshots
#     with feed=sip and the market session set to pre_market.
#     """
#
#     def __init__(self, api_key: str = "", secret_key: str = "") -> None:
#         raise NotImplementedError("AlpacaSipPreMarketProvider is not yet implemented")
#
#     def get_premarket_quote(self, symbol: str) -> PreMarketQuote | None:
#         raise NotImplementedError


# class PolygonPreMarketProvider:
#     """Pre-market quotes via Polygon.io.
#
#     Requires env var: POLYGON_API_KEY.
#     Endpoint: GET https://api.polygon.io/v2/aggs/ticker/{ticker}/prev
#     or the /v2/snapshot/locale/us/markets/stocks/tickers/{ticker} endpoint
#     for intraday pre-market data.
#     """
#
#     def __init__(self, api_key: str = "") -> None:
#         raise NotImplementedError("PolygonPreMarketProvider is not yet implemented")
#
#     def get_premarket_quote(self, symbol: str) -> PreMarketQuote | None:
#         raise NotImplementedError
