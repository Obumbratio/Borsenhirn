# Börsenhirn — Financial Intelligence & Algorithmic Trading Platform

[![CI](https://github.com/Obumbratio/proyecto_trading/actions/workflows/ci.yml/badge.svg)](https://github.com/Obumbratio/proyecto_trading/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.14%20(target)%20%7C%203.12%20(docker)-blue.svg)](.python-version)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%7C%2018%20(RLS)-336791.svg)](borsenhirn/tenancy/)
[![Next.js](https://img.shields.io/badge/frontend-Next.js%2014-black.svg)](frontend/)
[![Coverage](https://img.shields.io/badge/coverage-%3E60%25-brightgreen)](htmlcov/index.html)
[![Tests](https://img.shields.io/badge/tests-414%2B%20passed-brightgreen)](tests/)
[![Status](https://img.shields.io/badge/maturity-75%25%20complete-orange)](#-completion-status)
[![License](https://img.shields.io/badge/license-research-lightgrey)](#license)

> **⚠ EDUCATIONAL TOOL — NOT FINANCIAL ADVICE.** Cualquier "señal", "score" o sugerencia
> producida por este software es para investigación personal. Resultados pasados (backtest
> o paper trading) **no predicen** retornos futuros. Operás con tu propio capital bajo tu
> propio riesgo. Lee el [DISCLAIMER completo](legal/DISCLAIMER.md) antes de usar.

---

Börsenhirn es una plataforma de inteligencia financiera y trading algorítmico multi-tenant orientada a comercialización SaaS (**Modelo A — BYO Alpaca Broker**). El sistema combina un motor autónomo de ejecución en paper trading con un frontend web para inversores que ejecutan sus propias decisiones con credenciales cifradas en reposo, respaldado por una infraestructura de seguridad institucional (Postgres RLS, Vault Fernet) y validación cuantitativa rigurosa (López de Prado).

Construido como proyecto de portfolio para roles de **Data Engineer / ML Engineer / ML Ops** — el énfasis está en la **infraestructura de producción, defensa de datos y seguridad**, no en pretender que un modelo predice el mercado mágicamente.

---

## 📊 Completion Status

El proyecto se encuentra en un **75% de madurez global**. El backend, motor de ejecución, validación ML, multi-tenancy y capa de seguridad son de **grado institucional** y están validados por más de **414 tests automatizados**. Las superficies analíticas avanzadas del frontend se encuentran en fase de prototipado/maqueta.

Auditoría detallada disponible en el archivo de referencia: [`STATUS.md`](STATUS.md).

| Área | Completitud | Estado actual |
|---|:---:|---|
| **Core Logic & Trading Engine** | **82%** | Motor de trading decoupled, 4 regímenes, scanner multi-símbolo, multi-tenancy RLS y workers aislados. *(M1/M2/M4/M5 aún como scripts CLI independientes)*. |
| **Seguridad & Multi-Tenancy** | **95%** | RLS estricto en 17–21 tablas, bóveda de secretos Fernet per-tenant, Clerk RS256 JWKS y audit log inmutable. |
| **Validación Cuantitativa (ML)** | **92%** | Walk-forward purged CV, triple-barrier labeling, detección de leakage y reproducibilidad bit-exacta. |
| **Tests & QA** | **86%** | 414+ tests en Python, 8 tests en Vitest, tests property-based con Hypothesis. *(Tests de Streamlit desactivados en CI)*. |
| **Documentación** | **88%** | Planes de producción cerrados (B1–B10), bitácoras, diagnósticos ML y runbooks operativos. |
| **UI / Frontend (Next.js 14)** | **64%** | Conexión BYO broker, calculadora de riesgo TS, feed de señales y diálogo de orden manual operativos. *(Whale, Hirn y Track son maquetas demo)*. |
| **Deployment / Config** | **55%** | Local-first funcional con DB PostgreSQL y CI verde. *(Falta orquestar Next.js en docker-compose y sincronizar versiones)*. |
| **GLOBAL** | **75%** | **Backend y seguridad production-grade; frontend en integración activa.** |

---

## 🧠 Arquitectura: "Un Cerebro, Dos Caras"

Para garantizar separación regulatoria y técnica, el sistema desacopla la generación de análisis de la ejecución:

```
                                ┌───────────────────────────────────────┐
                                │          FUENTES DE MERCADO           │
                                │   Alpaca API · FRED · EDGAR · News    │
                                └──────────────────┬────────────────────┘
                                                   │
                                                   ▼
                                ┌───────────────────────────────────────┐
                                │     SignalEngine (Cerebro Común)      │
                                │  Régimen (4 estados) · VIX dinámico   │
                                │  Scanner 44 símbolos · RSI/MACD/BB    │
                                │  Score neutral 0.5 (impersonal)       │
                                └──────────┬─────────────────┬──────────┘
                                           │                 │
                  ┌────────────────────────┘                 └────────────────────────┐
                  ▼                                                                   ▼
    ┌───────────────────────────┐                                       ┌───────────────────────────┐
    │       CARA INTERNA        │                                       │       CARA CLIENTE        │
    │  (Auto-Trader / Fund)     │                                       │   (SaaS Autogestionado)   │
    ├───────────────────────────┤                                       ├───────────────────────────┤
    │ · borsenhirn/internal/    │                                       │ · Next.js 14 + Clerk JWT  │
    │ · Ejecuta en paper 24/7   │                                       │ · Vault cifrado (Fernet)  │
    │ · Auto SL / Trailing Stops│                                       │ · Calculadora riesgo (TS) │
    │ · Registra outcomes       │                                       │ · Diálogo orden manual    │
    │ · Alimenta Track Record   │                                       │ · Gate legal (HTTP 451)   │
    └─────────────┬─────────────┘                                       └─────────────┬─────────────┘
                  │                                                                   │
                  └────────────────────────┬──────────────────────────────────────────┘
                                           ▼
                                ┌───────────────────────────────────────┐
                                │      POSTGRESQL 18 / 16 (RLS)         │
                                │  `app.current_tenant_id` session GUC  │
                                │  Rol no privilegiado borsenhirn_app   │
                                │  Audit log inmutable · Killswitch     │
                                └───────────────────────────────────────┘
```

1. **El Cerebro Compartido (`SignalEngine`):** Analiza el mercado de forma determinista e impersonal. Genera las mismas tarjetas de análisis y niveles de stop para todos los actores.
2. **La Cara Interna (`borsenhirn/internal/autotrader/`):** Motor autónomo que opera una cuenta de paper trading corporativa, prueba estrategias y almacena su historial para auditar el track record. Aislado por guardrails de importación para evitar contaminación de código.
3. **La Cara Cliente (Frontend Next.js 14):** Los usuarios conectan su propia cuenta de Alpaca mediante BYO broker. El usuario calcula su propio tamaño de lote y **debe presionar explícitamente el botón de compra**. La plataforma jamás ejecuta órdenes automáticas en cuentas de clientes.

---

## 📍 Estado de Módulos y Funcionalidades

### ✅ 1. Completamente Implementado (Working)
- **Trading Engine & State Machine:** Detección de 4 regímenes (`BULL`, `BEAR`, `SIDEWAYS`, `PANIC`), scanner sobre 44 activos y ejecución en Alpaca con gestión de órdenes bracket/trailing.
- **Validación ML Rigurosa:** PurgedKFold cross-validation con embargo temporal (López de Prado), triple-barrier labeling, detección de leakage de etiquetas y verificación de reproducibilidad SHA-256 bit-a-bit.
- **Safety Stack & Kill Switches:** 7 verificaciones pre-orden (`sanity.py`), kill switches persistidos en base de datos por tenant y a nivel global (`global_killswitch.py`), circuit breaker para la API de Alpaca y alertas a Discord y Email.
- **Multi-Tenancy por Row-Level Security:** 17 a 21 tablas con `tenant_id` forzado a nivel de motor PostgreSQL, rol de aplicación `borsenhirn_app` sin permisos de superusuario (`NOSUPERUSER`, `NOBYPASSRLS`), y aislamiento estricto validado por tests.
- **Bóveda de Credenciales (Vault):** Cifrado en reposo con Fernet (`CredentialStore`) para almacenar llaves de Alpaca de clientes, con soporte de rotación de llave maestra.
- **Autenticación & API Multi-Tenant:** FastAPI estructurado con verificación Clerk RS256 JWKS, aprovisionamiento lazy de tenants y resolución de contexto por JWT.
- **Ejecución Manual del Cliente:** Endpoint `POST /me/orders` con deduplicación por `idempotency_key`, límites de sanidad de volumen y cumplimiento legal forzado.
- **Audit Log & GDPR:** Tabla append-only bajo RLS que registra operaciones sensibles, con endpoints `/me/audit` y `/me/export` (exportación completa en JSON).
- **Worker Isolation & Detección de Anomalías:** Orquestador secuencial que aísla fallos entre tenants y escaneo periódico de anomalías operativas.
- **Frontend Core (Next.js 14):** Autenticación completa con Clerk, conexión segura con Alpaca (`/me/broker`), visualizador de setups (`/signals`), calculadora de posición en TypeScript puro con tests Vitest, y panel de posiciones con alertas TP/SL informativas (`/me/positions`).

### 🟡 2. Parcialmente Implementado (Partial)
- **Billing con Stripe:** Backend completo con creación de clientes, sesiones de checkout/portal y verificación de webhooks (`borsenhirn/billing/`). *Faltan los botones de checkout en la interfaz de usuario de Next.js.*
- **Cache y Rate Limiting:** Cliente Redis con algoritmo Token Bucket y decoradores probados con 104× de aceleración (`borsenhirn/cache/`). *Aún no está cableado como middleware global en las rutas de FastAPI.*
- **Dashboard Streamlit ("Bitácora Nocturna"):** Panel operativo para monitoreo de trading en modo single-user (`dashboard.py`). *Funciona pero sus tests unitarios están temporalmente excluidos de CI y no es multi-tenant.*
- **Módulos de Inteligencia M1, M2, M4, M5:** Scripts funcionales en la raíz (`M1_research.py`, `m2_analyst.py`, `m4_whale.py`, `m5_assistant.py`) con Claude, FRED y SEC EDGAR. *Operan como herramientas CLI independientes; sus paquetes en `borsenhirn/m*/` son stubs vacíos y no están expuestos a la API SaaS.*
- **Contenedores (Docker):** `Dockerfile` y `docker-compose.yml` operativos para el bot y Streamlit. *Falta incorporar el servicio de Next.js y sincronizar versiones.*

### 🚧 3. En Desarrollo / Maqueta Demo (In Progress)
- **Frontend: Whale Alerts (`/dashboard/whale`):** Actualmente es una maqueta visual con el badge `MAQUETA DEMO` que renderiza una lista estática `MOCK_ALERTS`. Falta conectar con el parser 13F de `m4_whale.py`.
- **Frontend: Hirn Copilot (`/dashboard/hirn`):** Maqueta visual con `MAQUETA DEMO` y campo de texto deshabilitado. Falta exponer `m5_assistant.py` mediante un endpoint multi-tenant en FastAPI.
- **Frontend: Track Record Público (`/dashboard/track`):** Maqueta visual con `MAQUETA DEMO` y curva de equity simulada con `MOCK_CLOSED_TRADES`. Falta conectar a las métricas reales de `bot_trade_outcomes`.

---

## 🔬 Honestidad en Machine Learning

El modelo Random Forest actual sobre indicadores técnicos obtiene un **AUC ≈ 0.50** bajo validación walk-forward purgada con embargo — es decir, **rendimiento indistinguible del azar**.

El proyecto **no afirma tener un alpha predictivo resuelto**; afirma tener la **infraestructura matemática para detectar y demostrar si una estrategia tiene o no tiene edge**, evitando el autoengaño típico del overfitting y data leakage. Toda la metodología y resultados están documentados en [`PLAN_VALIDACION_ML.md`](PLAN_VALIDACION_ML.md).

---

## ⚠ Known Limitations & Development Setup

1. **Vistas Frontend en Maqueta:** Las secciones de *Ballenas*, *Asistente Hirn* y *Track Record* en el dashboard Next.js muestran datos de prueba con carteles visibles de advertencia.
2. **Módulos M1–M5 Desacoplados:** Los scripts de análisis macro, 13F y scraping funcionan vía línea de comandos pero no alimentan directamente el feed `/signals` del cliente (decisión tomada para mantener las señales deterministas y libres de alucinaciones de LLM).
3. **Credenciales en Entorno de Desarrollo:**
   - En entornos locales de prueba, la configuración utiliza contraseñas por defecto (`uriel`) para PostgreSQL. **En producción es obligatorio configurar variables de entorno reales.**
   - El auto-trader interno y el usuario de prueba comparten la misma cuenta de Alpaca Paper en desarrollo, por lo que el panel de posiciones puede mostrar compras ejecutadas por el bot. Para testing puro de usuario, use cuentas de paper trading separadas.
4. **Diferencias de Versión en Contenedores:**
   - **Target Host / Entorno Local:** Python 3.14.0 (`.python-version`) / PostgreSQL 18.
   - **Contenedores Docker Actuales:** `python:3.12-slim` en `Dockerfile` y `postgres:16-alpine` en `docker-compose.yml`.

---

## 🚀 Quick Start (Entorno Local)

### Prerrequisitos
- Python 3.12+ (recomendado 3.14)
- PostgreSQL 16+ con soporte de RLS
- Node.js 18+ (para el frontend de Next.js)
- Redis (opcional, para caché y rate limiting)

### 1. Clonar e Instalar Backend
```bash
git clone https://github.com/Obumbratio/proyecto_trading.git
cd proyecto_trading

# Crear entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1       # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS

# Instalar dependencias con hashes verificados
pip install pip-tools
pip-sync requirements.txt requirements-dev.txt
```

### 2. Configuración de Entorno
```bash
cp .env.example .env
# Configurar las variables en .env:
# - DB_USER, DB_PASSWORD, DB_NAME
# - BORSENHIRN_MASTER_KEY (clave Fernet para la bóveda)
# - CLERK_ISSUER, CLERK_JWKS_URL
# - ALPACA_API_KEY, ALPACA_SECRET_KEY
```

### 3. Migración de Base de Datos
```bash
psql -U postgres -d borsenhirn -f borsenhirn/safety/migrations.sql
```

### 4. Ejecución de Tests
```bash
# Tests de backend (414+ tests)
pytest -q

# Test de reproducibilidad del modelo
python scripts/verify_reproducibility.py

# Tests de la calculadora en el frontend
cd frontend
npm install
npm test
cd ..
```

### 5. Iniciar la Plataforma
Para levantar todo el stack en desarrollo:
```bash
# Iniciar API FastAPI (puerto 8000)
python -m uvicorn borsenhirn.api.main:app --host 0.0.0.0 --port 8000 --reload

# Iniciar Frontend Next.js (en otra terminal, puerto 3000)
cd frontend
npm run dev
```

O para ejecutar el dashboard Streamlit legacy:
```bash
streamlit run dashboard.py
```

---

## 📁 Estructura del Repositorio

```
proyecto_trading/
├── borsenhirn/
│   ├── anomaly/              # Detección de anomalías operativas y de volumen
│   ├── api/                  # FastAPI endpoints (/me, /signals, /me/orders)
│   ├── audit/                # Registro de auditoría inmutable
│   ├── auth/                 # Verificación JWT de Clerk (RS256 JWKS)
│   ├── backups/              # Exportación de datos per-tenant (GDPR)
│   ├── billing/              # Integración con Stripe (webhooks y sesiones)
│   ├── cache/                # Caché Redis y limitador de tasa Token Bucket
│   ├── dashboard/            # Componentes del dashboard Streamlit
│   ├── internal/autotrader/  # Cara interna: auto-trader 24/7 (NO-producto)
│   ├── legal/                # Control de versiones y aceptación legal (HTTP 451)
│   ├── ml/                   # PurgedKFold, labeling y auditoría de leakage
│   ├── news/                 # Feed de noticias agregadas vía Alpaca/Benzinga
│   ├── safety/               # Kill switches, checks de sanidad y alertas
│   ├── security/             # Bóveda de credenciales cifradas con Fernet
│   ├── signals/              # SignalEngine determinista y tarjetas honestas
│   ├── tenancy/              # Constantes y gestión de inquilinos (RLS)
│   └── workers/              # Orquestador multi-tenant de ciclos del bot
│
├── frontend/                 # Aplicación Next.js 14 (App Router)
│   ├── src/app/dashboard/    # Vistas de señales, broker, órdenes y maquetas
│   ├── src/components/       # Calculadora de riesgo, diálogo de compra
│   └── src/lib/              # Clientes de API, lógica pura de sizing (Vitest)
│
├── legal/                    # Documentación legal obligatoria
│   ├── DISCLAIMER.md         # Exención de responsabilidad
│   ├── TERMS.md              # Términos de servicio
│   └── PRIVACY.md            # Política de privacidad
│
├── scripts/                  # Herramientas CLI, validación ML y migraciones
├── tests/                    # 414+ tests unitarios, de integración y property-based
├── main.py                   # Loop del bot single-tenant / local
├── strategy.py               # Lógica técnica de indicadores (RSI/MACD/BB)
├── execution.py              # Wrapper de ejecución de órdenes en Alpaca
└── STATUS.md                 # Auditoría de estado y checklist de pendientes
```

---

## 📚 Documentación Técnica Detallada

| Documento | Contenido |
|---|---|
| [`STATUS.md`](STATUS.md) | **Auditoría oficial del repositorio, métricas y checklist de roadmap.** |
| [`PLAN_VALIDACION_ML.md`](PLAN_VALIDACION_ML.md) | Diagnóstico completo de ML: por qué el split 80/20 miente y cómo se implementó Purged CV. |
| [`MULTI_TENANCY.md`](MULTI_TENANCY.md) | Especificación de la arquitectura Postgres RLS y variables de sesión. |
| [`SECRETS.md`](SECRETS.md) | Diseño criptográfico de la bóveda Fernet y rotación de llaves. |
| [`INTEGRACION_SAFETY.md`](INTEGRACION_SAFETY.md) | Cableado de kill switches y verificaciones pre-orden. |
| [`RATE_LIMITING.md`](RATE_LIMITING.md) | Arquitectura del limitador de tasa y caché distribuido en Redis. |
| [`REPRODUCIBILIDAD.md`](REPRODUCIBILIDAD.md) | Protocolo de lockfiles con hashes y validación bit-a-bit. |

---

## ⚖ License

Uso educativo y de investigación. Para licencias comerciales o despliegue institucional, contactar al autor. Consultar [`legal/TERMS.md`](legal/TERMS.md).

---

## 👤 Autor

**Uriel Castañeda**  
GitHub: [@Obumbratio](https://github.com/Obumbratio)  
Portfolio orientado a roles de **Data Engineer / ML Engineer / MLOps**.
