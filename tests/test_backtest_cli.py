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
