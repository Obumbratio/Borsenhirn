# Privacy Policy — Börsenhirn

**Effective date:** 2026-04-24

This Privacy Policy describes what data Börsenhirn collects, how it is
used, where it is stored, and what rights you have.

This policy applies to:

- The **self-hosted** version of the Software (you run it on your own
  machine). In this case, **you are the data controller** and most of
  this document describes what the Software itself handles locally.
- Any **hosted service** offered by the author in the future. When
  that service launches, this policy will describe the author's role
  as data processor / controller.

---

## 1. Data we collect

### When you run Börsenhirn locally

The Software stores the following on **your machine** (typically in
PostgreSQL + local files):

- **Trade records**: timestamps, symbols, prices, quantities,
  side (buy/sell), reasons, realized and unrealized PnL, fills.
- **Portfolio snapshots**: equity curves, daily PnL, position sizes.
- **Market data**: historical bars downloaded from Alpaca / yfinance /
  etc., cached locally.
- **AI conversation history**: prompts and responses exchanged with
  Anthropic's Claude API (for the "Hirn" assistant).
- **ML model artifacts**: `.pkl` files with serialized RandomForest /
  scaler.
- **Logs**: application logs in `logs/`, rotated nightly, retained 30
  days by default.
- **Kill switch state and alerts log**: in Postgres tables
  `killswitch_state` and `alerts_log`.

### When we interact with third-party services

When you use Börsenhirn, data may be sent to:

| Service | What is sent | Purpose |
|---|---|---|
| **Alpaca** | API key, order details (symbol, qty, side) | Trade execution |
| **Anthropic (Claude API)** | Conversation history, portfolio context | AI assistant |
| **Finnhub / Alpha Vantage / Polygon** | Symbols, API key | Market data |
| **FRED** | Macro series IDs, API key | Macro data |
| **NewsAPI / yfinance** | Ticker symbols | News, fallback data |
| **Discord (webhook)** | Alert messages with metadata | Notifications |
| **SMTP provider (Gmail, etc.)** | Alert messages | Email notifications |

Each of these providers has its own privacy policy and data practices.
The author has no control over what they do with data once it leaves
your machine.

### When we offer a hosted service (future)

If and when the author offers a hosted / paid version, we will collect:

- **Account information**: email, password hash, billing metadata
  (via Stripe — we never see your card).
- **Subscription / payment history**: via Stripe.
- **Usage telemetry**: feature usage, error rates, latencies (aggregated).
- **Your broker API keys**: stored **encrypted at rest** with
  `cryptography.fernet` and a master key held in a secrets manager
  separate from the database.

We will **not** sell personal data. We will not train AI models on
your conversation data beyond what Anthropic's own enterprise
controls allow.

## 2. Why we collect it

- To operate the Software (execute trades you authorize).
- To persist state across restarts (kill switches, memory of the AI
  assistant, entry prices).
- To generate reports, dashboards, and analytics that you requested.
- To debug and improve the Software (for the hosted version, with
  your consent).
- To comply with legal and tax obligations (hosted version only).

## 3. How long we keep it

### Local / self-hosted

You control retention. Delete the Postgres database or the
`logs/` directory to wipe local state.

Defaults:

- Logs: rotated nightly, 30 days retention.
- Trade records: indefinite unless you delete them.
- AI conversations (Hirn memory): indefinite unless you clear.

### Hosted (future)

- Account data: while your account is active, plus 90 days after
  deletion for tax/dispute purposes.
- Trade records: as above.
- Payment records: 7 years (regulatory requirement in most
  jurisdictions).
- Aggregated telemetry: indefinite, but anonymized.

## 4. Who we share it with

The author **does not sell** your data to third parties.

Data is shared only with:

- **Service providers** (Alpaca, Anthropic, Stripe, etc.) strictly as
  necessary to deliver the functionality you requested.
- **Law enforcement** when legally required and within the minimum
  scope of the request.
- **Successors** in case of a sale or acquisition of the business,
  subject to notice and your right to opt out.

## 5. Security

### Local

Your local security is your responsibility. Recommendations:

- Do not commit `.env` to git (the `.gitignore` excludes it).
- Use strong Postgres passwords.
- Rotate API keys quarterly.
- Rotate Discord webhooks if you ever paste them in any shared
  context (chat, issue tracker, AI prompt).

### Hosted (future)

- All credentials encrypted at rest (AES-256 via Fernet).
- TLS 1.3 on all endpoints.
- Postgres Row-Level Security enforced for multi-tenant isolation.
- Rate limiting and audit logs.
- Incident disclosure within 72 hours of confirmed breach.

## 6. Your rights

Depending on your jurisdiction, you may have the right to:

- **Access** the personal data we hold about you.
- **Correct** inaccurate data.
- **Delete** your data ("right to be forgotten").
- **Port** your data to another service.
- **Object to** or **restrict** certain processing.
- **Withdraw consent** at any time.
- **Lodge a complaint** with your data protection authority.

To exercise these rights on the hosted service, contact the author.
On the self-hosted version, you have full control over your own data.

## 7. Children

Börsenhirn is not directed at children under 18. We do not knowingly
collect data from minors. If you believe a child has provided us with
personal data, contact the author to request deletion.

## 8. International transfers

If and when a hosted service is launched, data may be stored and
processed in countries other than yours. We will implement standard
contractual clauses or equivalent safeguards as required by
applicable law (GDPR, LGPD, etc.).

## 9. Changes

The author may update this Policy from time to time. Material changes
will be communicated via the repository, the dashboard, or email (for
hosted users).

## 10. Contact

For privacy questions or requests: open an issue in the repository
or contact the author directly.

---

**PLACEHOLDER — this is a standard-practices template. Before
commercial launch, have it reviewed against GDPR, CCPA, Colombia's
Ley 1581 de 2012 and any jurisdiction-specific requirements.**
