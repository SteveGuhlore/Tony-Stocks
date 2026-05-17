# Trading Bot Project — Project Context

_Last updated: 2026-05-17_

## 1. Project identity

This is a Python-based stock-market trading bot project. The user wants to eventually build a bot that can research market conditions, generate strategy signals, and potentially place trades on the user’s behalf.

The current project stage is **infrastructure first**. The goal is to create a clean local project that can support AI-assisted coding with Codex, Claude, and Cursor while preventing messy agent handoffs.

## 2. Core goal

Build a safe and extensible trading research system that can eventually become a paper-trading bot, then only much later a carefully controlled live-trading bot.

The system should support:

- Historical data loading.
- Strategy research.
- Backtesting.
- Risk management.
- Metrics/reporting.
- Paper trading.
- Broker integration.
- AI-assisted code workflow.
- Agent handoffs when usage limits require switching tools.

## 3. Important scope correction

The goal is not to immediately create a “profitable autonomous trader.” That is too risky and unrealistic as a first build.

Correct first version:

```text
Research dashboard + backtesting engine + paper trader
```

Later version:

```text
Small-size live trader with kill switch and strict risk rules
```

## 4. AI-agent workflow

The user will rotate between Codex, Claude, and Cursor based on usage limits.

Therefore:

- Any agent may code.
- Any agent may plan.
- Any agent may review.
- Every agent must read the same docs first.
- Every agent must update `AGENT_STATE.md` before handoff.
- No agent should assume it has private context from another agent.

## 5. Trading safety philosophy

This project must prioritize:

1. Capital preservation.
2. Explainability.
3. Reproducible testing.
4. Paper trading before live trading.
5. Small, reversible steps.
6. Clear logs and auditability.

No agent should promise profitability.

## 6. First technical direction

Start with simple, explainable strategies:

- Moving average crossover.
- RSI filter.
- Volatility filter.
- Fixed fractional position sizing.
- Maximum drawdown guard.

Avoid starting with:

- Options trading.
- High-frequency trading.
- Short selling.
- Margin.
- Reinforcement learning.
- News-only trading.
- Black-box deep learning.

## 7. Long-term direction

The long-term system can eventually include:

- Multiple strategies.
- Multiple assets.
- Portfolio-level risk management.
- Broker paper trading.
- Live trading with small size.
- News/sentiment modules.
- Research reports.
- Performance dashboard.
- Scheduled scans.
- Watchlist scoring.

But these should be added only after the base engine is reliable.

