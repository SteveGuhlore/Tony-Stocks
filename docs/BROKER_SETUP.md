# Broker Setup Guide

_Last updated: 2026-05-17_

This project should start with paper trading only.

## Recommended starting brokers

Start with one paper-trading broker. Do not integrate multiple brokers at once.

Good first options:

- Alpaca paper trading.
- Interactive Brokers paper account.

## API key rules

Never put keys directly in code.

Use `.env` or environment variables:

```env
BROKER_MODE=paper
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets
```

The `.env` file must stay ignored by git.

## Broker adapter design

The bot should use an adapter pattern:

```text
Strategy signal
→ RiskManager approval
→ Broker adapter
→ Paper or live execution later
```

Current package includes a paper/mock execution layer only. Live execution should be added later after tests and paper trading are stable.

## Live trading gate

Live trading must remain off until:

- backtests work,
- paper trading works,
- risk manager tests pass,
- order logs are saved,
- emergency stop is implemented,
- user explicitly approves.

