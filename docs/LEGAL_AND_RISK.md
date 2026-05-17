## Regulatory Compliance and Risk Management

Automated trading is legal in the United States and most global markets, but it is subject to strict regulation.  Failure to comply with these rules can result in fines, account suspension or worse.  This document summarises key legal considerations and risk‑management practices for developing your trading bot.

### 1. Regulatory requirements

* **Use regulated brokers** – In the U.S., the Securities and Exchange Commission (SEC) and the Commodity Futures Trading Commission (CFTC) require that execution platforms be registered as broker‑dealers【135332277457099†L61-L66】.  Choose reputable brokers such as Interactive Brokers, Tradier or Alpaca, all of which offer paper‑trading accounts.

* **Avoid manipulative practices** – Bots must follow the same market‑manipulation rules as human traders.  Practices such as spoofing (placing fake orders to move price) or pump‑and‑dump schemes are illegal.  Ensure your strategy uses transparent, rule‑based signals and does not attempt to deceive other participants【135332277457099†L52-L86】.

* **Disclose risk and performance** – If you provide trading signals or operate the bot on behalf of others, the SEC and FINRA require you to disclose risks, performance data and fees【135332277457099†L61-L82】.  This repository assumes the bot is for personal research; consult a legal professional if you plan to commercialise it.

* **Start with small sizes** – Regulators encourage traders to test strategies with small position sizes before scaling up【135332277457099†L115-L127】.  Begin with paper‑trading to validate performance and compliance.

* **International considerations** – If you trade outside the U.S., local regulators (e.g., SEBI in India, FCA in the UK) may require your algorithm to be registered or routed through approved systems.  Ensure you understand your jurisdiction’s rules before live trading.

* **AI‑specific regulation is emerging** – Regulators are scrutinising the use of artificial intelligence in trading.  In 2024 the U.S. Securities and Exchange Commission (SEC) proposed rules requiring broker‑dealers and investment advisers to identify and neutralise conflicts of interest when using predictive analytics and AI【355451351094748†L430-L457】.  FINRA’s 2025 guidance obliges member firms to keep records of AI model development, testing and performance【355451351094748†L460-L466】.  The EU’s AI Act classifies financial AI systems as “high risk” and mandates transparency, human oversight and documentation of training data【355451351094748†L476-L499】.  Because final rules have not yet been adopted (as of May 2026), the compliance landscape remains uncertain【355451351094748†L430-L457】.  Traders should favour platforms that proactively invest in regulatory compliance and be prepared for additional record‑keeping and explainability requirements.

### 2. Risk management best practices

Risk management is central to sustainable trading.  Even strategies with positive expectancy can suffer catastrophic losses without proper controls.  Incorporate the following practices into your bot:

* **Position sizing:** Limit each trade to **1 – 2 % of your total capital**【962155084126409†L211-L213】.  Use dynamic sizing based on volatility or risk‑reward ratio where appropriate.

* **Stop‑losses:** Set individual stop‑loss orders 2–5 % below the entry price and implement a **maximum portfolio drawdown of ~15 %**【962155084126409†L211-L216】.  Use trailing stops to adjust stop levels as prices move in your favour【962155084126409†L216-L218】.

* **Volatility filters:** Temporarily pause trading during extreme market conditions—for example, when the VIX index exceeds a predefined threshold or when price moves exceed two standard deviations【962155084126409†L217-L223】.  This reduces exposure to sudden price swings.

* **Diversification:** Avoid concentrating all capital in a single strategy or asset.  Diversify across sectors, timeframes and strategy types (trend following, mean reversion, etc.).

* **Back‑testing discipline:** Split your historical data into training and testing sets.  Allocate roughly **30 % of data for out‑of‑sample validation** and account for transaction costs and slippage in your simulation【962155084126409†L304-L309】.  Use Monte Carlo or walk‑forward testing to estimate worst‑case outcomes.

* **Regular monitoring:** Bots are not set‑and‑forget.  Monitor performance metrics (Sharpe ratio, drawdown, win rate) and disable the bot if it deviates significantly from expectations.  Ensure that order submissions, cancellations and fills function properly.

* **Secure your keys:** Store API keys in environment variables or encrypted secret managers.  Do not commit secrets to version control.  Rotate keys periodically and use IP whitelisting where supported.

### 3. The limits of AI assistance

Large‑language‑model tools like ChatGPT, Codex and Claude are powerful, but they are not infallible.  They may hallucinate code, overlook edge cases or misinterpret regulatory nuances.  Always treat AI‑generated content as a starting point and review it critically.  Combine AI assistance with your own expertise, robust testing and professional advice.