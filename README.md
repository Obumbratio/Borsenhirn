# Börsenhirn — financial intelligence platform

[![CI](https://github.com/Obumbratio/proyecto_trading/actions/workflows/ci.yml/badge.svg)](https://github.com/Obumbratio/proyecto_trading/actions/workflows/ci.yml)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/release/python-3140/)
[![Coverage](https://img.shields.io/badge/coverage-%3E60%25-brightgreen)](htmlcov/index.html)
[![License](https://img.shields.io/badge/license-research-lightgrey)](#license)
[![Tests](https://img.shields.io/badge/tests-150%2B-brightgreen)](tests/)

> **⚠ EDUCATIONAL TOOL — NOT FINANCIAL ADVICE.** Cualquier "señal", "score" o sugerencia
> producida por este software es para investigación personal. Resultados pasados (backtest
> o paper trading) **no predicen** retornos futuros. Operás con tu propio capital bajo tu
> propio riesgo. Lee el [DISCLAIMER completo](legal/DISCLAIMER.md) antes de usar.

---

End-to-end research platform que combina un trading bot algorítmico, un asistente
conversacional con memoria persistente, y una capa rigurosa de validación ML +
infraestructura de seguridad. Construido como proyecto de portfolio para roles
de **Data Engineer / ML Engineer / ML Ops** — el énfasis está en la **infra de
producción**, no en pretender que un modelo predice el mercado.

## Lo que hace

- **Trading bot** sobre Alpaca (paper trading) con 44 símbolos, detector de régimen
  de 4 estados (PANIC/BEAR/SIDEWAYS/BULL), umbrales dinámicos según VIX, trailing
  stops y stop-losses configurables.
- **5 módulos de inteligencia:**
  - `M1 · Research` — agregación multi-fuente con Anthropic Claude.
  - `M2 · Analyst` — convergencia de FRED macro, SEC Form 4, 13F institucional,
    Prophet forecasts.
  - `M3 · Risk Engine` — scoring heurístico de riesgo de mercado por símbolo.
  - `M4 · Whale Tracker` — parser de filings 13F de 47 instituciones.
  - `M5 · Hirn` — asistente Claude con memoria persistente en Postgres.
- **Safety layer** real: kill switches con estado persistente, sanity checks
  pre-orden, multi-canal de alertas (Discord + Email + Dashboard), circuit
  breakers para APIs externas.
- **Validación ML rigurosa:** walk-forward purged CV (López de Prado),
  triple-barrier labeling, meta-labeling, audit de leakage, reproducibilidad
  bit-exacta del modelo.
- **Dashboard Streamlit** con vista de portfolio, régimen, trades, alertas, P&L.

## Lo que NO hace (honestidad)

El componente ML actual (Random Forest sobre features técnicas) tiene
**AUC ≈ 0.50** en walk-forward purged validation — es decir, casi azar. El
proyecto **no afirma** tener edge predictivo; afirma tener la **infra para
medir si tendrías edge**. Detalle completo en
[`PLAN_VALIDACION_ML.md`](PLAN_VALIDACION_ML.md).

Eso es deliberado: prefiero un proyecto de portfolio honesto sobre uno que
infla métricas. Lo que vende este repo no es "inventé un alpha", es
"sé construir infraestructura ML defendible bajo escrutinio".

---

## Arquitectura

```
                    ┌─────────────────────┐
                    │   main.py (loop)    │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼───────────────────────┐
        ▼                      ▼                       ▼
  ┌──────────┐          ┌────────────┐          ┌────────────┐
  │ Scanner  │          │ Strategy   │          │ Safety     │
  │ (44 sym) │          │ + ML model │          │ stack      │
  └────┬─────┘          └──────┬─────┘          └─────┬──────┘
       │                       │                      │
       │      ┌────────────────┴──────────┐           ▼
       │      │                           │     KillSwitch
       ▼      ▼                           │     SanityChecker
  ┌─────────────────┐                     │     AlertManager
  │ DataFetcher     │                     │     CircuitBreaker
  │ (Alpaca + IEX)  │                     │
  └────────┬────────┘                     ▼
           │                         ┌──────────┐
           ▼                         │ Executor │ ──→ Alpaca paper / live
  ┌─────────────────┐                └──────────┘
  │ market_context  │
  │  (VIX, F&G)     │     ┌────────────────────────┐
  └─────────────────┘     │ borsenhirn/ml/         │
                          │  validation, labeling, │
  ┌─────────────────┐     │  metrics, audit,       │
  │ M1-M5 modules   │     │  features              │
  │ (Claude API)    │     └────────────────────────┘
  └────────┬────────┘     (used by scripts/validate_*.py)
           │
           ▼
  ┌─────────────────┐         ┌─────────────────┐
  │ bot_memory_pg   │ ──────→ │  PostgreSQL 18  │
  └─────────────────┘         └─────────────────┘
                                     ▲
                              ┌──────┴──────┐
                              │ alerts_log  │
                              │ killswitch  │
                              └─────────────┘
```

## Module integration status

Algunos módulos del repo están **integrados activamente** al bot vivo;
otros son **foundation listo para SaaS / multi-user** pero NO se usan
en el bot single-tenant actual. Esto es **decisión consciente del
sprint**, no un oversight — separa "production now" de "production
ready when needed".

| Módulo | Estado | Notas |
|---|---|---|
| `borsenhirn/safety/` | ✅ **Integrado** | Wired a `main.py` líneas 19-21, 138-142, 326. Kill switches + sanity + Discord/email alerts activos en cada ciclo. |
| `borsenhirn/ml/` | ✅ **Disponible** | Usado por `scripts/validate_*.py` para auditoría del modelo. NO se ejecuta en el loop del bot por design (la validación se corre manual cuando reentrenamos). |
| `borsenhirn/cache/` | 🟡 **Foundation** | Listo y testeado (60 tests, demo end-to-end con 104× speedup). NO está envolviendo `data_fetcher.get_historical` ni el FastAPI middleware todavía. Wrappers prontos en `borsenhirn/cache/api_cache.py`. |
| `borsenhirn/security/` (vault) | 🟡 **Foundation** | Encryption at rest verificado (48 tests + demo). NO se usa en el bot legacy porque el bot single-tenant usa una sola key Alpaca de `.env`. Activable cuando aceptes credenciales de usuarios externos. |
| `borsenhirn/tenancy/` | 🟡 **Foundation** | Fase A completa (48 tests + demo RLS). Fase B (migrar `bot_memory_pg.py` a multi-tenant + crear roles Postgres `borsenhirn_app/admin`) **archivada hasta SaaS** — ver [`MULTI_TENANCY.md`](MULTI_TENANCY.md). |
| `borsenhirn/core/cache.py` (legacy) | ⚠️ **A deprecar** | API previa a `borsenhirn/cache/`. Sigue funcionando, pero el código nuevo debería usar el módulo nuevo. |

Si estás auditando el repo: lo que se ejecuta hoy en producción (paper
trading) es `main.py` + `bot_memory_pg.py` + `borsenhirn/safety/*`. El
resto es infra ready pero no en el critical path.

## Stack

- **Lenguaje:** Python 3.14 (pin exacto en `.python-version`).
- **Datos:** PostgreSQL 18 + Redis (cache).
- **APIs:** Alpaca Markets, Anthropic Claude, FRED, Finnhub, Alpha Vantage,
  Polygon, NewsAPI, yfinance, SEC EDGAR.
- **ML:** scikit-learn (RandomForest), Prophet, hypothesis para property-based
  testing.
- **Web:** FastAPI (`/health`, `/status`, `/trades/list`), Streamlit (dashboard).
- **Reproducibilidad:** pip-tools (lockfile con hashes), `.python-version`,
  script de verify_reproducibility con SHA256.

---

## Quick start (self-hosted)

```bash
# 1. Clone
git clone https://github.com/Obumbratio/proyecto_trading.git
cd proyecto_trading

# 2. Python 3.14 + venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1            # Windows
# source .venv/bin/activate              # Linux/Mac

# 3. Dependencias
pip install pip-tools
pip-compile --generate-hashes --output-file=requirements.txt requirements.in
pip-compile --generate-hashes --output-file=requirements-dev.txt requirements-dev.in
pip-sync requirements.txt requirements-dev.txt

# 4. Variables de entorno
cp .env.example .env
# Editar .env con tus claves: ALPACA, ANTHROPIC, DB, DISCORD_WEBHOOK_URL, SMTP

# 5. Postgres schema
psql -U postgres -d borsenhirn -f borsenhirn/safety/migrations.sql

# 6. Smoke test de canales de alertas
python scripts/test_alerts.py

# 7. Tests
pytest --cov

# 8. Validar el modelo ML
python scripts/validate_model.py --symbol SPY --start 2020-01-01

# 9. Correr el bot (un ciclo)
python main.py --once

# 10. Dashboard
streamlit run dashboard.py
```

## Project layout

```
proyecto_trading/
├── main.py                       # Loop principal del bot
├── strategy.py                   # Reglas técnicas (RSI/MACD/BB + ML override)
├── ml_model.py                   # RandomForest training/predict
├── m3_risk.py                    # Risk scoring heurístico
├── regime_detector.py            # Detector BULL/BEAR/SIDEWAYS/PANIC
├── scanner.py                    # Scanner multi-símbolo
├── execution.py                  # Wrapper Alpaca
├── data_fetcher.py               # Alpaca + circuit_breaker
├── circuit_breaker.py            # Pattern para APIs externas
├── risk_manager.py               # Daily loss / max trades / capital checks
├── bot_memory_pg.py              # Estado persistente en Postgres
├── dashboard.py                  # Streamlit UI
├── bot_api.py                    # FastAPI endpoints (/status /trades)
│
├── borsenhirn/
│   ├── safety/                   # ✨ Safety layer
│   │   ├── alerts.py             #   Discord + Email + Dashboard channels
│   │   ├── killswitch.py         #   Reglas de halt automático
│   │   ├── sanity.py             #   7 checks pre-orden
│   │   ├── health.py             #   Snapshot para /health
│   │   ├── state_store_pg.py     #   Backend Postgres
│   │   ├── bootstrap.py          #   SafetyStack: init + safe_submit_buy
│   │   └── migrations.sql        #   Schema killswitch_state + alerts_log
│   │
│   └── ml/                       # ✨ Validación ML rigurosa
│       ├── validation.py         #   PurgedKFold + walk_forward_split
│       ├── labeling.py           #   Triple-barrier (López de Prado)
│       ├── meta_model.py         #   Meta-labeling pipeline
│       ├── features.py           #   19 meta-features contextuales
│       ├── metrics.py            #   AUC, PR-AUC, Brier, baselines
│       └── audit.py              #   PSI, label leakage detector
│
├── scripts/
│   ├── validate_model.py         # Walk-forward purged CV del RF
│   ├── validate_meta_model.py    # Pipeline meta-labeling completo
│   ├── verify_reproducibility.py # SHA256 de modelo entre runs
│   ├── test_alerts.py            # Smoke test multi-canal
│   └── audit_language.py         # Detector de lenguaje riesgoso
│
├── tests/                        # 150+ tests, coverage >60%
│   ├── conftest.py               # Fixtures comunes
│   ├── test_safety_*.py          # alerts, killswitch, sanity, bootstrap
│   ├── test_ml_*.py              # validation, labeling, metrics, audit
│   ├── test_property_based.py    # Hypothesis: 7 invariantes
│   ├── test_circuit_breaker.py
│   ├── test_risk_manager.py
│   └── test_core.py              # strategy, m3_risk, regime
│
├── legal/                        # ✨ Compliance docs
│   ├── DISCLAIMER.md
│   ├── TERMS.md
│   ├── PRIVACY.md
│   └── README.md                 # Cuándo necesitás abogado
│
├── .github/workflows/ci.yml      # CI: ruff + pytest + reproducibility
├── pyproject.toml                # pytest, coverage, ruff, mypy config
├── requirements.in               # Top-level deps
├── requirements-dev.in           # Dev deps (pytest, hypothesis, ruff)
├── .python-version               # 3.14.x exacto
│
├── PLAN_VALIDACION_ML.md         # Diagnóstico ML completo
├── PLAN_PRODUCCION.md            # Roadmap de los 8 gaps originales
├── REPRODUCIBILIDAD.md           # Guía pip-tools + verify
├── TESTS.md                      # Plan de testing
├── INTEGRACION_SAFETY.md         # Cómo cablear safety/ a main.py
└── CHECKLIST_VALIDACION.md       # Comandos para validar todo end-to-end
```

---

## Development

### Tests

```bash
pytest                            # corre todo
pytest --cov --cov-report=html    # con coverage HTML
pytest -m "not integration"       # skip tests que tocan DB/API
pytest -k "killswitch"            # filtrar por nombre
```

Coverage targets:
- `borsenhirn/safety/*` → >90%
- `borsenhirn/ml/*` → >80%
- `risk_manager`, `circuit_breaker` → >90%
- `strategy`, `regime_detector` → >60%
- **CI gate:** total >60%

### Lint

```bash
ruff check .                      # linter rápido
ruff format .                     # autoformatter (opcional)
mypy borsenhirn/                  # type checking
```

### Reproducibilidad

```bash
python scripts/verify_reproducibility.py
# Entrena 2 veces el modelo con mismo seed y compara SHA256 de los bytes.
# Output esperado: "OK — Modelo BIT-IDENTICO entre runs."
```

### CI

GitHub Actions corre en cada push/PR:

1. **Lint** con ruff (warning, no bloquea).
2. **Tests + coverage** con `--cov-fail-under=60`.
3. **Reproducibility check**.
4. **Language audit** (HIGH risk only, no bloquea).

Ver [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Documentación interna

| Archivo | De qué trata |
|---|---|
| [`legal/DISCLAIMER.md`](legal/DISCLAIMER.md) | Disclaimer legal — leer antes de cualquier uso |
| [`legal/TERMS.md`](legal/TERMS.md) | Terms of Service (template) |
| [`legal/PRIVACY.md`](legal/PRIVACY.md) | Privacy Policy (template) |
| [`PLAN_VALIDACION_ML.md`](PLAN_VALIDACION_ML.md) | Diagnóstico completo del ML — qué se validó y resultado |
| [`PLAN_PRODUCCION.md`](PLAN_PRODUCCION.md) | Roadmap de los 8 gaps de arquitectura (5 cerrados) |
| [`INTEGRACION_SAFETY.md`](INTEGRACION_SAFETY.md) | Cómo se cableó el safety layer a main.py |
| [`REPRODUCIBILIDAD.md`](REPRODUCIBILIDAD.md) | Guía de pip-tools y verify_reproducibility |
| [`TESTS.md`](TESTS.md) | Plan de tests, coverage targets, qué falta |
| [`CHECKLIST_VALIDACION.md`](CHECKLIST_VALIDACION.md) | Lista de comandos para validar todo |

---

## Estado del proyecto

| # | Componente | Estado |
|---|---|---|
| 1 | ML validation (walk-forward purged) | ✅ Cerrado — modelo confirmado marginal |
| 2 | Safety stack (kill switches + alertas) | ✅ Cerrado — Discord/Email/Dashboard |
| 6 | Compliance / disclaimers | ✅ Cerrado — banner UI + 3 docs legales |
| 7 | Reproducibilidad ML bit-exacta | ✅ Cerrado — pip-tools + verify SHA256 |
| 8 | Tests + CI | ✅ Cerrado — 150+ tests, coverage >60%, CI verde |
| 3 | Secrets encryption (Fernet) | 🟡 Pendiente — pre-SaaS |
| 4 | Multi-tenancy (tenant_id + RLS) | 🟡 Pendiente — pre-SaaS |
| 5 | Rate limiting + Redis cache | 🟡 Pendiente — pre-SaaS |

---

## License

Research / educational use. Para uso comercial o redistribución, contactar
al autor. Ver [`legal/TERMS.md`](legal/TERMS.md).

---

## Autor

**Uriel Castanada** — Computer Science student.
GitHub: [@Obumbratio](https://github.com/Obumbratio)

Este proyecto es portfolio para aplicar a roles de Data Engineer / ML Engineer
/ ML Ops. Si te interesa el approach (infra ML rigurosa > pretender alpha),
abrí un issue o contactame.
