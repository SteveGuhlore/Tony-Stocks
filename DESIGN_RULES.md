# Trading Bot Project — Design Rules

_Last updated: 2026-05-17_

## 1. Main design philosophy

The project goal is not to gamble with automation. The goal is to build a structured research and trading system that can test ideas safely.

## 2. Explainable first

Start with strategies that can be explained in plain English:

- Moving average crossover.
- RSI filter.
- Trend-following filter.
- Volatility filter.
- Mean reversion with clear entry/exit rules.

Do not start with black-box machine learning.

## 3. Backtest before paper trade

A strategy must pass a backtest before it is allowed into paper trading.

A backtest should include:

- trade count,
- total return,
- max drawdown,
- win rate,
- comparison to buy-and-hold,
- date range,
- data source.

## 4. Paper trade before live trade

A strategy must run in paper trading before any live trading is considered.

Paper trading should verify:

- order sizing,
- order timing,
- logs,
- risk guard behavior,
- no duplicate orders,
- broker API stability.

## 5. Risk is a feature

Risk controls are part of the product, not optional add-ons.

Default risk controls should include:

- maximum percent of capital per trade,
- maximum portfolio drawdown,
- stop loss,
- no margin by default,
- no shorting by default,
- emergency stop.

## 6. Profitability research rule

Do not judge a strategy by one good backtest.

Require:

- multiple tickers,
- multiple market regimes,
- out-of-sample testing,
- realistic slippage/fees,
- enough trades to be meaningful.

## 7. Avoid overfitting

Red flags:

- too many parameters,
- perfect historical results,
- only works on one ticker,
- only works in one date range,
- requires exact settings to work.

## 8. Rotating-agent design rule

Since different AI tools will touch the code, avoid clever code that is hard to maintain. Prefer boring, readable, testable code.

