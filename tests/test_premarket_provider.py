"""Tests for premarket_provider seam (Task 2 — Off-Hours Research Engine).

TDD: tests were written before the implementation.  The module is a pure seam:
NullPreMarketProvider always returns None; future real providers slot in via the
PreMarketProvider Protocol without touching call sites.
"""
from __future__ import annotations

import dataclasses
import pytest

from trading_bot.data.premarket_provider import (
    NullPreMarketProvider,
    PreMarketProvider,
    PreMarketQuote,
)


# ---------------------------------------------------------------------------
# PreMarketQuote dataclass
# ---------------------------------------------------------------------------

class TestPreMarketQuote:
    """PreMarketQuote is a frozen dataclass — fields stored, mutation raises."""

    def test_stores_fields(self) -> None:
        q = PreMarketQuote(
            symbol="NVDA",
            last=130.0,
            prev_close=125.0,
            gap_pct=4.0,
            as_of="2026-06-06T08:00:00-04:00",
        )
        assert q.symbol == "NVDA"
        assert q.last == 130.0
        assert q.prev_close == 125.0
        assert q.gap_pct == 4.0
        assert q.as_of == "2026-06-06T08:00:00-04:00"

    def test_frozen_raises_on_assign(self) -> None:
        q = PreMarketQuote(
            symbol="NVDA",
            last=130.0,
            prev_close=125.0,
            gap_pct=4.0,
            as_of="2026-06-06T08:00:00-04:00",
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            q.symbol = "AAPL"  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(PreMarketQuote)


# ---------------------------------------------------------------------------
# NullPreMarketProvider
# ---------------------------------------------------------------------------

class TestNullPreMarketProvider:
    """NullPreMarketProvider satisfies the Protocol and always returns None."""

    def test_get_premarket_quote_returns_none(self) -> None:
        provider = NullPreMarketProvider()
        assert provider.get_premarket_quote("NVDA") is None

    def test_arbitrary_symbol_returns_none(self) -> None:
        provider = NullPreMarketProvider()
        assert provider.get_premarket_quote("AAPL") is None
        assert provider.get_premarket_quote("") is None

    def test_satisfies_protocol(self) -> None:
        """Runtime check: NullPreMarketProvider is structurally compatible."""
        provider: PreMarketProvider = NullPreMarketProvider()
        result = provider.get_premarket_quote("TSLA")
        assert result is None


# ---------------------------------------------------------------------------
# Fake provider — tests that gap_pct is computed correctly
# ---------------------------------------------------------------------------

class _FakePreMarketProvider:
    """Minimal fake that builds a PreMarketQuote with a real gap_pct."""

    def get_premarket_quote(self, symbol: str) -> PreMarketQuote | None:
        last = 130.0
        prev_close = 125.0
        gap_pct = (last - prev_close) / prev_close * 100
        return PreMarketQuote(
            symbol=symbol.upper(),
            last=last,
            prev_close=prev_close,
            gap_pct=gap_pct,
            as_of="2026-06-06T08:00:00-04:00",
        )


class TestFakePreMarketProvider:
    """Fake implementing the Protocol produces a correctly-computed gap_pct."""

    def test_gap_pct_positive(self) -> None:
        provider: PreMarketProvider = _FakePreMarketProvider()
        quote = provider.get_premarket_quote("NVDA")
        assert quote is not None
        assert quote.symbol == "NVDA"
        assert quote.last == 130.0
        assert quote.prev_close == 125.0
        # (130 - 125) / 125 * 100 == 4.0
        assert abs(quote.gap_pct - 4.0) < 1e-9

    def test_gap_pct_negative(self) -> None:
        """Negative gap (pre-market below prev close) computes correctly."""

        class _DownFake:
            def get_premarket_quote(self, symbol: str) -> PreMarketQuote | None:
                last = 120.0
                prev_close = 125.0
                gap_pct = (last - prev_close) / prev_close * 100
                return PreMarketQuote(
                    symbol=symbol.upper(),
                    last=last,
                    prev_close=prev_close,
                    gap_pct=gap_pct,
                    as_of="2026-06-06T08:00:00-04:00",
                )

        provider: PreMarketProvider = _DownFake()
        quote = provider.get_premarket_quote("NVDA")
        assert quote is not None
        # (120 - 125) / 125 * 100 == -4.0
        assert abs(quote.gap_pct - (-4.0)) < 1e-9

    def test_as_of_stored_verbatim(self) -> None:
        provider: PreMarketProvider = _FakePreMarketProvider()
        quote = provider.get_premarket_quote("NVDA")
        assert quote is not None
        assert quote.as_of == "2026-06-06T08:00:00-04:00"
