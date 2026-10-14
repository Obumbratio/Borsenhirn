# STATUS AUDIT (source of truth)

### Overall Completion: 75%

### 🎯 META (End Goal)
Börsenhirn is designed to become a production-grade, multi-tenant financial intelligence and self-directed algorithmic trading SaaS platform ("Modelo A — BYO Alpaca Broker"), architected around the "Un cerebro, dos caras" paradigm:

1. **Cara Interna:** Headless auto-trading engine with 4-state regime detection, dynamic VIX bands, trailing stops, and verifiable track record persistence.
2. **Cara Cliente:** Secure web app with Clerk auth, encrypted Alpaca credential vault (Postgres RLS), deterministic signals, position sizing calculators, and manual order execution with legal consent gating.
3. **Intelligence (Hirn M1-M5):** Multi-agent system integrating FRED macro, SEC EDGAR 13F (47 institutions), Form 4 insider trades, Benzinga news, and Claude conversational copilot.
4. **Defensible ML & Security:** López de Prado purged walk-forward CV, triple-barrier labeling, leakage detection, RLS tenant isolation, append-only audit logging, kill switches, multi-channel alerts.

---

### 📍 CURRENT STATE

| Component | Status | Notes |
|---|---|---|
| Core Trading & Execution Engine | ✅ Implemented | 4-state regime detector, multi-symbol scanner, technical signals, trailing stops, Alpaca paper execution |
| ML Validation Framework | ✅ Implemented | López de Prado purged K-Fold, triple-barrier labeling, leakage audit, SHA-256 reproducibility |
| Safety Layer & Circuit Breakers | ✅ Implemented | 7 pre-order checks, Postgres kill switches, global admin halt, circuit breaker, Discord/Email alerts |
| Multi-Tenancy & Database | ✅ Implemented | 17-21 tables with PostgreSQL RLS via session GUC and unprivileged app roles |
| Secrets Vault & Encryption | ✅ Implemented | Fernet encryption-at-rest for Alpaca keys, key rotation, tenant isolation |
| Authentication & Core API | ✅ Implemented | FastAPI + Clerk RS256 JWKS, lazy tenant provisioning, tenant-scoped endpoints |
| Manual Execution & Positions API | ✅ Implemented | Paper orders with idempotency, sanity caps, TP/SL alerts, legal compliance gating |
| Audit Logging & GDPR Export | ✅ Implemented | Append-only audit_log under RLS, /me/audit and /me/export endpoints |
| Worker Orchestration & Anomaly Detection | ✅ Implemented | Sequential tenant runner, systemd hourly anomaly scanner |
| Legal Compliance Engine | ✅ Implemented | Versioned legal acceptance, HTTP 451 enforcement on trade execution |
| M3 Risk Engine | ✅ Implemented | Rule-based heuristic risk scoring integrated into signal pipeline |
| Next.js Frontend (Core) | ✅ Implemented | Clerk auth, Alpaca BYO connect, signals feed, position calculator (8 vitest tests), order modal |
| Stripe Billing | 🟡 Partial | Backend checkout/portal/webhooks exist; frontend UI buttons missing |
| Redis Caching & Rate Limiting | 🟡 Partial | Cache client and rate limiter tested (104x speedup); not wired into API routes |
| Streamlit Dashboard | 🟡 Partial | "Bitácora Nocturna" works single-tenant; tests disabled in CI |
| M1 Research Agent | 🟡 Partial | Root script works; borsenhirn/m1_research/ is empty stub |
| M2 Financial Analyst | 🟡 Partial | Root script connects FRED/SEC/Prophet; borsenhirn/m2_analyst/ is empty stub |
| M4 Whale Tracker Engine | 🟡 Partial | 13F EDGAR scraper for 47 institutions exists; package empty, not connected to API/UI |
| M5 Hirn Assistant Engine | 🟡 Partial | CLI assistant works; no multi-tenant RLS, not connected to UI |
| Containerization | 🟡 Partial | Docker runs bot + Streamlit with Python 3.12/Postgres 16; Next.js frontend omitted |
| Frontend: Whale Alerts UI | ❌ Missing/Stub | Hardcoded "MAQUETA DEMO" with static MOCK_ALERTS |
| Frontend: Hirn Copilot UI | ❌ Missing/Stub | Static mock chat with disabled input; no API connection |
| Frontend: Track Record UI | ❌ Missing/Stub | Hardcoded demo with fake metrics and static SVG equity curves |

---

### 📋 PROCESS (Current → Goal)

#### 1. Critical — Blocks demo-readiness
- [ ] Separate internal autotrader from client paper account (shared Alpaca credentials in dev)
- [ ] Synchronize Docker environments (Python 3.12 vs 3.14, Postgres 16 vs 18, add Next.js container)
- [ ] Eliminate hardcoded default credentials (password "uriel" in config.py, docker-compose.yml, m5_assistant.py)
- [ ] Provide unified multi-service startup script (Postgres, Redis, FastAPI, Next.js)

#### 2. Important — Feature parity with README
- [ ] Connect Whale Alerts UI to real SEC 13F backend (replace MOCK_ALERTS)
- [ ] Connect Hirn Copilot UI to Claude assistant backend (replace mock chat)
- [ ] Connect Track Record UI to real bot_trade_outcomes (replace MOCK_CLOSED_TRADES)
- [ ] Wire Redis rate limiting into API routes and data fetchers
- [ ] Add Stripe billing UI buttons in frontend
- [ ] Migrate M1/M2/M4/M5 root scripts into borsenhirn/ packages and expose via API
- [ ] Fix and un-ignore Streamlit dashboard tests

#### 3. Polish — Cleanup & optimization
- [ ] Archive ~163 KB of dead legacy files (dashboard.py.backup, auditor.py, fixes.py, etc.)
- [ ] Deprecate legacy cache in borsenhirn/core/cache.py
- [ ] Clean 37 dead imports (ruff check --fix)
- [ ] Add position concentration guardrail badge (>40% portfolio warning)
- [ ] Centralize API URLs (replace hardcoded localhost:8000)

---

### 📊 COMPLETION BREAKDOWN

| Area | Score | Notes |
|---|---|---|
| Core Logic | 82% | Robust engine, safety stack, RLS multi-tenancy. Docked for disconnected M1/M2/M4/M5 |
| UI / Frontend | 64% | Core flow works; 3 major views are hardcoded mockups |
| Tests & Validation | 86% | 414+ Python tests, 8 vitest, Hypothesis invariants. Dashboard tests excluded |
| Documentation | 88% | Extensive and high-quality. Minor version discrepancies |
| Deployment / Config | 55% | Local Postgres + CI work. Missing Next.js in Docker, version mismatches, hardcoded passwords |
| **Overall** | **75%** | **Production-grade backend and multi-tenant security; frontend intelligence views and deployment configs in progress.** |
