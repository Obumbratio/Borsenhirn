# Important Disclaimer — Börsenhirn

**Read this before using Börsenhirn in any form.**

---

## Not financial advice

Börsenhirn is an **educational and research tool** for algorithmic trading
experimentation. Anything it produces — signals, scores, probabilities,
backtests, "buy" or "sell" indicators, AI-generated commentary, regime
labels, risk scores, or portfolio statistics — is **not**:

- Investment advice.
- A recommendation to buy, sell, hold, or short any security.
- A solicitation to engage in any trading strategy.
- A guarantee of past or future performance.
- A representation that any outcome is likely, safe, or profitable.

No person operating Börsenhirn, contributing to its code, or authoring
its documentation is acting as a **registered investment advisor**,
**broker-dealer**, **financial planner**, or fiduciary of any kind.
No advisory relationship is created by using this software.

## You are 100% responsible for your trades

Every order placed — whether by the automated bot, by you manually, or
triggered by any signal — is **your decision and your risk alone**. You
are responsible for:

- Understanding the instruments you trade.
- Setting your own position sizing, stop-losses, and risk limits.
- Complying with your local laws, tax obligations, and broker terms.
- Monitoring the bot's behavior; software can fail silently.

## Losses are expected and permanent

Trading equities, options, ETFs, cryptocurrencies, or any financial
instrument carries **substantial risk of loss**. Losses can exceed
deposited capital when leverage or short positions are involved. **Past
performance — including any backtest, paper trading result, or metric
shown by this software — does not predict future returns.**

In particular, the author has observed via walk-forward purged
cross-validation (see `PLAN_VALIDACION_ML.md` in this repository) that
the machine learning component of Börsenhirn has **AUC ≈ 0.50** on
out-of-sample data — meaning it performs near chance. The software
should not be interpreted as having proven predictive power.

## No warranty

Börsenhirn is provided **"as is"**, without warranty of any kind,
express or implied, including but not limited to warranties of
merchantability, fitness for a particular purpose, and
non-infringement. The author is not liable for any damages —
direct, indirect, incidental, consequential, or punitive — arising
out of the use of this software, including loss of capital.

## Regulatory considerations

- **United States**: This software is not registered with the SEC or
  FINRA. It is not a registered investment adviser. It is not
  available to US persons as a paid advisory service.
- **Colombia**: No está registrado ante la Superintendencia Financiera
  de Colombia. No constituye asesoría ni comercialización de
  productos financieros.
- **European Union**: Not compliant with MiFID II. Not offered as a
  regulated service.

If you are a resident of a jurisdiction that regulates algorithmic
trading advisors, **use this software only for personal
experimentation with your own capital**, not on behalf of others.

## Third-party services

Börsenhirn integrates with third-party APIs (Alpaca, Anthropic Claude,
Finnhub, Alpha Vantage, FRED, Polygon, NewsAPI, yfinance). Each
provider has its own Terms of Service and data licenses. The author
makes no representation that the data these providers return is
accurate, complete, or timely. Broker executions may differ from
modeled prices due to slippage, partial fills, or outages.

## AI-generated content

The "Hirn" assistant (M5) uses Anthropic's Claude API to generate
natural-language responses grounded in your portfolio state. These
outputs are **probabilistic generations**, not facts. They may contain
errors, hallucinations, or outdated information. Always verify before
acting on any statement produced by the assistant.

## Summary

- Educational tool, not advice.
- You own every trade.
- Expect losses. Past results ≠ future results.
- No warranty. No liability.
- Consult a licensed professional before investing real money.

---

**Last updated:** 2026-04-24.
By using Börsenhirn you confirm that you have read, understood, and
accept this disclaimer in full.
