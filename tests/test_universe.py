from pathlib import Path

from trading_bot.data.universe import (
    load_symbols_from_csv,
    load_universe,
    load_universe_metadata,
    load_universe_tags,
    normalize_symbol,
)


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
