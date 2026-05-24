# Obsidian Memory Layer (B-Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `src/trading_bot/vault/` module that writes Obsidian-compatible markdown vault notes and a bridge export to the AI Operations Command Center after every EOD run.

**Architecture:** `writer.py` builds daily notes + ticker pages inside `vault/`; `bridge.py` writes curated analyst briefs to the Command Center bridge folder. Both are called at the end of `run_after_market_review()` in `cli.py`. A one-time `scripts/seed_vault.py` backfills from existing SQLite data.

**Tech Stack:** Python stdlib only (pathlib, datetime) — no new dependencies. pytest for tests. YAML for config.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/trading_bot/vault/__init__.py` | Public API exports |
| Create | `src/trading_bot/vault/sector_map.py` | Static `SECTOR_MAP` dict: ticker → `{sector, etf}` |
| Create | `src/trading_bot/vault/writer.py` | `write_daily_note()`, `upsert_ticker_page()`, `update_vault_index()` |
| Create | `src/trading_bot/vault/bridge.py` | `write_bridge_export()` — full analyst brief markdown |
| Create | `tests/test_vault_writer.py` | Tests for writer.py |
| Create | `tests/test_vault_bridge.py` | Tests for bridge.py |
| Create | `scripts/seed_vault.py` | One-time SQLite → vault backfill |
| Modify | `src/trading_bot/settings.py:55` | Add `vault: dict[str, Any] \| None = None` after `pre_screener` |
| Modify | `config/default_config.yaml` | Append `vault:` config block at end |
| Modify | `src/trading_bot/cli.py` | Wire vault/bridge into `run_after_market_review()` + `export-to-vault` command |

---

### Task 1: sector_map.py — static ticker-to-sector lookup

**Files:**
- Create: `src/trading_bot/vault/sector_map.py`

No tests needed — pure static data, no logic.

- [ ] **Step 1: Create sector_map.py**

```python
# src/trading_bot/vault/sector_map.py
from __future__ import annotations

# Maps each universe ticker to its sector name and parent sector ETF.
# Extend this dict as the universe grows.
SECTOR_MAP: dict[str, dict[str, str]] = {
    # Technology — XLK
    "AAPL": {"sector": "Technology", "etf": "XLK"},
    "MSFT": {"sector": "Technology", "etf": "XLK"},
    "NVDA": {"sector": "Technology", "etf": "XLK"},
    "AMD": {"sector": "Technology", "etf": "XLK"},
    "GOOGL": {"sector": "Technology", "etf": "XLK"},
    "GOOG": {"sector": "Technology", "etf": "XLK"},
    "META": {"sector": "Technology", "etf": "XLK"},
    "ORCL": {"sector": "Technology", "etf": "XLK"},
    "CRM": {"sector": "Technology", "etf": "XLK"},
    "ADBE": {"sector": "Technology", "etf": "XLK"},
    "INTC": {"sector": "Technology", "etf": "XLK"},
    "QCOM": {"sector": "Technology", "etf": "XLK"},
    "TXN": {"sector": "Technology", "etf": "XLK"},
    "ANET": {"sector": "Technology", "etf": "XLK"},
    "GTLB": {"sector": "Technology", "etf": "XLK"},
    "ZETA": {"sector": "Technology", "etf": "XLK"},
    "SNOW": {"sector": "Technology", "etf": "XLK"},
    "DDOG": {"sector": "Technology", "etf": "XLK"},
    "MDB": {"sector": "Technology", "etf": "XLK"},
    "NET": {"sector": "Technology", "etf": "XLK"},
    "CRWD": {"sector": "Technology", "etf": "XLK"},
    "PANW": {"sector": "Technology", "etf": "XLK"},
    "FTNT": {"sector": "Technology", "etf": "XLK"},
    "CYBR": {"sector": "Technology", "etf": "XLK"},
    "ZS": {"sector": "Technology", "etf": "XLK"},
    "S": {"sector": "Technology", "etf": "XLK"},
    "OKTA": {"sector": "Technology", "etf": "XLK"},
    "NOW": {"sector": "Technology", "etf": "XLK"},
    "WDAY": {"sector": "Technology", "etf": "XLK"},
    "INTU": {"sector": "Technology", "etf": "XLK"},
    "SHOP": {"sector": "Technology", "etf": "XLK"},
    "TWLO": {"sector": "Technology", "etf": "XLK"},
    "ZI": {"sector": "Technology", "etf": "XLK"},
    "BILL": {"sector": "Technology", "etf": "XLK"},
    "HUBS": {"sector": "Technology", "etf": "XLK"},
    "SMAR": {"sector": "Technology", "etf": "XLK"},
    # Communication Services — XLC
    "NFLX": {"sector": "Communication Services", "etf": "XLC"},
    "DIS": {"sector": "Communication Services", "etf": "XLC"},
    "T": {"sector": "Communication Services", "etf": "XLC"},
    "VZ": {"sector": "Communication Services", "etf": "XLC"},
    "TMUS": {"sector": "Communication Services", "etf": "XLC"},
    "LYFT": {"sector": "Communication Services", "etf": "XLC"},
    "UBER": {"sector": "Communication Services", "etf": "XLC"},
    "SNAP": {"sector": "Communication Services", "etf": "XLC"},
    "PINS": {"sector": "Communication Services", "etf": "XLC"},
    "RBLX": {"sector": "Communication Services", "etf": "XLC"},
    "EBAY": {"sector": "Communication Services", "etf": "XLC"},
    "ETSY": {"sector": "Communication Services", "etf": "XLC"},
    # Consumer Discretionary — XLY
    "AMZN": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "TSLA": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "HD": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "LOW": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "NKE": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "MCD": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "SBUX": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "TGT": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "BKNG": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "MAR": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "HLT": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "RCL": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "CCL": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "ABNB": {"sector": "Consumer Discretionary", "etf": "XLY"},
    # Consumer Staples — XLP
    "PG": {"sector": "Consumer Staples", "etf": "XLP"},
    "KO": {"sector": "Consumer Staples", "etf": "XLP"},
    "PEP": {"sector": "Consumer Staples", "etf": "XLP"},
    "COST": {"sector": "Consumer Staples", "etf": "XLP"},
    "WMT": {"sector": "Consumer Staples", "etf": "XLP"},
    "CVS": {"sector": "Consumer Staples", "etf": "XLP"},
    "WBA": {"sector": "Consumer Staples", "etf": "XLP"},
    "MO": {"sector": "Consumer Staples", "etf": "XLP"},
    "PM": {"sector": "Consumer Staples", "etf": "XLP"},
    # Healthcare — XLV
    "JNJ": {"sector": "Healthcare", "etf": "XLV"},
    "UNH": {"sector": "Healthcare", "etf": "XLV"},
    "PFE": {"sector": "Healthcare", "etf": "XLV"},
    "MRK": {"sector": "Healthcare", "etf": "XLV"},
    "ABBV": {"sector": "Healthcare", "etf": "XLV"},
    "LLY": {"sector": "Healthcare", "etf": "XLV"},
    "BMY": {"sector": "Healthcare", "etf": "XLV"},
    "AMGN": {"sector": "Healthcare", "etf": "XLV"},
    "GILD": {"sector": "Healthcare", "etf": "XLV"},
    "REGN": {"sector": "Healthcare", "etf": "XLV"},
    "VRTX": {"sector": "Healthcare", "etf": "XLV"},
    "BIIB": {"sector": "Healthcare", "etf": "XLV"},
    "MRNA": {"sector": "Healthcare", "etf": "XLV"},
    "ISRG": {"sector": "Healthcare", "etf": "XLV"},
    "DHR": {"sector": "Healthcare", "etf": "XLV"},
    "ABT": {"sector": "Healthcare", "etf": "XLV"},
    "TMO": {"sector": "Healthcare", "etf": "XLV"},
    "MDT": {"sector": "Healthcare", "etf": "XLV"},
    "SYK": {"sector": "Healthcare", "etf": "XLV"},
    "ZBH": {"sector": "Healthcare", "etf": "XLV"},
    # Financials — XLF
    "JPM": {"sector": "Financials", "etf": "XLF"},
    "BAC": {"sector": "Financials", "etf": "XLF"},
    "WFC": {"sector": "Financials", "etf": "XLF"},
    "GS": {"sector": "Financials", "etf": "XLF"},
    "MS": {"sector": "Financials", "etf": "XLF"},
    "C": {"sector": "Financials", "etf": "XLF"},
    "AXP": {"sector": "Financials", "etf": "XLF"},
    "V": {"sector": "Financials", "etf": "XLF"},
    "MA": {"sector": "Financials", "etf": "XLF"},
    "PYPL": {"sector": "Financials", "etf": "XLF"},
    "SQ": {"sector": "Financials", "etf": "XLF"},
    "AFRM": {"sector": "Financials", "etf": "XLF"},
    "SOFI": {"sector": "Financials", "etf": "XLF"},
    "HOOD": {"sector": "Financials", "etf": "XLF"},
    "COF": {"sector": "Financials", "etf": "XLF"},
    "USB": {"sector": "Financials", "etf": "XLF"},
    "PNC": {"sector": "Financials", "etf": "XLF"},
    "BLK": {"sector": "Financials", "etf": "XLF"},
    "SCHW": {"sector": "Financials", "etf": "XLF"},
    "ICE": {"sector": "Financials", "etf": "XLF"},
    "CME": {"sector": "Financials", "etf": "XLF"},
    # Energy — XLE
    "XOM": {"sector": "Energy", "etf": "XLE"},
    "CVX": {"sector": "Energy", "etf": "XLE"},
    "COP": {"sector": "Energy", "etf": "XLE"},
    "EOG": {"sector": "Energy", "etf": "XLE"},
    "SLB": {"sector": "Energy", "etf": "XLE"},
    "OXY": {"sector": "Energy", "etf": "XLE"},
    "MPC": {"sector": "Energy", "etf": "XLE"},
    "VLO": {"sector": "Energy", "etf": "XLE"},
    "PSX": {"sector": "Energy", "etf": "XLE"},
    "BKR": {"sector": "Energy", "etf": "XLE"},
    "KMI": {"sector": "Energy", "etf": "XLE"},
    "WMB": {"sector": "Energy", "etf": "XLE"},
    "OKE": {"sector": "Energy", "etf": "XLE"},
    "ET": {"sector": "Energy", "etf": "XLE"},
    # Industrials — XLI
    "GE": {"sector": "Industrials", "etf": "XLI"},
    "HON": {"sector": "Industrials", "etf": "XLI"},
    "CAT": {"sector": "Industrials", "etf": "XLI"},
    "DE": {"sector": "Industrials", "etf": "XLI"},
    "RTX": {"sector": "Industrials", "etf": "XLI"},
    "LMT": {"sector": "Industrials", "etf": "XLI"},
    "NOC": {"sector": "Industrials", "etf": "XLI"},
    "BA": {"sector": "Industrials", "etf": "XLI"},
    "UPS": {"sector": "Industrials", "etf": "XLI"},
    "FDX": {"sector": "Industrials", "etf": "XLI"},
    "CSX": {"sector": "Industrials", "etf": "XLI"},
    "NSC": {"sector": "Industrials", "etf": "XLI"},
    "DAL": {"sector": "Industrials", "etf": "XLI"},
    "UAL": {"sector": "Industrials", "etf": "XLI"},
    "AAL": {"sector": "Industrials", "etf": "XLI"},
    "WM": {"sector": "Industrials", "etf": "XLI"},
    "RSG": {"sector": "Industrials", "etf": "XLI"},
    # Materials — XLB
    "LIN": {"sector": "Materials", "etf": "XLB"},
    "APD": {"sector": "Materials", "etf": "XLB"},
    "ECL": {"sector": "Materials", "etf": "XLB"},
    "SHW": {"sector": "Materials", "etf": "XLB"},
    "NEM": {"sector": "Materials", "etf": "XLB"},
    "FCX": {"sector": "Materials", "etf": "XLB"},
    "AA": {"sector": "Materials", "etf": "XLB"},
    "X": {"sector": "Materials", "etf": "XLB"},
    "NUE": {"sector": "Materials", "etf": "XLB"},
    # Real Estate — XLRE
    "AMT": {"sector": "Real Estate", "etf": "XLRE"},
    "PLD": {"sector": "Real Estate", "etf": "XLRE"},
    "CCI": {"sector": "Real Estate", "etf": "XLRE"},
    "EQIX": {"sector": "Real Estate", "etf": "XLRE"},
    "WELL": {"sector": "Real Estate", "etf": "XLRE"},
    # Utilities — XLU
    "NEE": {"sector": "Utilities", "etf": "XLU"},
    "DUK": {"sector": "Utilities", "etf": "XLU"},
    "SO": {"sector": "Utilities", "etf": "XLU"},
    "D": {"sector": "Utilities", "etf": "XLU"},
    "AEP": {"sector": "Utilities", "etf": "XLU"},
    "XEL": {"sector": "Utilities", "etf": "XLU"},
    "EXC": {"sector": "Utilities", "etf": "XLU"},
    "PCG": {"sector": "Utilities", "etf": "XLU"},
    "ED": {"sector": "Utilities", "etf": "XLU"},
    # Sector ETFs (self-referencing for bridge ETF snapshot)
    "XLK": {"sector": "Technology", "etf": "XLK"},
    "XLE": {"sector": "Energy", "etf": "XLE"},
    "XLV": {"sector": "Healthcare", "etf": "XLV"},
    "XLU": {"sector": "Utilities", "etf": "XLU"},
    "XLI": {"sector": "Industrials", "etf": "XLI"},
    "XLF": {"sector": "Financials", "etf": "XLF"},
    "XLP": {"sector": "Consumer Staples", "etf": "XLP"},
    "XLY": {"sector": "Consumer Discretionary", "etf": "XLY"},
    "XLB": {"sector": "Materials", "etf": "XLB"},
    "XLRE": {"sector": "Real Estate", "etf": "XLRE"},
    "XLC": {"sector": "Communication Services", "etf": "XLC"},
    # Benchmarks / broad market
    "SPY": {"sector": "Benchmark", "etf": "SPY"},
    "QQQ": {"sector": "Benchmark", "etf": "QQQ"},
    "IWM": {"sector": "Benchmark", "etf": "IWM"},
    "DIA": {"sector": "Benchmark", "etf": "DIA"},
}


def get_sector(ticker: str) -> str:
    """Return sector name for ticker, or 'Unknown' if not in map."""
    return SECTOR_MAP.get(ticker, {}).get("sector", "Unknown")


def get_etf(ticker: str) -> str:
    """Return parent sector ETF for ticker, or '' if not in map."""
    return SECTOR_MAP.get(ticker, {}).get("etf", "")
```

- [ ] **Step 2: Commit**

```bash
git add src/trading_bot/vault/sector_map.py
git commit -m "feat(vault): add sector_map.py — static ticker-to-sector lookup"
```

---

### Task 2: settings.py — add vault config field

**Files:**
- Modify: `src/trading_bot/settings.py:55`

- [ ] **Step 1: Add vault field to ScannerSettings**

In `src/trading_bot/settings.py`, add one line after `pre_screener`:

```python
    pre_screener: dict[str, Any] | None = None
    vault: dict[str, Any] | None = None
```

- [ ] **Step 2: Run tests to confirm no regressions**

```
$env:PYTHONPATH = "src"; python -m pytest tests/ -x -q
```

Expected: all existing tests pass (vault field is optional with None default).

- [ ] **Step 3: Commit**

```bash
git add src/trading_bot/settings.py
git commit -m "feat(vault): add vault config field to ScannerSettings"
```

---

### Task 3: default_config.yaml — add vault block

**Files:**
- Modify: `config/default_config.yaml`

- [ ] **Step 1: Append vault block at end of file**

```yaml
vault:
  enabled: true
  vault_dir: vault
  command_center_dir: C:/Users/alexa/Downloads/AI Operations Command Center
  bridge_enabled: true
```

- [ ] **Step 2: Verify settings load**

```
$env:PYTHONPATH = "src"; python -c "from trading_bot.settings import load_scanner_settings; s = load_scanner_settings('config/default_config.yaml'); print(s.vault)"
```

Expected: `{'enabled': True, 'vault_dir': 'vault', 'command_center_dir': 'C:/Users/alexa/Downloads/AI Operations Command Center', 'bridge_enabled': True}`

- [ ] **Step 3: Commit**

```bash
git add config/default_config.yaml
git commit -m "feat(vault): add vault config block to default_config.yaml"
```

---

### Task 4: writer.py — daily notes, ticker pages, vault index

**Files:**
- Create: `src/trading_bot/vault/writer.py`
- Test: `tests/test_vault_writer.py`

Snapshot dict structure (from `eod_result["snapshots"]`):
```python
{
    "symbol": "GTLB",           # str
    "score": 87,                # int
    "setup_category": "Breakout Watch",  # str
    "status": "active",         # str: active | waiting_alert | waiting | watching | closed
    "days_active": 4,           # int
    "latest_close": 58.20,      # float | None
    "target_price": 63.50,      # float | None
    "stop_price": 55.80,        # float | None
}
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vault_writer.py
from __future__ import annotations

from pathlib import Path

import pytest

from trading_bot.vault.writer import write_daily_note, upsert_ticker_page, update_vault_index


def _minimal_eod_result() -> dict:
    return {
        "report_date": "2026-05-22",
        "scan_coverage": {
            "universe_size": 349,
            "scored_count": 12,
            "coverage_pct": 3.4,
            "cycles_completed": 2,
            "real_data_count": 10,
        },
        "watch_run_summary": {},
        "signal_scorecard": {},
        "terminal_outcome_summary": {
            "target_hits": 1,
            "stop_hits": 0,
            "active_count": 3,
            "avg_terminal_pl": 2.1,
        },
        "tony_self_review": {
            "strongest_setup": "Breakout Watch",
            "weakest_setup": "Pullback Watch",
            "rule_suggestions": [
                {"confidence": "medium", "suggestion": "Prioritize Breakout Watch"},
            ],
        },
        "replay_summary": {},
        "strategy_version_report": {"current_version": "v1"},
        "rotation_diagnostics": {
            "unique_symbols_scanned": 12,
            "fresh_discoveries": 5,
            "repeat_scans": 7,
            "universe_coverage_pct": 3.4,
        },
        "snapshots": [
            {
                "symbol": "GTLB",
                "score": 87,
                "setup_category": "Breakout Watch",
                "status": "active",
                "days_active": 4,
                "latest_close": 58.20,
                "target_price": 63.50,
                "stop_price": 55.80,
            },
            {
                "symbol": "ZETA",
                "score": 82,
                "setup_category": "Momentum Continuation",
                "status": "waiting_alert",
                "days_active": 3,
                "latest_close": 18.10,
                "target_price": 20.50,
                "stop_price": 16.80,
            },
        ],
        "skip_reasons": {"not_enough_bars": 5, "avg_volume_below_minimum": 3},
    }


class TestWriteDailyNote:
    def test_creates_file(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        assert (tmp_path / "daily" / "2026-05-22.md").exists()

    def test_frontmatter_fields(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "date: 2026-05-22" in content
        assert "tags: [daily, eod]" in content
        assert "strategy_version: v1" in content
        assert "universe_size: 349" in content
        assert "scored_count: 12" in content

    def test_ten_sections_present(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        for n in range(1, 11):
            assert f"## {n}." in content

    def test_scored_symbols_table_has_tickers(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "GTLB" in content
        assert "ZETA" in content

    def test_skip_reasons_section(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "not_enough_bars" in content

    def test_wikilinks_in_scored_table(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "[[GTLB]]" in content

    def test_nav_links(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "[[index]]" in content

    def test_idempotent_overwrite(self, tmp_path):
        eod = _minimal_eod_result()
        write_daily_note("2026-05-22", eod, tmp_path)
        write_daily_note("2026-05-22", eod, tmp_path)
        assert len(list((tmp_path / "daily").iterdir())) == 1

    def test_missing_optional_keys_no_crash(self, tmp_path):
        write_daily_note("2026-05-22", {"report_date": "2026-05-22"}, tmp_path)
        assert (tmp_path / "daily" / "2026-05-22.md").exists()


class TestUpsertTickerPage:
    def _snap(self, **kwargs) -> dict:
        base = {"symbol": "GTLB", "score": 87, "setup_category": "Breakout Watch",
                "status": "active", "days_active": 4}
        return {**base, **kwargs}

    def test_creates_file_on_first_call(self, tmp_path):
        upsert_ticker_page("2026-05-22", self._snap(), tmp_path)
        assert (tmp_path / "signals" / "GTLB.md").exists()

    def test_frontmatter_ticker_field(self, tmp_path):
        upsert_ticker_page("2026-05-22", self._snap(), tmp_path)
        content = (tmp_path / "signals" / "GTLB.md").read_text(encoding="utf-8")
        assert "ticker: GTLB" in content
        assert "first_seen: 2026-05-22" in content

    def test_signal_history_row_appended(self, tmp_path):
        upsert_ticker_page("2026-05-22", self._snap(), tmp_path)
        upsert_ticker_page("2026-05-23", self._snap(score=89, days_active=5), tmp_path)
        content = (tmp_path / "signals" / "GTLB.md").read_text(encoding="utf-8")
        assert "2026-05-22" in content
        assert "2026-05-23" in content
        assert content.count("| [[2026-05-") == 2

    def test_no_duplicate_row_on_same_date(self, tmp_path):
        snap = self._snap()
        upsert_ticker_page("2026-05-22", snap, tmp_path)
        upsert_ticker_page("2026-05-22", snap, tmp_path)
        content = (tmp_path / "signals" / "GTLB.md").read_text(encoding="utf-8")
        assert content.count("| [[2026-05-22]]") == 1


class TestUpdateVaultIndex:
    def test_creates_index(self, tmp_path):
        update_vault_index("2026-05-22", [], tmp_path)
        assert (tmp_path / "index.md").exists()

    def test_index_links_to_daily(self, tmp_path):
        update_vault_index("2026-05-22", [], tmp_path)
        content = (tmp_path / "index.md").read_text(encoding="utf-8")
        assert "[[daily/2026-05-22]]" in content

    def test_index_lists_active_snapshots(self, tmp_path):
        snapshots = [
            {"symbol": "GTLB", "status": "active", "score": 87},
            {"symbol": "ZETA", "status": "active", "score": 82},
            {"symbol": "CVS", "status": "closed", "score": 71},
        ]
        update_vault_index("2026-05-22", snapshots, tmp_path)
        content = (tmp_path / "index.md").read_text(encoding="utf-8")
        assert "GTLB" in content
        assert "ZETA" in content
        assert "CVS" not in content
```

- [ ] **Step 2: Run tests — confirm they fail**

```
$env:PYTHONPATH = "src"; python -m pytest tests/test_vault_writer.py -v
```

Expected: `ModuleNotFoundError: No module named 'trading_bot.vault'`

- [ ] **Step 3: Implement writer.py**

```python
# src/trading_bot/vault/writer.py
from __future__ import annotations

from pathlib import Path
from typing import Any


def write_daily_note(date: str, eod_result: dict[str, Any], vault_dir: str | Path) -> Path:
    """Write vault/daily/YYYY-MM-DD.md from eod_result dict. Overwrites if exists."""
    vault_path = Path(vault_dir)
    daily_dir = vault_path / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    note_path = daily_dir / f"{date}.md"

    sc = eod_result.get("scan_coverage") or {}
    sr = eod_result.get("tony_self_review") or {}
    svr = eod_result.get("strategy_version_report") or {}
    tos = eod_result.get("terminal_outcome_summary") or {}
    rd = eod_result.get("rotation_diagnostics") or {}
    skip = eod_result.get("skip_reasons") or {}
    snapshots = eod_result.get("snapshots") or []
    scorecard = eod_result.get("signal_scorecard") or {}
    suggestions = sr.get("rule_suggestions") or []
    strategy_version = (svr.get("current_version") or "v1")

    universe_size = sc.get("universe_size", 0)
    scored_count = sc.get("scored_count", 0)
    coverage_pct = sc.get("coverage_pct", 0.0)
    cycles = sc.get("cycles_completed", 0)
    real_data_count = sc.get("real_data_count", 0)
    active_count = tos.get("active_count", 0)
    target_hits = tos.get("target_hits", 0)
    stop_hits = tos.get("stop_hits", 0)
    avg_pl = tos.get("avg_terminal_pl", None)
    pl_str = f"{avg_pl:.1f}%" if isinstance(avg_pl, (int, float)) else "N/A"

    lines: list[str] = [
        "---",
        f"date: {date}",
        "tags: [daily, eod]",
        f"strategy_version: {strategy_version}",
        f"universe_size: {universe_size}",
        f"scored_count: {scored_count}",
        f"coverage_pct: {coverage_pct}",
        f"cycles: {cycles}",
        "---",
        "",
        f"# {date} — EOD Daily Note",
        "",
        "## 1. Scan Coverage",
        f"- Universe: {universe_size} symbols | Scored: {scored_count} ({coverage_pct:.1f}%)",
        f"- Cycles completed: {cycles}",
        f"- Real data symbols: {real_data_count}",
        "",
        "## 2. All Scored Symbols",
        "*(every symbol that ran through scoring)*",
        "",
        "| Ticker | Score | Setup Category | Status | Days Active |",
        "|--------|-------|----------------|--------|-------------|",
    ]
    for snap in snapshots:
        sym = snap.get("symbol", "")
        lines.append(
            f"| [[{sym}]] | {snap.get('score', '')} | {snap.get('setup_category', '')} "
            f"| {snap.get('status', '')} | {snap.get('days_active', 0)} |"
        )
    lines.append("")

    lines += [
        "## 3. Skip Reasons",
        "*(why symbols didn't get scored)*",
        "",
        "| Reason | Count |",
        "|--------|-------|",
    ]
    for reason, count in (skip.items() if skip else [("—", "—")]):
        lines.append(f"| {reason} | {count} |")
    lines.append("")

    unique = rd.get("unique_symbols_scanned", 0)
    fresh = rd.get("fresh_discoveries", 0)
    repeats = rd.get("repeat_scans", 0)
    uni_cov = rd.get("universe_coverage_pct", 0.0)
    lines += [
        "## 4. Rotation Diagnostics",
        f"- Unique symbols scanned today: {unique}",
        f"- Fresh discoveries: {fresh}",
        f"- Repeat scans: {repeats}",
        f"- Universe coverage: {uni_cov:.1f}%",
        "",
    ]

    tier1 = [s for s in snapshots if s.get("days_active", 0) >= 3]
    tier2 = [s for s in snapshots if s.get("days_active", 0) == 2]
    tier3 = [s for s in snapshots if s.get("days_active", 0) == 1]
    lines += ["## 5. Top Signals (Curated)", ""]
    if tier1:
        lines += ["### Tier 1 — High Conviction (3+ days)",
                  "| Ticker | Setup | Score | Days Active |",
                  "|--------|-------|-------|-------------|"]
        for s in tier1:
            lines.append(f"| [[{s['symbol']}]] | {s.get('setup_category', '')} | {s.get('score', '')} | {s.get('days_active', '')} |")
        lines.append("")
    if tier2:
        lines += ["### Tier 2 — Medium Conviction (2 days)",
                  "| Ticker | Setup | Score | Days Active |",
                  "|--------|-------|-------|-------------|"]
        for s in tier2:
            lines.append(f"| [[{s['symbol']}]] | {s.get('setup_category', '')} | {s.get('score', '')} | {s.get('days_active', '')} |")
        lines.append("")
    if tier3:
        lines += [f"### Tier 3 — Monitor (1 day)",
                  " · ".join(f"[[{s['symbol']}]]" for s in tier3), ""]
    if not (tier1 or tier2 or tier3):
        lines += ["*No scored signals today.*", ""]

    lines += [
        "## 6. Outcomes Today",
        f"- Active positions: {active_count}",
        f"- Target hits: {target_hits}",
        f"- Stop hits: {stop_hits}",
        f"- Avg terminal P/L: {pl_str}",
        "",
        "## 7. Signal Scorecard",
        "| Setup | Triggered | Target Rate | Stop Rate |",
        "|-------|-----------|-------------|-----------|",
    ]
    if isinstance(scorecard, dict) and scorecard:
        for setup, stats in scorecard.items():
            if not isinstance(stats, dict):
                continue
            triggered = stats.get("triggered", stats.get("total_triggered", ""))
            tr = stats.get("target_rate", "")
            sr2 = stats.get("stop_rate", "")
            if isinstance(tr, float):
                tr = f"{tr:.0%}"
            if isinstance(sr2, float):
                sr2 = f"{sr2:.0%}"
            lines.append(f"| {setup} | {triggered} | {tr} | {sr2} |")
    else:
        lines.append("| — | — | — | — |")
    lines.append("")

    strongest = sr.get("strongest_setup", "N/A")
    weakest = sr.get("weakest_setup", "N/A")
    tomorrow_watch = sr.get("tomorrow_watch", "")
    lines += [
        "## 8. EOD Self-Review",
        f"- Strongest: {strongest}",
        f"- Weakest: {weakest}",
        f"- Active carry over tomorrow: {active_count}",
    ]
    if tomorrow_watch:
        lines.append(f"- Tomorrow watch: {tomorrow_watch}")
    lines.append("")

    lines += ["## 9. Rule Suggestions"]
    if suggestions:
        for i, sug in enumerate(suggestions, 1):
            lines.append(f"{i}. [{sug.get('confidence', '')}] {sug.get('suggestion', '')}")
    else:
        lines.append("*No suggestions today.*")
    lines += [
        "",
        "## 10. Strategy",
        f"- Version: {strategy_version} | Proposals pending: {len(suggestions)}",
        "- No changes applied today",
        "",
        "## Links",
        f"← [[{date}]] | [[index]]",
    ]

    note_path.write_text("\n".join(lines), encoding="utf-8")
    return note_path


def upsert_ticker_page(date: str, snapshot: dict[str, Any], vault_dir: str | Path) -> Path:
    """Create or append-to vault/signals/TICKER.md. Never overwrites existing history rows."""
    vault_path = Path(vault_dir)
    signals_dir = vault_path / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)

    symbol = snapshot.get("symbol", "UNKNOWN")
    page_path = signals_dir / f"{symbol}.md"
    score = snapshot.get("score", "")
    setup = snapshot.get("setup_category", "")
    status = snapshot.get("status", "")
    days_active = snapshot.get("days_active", 0)
    new_row = f"| [[{date}]] | {setup} | {score} | {status} |"

    if not page_path.exists():
        lines = [
            "---",
            f"ticker: {symbol}",
            "tags: [signal]",
            f"status: {status}",
            f"first_seen: {date}",
            f"days_active: {days_active}",
            "---",
            "",
            f"# {symbol}",
            "",
            f"**Status:** {status}",
            f"**Days Active:** {days_active}",
            "",
            "## Signal History",
            "| Date | Setup | Score | Status |",
            "|------|-------|-------|--------|",
            new_row,
            "",
            "## Entry Plan",
            "*Populated when entry triggered.*",
            "",
            "## Outcome",
            "*Populated on close.*",
            "",
            "## Notes",
            "",
        ]
        page_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        content = page_path.read_text(encoding="utf-8")
        if f"[[{date}]]" in content:
            return page_path
        lines = content.splitlines()
        insert_idx = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith("| [["):
                insert_idx = i + 1
                break
        if insert_idx is None:
            lines.append(new_row)
        else:
            lines.insert(insert_idx, new_row)
        updated = []
        for line in lines:
            if line.startswith("days_active:"):
                updated.append(f"days_active: {days_active}")
            elif line.startswith("status:") and not line.startswith("**"):
                updated.append(f"status: {status}")
            else:
                updated.append(line)
        page_path.write_text("\n".join(updated), encoding="utf-8")

    return page_path


def update_vault_index(date: str, snapshots: list[dict[str, Any]], vault_dir: str | Path) -> Path:
    """Write/overwrite vault/index.md with current state summary."""
    vault_path = Path(vault_dir)
    vault_path.mkdir(parents=True, exist_ok=True)
    index_path = vault_path / "index.md"

    active = sorted(
        [s for s in snapshots if s.get("status") in ("active", "waiting_alert", "waiting")],
        key=lambda s: s.get("score", 0), reverse=True,
    )

    lines = [
        "# Trading Bot Vault — Index",
        "",
        f"*Last updated: {date}*",
        "",
        "## Latest Daily Note",
        f"[[daily/{date}]]",
        "",
        "## Current Active Positions",
        "| Ticker | Score | Status |",
        "|--------|-------|--------|",
    ]
    for s in active:
        sym = s.get("symbol", "")
        lines.append(f"| [[signals/{sym}]] | {s.get('score', '')} | {s.get('status', '')} |")
    if not active:
        lines.append("| — | — | — |")
    lines += [
        "",
        "## Navigation",
        "- [[daily/]] — all daily notes",
        "- [[signals/]] — all ticker pages",
        "- [[outcomes/]] — performance ledger",
        "- [[strategy/]] — strategy versions and proposals",
        "- [[memory/agent-context]] — curated vault summary",
    ]

    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path
```

- [ ] **Step 4: Create `src/trading_bot/vault/__init__.py`**

```python
# src/trading_bot/vault/__init__.py
from trading_bot.vault.writer import update_vault_index, upsert_ticker_page, write_daily_note
from trading_bot.vault.bridge import write_bridge_export

__all__ = [
    "write_daily_note",
    "upsert_ticker_page",
    "update_vault_index",
    "write_bridge_export",
]
```

- [ ] **Step 5: Run writer tests**

```
$env:PYTHONPATH = "src"; python -m pytest tests/test_vault_writer.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/trading_bot/vault/__init__.py src/trading_bot/vault/writer.py tests/test_vault_writer.py
git commit -m "feat(vault): writer.py — daily notes, ticker pages, vault index"
```

---

### Task 5: bridge.py — analyst brief export to Command Center

**Files:**
- Create: `src/trading_bot/vault/bridge.py`
- Test: `tests/test_vault_bridge.py`

Bridge export file path: `{command_center_dir}/bridge/tony-stocks/YYYY-MM-DD.md`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vault_bridge.py
from __future__ import annotations

from pathlib import Path

import pytest

from trading_bot.vault.bridge import write_bridge_export, _detect_clusters, _build_sector_etf_snapshot


def _eod_result_with_tiers() -> dict:
    return {
        "report_date": "2026-05-22",
        "scan_coverage": {"universe_size": 349, "scored_count": 175, "coverage_pct": 50.1, "cycles_completed": 12},
        "strategy_version_report": {"current_version": "v1"},
        "tony_self_review": {
            "rule_suggestions": [{"confidence": "medium", "suggestion": "Prioritize Breakout Watch"}],
        },
        "terminal_outcome_summary": {"active_count": 7},
        "signal_scorecard": {
            "Breakout Watch": {"triggered": 14, "target_rate": 0.64, "stop_rate": 0.21},
        },
        "snapshots": [
            {"symbol": "GTLB", "score": 87, "setup_category": "Breakout Watch",
             "status": "active", "days_active": 4,
             "latest_close": 58.20, "target_price": 63.50, "stop_price": 55.80},
            {"symbol": "ZETA", "score": 82, "setup_category": "Momentum Continuation",
             "status": "waiting_alert", "days_active": 3,
             "latest_close": 18.10, "target_price": 20.50, "stop_price": 16.80},
            {"symbol": "CVS", "score": 71, "setup_category": "Breakout Watch",
             "status": "waiting", "days_active": 2,
             "latest_close": 62.10, "target_price": 67.20, "stop_price": 58.90},
            {"symbol": "ANET", "score": 61, "setup_category": "Breakout Watch",
             "status": "watching", "days_active": 1,
             "latest_close": 312.40, "target_price": 340.0, "stop_price": 298.0},
            {"symbol": "XLK", "score": 72, "setup_category": "Breakout Watch",
             "status": "watching", "days_active": 1,
             "latest_close": 200.0, "target_price": None, "stop_price": None},
        ],
        "outcomes_since_last_brief": [
            {"symbol": "ORCL", "result": "target_hit", "entry_date": "2026-05-20",
             "days_held": 2, "pl_pct": 4.2},
        ],
    }


class TestWriteBridgeExport:
    def test_creates_file(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result_with_tiers(), tmp_path)
        assert (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").exists()

    def test_frontmatter_present(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result_with_tiers(), tmp_path)
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "date: 2026-05-22" in content
        assert "source: TradingBotAgentProject" in content
        assert "export_type: eod-bridge" in content

    def test_tier1_block_present(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result_with_tiers(), tmp_path)
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Tier 1" in content
        assert "GTLB" in content
        assert "ZETA" in content

    def test_tier2_table_present(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result_with_tiers(), tmp_path)
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Tier 2" in content
        assert "CVS" in content

    def test_tier3_present(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result_with_tiers(), tmp_path)
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Tier 3" in content
        assert "ANET" in content

    def test_outcomes_section(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result_with_tiers(), tmp_path)
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Outcomes Since Last Brief" in content
        assert "ORCL" in content

    def test_scorecard_section(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result_with_tiers(), tmp_path)
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Signal Scorecard" in content
        assert "Breakout Watch" in content

    def test_rule_suggestions_section(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result_with_tiers(), tmp_path)
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Rule Suggestions" in content
        assert "medium" in content

    def test_for_tony_section(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result_with_tiers(), tmp_path)
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## For Tony" in content

    def test_empty_eod_no_crash(self, tmp_path):
        write_bridge_export("2026-05-22", {"report_date": "2026-05-22"}, tmp_path)
        assert (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").exists()


class TestDetectClusters:
    def test_flags_cluster_of_three(self):
        snapshots = [
            {"symbol": "GTLB", "days_active": 4},
            {"symbol": "ANET", "days_active": 2},
            {"symbol": "CRM", "days_active": 1},
            {"symbol": "ORCL", "days_active": 3},
        ]
        clusters = _detect_clusters(snapshots, threshold=3)
        assert any(c["sector"] == "Technology" for c in clusters)

    def test_no_cluster_below_threshold(self):
        snapshots = [
            {"symbol": "GTLB", "days_active": 4},
            {"symbol": "XOM", "days_active": 2},
        ]
        clusters = _detect_clusters(snapshots, threshold=3)
        assert clusters == []


class TestBuildSectorEtfSnapshot:
    def test_returns_known_etfs(self):
        snapshots = [
            {"symbol": "XLK", "score": 72, "setup_category": "Breakout Watch"},
            {"symbol": "XLE", "score": 58, "setup_category": "Pullback Watch"},
        ]
        result = _build_sector_etf_snapshot(snapshots)
        etfs = [r["etf"] for r in result]
        assert "XLK" in etfs
        assert "XLE" in etfs

    def test_score_and_setup_carried(self):
        snapshots = [{"symbol": "XLK", "score": 72, "setup_category": "Breakout Watch"}]
        result = _build_sector_etf_snapshot(snapshots)
        xlk = next(r for r in result if r["etf"] == "XLK")
        assert xlk["score"] == 72
        assert xlk["setup"] == "Breakout Watch"
```

- [ ] **Step 2: Run tests — confirm they fail**

```
$env:PYTHONPATH = "src"; python -m pytest tests/test_vault_bridge.py -v
```

Expected: `ModuleNotFoundError: No module named 'trading_bot.vault.bridge'`

- [ ] **Step 3: Implement bridge.py**

```python
# src/trading_bot/vault/bridge.py
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from trading_bot.vault.sector_map import SECTOR_MAP, get_etf, get_sector

_SECTOR_ETFS = ["XLK", "XLE", "XLV", "XLU", "XLI", "XLF", "XLP", "XLY", "XLB", "XLRE", "XLC"]


def _pct(val: float | None, ref: float | None) -> str:
    if val is None or ref is None or ref == 0:
        return "N/A"
    diff = ((val - ref) / ref) * 100
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.1f}%"


def _rr(target: float | None, close: float | None, stop: float | None) -> str:
    if target is None or close is None or stop is None or close == 0:
        return "N/A"
    upside = abs(target - close)
    downside = abs(close - stop)
    if downside == 0:
        return "N/A"
    return f"{upside / downside:.1f}:1"


def _detect_clusters(
    snapshots: list[dict[str, Any]], threshold: int = 3
) -> list[dict[str, Any]]:
    sector_tickers: dict[str, list[str]] = {}
    for snap in snapshots:
        sym = snap.get("symbol", "")
        sector = get_sector(sym)
        if sector in ("Unknown", "Benchmark"):
            continue
        sector_tickers.setdefault(sector, []).append(sym)
    clusters = []
    for sector, tickers in sector_tickers.items():
        if len(tickers) >= threshold:
            etf = get_etf(tickers[0]) if tickers else ""
            clusters.append({"sector": sector, "etf": etf, "tickers": tickers})
    return clusters


def _build_sector_etf_snapshot(
    snapshots: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    etf_map = {s["symbol"]: s for s in snapshots if s.get("symbol") in _SECTOR_ETFS}
    result = []
    for etf in _SECTOR_ETFS:
        if etf in etf_map:
            snap = etf_map[etf]
            score = snap.get("score", "N/A")
            setup = snap.get("setup_category", "")
            trend = (
                "↑ bullish" if isinstance(score, (int, float)) and score >= 65
                else "↓ weak" if isinstance(score, (int, float)) and score <= 45
                else "→ neutral"
            )
            result.append({"etf": etf, "score": score, "setup": setup, "trend": trend})
    return result


def write_bridge_export(
    date: str, eod_result: dict[str, Any], command_center_dir: str | Path
) -> Path:
    """Write curated analyst brief to {command_center_dir}/bridge/tony-stocks/YYYY-MM-DD.md."""
    cc_path = Path(command_center_dir)
    bridge_dir = cc_path / "bridge" / "tony-stocks"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    out_path = bridge_dir / f"{date}.md"

    sc = eod_result.get("scan_coverage") or {}
    snapshots = eod_result.get("snapshots") or []
    scorecard = eod_result.get("signal_scorecard") or {}
    sr = eod_result.get("tony_self_review") or {}
    svr = eod_result.get("strategy_version_report") or {}
    tos = eod_result.get("terminal_outcome_summary") or {}
    outcomes = eod_result.get("outcomes_since_last_brief") or []
    suggestions = sr.get("rule_suggestions") or []

    universe_size = sc.get("universe_size", 0)
    scored_count = sc.get("scored_count", 0)
    coverage_pct = sc.get("coverage_pct", 0.0)
    cycles = sc.get("cycles_completed", 0)
    strategy_version = svr.get("current_version") or "v1"
    active_count = tos.get("active_count", 0)

    non_etf = [s for s in snapshots if s.get("symbol") not in _SECTOR_ETFS]
    tier1 = sorted([s for s in non_etf if s.get("days_active", 0) >= 3],
                   key=lambda s: s.get("score", 0), reverse=True)
    tier2 = sorted([s for s in non_etf if s.get("days_active", 0) == 2],
                   key=lambda s: s.get("score", 0), reverse=True)
    tier3 = sorted([s for s in non_etf if s.get("days_active", 0) == 1],
                   key=lambda s: s.get("score", 0), reverse=True)

    clusters = _detect_clusters(snapshots)
    etf_snapshot = _build_sector_etf_snapshot(snapshots)

    try:
        prev_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        prev_date = "previous"

    lines: list[str] = [
        "---",
        f"date: {date}",
        "source: TradingBotAgentProject",
        f"strategy_version: {strategy_version}",
        "export_type: eod-bridge",
        "---",
        "",
        f"# Tony Stocks Bridge — {date}",
        "",
        "## Scanner Summary",
        f"- Universe: {universe_size} | Scored: {scored_count} ({coverage_pct:.1f}%) | Cycles: {cycles}",
        "",
        "## Tier 1 — Hand Off for Deep Analysis",
        "*(3+ days active — full conviction review)*",
        "",
    ]
    if tier1:
        for s in tier1:
            sym = s.get("symbol", "")
            close = s.get("latest_close")
            target = s.get("target_price")
            stop = s.get("stop_price")
            entry_triggered = s.get("status") == "active"
            lines += [
                f"### {sym}",
                f"- Days active: {s.get('days_active', '')} | Score: {s.get('score', '')} | Setup: {s.get('setup_category', '')}",
                f"- Last close: ${close} | Target: ${target} ({_pct(target, close)}) | Stop: ${stop} ({_pct(stop, close)})",
                f"- R/R: {_rr(target, close, stop)} | Entry triggered: {'yes' if entry_triggered else 'no'}",
                "",
            ]
    else:
        lines += ["*No Tier 1 signals today.*", ""]

    lines += ["## Tier 2 — Monitor", "*(2 days — building conviction)*", "",
              "| Ticker | Score | Setup | Close | To Target | To Stop | R/R |",
              "|--------|-------|-------|-------|-----------|---------|-----|"]
    if tier2:
        for s in tier2:
            close = s.get("latest_close")
            target = s.get("target_price")
            stop = s.get("stop_price")
            lines.append(
                f"| {s.get('symbol', '')} | {s.get('score', '')} | {s.get('setup_category', '')} "
                f"| ${close} | {_pct(target, close)} | {_pct(stop, close)} | {_rr(target, close, stop)} |"
            )
    else:
        lines.append("| — | — | — | — | — | — | — |")
    lines.append("")

    lines += ["## Tier 3 — New Signals (1 day)", "",
              "| Ticker | Score | Setup | Close |", "|--------|-------|-------|-------|"]
    if tier3:
        for s in tier3:
            lines.append(f"| {s.get('symbol', '')} | {s.get('score', '')} | {s.get('setup_category', '')} | ${s.get('latest_close', '')} |")
    else:
        lines.append("| — | — | — | — |")
    lines.append("")

    lines += ["## Sector ETF Snapshot", "*(macro context for signal clusters)*", "",
              "| ETF | Sector | Score | Setup | Trend |",
              "|-----|--------|-------|-------|-------|"]
    if etf_snapshot:
        for e in etf_snapshot:
            sector = SECTOR_MAP.get(e["etf"], {}).get("sector", "")
            lines.append(f"| {e['etf']} | {sector} | {e['score']} | {e['setup']} | {e['trend']} |")
    else:
        lines.append("| — | — | — | — | — |")
    lines.append("")

    lines += ["## Cluster Risk Flags", "*(concentration warning — same sector exposure)*", ""]
    if clusters:
        for c in clusters:
            tickers_str = " + ".join(c["tickers"])
            lines += [
                f"⚠ {c['sector'].upper()} CLUSTER: {tickers_str} = {len(c['tickers'])} signals",
                f"  → All correlated to {c['etf']}",
                f"  → Risk: sector-wide drawdown affects all {len(c['tickers'])}",
                "",
            ]
    else:
        lines += ["*No cluster risk flags today.*", ""]

    lines += ["## Outcomes Since Last Brief", "",
              "| Ticker | Result | Entry Date | Days Held | P/L |",
              "|--------|--------|-----------|-----------|-----|"]
    if outcomes:
        for o in outcomes:
            pl = o.get("pl_pct")
            pl_str = f"{pl:+.1f}%" if isinstance(pl, (int, float)) else "N/A"
            result = o.get("result", "")
            icon = "✅" if "target" in result else ("❌" if "stop" in result else "⏳")
            lines.append(
                f"| {o.get('symbol', '')} | {icon} {result.replace('_', ' ')} "
                f"| {o.get('entry_date', '')} | {o.get('days_held', '')} | {pl_str} |"
            )
    else:
        lines.append("| — | — | — | — | — |")
    lines += ["", f"Active carry-over: {active_count} positions", ""]

    lines += ["## Signal Scorecard (running totals)", "",
              "| Setup | Triggered | Target Rate | Stop Rate |",
              "|-------|-----------|-------------|-----------|"]
    if isinstance(scorecard, dict) and scorecard:
        for setup, stats in scorecard.items():
            if not isinstance(stats, dict):
                continue
            triggered = stats.get("triggered", stats.get("total_triggered", ""))
            tr = stats.get("target_rate", "")
            sr2 = stats.get("stop_rate", "")
            if isinstance(tr, float):
                tr = f"{tr:.0%}"
            if isinstance(sr2, float):
                sr2 = f"{sr2:.0%}"
            lines.append(f"| {setup} | {triggered} | {tr} | {sr2} |")
    else:
        lines.append("| — | — | — | — |")
    lines.append("")

    lines += ["## Rule Suggestions Pending Review"]
    if suggestions:
        for i, sug in enumerate(suggestions, 1):
            lines.append(f"{i}. [{sug.get('confidence', '')}] {sug.get('suggestion', '')}")
    else:
        lines.append("*No suggestions pending.*")
    lines.append("")

    tier1_action = ", ".join(s.get("symbol", "") for s in tier1) if tier1 else "none"
    cluster_action = ", ".join(c["sector"] for c in clusters) if clusters else "none"
    lines += [
        "## For Tony",
        "Daily brief from scanner. Action items:",
        f"- Deep analysis on Tier 1: {tier1_action}",
        f"- Cluster risk review: {cluster_action}",
        "- Update signal-ledger.md + index.md after review",
        f"Previous brief: bridge/tony-stocks/{prev_date}.md",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
```

- [ ] **Step 4: Run bridge tests**

```
$env:PYTHONPATH = "src"; python -m pytest tests/test_vault_bridge.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run full test suite**

```
$env:PYTHONPATH = "src"; python -m pytest tests/ -x -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/trading_bot/vault/bridge.py tests/test_vault_bridge.py
git commit -m "feat(vault): bridge.py — analyst brief export to Command Center"
```

---

### Task 6: cli.py — wire vault into after-market-review + export-to-vault command

**Files:**
- Modify: `src/trading_bot/cli.py`

- [ ] **Step 1: Add vault import near top of cli.py**

After the existing import block (around line 50), add:

```python
from trading_bot.vault import write_bridge_export, write_daily_note, update_vault_index, upsert_ticker_page
```

- [ ] **Step 2: Add vault helper function before run_after_market_review()**

```python
def _run_vault_export(report_date: str, eod_result: dict[str, Any], vault_cfg: dict[str, Any]) -> None:
    """Write vault daily note, ticker pages, index, and bridge export if configured."""
    vault_dir = Path(vault_cfg.get("vault_dir", "vault"))
    snapshots_list = eod_result.get("snapshots") or []
    print(f"\nWriting vault → {vault_dir}/daily/{report_date}.md")
    write_daily_note(report_date, eod_result, vault_dir)
    for snap in snapshots_list:
        upsert_ticker_page(report_date, snap, vault_dir)
    update_vault_index(report_date, snapshots_list, vault_dir)
    print(f"  Vault: {len(snapshots_list)} ticker pages updated.")

    if vault_cfg.get("bridge_enabled", False):
        cc_dir = vault_cfg.get("command_center_dir", "")
        if cc_dir:
            print(f"\nWriting bridge export → {cc_dir}/bridge/tony-stocks/{report_date}.md")
            write_bridge_export(report_date, eod_result, Path(cc_dir))
            print("  Bridge export written.")
        else:
            print("\nVault bridge_enabled but command_center_dir not set — skipping.")
```

- [ ] **Step 3: Add vault call at end of run_after_market_review() before return statement**

In `run_after_market_review()`, add after the proposal replay block (before the `return` dict at line 2532):

```python
    # 8. Write vault notes and bridge export (if vault enabled)
    settings = load_scanner_settings(getattr(args, "config", "config/default_config.yaml"))
    vault_cfg = settings.vault or {}
    if vault_cfg.get("enabled", False):
        _run_vault_export(report_date, eod_result, vault_cfg)
```

- [ ] **Step 4: Add run_export_to_vault function before run_after_market_review()**

```python
def run_export_to_vault(args: argparse.Namespace) -> None:
    """Re-export vault notes and bridge brief from a saved EOD report JSON."""
    report_date = getattr(args, "date", None) or new_york_market_date()
    output_base = Path(getattr(args, "output_dir", "reports")) / report_date
    eod_json_path = output_base / "eod_report.json"

    if not eod_json_path.exists():
        print(f"No EOD report found at {eod_json_path}. Run after-market-review first.")
        return

    eod_result = json.loads(eod_json_path.read_text(encoding="utf-8"))
    settings = load_scanner_settings(args.config)
    vault_cfg = settings.vault or {}

    if not vault_cfg.get("enabled", False):
        print("Vault not enabled in config. Set vault.enabled: true.")
        return

    _run_vault_export(report_date, eod_result, vault_cfg)
    print("export-to-vault complete.")
```

- [ ] **Step 5: Register export-to-vault subcommand in main()**

Find where subparsers are added (look for `add_parser` calls) and add:

```python
    export_vault_parser = subparsers.add_parser(
        "export-to-vault",
        help="Re-export vault notes and bridge brief from the most recent EOD report.",
    )
    export_vault_parser.add_argument("--config", default="config/default_config.yaml")
    export_vault_parser.add_argument("--date", default=None, help="Report date YYYY-MM-DD")
    export_vault_parser.add_argument("--output-dir", default="reports")
    export_vault_parser.set_defaults(func=run_export_to_vault)
```

- [ ] **Step 6: Run full test suite**

```
$env:PYTHONPATH = "src"; python -m pytest tests/ -x -q
```

Expected: all tests pass.

- [ ] **Step 7: Smoke test CLI**

```
$env:PYTHONPATH = "src"; python -m trading_bot.cli export-to-vault --help
```

Expected: help text prints without error.

- [ ] **Step 8: Commit**

```bash
git add src/trading_bot/cli.py
git commit -m "feat(vault): wire vault/bridge into after-market-review; add export-to-vault command"
```

---

### Task 7: seed_vault.py — one-time backfill from SQLite

**Files:**
- Create: `scripts/seed_vault.py`

No automated tests. Manual smoke-test with `--dry-run`.

- [ ] **Step 1: Create seed_vault.py**

```python
#!/usr/bin/env python3
"""One-time backfill: write vault/ notes from existing SQLite snapshot data.

Usage:
    $env:PYTHONPATH = "src"
    python scripts/seed_vault.py --config config/default_config.yaml --dry-run
    python scripts/seed_vault.py --config config/default_config.yaml --days-back 60
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trading_bot.settings import load_scanner_settings
from trading_bot.storage.database import initialize_database
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.vault.writer import update_vault_index, upsert_ticker_page, write_daily_note


def _group_by_date(snapshots: list[dict]) -> dict[str, list[dict]]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for snap in snapshots:
        date = (snap.get("report_date") or snap.get("created_at") or "")[:10]
        if date:
            by_date[date].append(snap)
    return dict(by_date)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill vault/ from existing SQLite data.")
    parser.add_argument("--config", default="config/default_config.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days-back", type=int, default=30)
    args = parser.parse_args()

    settings = load_scanner_settings(args.config)
    vault_cfg = settings.vault or {}
    if not vault_cfg.get("enabled", False):
        print("Vault not enabled in config. Set vault.enabled: true.")
        sys.exit(1)

    vault_dir = Path(vault_cfg.get("vault_dir", "vault"))
    conn = initialize_database(str(settings.database_path))
    repo = ScannerRepository(conn)

    try:
        all_snapshots = repo.get_all_candidate_snapshots()
    except Exception as e:
        print(f"Could not load snapshots: {e}")
        all_snapshots = []

    by_date = _group_by_date(all_snapshots)
    dates = sorted(by_date.keys())[-args.days_back:]

    print(f"Found {len(all_snapshots)} snapshots across {len(by_date)} dates.")
    print(f"Backfilling {len(dates)} dates → {vault_dir}/")

    for date in dates:
        snaps = by_date[date]
        if args.dry_run:
            print(f"  [DRY RUN] {date}: {len(snaps)} snapshots")
            continue
        eod_result = {
            "report_date": date,
            "snapshots": snaps,
            "scan_coverage": {},
            "signal_scorecard": {},
            "terminal_outcome_summary": {},
            "tony_self_review": {},
            "strategy_version_report": {"current_version": "v1"},
            "rotation_diagnostics": {},
            "skip_reasons": {},
        }
        write_daily_note(date, eod_result, vault_dir)
        for snap in snaps:
            upsert_ticker_page(date, snap, vault_dir)
        print(f"  {date}: {len(snaps)} snapshots written")

    if not args.dry_run and dates:
        last_snaps = by_date.get(dates[-1], [])
        update_vault_index(dates[-1], last_snaps, vault_dir)
        print(f"Index updated → {vault_dir}/index.md")

    print("Seed complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test (dry run)**

```
$env:PYTHONPATH = "src"; python scripts/seed_vault.py --config config/default_config.yaml --dry-run
```

Expected: prints date list, no files written.

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_vault.py
git commit -m "feat(vault): seed_vault.py — one-time SQLite backfill script"
```

---

### Task 8: AGENT_STATE.md update

**Files:**
- Modify: `AGENT_STATE.md`

- [ ] **Step 1: Update AGENT_STATE.md**

Read `AGENT_STATE.md` and update the current status section to reflect B-Phase 1 complete:
- Module `src/trading_bot/vault/` built: writer.py, bridge.py, sector_map.py, __init__.py
- Tests: test_vault_writer.py, test_vault_bridge.py
- Config: vault block in default_config.yaml
- CLI: export-to-vault command added
- Seed script: scripts/seed_vault.py
- Next: run `python scripts/seed_vault.py --days-back 60` to populate vault, then A-Phase 1 / V34C

- [ ] **Step 2: Final full test run**

```
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add AGENT_STATE.md
git commit -m "docs: update AGENT_STATE after B-Phase 1 vault implementation complete"
```

---

## Final Verification Checklist

- [ ] `python -m pytest tests/test_vault_writer.py tests/test_vault_bridge.py -v` — all pass
- [ ] Full test suite green
- [ ] `python -m trading_bot.cli export-to-vault --help` prints without error
- [ ] `python scripts/seed_vault.py --dry-run` prints date list without error
- [ ] `vault:` block present in `config/default_config.yaml`
- [ ] `AGENT_STATE.md` updated

## Post-implementation: seed and open in Obsidian

Run the backfill:
```
$env:PYTHONPATH = "src"
python scripts/seed_vault.py --config config/default_config.yaml --days-back 60
```

Open Obsidian → Add vault → point at `C:\Users\alexa\Downloads\TradingBotAgentProject\vault\`
All daily notes, ticker pages, and the index will be linked automatically via wikilinks.
