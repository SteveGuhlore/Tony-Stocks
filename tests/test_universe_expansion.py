"""Tests for the quality-gated universe expansion (stage 4 — screened, not curated).

Pure-core coverage (asset filtering, liquidity screen, sector mapping, YAML emission/
insertion) plus the orchestrator end-to-end with fake fetchers, and a round-trip that
proves the written YAML re-parses through the real universe loader with boolean-ticker
symbols intact. All offline — no keys, no network.
"""
from __future__ import annotations

from collections import Counter

import pytest

from trading_bot.data.universe import load_universe_config
from trading_bot.data.universe_expansion import (
    ExpansionCandidate,
    ScreenThresholds,
    assign_role,
    build_yaml_blocks,
    bump_max_universe_size,
    filter_assets,
    insert_blocks_into_yaml,
    map_industry_to_sector,
    run_expansion,
    screen_candidate,
)


def _asset(symbol="NEWA", name="New Co Common Stock", exchange="NYSE", tradable=True, **over):
    base = {"symbol": symbol, "name": name, "exchange": exchange, "tradable": tradable,
            "status": "active", "class": "us_equity"}
    base.update(over)
    return base


TH = ScreenThresholds()


class TestFilterAssets:
    def test_keeps_clean_common_stock(self):
        kept, rejected = filter_assets([_asset()], existing_symbols=[], quarantined_symbols=[])
        assert [a["symbol"] for a in kept] == ["NEWA"]
        assert sum(rejected.values()) == 0

    def test_drops_existing_and_quarantined(self):
        assets = [_asset("AAPL"), _asset("HCP"), _asset("FRSH")]
        kept, rejected = filter_assets(assets, existing_symbols={"AAPL", "FRSH"}, quarantined_symbols={"HCP"})
        assert kept == []
        assert rejected["already_in_universe"] == 2
        assert rejected["quarantined"] == 1

    def test_drops_otc_and_untradable(self):
        assets = [_asset("OTCX", exchange="OTC"), _asset("HALT", tradable=False)]
        kept, rejected = filter_assets(assets, [], [])
        assert kept == []
        assert rejected["exchange"] == 1
        assert rejected["not_tradable"] == 1

    def test_drops_share_class_and_long_symbols(self):
        # dots/dashes never match the [A-Z]{1,5} shape; 6+ letters out too
        assets = [_asset("BRK.B"), _asset("ABC-W"), _asset("TOOLONG")]
        kept, rejected = filter_assets(assets, [], [])
        assert kept == []
        assert rejected["symbol_shape"] == 3

    def test_drops_warrants_units_preferred_by_name(self):
        assets = [
            _asset("WARR", name="Acme Acquisition Warrant"),
            _asset("UNIT", name="SPAC Holdings Units"),
            _asset("PREF", name="Bank Preferred Series C"),
        ]
        kept, rejected = filter_assets(assets, [], [])
        assert kept == []
        assert rejected["instrument_type"] == 3

    def test_duplicate_listings_counted_once(self):
        kept, rejected = filter_assets([_asset("DUP"), _asset("DUP")], [], [])
        assert len(kept) == 1
        assert rejected["duplicate_listing"] == 1

    def test_malformed_rows_never_raise(self):
        kept, rejected = filter_assets([None, "junk", {}], [], [])  # type: ignore[list-item]
        assert kept == []
        assert rejected["malformed"] == 2  # None + "junk"; {} fails symbol_shape
        assert rejected["symbol_shape"] == 1


class TestScreenCandidate:
    def _bars(self, close=50.0, volume=1_000_000.0, n=30):
        return [close] * n, [volume] * n

    def test_liquid_name_passes(self):
        closes, volumes = self._bars()
        ok, reason, metrics = screen_candidate(closes, volumes, TH)
        assert ok and reason == ""
        assert metrics["dollar_volume"] == pytest.approx(50_000_000.0)

    def test_insufficient_bars_fails_closed(self):
        closes, volumes = self._bars(n=10)  # < min_bars: IEX can't serve it -> quarantine churn
        ok, reason, _ = screen_candidate(closes, volumes, TH)
        assert not ok and reason == "insufficient_bars"

    def test_price_bounds(self):
        ok, reason, _ = screen_candidate(*self._bars(close=4.99), TH)
        assert not ok and reason == "price_below_min"
        ok, reason, _ = screen_candidate(*self._bars(close=500.01), TH)
        assert not ok and reason == "price_above_max"

    def test_volume_floor(self):
        ok, reason, _ = screen_candidate(*self._bars(volume=299_999.0), TH)
        assert not ok and reason == "avg_volume_below_min"

    def test_dollar_volume_floor(self):
        # 6 * 400k = $2.4M < $5M floor (volume floor passes)
        ok, reason, _ = screen_candidate(*self._bars(close=6.0, volume=400_000.0), TH)
        assert not ok and reason == "dollar_volume_below_min"

    def test_exact_boundaries_pass(self):
        ok, _, _ = screen_candidate(*self._bars(close=5.0, volume=1_000_000.0), TH)
        assert ok
        ok, _, _ = screen_candidate(*self._bars(close=500.0, volume=300_000.0), TH)
        assert ok


class TestSectorMapping:
    @pytest.mark.parametrize("industry,expected", [
        ("Banking", "financials"),
        ("Semiconductors", "technology"),
        ("Biotechnology", "healthcare"),
        ("Metals & Mining", "materials"),
        ("Hotels Restaurants & Leisure", "consumer"),
        ("Aerospace & Defense", "industrials"),
        ("Real Estate", "real_estate"),
        ("Utilities", "utilities"),
        ("Media", "communication"),
        ("Energy", "energy"),
    ])
    def test_exact_finnhub_industries(self, industry, expected):
        assert map_industry_to_sector(industry) == expected

    def test_keyword_fallback(self):
        assert map_industry_to_sector("Regional Banks") == "financials"
        assert map_industry_to_sector("Oil & Gas Midstream") == "energy"

    def test_unknown_maps_to_empty(self):
        assert map_industry_to_sector("Frontier Yak Farming") == ""
        assert map_industry_to_sector("") == ""
        assert map_industry_to_sector(None) == ""


class TestYamlEmission:
    def _candidate(self, symbol="ON", sector="technology", dv=30_000_000.0):
        return ExpansionCandidate(symbol=symbol, name="ON Semiconductor", sector=sector,
                                  last_close=50.0, avg_volume=600_000.0, dollar_volume=dv)

    def test_role_by_liquidity_tier(self):
        assert assign_role(25_000_000.0, TH)[0] == "primary_candidate"
        assert assign_role(24_999_999.0, TH)[0] == "speculative_candidate"

    def test_blocks_quote_symbols_and_names(self):
        blocks = build_yaml_blocks([self._candidate()], TH)
        assert '- symbol: "ON"' in blocks          # YAML-1.1 boolean ticker stays a string
        assert 'name: "ON Semiconductor"' in blocks
        assert "sector: technology" in blocks
        assert "universe_role: primary_candidate" in blocks

    def test_unclassified_omits_sector_line(self):
        blocks = build_yaml_blocks([self._candidate(sector="")], TH)
        assert "sector:" not in blocks

    def test_insert_before_filters_anchor(self):
        text = "symbols:\n  - symbol: SPY\n    name: S&P 500 ETF\nfilters:\n  max_universe_size: 1100\n"
        out = insert_blocks_into_yaml(text, build_yaml_blocks([self._candidate()], TH))
        assert out.index('symbol: "ON"') < out.index("filters:")

    def test_missing_anchor_refuses(self):
        with pytest.raises(ValueError):
            insert_blocks_into_yaml("symbols:\n  - symbol: SPY\n", "  - symbol: \"ON\"\n")

    def test_bump_max_universe_size(self):
        text = "filters:\n  max_universe_size: 1100\n"
        assert "max_universe_size: 2200" in bump_max_universe_size(text, 2200)
        # already large enough -> unchanged
        assert bump_max_universe_size(text, 900) == text


class TestRunExpansion:
    def _fixture_yaml(self, tmp_path):
        path = tmp_path / "universe.yaml"
        path.write_text(
            "symbols:\n"
            "  - symbol: SPY\n"
            "    name: S&P 500 ETF\n"
            "    tags: [etf, benchmark]\n"
            "    sector: market\n"
            "    universe_role: benchmark\n"
            "filters:\n"
            "  min_price: 3\n"
            "  max_universe_size: 1100\n",
            encoding="utf-8",
        )
        return path

    def _run(self, tmp_path, *, execute=False, max_add=1000, sector_fetcher=None):
        liquid = ([60.0] * 30, [2_000_000.0] * 30)      # passes everything
        illiquid = ([6.0] * 30, [50_000.0] * 30)        # volume floor fails
        assets = [
            _asset("LIQA", name="Liquid Alpha Inc"),
            _asset("THIN", name="Thin Tape Corp"),
            _asset("SPY"),                               # already in universe
            _asset("WARR", name="Acme Warrant"),
        ]
        return run_expansion(
            universe_path=self._fixture_yaml(tmp_path) if not hasattr(self, "_path") else self._path,
            existing_symbols=["SPY"],
            quarantined_symbols=[],
            assets=assets,
            bars_fetcher=lambda syms: {"LIQA": liquid, "THIN": illiquid},
            sector_fetcher=sector_fetcher,
            max_add=max_add,
            execute=execute,
            sector_sleep_seconds=0.0,
        )

    def test_dry_run_screens_and_reports_without_writing(self, tmp_path):
        report = self._run(tmp_path)
        assert report.discovered == 4
        assert report.screened_out["already_in_universe"] == 1
        assert report.screened_out["instrument_type"] == 1
        assert report.screened_out["avg_volume_below_min"] == 1
        assert [c.symbol for c in report.added] == ["LIQA"]
        assert report.written is False

    def test_execute_writes_parseable_yaml(self, tmp_path):
        path = self._fixture_yaml(tmp_path)
        self._path = path
        report = self._run(tmp_path, execute=True,
                           sector_fetcher=lambda s: "Semiconductors")
        del self._path
        assert report.written is True
        config = load_universe_config(path)            # round-trip through the REAL loader
        assert "LIQA" in config.symbols
        meta = config.metadata_by_symbol["LIQA"]
        assert meta.sector == "technology"             # Semiconductors -> technology
        assert meta.universe_role == "primary_candidate"   # $120M dollar volume

    def test_unclassified_sector_flagged(self, tmp_path):
        report = self._run(tmp_path, sector_fetcher=lambda s: "Frontier Yak Farming")
        assert report.unknown_sector == ["LIQA"]
        assert report.sector_distribution["unclassified"] == 1

    def test_max_add_caps_by_dollar_volume_rank(self, tmp_path):
        big = ([60.0] * 30, [5_000_000.0] * 30)
        small = ([60.0] * 30, [200_000.0] * 30)  # passes floors: 12M dollar vol, 200k vol < 300k -> fails!
        mid = ([60.0] * 30, [1_000_000.0] * 30)
        report = run_expansion(
            universe_path=self._fixture_yaml(tmp_path),
            existing_symbols=["SPY"], quarantined_symbols=[],
            assets=[_asset("BIGV"), _asset("MIDV"), _asset("SMLV")],
            bars_fetcher=lambda syms: {"BIGV": big, "MIDV": mid, "SMLV": small},
            sector_fetcher=None, max_add=1, execute=False, sector_sleep_seconds=0.0,
        )
        assert [c.symbol for c in report.added] == ["BIGV"]  # highest dollar volume wins the cap
        assert report.survivors == 2                          # SMLV failed the volume floor
