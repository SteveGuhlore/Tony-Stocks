from pathlib import Path

from trading_bot.data.symbol_quarantine import apply_symbol_quarantine
from trading_bot.data.universe import (
    load_symbols_from_csv,
    load_universe,
    load_universe_metadata,
    load_universe_tags,
    normalize_symbol,
)
from trading_bot.data.universe_rotation import WatchUniverseRotator
from trading_bot.settings import load_scanner_settings

# Path to the real production universe config
_REAL_CONFIG = Path(__file__).parent.parent / "config" / "universe_swing_research_config.yaml"
_DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "default_config.yaml"

VALID_ROLES = {"benchmark", "reference", "primary_candidate", "speculative_candidate", "excluded_by_default"}


def test_normalize_symbol():
    assert normalize_symbol(" aapl ") == "AAPL"


def test_load_universe_dedupes_and_limits(tmp_path: Path):
    config = tmp_path / "universe.yaml"
    config.write_text(
        """
symbols:
  - AAPL
  - aapl
  - MSFT
csv_path:
filters:
  max_universe_size: 2
""",
        encoding="utf-8",
    )
    assert load_universe(config) == ["AAPL", "MSFT"]


def test_load_universe_tags(tmp_path: Path):
    config = tmp_path / "universe.yaml"
    config.write_text(
        """
symbols:
  - symbol: SPY
    tags: [etf, benchmark]
  - symbol: AAPL
    tags: [mega_cap, tech]
csv_path:
filters:
  max_universe_size: 10
""",
        encoding="utf-8",
    )
    tags = load_universe_tags(config)
    assert tags["SPY"] == ("etf", "benchmark")
    assert tags["AAPL"] == ("mega_cap", "tech")


def test_load_universe_metadata(tmp_path: Path):
    config = tmp_path / "universe.yaml"
    config.write_text(
        """
symbols:
  - symbol: PLTR
    name: Palantir
    tags: [mid_cap, software, breakout_candidate]
    sector: technology
    industry: software
    universe_role: primary_candidate
    demo_profile: clean_breakout
    notes: Static demo metadata.
csv_path:
filters:
  max_universe_size: 10
""",
        encoding="utf-8",
    )
    metadata = load_universe_metadata(config)["PLTR"]
    assert metadata.name == "Palantir"
    assert metadata.universe_role == "primary_candidate"
    assert metadata.demo_profile == "clean_breakout"
    assert metadata.sector == "technology"


def test_load_symbols_from_csv(tmp_path: Path):
    csv = tmp_path / "symbols.csv"
    csv.write_text("symbol\nspy\nqqq\n", encoding="utf-8")
    assert load_symbols_from_csv(csv) == ["SPY", "QQQ"]


class TestProductionUniverseSize:
    def test_loads_at_least_300_symbols(self):
        syms = load_universe(_REAL_CONFIG)
        assert len(syms) >= 300, f"Expected at least 300 symbols, got {len(syms)}"

    def test_no_duplicates(self):
        syms = load_universe(_REAL_CONFIG)
        assert len(syms) == len(set(syms)), "Duplicate symbols found after load"

    def test_all_symbols_uppercase(self):
        syms = load_universe(_REAL_CONFIG)
        for s in syms:
            assert s == s.upper(), f"Symbol not uppercase: {s!r}"


class TestProductionUniverseBenchmarks:
    def test_core_benchmarks_present(self):
        syms = load_universe(_REAL_CONFIG)
        for expected in ("SPY", "QQQ", "IWM"):
            assert expected in syms, f"Core benchmark {expected} missing from universe"

    def test_benchmark_role_assigned(self):
        meta = load_universe_metadata(_REAL_CONFIG)
        for sym in ("SPY", "QQQ", "IWM"):
            assert sym in meta, f"{sym} has no metadata"
            assert meta[sym].universe_role == "benchmark", f"{sym} should have role=benchmark"

    def test_at_least_three_benchmarks(self):
        meta = load_universe_metadata(_REAL_CONFIG)
        benchmarks = [s for s, m in meta.items() if m.universe_role == "benchmark"]
        assert len(benchmarks) >= 3, f"Expected at least 3 benchmarks, got {len(benchmarks)}"


class TestProductionUniverseRoles:
    def test_all_roles_are_valid(self):
        meta = load_universe_metadata(_REAL_CONFIG)
        for sym, m in meta.items():
            assert m.universe_role in VALID_ROLES, f"{sym} has invalid role {m.universe_role!r}"

    def test_has_primary_candidates(self):
        meta = load_universe_metadata(_REAL_CONFIG)
        primaries = [s for s, m in meta.items() if m.universe_role == "primary_candidate"]
        assert len(primaries) >= 50, f"Expected at least 50 primary_candidates, got {len(primaries)}"

    def test_has_speculative_candidates(self):
        meta = load_universe_metadata(_REAL_CONFIG)
        speculatives = [s for s, m in meta.items() if m.universe_role == "speculative_candidate"]
        assert len(speculatives) >= 10, f"Expected at least 10 speculative_candidates, got {len(speculatives)}"


class TestProductionUniverseTags:
    def test_watchlist_core_symbols_present(self):
        tags = load_universe_tags(_REAL_CONFIG)
        core = [s for s, t in tags.items() if "watchlist_core" in t]
        assert len(core) >= 3, f"Expected at least 3 watchlist_core symbols, got {len(core)}"

    def test_spy_qqq_iwm_are_watchlist_core(self):
        tags = load_universe_tags(_REAL_CONFIG)
        for sym in ("SPY", "QQQ", "IWM"):
            assert sym in tags, f"{sym} has no tags"
            assert "watchlist_core" in tags[sym], f"{sym} should have watchlist_core tag"

    def test_discovery_pool_exists(self):
        tags = load_universe_tags(_REAL_CONFIG)
        discovery = [s for s, t in tags.items() if "discovery" in t]
        assert len(discovery) >= 20, f"Expected at least 20 discovery-tagged symbols, got {len(discovery)}"

    def test_no_symbol_in_both_watchlist_core_and_excluded(self):
        meta = load_universe_metadata(_REAL_CONFIG)
        tags = load_universe_tags(_REAL_CONFIG)
        for sym, m in meta.items():
            if m.universe_role == "excluded_by_default" and sym in tags:
                assert "watchlist_core" not in tags[sym], (
                    f"{sym} is excluded_by_default but has watchlist_core tag"
                )


class TestProductionUniverseRotationBudget:
    def test_watchlist_core_fits_within_default_core_max(self):
        tags = load_universe_tags(_REAL_CONFIG)
        core = [s for s, t in tags.items() if "watchlist_core" in t]
        assert len(core) <= 50, f"watchlist_core count {len(core)} exceeds core_max_symbols=50"

    def test_total_non_excluded_fits_within_max_universe_size(self):
        # Read the cap from config so a staged universe expansion only needs the
        # filters.max_universe_size bump — not a hardcoded edit here. The invariant
        # that matters: active symbols must fit so load_universe() never silently
        # truncates curated names (universe.py returns result[:max_universe_size]).
        import yaml
        with open(_REAL_CONFIG, encoding="utf-8") as fh:
            cap = yaml.safe_load(fh)["filters"]["max_universe_size"]
        meta = load_universe_metadata(_REAL_CONFIG)
        active = [s for s, m in meta.items() if m.universe_role != "excluded_by_default"]
        assert len(active) <= cap, f"Active symbol count {len(active)} exceeds max_universe_size={cap}"

    def test_default_config_quarantine_still_excludes_known_symbols_from_real_flow(self):
        settings = load_scanner_settings(_DEFAULT_CONFIG)
        symbols = load_universe(settings.universe_config_path)
        kept, excluded = apply_symbol_quarantine(symbols, settings, True)
        excluded_symbols = {entry.symbol for entry in excluded}
        assert {"HCP", "SAMSF", "SMAR", "SQ"}.issubset(excluded_symbols)
        assert {"HCP", "SAMSF", "SMAR", "SQ"}.isdisjoint(set(kept))

    def test_rotation_still_caps_cycle_and_preserves_priority_sets(self):
        settings = load_scanner_settings(_DEFAULT_CONFIG)
        universe = load_universe(settings.universe_config_path)
        kept, _ = apply_symbol_quarantine(universe, settings, True)
        rotation_cfg = settings.watch_universe_rotation or {}
        rotator = WatchUniverseRotator(kept, rotation_cfg)
        rotator.update_previous_candidates(["ANET", "LLY", "ETN"])

        result = rotator.get_cycle_symbols(open_snapshot_symbols=["PLTR", "CRWD"])

        assert result.total == len(result.symbols)
        assert result.total <= int(rotation_cfg.get("max_symbols_per_cycle", 175))
        assert result.symbols[:3] == ["SPY", "QQQ", "IWM"]
        assert {"PLTR", "CRWD", "ANET", "LLY", "ETN"}.issubset(set(result.symbols))
        assert len(result.symbols) == len(set(result.symbols))
