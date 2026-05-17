## Strategy Design Guidelines

This document explains how to design, test and evaluate trading strategies for a stock‑trading bot.  The goal is not to prescribe a single “best” strategy—markets evolve and no strategy works forever—but to provide a framework you can adapt and refine.  Combine these guidelines with the regulatory and risk‑management principles described in `legal_and_risk.md`.

### 1. Select your strategy type

Trading strategies generally fall into a few broad categories.  Choosing a type helps narrow the indicators and logic you will use:

| Strategy type | Description | Typical indicators |
| --- | --- | --- |
| **Trend following** | Seeks to ride established trends and avoid whipsaws.  The bot opens long positions when the market is in an up‑trend and exits or goes short when the trend turns. | Moving averages (simple/EMA), MACD, Directional Movement Index (DMI), ADX |
| **Mean reversion** | Assumes that prices oscillate around a fair value and will revert after extreme moves.  Trades are opened against short‑term extremes. | Relative Strength Index (RSI), Bollinger Bands, Keltner Channels |
| **Breakout** | Looks for price breaking out of a consolidation range or key support/resistance level.  Entry signals occur when price moves beyond recent highs/lows. | Donchian Channels, Bollinger Band squeeze, Volume breakouts |
| **News/sentiment based** | Uses natural‑language processing to gauge market sentiment from news and social media. | Sentiment scores, word‑count signals |

You can also combine types (e.g., a trend strategy with a volatility filter) to reduce false signals【962155084126409†L193-L200】.  ChatGPT or Claude can help brainstorm ideas, but always validate them through testing and research.

### 2. Define entry and exit rules

After choosing a strategy type, formalise the conditions for entering and exiting trades.  Use clear, rule‑based signals so your bot’s behaviour is deterministic.  For example, a moving‑average crossover strategy might look like this【962155084126409†L185-L196】:

* **Entry:** Buy when the 50‑period simple moving average (SMA) crosses above the 100‑period SMA.
* **Exit:** Sell when the 100‑period SMA crosses back above the 50‑period SMA.
* **Stop‑loss:** Place a stop 2 % below the entry price【962155084126409†L211-L216】.

Another example uses the RSI with Bollinger Bands【962155084126409†L193-L201】:

* **Buy signal:** RSI < 30 *and* the Bollinger Bands percentage is below 0 (price near the lower band).
* **Sell signal:** RSI > 70 *and* the Bollinger Bands percentage is above 100 (price near the upper band).
* **Risk level:** Moderate, because the strategy enters against oversold/overbought conditions.

Combining multiple indicators helps reduce false signals【962155084126409†L193-L201】.  However, avoid over‑complicating your rules—each additional indicator should add demonstrable value.

### 3. Incorporate risk controls

Risk management is integral to strategy design.  Even profitable strategies can blow up without proper controls.  Implement these parameters in your code【962155084126409†L211-L223】:

* **Position sizing:** Allocate only 1–2 % of your total capital to each trade【962155084126409†L211-L213】.
* **Individual stop‑loss:** Set a stop 2–5 % below your entry price【962155084126409†L211-L216】.
* **Portfolio stop‑loss (drawdown cap):** Halt trading if your portfolio falls more than 15 % from its peak【962155084126409†L211-L216】.
* **Trailing stops:** Adjust stop levels as price moves in your favour【962155084126409†L216-L217】.
* **Volatility filters:** Pause trading during extreme conditions—when the VIX index spikes or when price moves exceed two standard deviations【962155084126409†L217-L223】.

These controls should be coded directly into your strategy class to ensure consistent execution.

### 4. Test before you trade

Robust testing separates viable strategies from curve‑fit fantasies.  Follow these steps when evaluating your strategy:

1. **Collect and clean data:** Gather historical price data at relevant timeframes (minute, hourly, daily) and adjust for splits/dividends.  A free API like Alpaca or Yahoo Finance can be used for research; ensure you have permission to use the data.
2. **Split into training and testing:** Use roughly 70 % of the data for development and reserve 30 % for out‑of‑sample validation【962155084126409†L304-L309】.  This helps detect overfitting.
3. **Back‑test:** Simulate each trade according to your rules, accounting for commissions and slippage.  Tools like backtrader, zipline‑reloaded or QuantConnect are well suited (see `frameworks.md`).
4. **Evaluate metrics:** Focus on risk‑adjusted measures such as the Sharpe ratio (target > 1.0), maximum drawdown (keep < 10 %), win rate (> 50 %), and profit factor【962155084126409†L349-L361】.  Avoid optimising solely for returns.
5. **Perform sensitivity analysis:** Vary parameters (e.g., moving‑average periods) and check whether performance remains stable.  If small changes lead to large differences, your strategy may be overfitted.
6. **Walk‑forward analysis:** Re‑train and test your strategy on rolling windows to mimic a real deployment.
7. **Paper trade:** Before risking real capital, run the bot in a paper‑trading environment to verify that it executes orders as expected.

### 5. Implement in code

Use a modular design.  Create a class that maintains internal state (positions, capital, indicators) and has methods to handle each new data point.  See `src/strategy_template.py` for a skeleton implementation.  When coding:

* Compute indicators incrementally to improve performance.
* Separate signal generation from execution logic so that risk management can override signals (e.g., to stop trading during high volatility).
* Log every decision for debugging and auditing.

### 6. Monitor and refine

Markets change.  Continuously monitor your bot’s performance and compare it to back‑test expectations.  Investigate deviations—are they due to market regime shifts, bugs, or unrealistic back‑test assumptions?  Periodically retrain or update your strategy.  Consider adding additional signals or filters if performance deteriorates, but avoid “data snooping”—the more you tweak, the higher the risk of overfitting.

### 7. Common pitfalls

Be mindful of these frequent mistakes:

* **Overfitting:** Too many parameters or signals may produce impressive back‑tests that fail in live trading.
* **Ignoring transaction costs:** Commissions, slippage and bid/ask spreads can erode profitability—always include them in your simulations.
* **Survivorship bias:** Ensure your historical dataset includes delisted stocks; otherwise you may underestimate risk.
* **Data leakage:** Avoid using future information when calculating indicators or signals, even inadvertently.
* **Lack of risk management:** Never disable stops or position sizing to chase returns.  Robust risk controls are non‑negotiable【962155084126409†L211-L223】.

By following these guidelines and combining them with insights from AI tools and human judgement, you can develop systematic strategies that are both grounded in evidence and adaptable to changing market conditions.