# Backtest CLI Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing `backtest` CLI command production-useful by adding date-range data fetching, multi-ticker support, CLI-configurable strategy params, and JSON/markdown report saving — matching the pattern of `backtest-review` and `after-market-review`.

**Architecture:** Enhance `run_backtest()` in `cli.py` and `load_yfinance` in `data/__init__.py`. No new modules. Report saving follows the identical pattern to `run_backtest_review()`. All backtests are research-only; no orders are placed.

**Tech Stack:** Python 3, yfinance (already a dep), pandas, existing `Backtester` + `MovingAverageCrossoverStrategy` + `RiskManager` classes.

---

## Roadmap context

The project is at V34B. Phase 4 (strategy validation) calls for a scanner-to-backtest workflow. The `backtest` command exists but only prints results and uses a fixed period string. This plan closes the gap so backtest results can be saved, compared across symbols, and date-scoped.

---

## Task 1: Fix EOD markdown skip-reason section header

**Files:**
- Modify: `src/trading_bot/cli.py` (1 line)

- [ ] **Step 1: Confirm the bug**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_outcome_analytics.py -x -q -k "markdown_includes_scan"
```
Expected: passes (test doesn't cover the zero-count case yet).

- [ ] **Step 2: Write the failing test**

In `tests/test_outcome_analytics.py`, find the `test_after_market_review_markdown_includes_scan_coverage_section` test. Add this new test immediately after it:

```python
def test_eod_markdown_skip_section_hidden_when_all_zero():
    """Skip-reasons section must not appear when all counts are zero."""
    eod = _sample_eod_result()
    # Force all skip counts to 0
    coverage = eod.get("scan_coverage") or {}
    if coverage:
        counts = coverage.get("skip_reason_counts") or {}
        for k in list(counts):
            counts[k] = 0
    md = cli._build_eod_report_markdown("2026-05-21", eod)
    assert "**Skip / not-scored reasons:**" not in md
```

- [ ] **Step 3: Run to confirm it fails**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_outcome_analytics.py -x -q -k "skip_section_hidden"
```
Expected: FAIL — the section header currently appears even when all counts are zero.

- [ ] **Step 4: Fix the condition in cli.py**

Find this block in `_build_eod_report_markdown` (around line 1630):

```python
        has_skip_data = any(int(v or 0) > 0 for v in skip_counts_md.values())
        if has_skip_data or skip_counts_md:
```

Change to:

```python
        has_skip_data = any(int(v or 0) > 0 for v in skip_counts_md.values())
        if has_skip_data:
```

- [ ] **Step 5: Run the test**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_outcome_analytics.py -x -q -k "skip_section_hidden or markdown_includes_scan"
```
Expected: both pass.

- [ ] **Step 6: Run full suite**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```
Expected: same pass count as before (717+).

- [ ] **Step 7: Commit**

```powershell
git add src/trading_bot/cli.py tests/test_outcome_analytics.py
git commit -m "2026-05-21 - Backtest - Fix skip-reason section hidden when all counts zero"
```

---

## Task 2: Add date-range support to load_yfinance

**Files:**
- Modify: `src/trading_bot/data/__init__.py`
- Modify: `tests/test_scanner_smoke.py` (or create `tests/test_backtest_cli.py`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_backtest_cli.py`:

```python
"""Tests for the backtest CLI enhancements (V35)."""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from trading_bot.data import load_yfinance_range


def _make_yf_df(n: int = 100) -> pd.DataFrame:
    """Minimal OHLCV DataFrame mimicking yfinance output."""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = list(range(100, 100 + n))
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [x + 1 for x in closes],
            "Low": [x - 1 for x in closes],
            "Close": closes,
            "Volume": [1_000_000] * n,
        },
        index=dates,
    )


def test_load_yfinance_range_calls_download_with_start_end():
    """load_yfinance_range passes start/end to yf.download, not period."""
    mock_df = _make_yf_df()
    with patch("yfinance.download", return_value=mock_df) as mock_dl:
        result = load_yfinance_range("SPY", start="2024-01-01", end="2024-06-30")
    mock_dl.assert_called_once()
    call_kwargs = mock_dl.call_args[1]
    assert call_kwargs.get("start") == "2024-01-01"
    assert call_kwargs.get("end") == "2024-06-30"
    assert "period" not in call_kwargs or call_kwargs.get("period") is None
    assert "close" in result.columns


def test_load_yfinance_range_raises_on_empty():
    """load_yfinance_range raises ValueError when yfinance returns no data."""
    with patch("yfinance.download", return_value=pd.DataFrame()):
        with pytest.raises(ValueError, match="No data returned"):
            load_yfinance_range("FAKE", start="2020-01-01", end="2020-01-02")


def test_load_yfinance_range_handles_multiindex_columns():
    """load_yfinance_range flattens MultiIndex columns from yfinance."""
    mock_df = _make_yf_df()
    multi_df = mock_df.copy()
    multi_df.columns = pd.MultiIndex.from_tuples(
        [(c, "SPY") for c in mock_df.columns]
    )
    with patch("yfinance.download", return_value=multi_df):
        result = load_yfinance_range("SPY", start="2024-01-01", end="2024-12-31")
    assert "close" in result.columns
    assert not isinstance(result.columns, pd.MultiIndex)
```

- [ ] **Step 2: Run to confirm it fails**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_backtest_cli.py -x -q
```
Expected: FAIL — `load_yfinance_range` does not exist yet.

- [ ] **Step 3: Implement load_yfinance_range**

In `src/trading_bot/data/__init__.py`, add after `load_yfinance`:

```python
def load_yfinance_range(ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Fetch OHLCV bars for a specific date range via yfinance."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is not installed. Run: pip install -r requirements.txt") from exc
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}' (start={start}, end={end}).")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return normalize_ohlcv(df)
```

Also add `"load_yfinance_range"` to the `__all__` list at the bottom of the file.

- [ ] **Step 4: Run tests**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_backtest_cli.py -x -q
```
Expected: all 3 pass.

- [ ] **Step 5: Commit**

```powershell
git add src/trading_bot/data/__init__.py tests/test_backtest_cli.py
git commit -m "2026-05-21 - Backtest - Add load_yfinance_range for date-range data fetching"
```

---

## Task 3: Add CLI args for multi-ticker, date range, and strategy params

**Files:**
- Modify: `src/trading_bot/cli.py` (parser only, ~20 lines)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_backtest_cli.py`:

```python
def test_backtest_parser_accepts_start_end_args():
    """backtest subcommand accepts --start, --end, --fast-window, --slow-window, --starting-cash."""
    from trading_bot import cli
    parser = cli.build_parser()
    args = parser.parse_args([
        "backtest",
        "--ticker", "SPY,QQQ",
        "--start", "2024-01-01",
        "--end", "2024-12-31",
        "--fast-window", "10",
        "--slow-window", "30",
        "--starting-cash", "25000",
        "--save-report",
        "--output-dir", "/tmp/reports",
    ])
    assert args.start == "2024-01-01"
    assert args.end == "2024-12-31"
    assert args.fast_window == 10
    assert args.slow_window == 30
    assert args.starting_cash == 25000.0
    assert args.save_report is True
    assert args.output_dir == "/tmp/reports"
```

- [ ] **Step 2: Run to confirm it fails**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_backtest_cli.py::test_backtest_parser_accepts_start_end_args -x -q
```
Expected: FAIL — `--start` etc. not yet added to the parser.

- [ ] **Step 3: Update the backtest parser in build_parser()**

Find the backtest parser block (lines 110-115) and replace with:

```python
    backtest = subparsers.add_parser("backtest", help="Run a backtest against historical OHLCV data.")
    source = backtest.add_mutually_exclusive_group(required=False)
    source.add_argument("--ticker", default=None,
                        help="Ticker(s) to fetch via yfinance. Comma-separate for multiple, e.g. SPY,QQQ.")
    source.add_argument("--csv", default=None, help="Path to a local OHLCV CSV file (single symbol).")
    backtest.add_argument("--period", default="1y",
                          help="yfinance download period (e.g. 6mo, 1y, 5y). Ignored when --start/--end set.")
    backtest.add_argument("--start", default=None, help="Start date for historical data (YYYY-MM-DD).")
    backtest.add_argument("--end", default=None, help="End date for historical data (YYYY-MM-DD).")
    backtest.add_argument("--fast-window", type=int, default=None,
                          help="Fast MA window. Overrides config value.")
    backtest.add_argument("--slow-window", type=int, default=None,
                          help="Slow MA window. Overrides config value.")
    backtest.add_argument("--starting-cash", type=float, default=None,
                          help="Starting cash for the backtest. Overrides config value.")
    backtest.add_argument("--save-report", action="store_true",
                          help="Save backtest_report.json and backtest_report.md to --output-dir.")
    backtest.add_argument("--output-dir", default="reports",
                          help="Base directory for saved reports (default: reports/).")
    backtest.add_argument("--config", default="configs/default_config.yaml",
                          help="Path to YAML config file.")
```

- [ ] **Step 4: Run the test**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_backtest_cli.py::test_backtest_parser_accepts_start_end_args -x -q
```
Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/trading_bot/cli.py tests/test_backtest_cli.py
git commit -m "2026-05-21 - Backtest - Add --start/--end/--fast-window/--slow-window/--save-report CLI args"
```

---

## Task 4: Implement multi-ticker backtest and report saving in run_backtest()

**Files:**
- Modify: `src/trading_bot/cli.py` (`run_backtest` function, ~80 lines)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_backtest_cli.py`:

```python
def _mock_yf_download(ticker, period=None, start=None, end=None, auto_adjust=True, progress=False):
    """Mock for yfinance.download — returns valid OHLCV data regardless of args."""
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = list(range(100, 100 + n))
    return pd.DataFrame(
        {"Open": closes, "High": [x+1 for x in closes],
         "Low": [x-1 for x in closes], "Close": closes, "Volume": [1_000_000]*n},
        index=dates,
    )


def test_run_backtest_multi_ticker_prints_each_symbol(tmp_path, capsys):
    """run_backtest with two tickers prints a summary for each."""
    from types import SimpleNamespace
    from trading_bot import cli

    args = SimpleNamespace(
        config="configs/default_config.yaml",
        ticker="SPY,QQQ",
        csv=None,
        period="1y",
        start=None,
        end=None,
        fast_window=3,
        slow_window=5,
        starting_cash=10_000.0,
        save_report=False,
        output_dir=str(tmp_path / "reports"),
    )
    with patch("yfinance.download", side_effect=_mock_yf_download):
        result = cli.run_backtest(args)

    out = capsys.readouterr().out
    assert "SPY" in out
    assert "QQQ" in out
    assert "symbols" in result
    assert "SPY" in result["symbols"]
    assert "QQQ" in result["symbols"]


def test_run_backtest_save_report_creates_files(tmp_path):
    """--save-report creates backtest_report.json and backtest_report.md."""
    from types import SimpleNamespace
    from trading_bot import cli
    import json

    args = SimpleNamespace(
        config="configs/default_config.yaml",
        ticker="SPY",
        csv=None,
        period="1y",
        start=None,
        end=None,
        fast_window=3,
        slow_window=5,
        starting_cash=10_000.0,
        save_report=True,
        output_dir=str(tmp_path / "reports"),
    )
    with patch("yfinance.download", side_effect=_mock_yf_download):
        cli.run_backtest(args)

    report_dirs = list((tmp_path / "reports").iterdir())
    assert len(report_dirs) == 1, "Expected one dated subdirectory"
    report_dir = report_dirs[0]
    json_file = report_dir / "backtest_report.json"
    md_file = report_dir / "backtest_report.md"
    assert json_file.exists(), "backtest_report.json not created"
    assert md_file.exists(), "backtest_report.md not created"

    report = json.loads(json_file.read_text())
    assert "symbols" in report
    assert "SPY" in report["symbols"]
    assert report["research_only"] is True


def test_run_backtest_uses_start_end_when_provided(tmp_path):
    """When --start/--end are set, load_yfinance_range is called, not load_yfinance."""
    from types import SimpleNamespace
    from trading_bot import cli

    args = SimpleNamespace(
        config="configs/default_config.yaml",
        ticker="SPY",
        csv=None,
        period="1y",
        start="2023-01-01",
        end="2023-12-31",
        fast_window=3,
        slow_window=5,
        starting_cash=10_000.0,
        save_report=False,
        output_dir=str(tmp_path / "reports"),
    )
    with patch("trading_bot.cli.load_yfinance_range") as mock_range, \
         patch("trading_bot.cli.load_yfinance") as mock_period:
        mock_range.return_value = pd.DataFrame(
            {"open": range(100,200), "high": range(101,201),
             "low": range(99,199), "close": range(100,200), "volume": [1_000_000]*100},
            index=pd.date_range("2023-01-01", periods=100, freq="B"),
        )
        cli.run_backtest(args)

    mock_range.assert_called_once_with("SPY", start="2023-01-01", end="2023-12-31")
    mock_period.assert_not_called()
```

- [ ] **Step 2: Run to confirm they fail**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_backtest_cli.py -x -q -k "multi_ticker or save_report or start_end"
```
Expected: all 3 FAIL.

- [ ] **Step 3: Rewrite run_backtest() in cli.py**

Replace the existing `run_backtest` function (lines 225–256) with:

```python
def run_backtest(args: argparse.Namespace) -> dict[str, Any]:
    """Run a strategy backtest against yfinance historical data. Research only."""
    config = load_config(args.config)

    fast_window = getattr(args, "fast_window", None) or config.strategy.fast_window
    slow_window = getattr(args, "slow_window", None) or config.strategy.slow_window
    starting_cash = float(getattr(args, "starting_cash", None) or config.backtest.starting_cash)

    strategy = MovingAverageCrossoverStrategy(fast_window=fast_window, slow_window=slow_window)
    risk_manager = RiskManager(
        starting_cash=starting_cash,
        max_position_fraction=config.risk.max_position_fraction,
        max_risk_per_trade_fraction=config.risk.max_risk_per_trade_fraction,
        max_drawdown_fraction=config.risk.max_drawdown_fraction,
        allow_shorting=config.risk.allow_shorting,
        allow_margin=config.risk.allow_margin,
        live_trading_enabled=config.risk.live_trading_enabled,
    )
    backtester = Backtester(
        strategy=strategy,
        risk_manager=risk_manager,
        starting_cash=starting_cash,
        fee_per_trade=config.backtest.fee_per_trade,
        slippage_fraction=config.backtest.slippage_fraction,
    )

    backtest_results: dict[str, Any] = {}

    if getattr(args, "csv", None):
        data = load_csv(args.csv)
        result = backtester.run(data)
        print(f"Data rows: {len(data)}")
        result.print_summary()
        backtest_results["CSV"] = result
    else:
        ticker_str = getattr(args, "ticker", None) or "SPY"
        tickers = [t.strip().upper() for t in ticker_str.split(",") if t.strip()]
        start = getattr(args, "start", None)
        end = getattr(args, "end", None)

        for ticker in tickers:
            if start or end:
                data = load_yfinance_range(ticker, start=start, end=end)
            else:
                data = load_yfinance(ticker=ticker, period=args.period)
            result = backtester.run(data)
            print(f"\n--- {ticker} ---")
            print(f"Data rows: {len(data)}")
            result.print_summary()
            backtest_results[ticker] = result

    if getattr(args, "save_report", False):
        _save_backtest_report(backtest_results, args, strategy.name)

    return {
        "symbols": {
            ticker: {
                "starting_cash": r.metrics.starting_cash,
                "ending_equity": r.metrics.ending_equity,
                "total_return_pct": round(r.metrics.total_return_fraction * 100, 2),
                "max_drawdown_pct": round(r.metrics.max_drawdown_fraction * 100, 2),
                "trade_count": r.metrics.trade_count,
                "win_rate_pct": (
                    round(r.metrics.win_rate_fraction * 100, 2)
                    if r.metrics.win_rate_fraction is not None else None
                ),
            }
            for ticker, r in backtest_results.items()
        }
    }
```

- [ ] **Step 4: Add _save_backtest_report and _build_backtest_markdown helpers**

Add these two functions immediately after `run_backtest` (before `run_scan`):

```python
def _save_backtest_report(
    results: dict[str, Any],
    args: argparse.Namespace,
    strategy_name: str,
) -> None:
    """Save backtest results as JSON and markdown. Research only."""
    from datetime import datetime as _dt
    report_date = _dt.now().strftime("%Y-%m-%d")
    output_base = Path(getattr(args, "output_dir", "reports")) / report_date
    output_base.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "report_date": report_date,
        "strategy": strategy_name,
        "research_only": True,
        "not_applied_note": "This is a research simulation. No orders were placed.",
        "symbols": {
            ticker: {
                "starting_cash": r.metrics.starting_cash,
                "ending_equity": r.metrics.ending_equity,
                "total_return_pct": round(r.metrics.total_return_fraction * 100, 2),
                "max_drawdown_pct": round(r.metrics.max_drawdown_fraction * 100, 2),
                "trade_count": r.metrics.trade_count,
                "win_rate_pct": (
                    round(r.metrics.win_rate_fraction * 100, 2)
                    if r.metrics.win_rate_fraction is not None else None
                ),
            }
            for ticker, r in results.items()
        },
    }
    json_path = output_base / "backtest_report.json"
    md_path = output_base / "backtest_report.md"
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_build_backtest_markdown(summary), encoding="utf-8")
    print(f"\nReport saved: {json_path}")
    print(f"Report saved: {md_path}")


def _build_backtest_markdown(summary: dict[str, Any]) -> str:
    """Build human-readable markdown from a backtest summary dict."""
    lines = [
        f"# Backtest Report — {summary['report_date']}",
        "",
        f"_Strategy: {summary['strategy']}_",
        "",
        "_Research only. Simulated returns using historical data. Not evidence of future performance. No orders placed._",
        "",
        "## Results by Symbol",
        "",
        "| Symbol | Return % | Max DD % | Trades | Win Rate % |",
        "|--------|----------|----------|--------|------------|",
    ]
    for ticker, data in summary.get("symbols", {}).items():
        wr = data.get("win_rate_pct")
        lines.append(
            f"| {ticker} | {data['total_return_pct']:.2f}% | "
            f"{data['max_drawdown_pct']:.2f}% | {data['trade_count']} | "
            f"{'—' if wr is None else f'{wr:.1f}%'} |"
        )
    lines += ["", "_End of report._"]
    return "\n".join(lines)
```

- [ ] **Step 5: Add import for load_yfinance_range in cli.py**

Find the existing import line (near the top of cli.py):
```python
from trading_bot.data import load_csv, load_yfinance
```
Change to:
```python
from trading_bot.data import load_csv, load_yfinance, load_yfinance_range
```

- [ ] **Step 6: Run the new tests**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_backtest_cli.py -x -q
```
Expected: all 6 tests pass.

- [ ] **Step 7: Run full suite**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```
Expected: all existing tests still pass.

- [ ] **Step 8: Smoke test the command**

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli backtest --ticker SPY --period 2y --fast-window 20 --slow-window 50
```
Expected: prints a result summary for SPY with return%, drawdown%, trade count.

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli backtest --ticker "SPY,QQQ,IWM" --period 1y --save-report --output-dir reports
```
Expected: prints 3 summaries, creates `reports/YYYY-MM-DD/backtest_report.json` and `.md`.

- [ ] **Step 9: Commit**

```powershell
git add src/trading_bot/cli.py tests/test_backtest_cli.py
git commit -m "2026-05-21 - Backtest - Multi-ticker, date range, strategy params, report saving"
```

---

## Task 5: Update stale documentation

**Files:**
- Modify: `CURRENT_STATUS.md`
- Modify: `FILE_STRUCTURE.md`
- Modify: `AGENT_STATE.md`

- [ ] **Step 1: Update CURRENT_STATUS.md**

At the top of the `## Overall status` section, prepend:

```
**V35** - Backtest CLI enhancements. The `backtest` command now supports multi-ticker runs (`--ticker SPY,QQQ`), date-range data fetching (`--start YYYY-MM-DD --end YYYY-MM-DD`), CLI-configurable strategy params (`--fast-window`, `--slow-window`, `--starting-cash`), and report saving (`--save-report` writes JSON + markdown to `reports/YYYY-MM-DD/`). Research only. No orders placed.

**V34B** - Code review bug fixes. Fixed backward-compat fold double-count in `_build_scan_coverage_summary`, removed `no_eligible_setup` from `skip_reason_counts` (it is now tracked separately as `no_eligible_setup_count` in the scan summary), wrapped `render_agent_insights()` in `try/except`, and fixed EOD markdown skip-reason header showing when all counts are zero.
```

- [ ] **Step 2: Update FILE_STRUCTURE.md**

Add the missing test files to the `tests/` section:

```
    test_dashboard_theme.py
    test_outcome_analytics.py
    test_v15_8_active_tracking.py
    test_v15_entry_triggers.py
    test_v27a_regression.py
    test_v31_rotation_diagnostics.py
    test_symbol_quarantine.py
    test_v14_5_intraday_provider.py
    test_backtest_cli.py               (V35) multi-ticker backtest CLI tests
```

Also add to `docs/superpowers/plans/` directory entry.

- [ ] **Step 3: Update AGENT_STATE.md**

Add a V35 handoff block at the top (after the last-updated line) following the existing format:

```markdown
## V35 handoff - Backtest CLI Enhancements

### Current active task

V35 is complete. The `backtest` command now supports multi-ticker runs, date ranges, CLI strategy params, and report saving.

### Changes

- **`src/trading_bot/cli.py`**
  - `run_backtest()`: rewrote to support multi-ticker (`--ticker SPY,QQQ`), `--start`/`--end` date range, `--fast-window`/`--slow-window`/`--starting-cash` overrides, and `--save-report` flag.
  - Added `_save_backtest_report()` and `_build_backtest_markdown()` helpers.
  - Updated import: added `load_yfinance_range`.
  - Fixed `_build_eod_report_markdown`: skip-reason section header no longer renders when all counts are zero.

- **`src/trading_bot/data/__init__.py`**
  - Added `load_yfinance_range(ticker, start, end)` — fetches bars for a specific date range.

- **`tests/test_backtest_cli.py`** (new)
  - 6 tests covering: date-range fetch, multi-ticker, report file creation, start/end routing.

- **`tests/test_outcome_analytics.py`**
  - Added `test_eod_markdown_skip_section_hidden_when_all_zero`.

### Files changed

- `src/trading_bot/cli.py`
- `src/trading_bot/data/__init__.py`
- `tests/test_backtest_cli.py` (new)
- `tests/test_outcome_analytics.py`
- `CURRENT_STATUS.md`
- `FILE_STRUCTURE.md`
- `AGENT_STATE.md`

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → **NNN passed**

### Safety

No scoring changes. No trigger-rule changes. No trading/paper/broker/orders. The `backtest` command remains research-only. All reports carry `research_only: True` and a `not_applied_note`.
```

- [ ] **Step 4: Commit**

```powershell
git add CURRENT_STATUS.md FILE_STRUCTURE.md AGENT_STATE.md
git commit -m "2026-05-21 - Docs - Update CURRENT_STATUS, FILE_STRUCTURE, AGENT_STATE to V35"
```

---

## Self-review checklist

- [x] **Spec coverage:** All roadmap Phase 4 items addressed by this plan: multi-ticker backtest, date-range data, report saving
- [x] **Placeholder scan:** No TBDs. Every step has exact code or commands
- [x] **Type consistency:** `load_yfinance_range` defined in Task 2, imported in Task 4. `_save_backtest_report` takes `dict[str, Any]` where values are `BacktestResult` objects — matches Task 4 usage
- [x] **Test isolation:** All tests use `unittest.mock.patch` for yfinance, no real network calls
- [x] **Safety:** Every report output includes `research_only: True` and `not_applied_note`
- [x] **Backward compat:** Existing `--ticker SPY` (single ticker) + `--csv` + `--period` all still work
