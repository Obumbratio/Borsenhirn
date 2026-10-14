# Börsenhirn — Financial Intelligence & Algorithmic Trading Platform

[![CI](https://github.com/Obumbratio/proyecto_trading/actions/workflows/ci.yml/badge.svg)](https://github.com/Obumbratio/proyecto_trading/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.14%20(target)%20%7C%203.12%20(docker)-blue.svg)](.python-version)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%7C%2018%20(RLS)-336791.svg)](borsenhirn/tenancy/)
[![Next.js](https://img.shields.io/badge/frontend-Next.js%2014-black.svg)](frontend/)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A560%25%20(CI%20gate)-brightgreen)](.github/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-414%2B%20passed-brightgreen)](tests/)
[![Status](https://img.shields.io/badge/maturity-75%25%20complete-orange)](#-completion-status)
[![License](https://img.shields.io/badge/license-proprietary%20(research%20use)-lightgrey)](legal/TERMS.md)

> **⚠ EDUCATIONAL TOOL — NOT FINANCIAL ADVICE.** Any "signal", "score", or suggestion
> produced by this software is strictly for personal research. Past performance (backtesting
> or paper trading) **does not predict** future returns. You trade with your own capital at your
> own risk. Read the [full DISCLAIMER](legal/DISCLAIMER.md) before using this platform.

---

Börsenhirn is a multi-tenant financial intelligence and self-directed algorithmic trading SaaS platform (**Model A — BYO Alpaca Broker**). The system combines an autonomous paper-trading execution engine with a secure web application where self-directed investors execute their own trading decisions using credentials encrypted at rest, backed by institutional-grade security infrastructure (Postgres RLS, Fernet Vault) and rigorous quantitative ML validation (López de Prado).

Built as a portfolio project for **Data Engineer / ML Engineer / MLOps** roles — the emphasis is on **production infrastructure, data defensibility, and security**, rather than claiming a model magically predicts the market.

---

## 📊 Completion Status

The project currently stands at **75% overall completion**. The backend, execution engine, ML validation, multi-tenancy, and safety stack are **institutional-grade** and validated by over **414 automated tests**. Advanced analytical frontend surfaces are currently in the prototyping/mockup phase.

Detailed audit available in the reference document: [`STATUS.md`](STATUS.md).

| Area | Score | Notes |
|---|:---:|---|
| **Core Logic** | **82%** | Robust engine, safety stack, RLS multi-tenancy (security, vault, ML validation all ✅). Docked for M1/M2/M4/M5 not yet connected to the API. |
| **UI / Frontend (Next.js 14)** | **64%** | Core flow works (BYO broker, signals, news, calculator, order dialog, positions). 3 major views are hardcoded mockups. |
| **Tests & Validation** | **86%** | 414+ Python tests, 8 Vitest tests, Hypothesis invariants. Streamlit dashboard tests excluded from CI. |
| **Documentation** | **88%** | Extensive production plans, ML diagnostics, and runbooks. Minor version discrepancies. |
| **Deployment / Config** | **55%** | Local Postgres + CI work. Next.js not in Docker, version mismatches, hardcoded dev passwords. |
| **Overall** | **75%** | **Production-grade backend; frontend intelligence views and deployment config in progress.** |

---

## 🧠 Architecture: "Un cerebro, dos caras" (One Brain, Two Faces)

To guarantee regulatory and technical separation, the system decouples signal generation from order execution:

```
                                ┌───────────────────────────────────────┐
                                │             MARKET DATA               │
                                │   Alpaca API · FRED · EDGAR · News    │
                                └──────────────────┬────────────────────┘
                                                   │
                                                   ▼
                                ┌───────────────────────────────────────┐
                                │      SignalEngine (Shared Brain)      │
                                │  4-state regime · Dynamic VIX bands   │
                                │  44-symbol scanner · RSI/MACD/BB      │
                                │  Neutral score 0.5 (impersonal)       │
                                └──────────┬─────────────────┬──────────┘
                                           │                 │
                  ┌────────────────────────┘                 └────────────────────────┐
                  ▼                                                                   ▼
    ┌───────────────────────────┐                                       ┌───────────────────────────┐
    │       INTERNAL FACE       │                                       │        CLIENT FACE        │
    │   (Auto-Trader / Fund)    │                                       │  (Self-Directed SaaS)     │
    ├───────────────────────────┤                                       ├───────────────────────────┤
    │ · borsenhirn/internal/    │                                       │ · Next.js 14 + Clerk JWT  │
    │ · 24/7 paper execution    │                                       │ · Encrypted vault (Fernet)│
    │ · Auto SL / Trailing Stops│                                       │ · Risk calculator (TS)    │
    │ · Persists trade outcomes │                                       │ · Manual order dialog     │
    │ · Powers Track Record     │                                       │ · Legal gate (HTTP 451)   │
    └─────────────┬─────────────┘                                       └─────────────┬─────────────┘
                  │                                                                   │
                  └────────────────────────┬──────────────────────────────────────────┘
                                           ▼
                                ┌───────────────────────────────────────┐
                                │       POSTGRESQL 18 / 16 (RLS)        │
                                │  `app.current_tenant_id` session GUC  │
                                │  Unprivileged role borsenhirn_app     │
                                │  Append-only audit log · Kill switch  │
                                └───────────────────────────────────────┘
```

1. **The Shared Brain (`SignalEngine`):** Analyzes the market deterministically and impersonally. Generates identical analysis cards and stop levels across all actors.
2. **The Internal Face (`borsenhirn/internal/autotrader/`):** Autonomous engine executing against an internal corporate paper trading account to test strategies and persist verifiable trade outcomes for track record auditing. Isolated with import guardrails to prevent code leakage.
3. **The Client Face (Next.js 14 Frontend):** Users connect their own Alpaca account via BYO broker onboarding. The user sizes their own position and **must explicitly click the buy button**. The platform never executes automated orders on client accounts.

---

## 📍 Module & Feature Implementation Status

### ✅ 1. Fully Implemented (Working)
- **Trading Engine & State Machine:** 4-state regime detection (`BULL`, `BEAR`, `SIDEWAYS`, `PANIC`), 44-asset scanner, and Alpaca execution with bracket/trailing order management.
- **Rigorous ML Validation:** PurgedKFold cross-validation with temporal embargo (López de Prado), triple-barrier labeling, label leakage detection, and bit-exact SHA-256 reproducibility verification.
- **Safety Stack & Kill Switches:** 7 pre-order sanity checks (`sanity.py`), per-tenant and global database-persisted kill switches (`global_killswitch.py`), Alpaca API circuit breaker, and multi-channel alerts (Discord & Email).
- **Multi-Tenancy via Row-Level Security:** 17 to 21 tables enforcing `tenant_id` at the PostgreSQL engine level, unprivileged application role `borsenhirn_app` (`NOSUPERUSER`, `NOBYPASSRLS`), and strict isolation validated by tests.
- **Credential Vault:** Fernet encryption-at-rest (`CredentialStore`) for tenant Alpaca keys, complete with master key rotation support.
- **Authentication & Multi-Tenant API:** Structured FastAPI app with Clerk RS256 JWKS verification, lazy tenant provisioning, and JWT context resolution.
- **Client Manual Execution:** `POST /me/orders` endpoint with `idempotency_key` deduplication, sanity caps on order volume, and enforced legal compliance gating.
- **Audit Logging & GDPR:** Append-only table under RLS tracking sensitive operations, with `/me/audit` and `/me/export` endpoints (full JSON data portability).
- **Worker Isolation & Anomaly Detection:** Sequential tenant runner isolating tenant failures and automated periodic anomaly scanner for operational anomalies.
- **Legal Compliance Engine:** Versioned legal acceptance (`/legal/current`, `/me/legal/accept`); order execution returns HTTP 451 until the current terms are accepted.
- **M3 Risk Engine:** Rule-based heuristic risk scoring integrated into the signal pipeline (`m3_risk.py`).
- **Core Frontend (Next.js 14):** Full Clerk authentication, secure Alpaca BYO broker connection (`/me/broker`), setup viewer (`/signals`), pure TypeScript risk calculator with Vitest suite, and live positions dashboard with informative TP/SL status badges (`/me/positions`).
- **News Feed (`/dashboard/noticias`):** Real Benzinga-via-Alpaca headlines from `GET /noticias` — the same impersonal feed for every tenant, with an empty state instead of fake data.

### 🟡 2. Partially Implemented (Partial)
- **Stripe Billing:** Complete backend supporting customer creation, checkout/portal sessions, and webhook signature verification (`borsenhirn/billing/`). *Checkout buttons currently missing from Next.js UI.*
- **Cache & Rate Limiting:** Redis client with Token Bucket rate limiter and caching decorators verified with 104× speedup (`borsenhirn/cache/`). *Pending global middleware integration in FastAPI route handlers.*
- **Streamlit Dashboard ("Nightly Journal"):** Operational dashboard for single-user trading monitoring (`dashboard.py`). *Functional, but unit tests are temporarily excluded in CI and it is not multi-tenant.*
- **Intelligence Modules M1, M2, M4, M5:** Standalone root scripts (`M1_research.py`, `m2_analyst.py`, `m4_whale.py`, `m5_assistant.py`) integrating Claude, FRED, and SEC EDGAR. *Operate as independent CLI tools; corresponding packages under `borsenhirn/m*/` are empty stubs not yet exposed to the SaaS API.*
- **Containerization (Docker):** `Dockerfile` (`python:3.12-slim`) starts the bot loop plus the FastAPI server (honors `$PORT`, used for Render); `docker-compose.yml` adds `postgres:16-alpine` and the Streamlit dashboard. *Next.js is not containerized yet, and versions differ from the local target (see Known Limitations).*
- **Investigador demo mode:** `/dashboard/investigador` uses real `/signals` data, but `?demo=1` renders a hardcoded demo company with a visible banner (temporary, `frontend/src/lib/demo-signals.ts`).

### 🚧 3. In Progress / Coming Soon (frontend mockups — not functional)
- **Whale Alerts (`/dashboard/whale`):** Visual mockup with a `MAQUETA DEMO` badge rendering static `MOCK_ALERTS`. Pending connection to the 13F parser in `m4_whale.py`.
- **Hirn Copilot (`/dashboard/hirn`):** Visual mockup with a `MAQUETA DEMO` badge and a disabled chat input; no API connection. Pending a multi-tenant FastAPI endpoint exposing `m5_assistant.py`.
- **Public Track Record (`/dashboard/track`):** Visual mockup with a `MAQUETA DEMO` badge, fake metrics, and a static SVG equity curve from `MOCK_CLOSED_TRADES`. Pending connection to real `bot_trade_outcomes` data.

---

## 🔬 Machine Learning Honesty

The current Random Forest model on technical indicators achieves an **AUC ≈ 0.50** under purged walk-forward cross-validation with embargo — in other words, **performance indistinguishable from chance**.

The project **does not claim to have discovered predictive alpha**; it demonstrates the **mathematical and operational infrastructure required to detect whether a strategy has a true statistical edge**, preventing common pitfalls like overfitting and data leakage. Full methodology and results are documented in [`PLAN_VALIDACION_ML.md`](PLAN_VALIDACION_ML.md).

---

## ⚠ Known Limitations & Development Setup

1. **Frontend Mockup Views:** The *Whale Alerts*, *Hirn Copilot*, and *Track Record* pages render hardcoded sample data behind a visible `MAQUETA DEMO` badge. They do not work yet.
2. **M1–M5 Modules Not Connected to the SaaS:** The intelligence scripts are real and run from the CLI (`M1_research.py`, `m2_analyst.py`, `m4_whale.py`, `m5_assistant.py` — FRED, SEC EDGAR 13F for 47 institutions, Prophet, Claude). They have not been migrated into their `borsenhirn/m*/` packages (empty stubs today) or exposed through FastAPI, so no tenant can reach them from the web app. `m5_assistant.py` also has no multi-tenant RLS yet. *(M3 is the exception: it is wired into the signal pipeline.)*
3. **Development Setup — hardcoded credentials ⚠:**
   - The PostgreSQL password `uriel` is hardcoded as a fallback in `config.py`, `m5_assistant.py`, and `docker-compose.yml`. It exists only for local development and is scheduled for removal. **Never deploy with these defaults — set `DB_PASSWORD` / `DATABASE_URL` explicitly.**
   - The internal auto-trader and the test client share the same Alpaca **paper** account in development, so `/me/positions` may show orders placed by the bot. Use separate paper accounts to test the client flow in isolation.
   - The frontend API base URL is hardcoded to `localhost:8000` in `frontend/src/lib/*.ts`.
4. **Container Version Discrepancies:**
   - **Target Host / Local Environment:** Python 3.14.0 (`.python-version`) / PostgreSQL 18.
   - **Current Docker Containers:** `python:3.12-slim` in `Dockerfile` and `postgres:16-alpine` in `docker-compose.yml`.

---

## 🚀 Quick Start (Local Environment)

### Prerequisites
- Python 3.12+ (Python 3.14 recommended)
- PostgreSQL 16+ with RLS support
- Node.js 18+ (for Next.js frontend)
- Redis (optional, for cache and rate limiting)

### 1. Clone & Install Backend
```bash
git clone https://github.com/Obumbratio/proyecto_trading.git
cd proyecto_trading

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1       # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS

# Install dependencies with verified hashes
pip install pip-tools
pip-sync requirements.txt requirements-dev.txt
```

### 2. Environment Configuration
```bash
cp .env.example .env
# Configure variables in .env:
# - DB_USER, DB_PASSWORD, DB_NAME
# - BORSENHIRN_MASTER_KEY (Fernet master key for secrets vault)
# - CLERK_ISSUER, CLERK_JWKS_URL
# - ALPACA_API_KEY, ALPACA_SECRET_KEY
```

### 3. Database Migration
```bash
psql -U postgres -d borsenhirn -f borsenhirn/safety/migrations.sql
```

### 4. Running Tests
```bash
# Backend test suite (414+ tests)
pytest -q

# Model reproducibility verification
python scripts/verify_reproducibility.py

# Frontend risk calculator Vitest suite
cd frontend
npm install
npm test
cd ..
```

### 5. Launch the Platform
To run the full development stack:
```bash
# Start FastAPI backend (port 8000)
python -m uvicorn borsenhirn.api.main:app --host 0.0.0.0 --port 8000 --reload

# Start Next.js frontend (in a separate terminal, port 3000)
cd frontend
npm run dev
```

Or run the legacy Streamlit monitoring dashboard:
```bash
streamlit run dashboard.py
```

---

## 📁 Repository Structure

```
proyecto_trading/
├── borsenhirn/
│   ├── anomaly/              # Volume and operational anomaly detection
│   ├── api/                  # FastAPI endpoints (/me, /signals, /me/orders)
│   ├── audit/                # Append-only immutable audit logging
│   ├── auth/                 # Clerk JWT verification (RS256 JWKS)
│   ├── backups/              # Per-tenant data export (GDPR portability)
│   ├── billing/              # Stripe integration (webhooks and checkout sessions)
│   ├── cache/                # Redis cache and Token Bucket rate limiting
│   ├── dashboard/            # Streamlit dashboard components
│   ├── internal/autotrader/  # Internal face: 24/7 auto-trader (non-product)
│   ├── legal/                # Versioned legal compliance gating (HTTP 451)
│   ├── ml/                   # PurgedKFold, labeling, and leakage auditing
│   ├── news/                 # News feed aggregation via Alpaca/Benzinga
│   ├── safety/               # Kill switches, sanity checks, and alerts
│   ├── security/             # Fernet-encrypted credential vault
│   ├── signals/              # Deterministic SignalEngine and honest cards
│   ├── tenancy/              # Tenant constants and RLS context management
│   └── workers/              # Multi-tenant bot cycle orchestrator
│
├── frontend/                 # Next.js 14 Web Application (App Router)
│   ├── src/app/dashboard/    # Signals, broker, orders, and mockup views
│   ├── src/components/       # Risk calculator, buy order modal
│   └── src/lib/              # API clients, pure sizing logic (Vitest)
│
├── legal/                    # Mandatory legal documentation
│   ├── DISCLAIMER.md         # Liability disclaimer
│   ├── TERMS.md              # Terms of Service
│   └── PRIVACY.md            # Privacy Policy
│
├── scripts/                  # CLI tools, ML validation, and migrations
├── tests/                    # 414+ unit, integration, and property-based tests
├── main.py                   # Single-tenant / local bot loop
├── strategy.py               # Technical indicators engine (RSI/MACD/BB)
├── execution.py              # Alpaca order execution wrapper
└── STATUS.md                 # Official status audit and roadmap checklist
```

---

## 📚 Detailed Technical Documentation

| Document | Content |
|---|---|
| [`STATUS.md`](STATUS.md) | **Official repository status audit, completion metrics, and roadmap checklist.** |
| [`PLAN_VALIDACION_ML.md`](PLAN_VALIDACION_ML.md) | Comprehensive ML diagnosis: why 80/20 train/test splits mislead and how Purged CV was built. |
| [`MULTI_TENANCY.md`](MULTI_TENANCY.md) | Architecture specification for PostgreSQL RLS and session GUC variables. |
| [`SECRETS.md`](SECRETS.md) | Cryptographic design of the Fernet credential vault and master key rotation. |
| [`INTEGRACION_SAFETY.md`](INTEGRACION_SAFETY.md) | Pre-order sanity checks and kill switch wiring. |
| [`RATE_LIMITING.md`](RATE_LIMITING.md) | Token Bucket rate limiter architecture and distributed Redis caching. |
| [`REPRODUCIBILIDAD.md`](REPRODUCIBILIDAD.md) | Hash-pinned dependency lockfile protocol and bit-by-bit model verification. |

---

## ⚖ License

Research and educational use. For commercial licensing or enterprise deployment, contact the author. See [`legal/TERMS.md`](legal/TERMS.md).

---

## 👤 Author

**Uriel Castañeda**  
GitHub: [@Obumbratio](https://github.com/Obumbratio)  
Portfolio focused on **Data Engineer / ML Engineer / MLOps** roles.
