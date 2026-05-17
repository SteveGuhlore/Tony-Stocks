# Profitability Research Plan

_Last updated: 2026-05-17_

This file exists because the user wants the bot to eventually become profitable. The right way to pursue that is not to ask an AI to “make profitable trades.” The right way is to build a research pipeline that can reject weak strategies quickly and preserve capital.

## What profitable requires

A trading strategy needs more than a good chart. It needs:

- a clear hypothesis,
- enough historical trades,
- realistic transaction costs,
- out-of-sample testing,
- drawdown control,
- paper trading validation,
- live monitoring,
- ability to stop when market regime changes.

## Research workflow

For every strategy idea:

1. Write the hypothesis.
2. Define entry and exit rules.
3. Define risk rules.
4. Backtest on multiple tickers.
5. Compare to buy-and-hold.
6. Test out-of-sample.
7. Paper trade.
8. Review performance.
9. Reject, revise, or promote.

## Promotion gates

A strategy can move from backtest to paper trading only if:

- tests pass,
- drawdown is acceptable,
- trade count is meaningful,
- rules are explainable,
- results are not from one lucky ticker/date range.

A strategy can move from paper to live only if:

- it survives a meaningful paper period,
- execution is stable,
- risk manager blocks bad orders,
- user explicitly approves tiny-size testing.

## Red flags

Reject strategies that:

- rely on one perfect parameter value,
- only work on one stock,
- have huge drawdowns,
- have too few trades,
- ignore fees and slippage,
- use future data by accident,
- cannot be explained.

