# Data Sources Guide

_Last updated: 2026-05-17_

## Supported starter data flow

The project starts with two data paths:

1. `yfinance` download for quick testing.
2. CSV loading for controlled repeatable tests.

## Required OHLCV columns

CSV data should include:

```text
date, open, high, low, close, volume
```

Column names are normalized to lowercase by the data loader.

## Data quality checks

Before backtesting, check:

- missing dates,
- missing close prices,
- duplicated rows,
- split/dividend adjustments,
- timezone consistency,
- unrealistic prices,
- low volume periods.

## Future data providers

Possible later additions:

- Alpaca historical bars.
- Polygon.io.
- Interactive Brokers.
- Tiingo.
- Nasdaq Data Link.

Do not add paid providers until the base system is stable.

