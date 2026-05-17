# Trading Bot Project — Architecture Rules

_Last updated: 2026-05-17_

## 1. Main architecture principle

Build clean, modular foundations without overengineering.

The project should be easy for rotating AI agents to understand. Prefer small modules with clear responsibilities over large files that do everything.

## 2. Module responsibilities

Recommended modules:

```text
src/trading_bot/data.py              data loading
src/trading_bot/indicators.py        technical indicators
src/trading_bot/risk.py              risk management
src/trading_bot/backtester.py        backtest engine
src/trading_bot/metrics.py           performance metrics
src/trading_bot/strategies/          strategy classes
src/trading_bot/execution/           paper/live broker adapters later
```

## 3. Strategy rule

A strategy should generate signals. It should not directly place real trades.

Correct flow:

```text
Data -> Strategy signal -> RiskManager approval -> Execution/PaperBroker -> Logs/Metrics
```

## 4. Risk manager rule

Risk rules must be centralized. Do not let every strategy invent its own separate position sizing or drawdown rules.

The strategy can suggest a trade. The risk manager decides whether it is allowed.

## 5. Broker abstraction rule

Do not hard-code a single broker throughout the app.

Use an adapter pattern:

```text
PaperBroker
AlpacaBroker later
InteractiveBrokersBroker later
```

## 6. Configuration rule

Do not hard-code API keys, secret keys, or account IDs.

Use:

- environment variables,
- `.env` files ignored by git,
- config files with safe defaults.

## 7. AI-agent readability rule

Because multiple agents will rotate in and out, keep files readable:

- descriptive names,
- docstrings,
- type hints,
- clear comments where logic is non-obvious,
- small functions.

## 8. Testing rule

Every new core module should have tests. At minimum:

- indicators,
- risk manager,
- backtester,
- strategy signal generation,
- broker paper execution.

