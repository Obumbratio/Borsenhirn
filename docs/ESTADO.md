# ESTADO — Börsenhirn
> Actualizar al cerrar sesión. Pegar al abrir un chat nuevo.
> Misión y decisiones de fondo: ver [PLAN.md](PLAN.md). Log por bloque: [B1_SESSION_LOG.md](B1_SESSION_LOG.md).

## Última actualización
2026-06-11

## ✅ PROD LOCAL-FIRST DESPLEGADA (2026-06-11) — DB `borsenhirn` viva y limpia
**Decisión:** local-first (en la máquina de Uriel, no nube — no rompe el principio, $0).
**Hecho (camino A, "DB nueva en el cluster local"):**
- DB `borsenhirn` creada en el Postgres local; **esquema clonado de `borsenhirn_dev`**
  (`pg_dump --schema-only`) → 21 tablas, 19 con RLS, idéntico a dev. Trae ya todo el
  multi-tenant final (RLS + clerk_id + billing + audit_log + legal_acceptance), así que
  **B1 Bloque 8 NO se necesitó** (sus scripts transformaban un prod single-user viejo
  inexistente; un prod nuevo se clona, no se transforma).
- Sembradas las 2 filas de sistema (`tenants`: SYSTEM …000 + default …001). **Sin datos
  de dev** (0 trades).
- Rol `borsenhirn_app` (ya existía en el cluster) con grants + CONNECT en `borsenhirn`.
  Smoke como rol app: NOSUPERUSER+NOBYPASSRLS, sin contexto→0 filas, RLS real ✓.
- `.env.prod` (gitignored, DB_NAME=borsenhirn) + `scripts/run_bot_prod.sh` (sourcea
  .env.prod; `config.load_dotenv()` no pisa env exportadas → prod gana sobre dev).
  Smoke del stack app contra prod: BotMemory OK (0 trades), Alpaca paper OK.

**Cómo correr el bot contra prod:** `bash scripts/run_bot_prod.sh`. Sin eso, el default
sigue siendo dev (`.env`). Plan/decisión: [DESPLIEGUE_PROD_PLAN.md](DESPLIEGUE_PROD_PLAN.md).

**Nota local-first:** prod y dev comparten cluster Postgres y el rol `borsenhirn_app`
(misma password) — la separación es a nivel DB + RLS, no de credenciales. OK para
local-first single-machine; si algún día prod sale a la nube, ahí sí rol/credenciales aparte.
**Pendiente menor:** el timer de anomalías y los systemd units apuntan a dev (`.env`);
para que monitoreen prod hay que sourcear `.env.prod` (ver run_bot_prod.sh como patrón).
Plan completo (por qué migrar + opciones L/C + secuencia): [DESPLIEGUE_PROD_PLAN.md](DESPLIEGUE_PROD_PLAN.md).
(Nota menor: ese `docker-compose.yml` tiene la password `uriel` hardcodeada y commiteada
— local/bajo riesgo, pero no reusarla si algún día prod sale de tu máquina.)

## 🖥️ Frontend Next.js — REBANADA 1 SCAFFOLDEADA (2026-06-11), falta app Clerk
Construir en rebanadas verticales. **Rebanada 1 (HECHA a nivel código):** `frontend/`
= Next.js 14 (App Router) + TS + Tailwind + `@clerk/nextjs` **v6** (v7 exige Next 15;
quedamos en Next 14). Node v24.16.0 vía nvm (sourcear `~/.nvm/nvm.sh` en shells no-interactivos).
Archivos: `src/middleware.ts` (protege /dashboard), `src/app/layout.tsx` (ClerkProvider +
header), `src/app/page.tsx` (landing), `src/app/dashboard/page.tsx` (server component:
toma JWT de Clerk y llama `GET /me`), `.env.local.example`. **TypeScript COMPILA**; el
build solo falla en prerender por `Missing publishableKey` (esperado sin keys).
Correr: `cd frontend && npm run dev` (tras poner keys). Después de R1: gate legal → billing → dashboard.

**Falta SOLO (del usuario) para correr/verificar R1 end-to-end:** crear app Clerk dev →
poner `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`/`CLERK_SECRET_KEY` en `frontend/.env.local` +
`AUTH_VERIFIER=clerk`/`CLERK_ISSUER`/`CLERK_JWKS_URL` en el `.env` del backend. Ahí
levantamos API (:8000) + `npm run dev` (:3000) y verificamos login → `/me`.

**Contrato del backend** (`borsenhirn/api/main.py`, FastAPI :8000) — verificado vivo:
`/health`, `/`, `/legal/current` responden OK. `/me`, `/me/legal*`, `/billing/*`,
`/me/audit`, `/me/export` requieren JWT Bearer (Clerk).

**Prerequisitos (del usuario, NO los hace Claude) — bloquean construir/verificar:**
1. **Node.js no instalado** (ni nvm/apt). Next.js lo necesita. Instalar vía nvm (sin sudo):
   `curl ... nvm install.sh | bash` → `nvm install --lts`.
2. **App de Clerk (tier dev, gratis):** da publishable key (frontend) + issuer/JWKS (backend).
3. **Configurar backend:** `AUTH_VERIFIER=clerk` + `CLERK_ISSUER` + `CLERK_JWKS_URL` en el env.
   HALLAZGO: hoy `/me` sin token da **HTTP 500** (no 401) — NO es bug: `build_verifier_from_env`
   tira `ValueError` porque no hay `AUTH_VERIFIER`/`AUTH_DEV_SECRET`. Con `AUTH_VERIFIER=clerk`
   se resuelve (sin token → 401 limpio; con token → OK). Stripe puede esperar (test mode).

Nada de frontend generado aún (no genero archivos que no puedo correr sin Node).

## 🔌 Wire-up del ciclo real del bot al worker multi-tenant (2026-06-11)
Hecho: la lógica del motor se extrajo de `main.run()` (656 líneas) a
`borsenhirn/engine.py::BotEngine` (setup en `__init__` + un ciclo en `run_cycle()`,
sin dormir). `main.py` quedó fino (61 líneas, misma firma `run(train,once,live)`
— no rompe `bot_api`). Nuevo `borsenhirn/workers/bot_cycle.py::make_bot_cycle_fn()`
cachea un `BotEngine` por tenant y lo inyecta a `run_all_tenants`/`WorkerOrchestrator`.
Tests: 393 passed (387 baseline + 5 wiring + 1 fix). **Smoke real validado**
(2026-06-11, mercado abierto): `run_all_tenants(make_bot_cycle_fn())` corrió un
ciclo real del DEFAULT contra Alpaca paper (regime BULL, trades OK). Destapó y
arregló un bug: el tenant SYSTEM (control-plane) figuraba ACTIVE y el orquestador
lo corría como tenant de trading → RLS violation; ahora `run_once` lo saltea
siempre (`67c494b`).
**Aislamiento per-tenant (2026-06-11, opción C):** cada `BotEngine` rutea sus
alertas a su propia `alert_mgr` (`_alert`, ya no al `send_alert` global), escribe
el trade-log CSV a ruta por-tenant (`_log_trade`) y lee/guarda el plan por tenant
(`my_plan.*(tenant_id=...)`). El DEFAULT conserva rutas/archivos globales (compat
dashboard/bot_api). `_handle_plan` pasó a método de `BotEngine`. Suite: 400 passed.
**Pendiente para tenants reales (no-default):** `BORSENHIRN_MASTER_KEY` (vault) +
creds por tenant; canales de alerta (Discord/email) por tenant en su `alert_mgr`.

## 🏁 Dónde voy — ROADMAP SaaS B1..B10 COMPLETO y MERGEADO A MAIN
Los 10 bloqueadores (backends) construidos y testeados en `borsenhirn_dev`, en
**PR #1 mergeado a `main`** (`e483556`). Tests: 387 baseline + 41 integración
(gated `RUN_DB_INTEGRATION`), todo verde. **No hay `borsenhirn` de producción
desplegada** (ver aviso ⛔ arriba) — todo el trabajo vive en `borsenhirn_dev`.
Cierres por bloque en `docs/B{n}_CLOSEOUT.md`.

### ✅ Pendientes OPERACIONALES (no es código nuevo; checklist próxima sesión)
- [ ] **DECISIÓN de despliegue (BLOQUEA B1 Bloque 8):** ¿SaaS en VPS de tercero sí/no?
      (rompe local-first). NO hay prod desplegado — ver el aviso ⛔ arriba.
- [ ] **Ejecutar "B1 Bloque 8"** — SOLO cuando exista prod. Scripts `scripts/b1_block8_*`
      (core + extras) listos/validados. Plan: [B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md).
      Hoy NO hay DB de prod a la que apuntar.
- [ ] **Migrar a prod** las tablas/columnas de B3..B7: `clerk_user_id`, billing en
      `tenants`, `audit_log`, `legal_acceptance`. **Variantes prod LISTAS y validadas
      (2026-06-11):** `scripts/b1_block8_extras_prod_migration.sql` + `_extras_apply.sh`
      (consolidado, guard prod, atómico/idempotente, validado en DB scratch). Corre como
      Paso 4.5 (tras rol + verify core). Los `b{3,4,5,7}_block1_*.sql` originales son dev-only.
- [ ] **Keys reales en `.env` de prod:** Clerk (`AUTH_VERIFIER=clerk`,
      `CLERK_ISSUER`, `CLERK_JWKS_URL`), Stripe (`BILLING_PROVIDER=stripe`,
      `STRIPE_*`), `ADMIN_API_KEY`, master key vía secret manager.
- [ ] **Cron de backups** (`scripts/db_backup.sh`) + destino offsite — [B9_BACKUP_RUNBOOK.md](B9_BACKUP_RUNBOOK.md).
- [ ] **Frontend Next.js** (Clerk + checkout/portal + modal legal) — esfuerzo aparte.
- [x] **Wire-up del ciclo real del bot** en el worker (`cycle_fn`) — hecho 2026-06-11
      (`BotEngine` + `make_bot_cycle_fn`); smoke real paper validado.
- [x] **`scan_and_alert` por tenant** — hecho 2026-06-11: pase de anomalías
      `borsenhirn/workers/anomaly_scan.py::scan_anomalies_all_tenants` (itera ACTIVE
      excl. SYSTEM, alert_mgr scoped por tenant, no saltea HALT, aísla errores).
      AlertManager factorizado a `bootstrap.build_alert_manager_from_config`. Suite: 404 passed.
- [x] **Agendado cada hora** (2026-06-11): systemd timer `scripts/borsenhirn-anomaly.timer`
      + service oneshot + entrypoint `scripts/run_anomaly_scan.py`. Instalación en
      [DEPLOY_ALWAYS_ON.md](DEPLOY_ALWAYS_ON.md) (la corre Uriel: `cp` units → `enable --now` el timer).

### Estado por bloque (todos ✅ backend)
B1 RLS · B2 Vault · B3 Auth Clerk · B4 Stripe · B5 Audit · B6 Workers ·
B7 Legal · B8 Kill-switch (per-tenant+global) · B9 Backups+export · B10 Anomaly.

> El detalle histórico por sub-bloque está más abajo (log del sprint).

**B3 (Auth Clerk): en progreso.** Decidido: 1 user Clerk = 1 tenant, pyjwt, provisión
lazy, user_id=tenant_id, solo endpoints nuevos protegidos. Plan: [B3_AUTH_PLAN.md](B3_AUTH_PLAN.md).
- B3.1 ✅ schema `clerk_user_id` + provisión (`provision_for_clerk_user`).
- B3.2 ✅ `borsenhirn/auth/` — `TokenVerifier` + `StaticTokenVerifier` (HS256, pyjwt). 11 tests.
- B3.3 ✅ `ClerkJWKSVerifier` (RS256+JWKS) + factory `build_verifier_from_env`.
  Config-driven (env); testeado con JWKS mockeado. Vars en `.env.example`.
  **Falta solo poner los valores reales de tu Clerk** (CLERK_ISSUER/JWKS_URL).
- B3.4 ✅ FastAPI `get_current_tenant` (`borsenhirn/auth/deps.py`) + endpoints
  `/me` y `/me/trades/count` en `api/main.py`. e2e: JWT→verify→provisión→RLS.
**Backend de B3 COMPLETO.** Para Clerk real en prod: poner `AUTH_VERIFIER=clerk`
+ `CLERK_ISSUER`/`CLERK_JWKS_URL` en el `.env`. Falta (aparte): frontend Next.js.
`api/main.py` ahora importa LAZY redis/sqlalchemy (solo en `/status` y `/signal`),
así la API y los endpoints `/me` corren sin esas libs. Baseline 323 passed.

**B4 (Stripe billing): en progreso.** Plan: [B4_BILLING_PLAN.md](B4_BILLING_PLAN.md).
- B4.1 ✅ columnas de billing en `tenants` (stripe_customer_id UNIQUE, subscription_id,
  plan, current_period_end) + `TenantManager.get_tenant_by_stripe_customer_id` / `set_billing`.
- B4.2 ✅ `borsenhirn/billing/`: `BillingProvider` + `StripeBillingProvider` +
  `FakeBillingProvider` + factory + mapeo stripe_status→tenant_status. 16 tests
  (firma de webhook verificada offline). SDK `stripe==12.5.1` en requirements.
- B4.3 ✅ `apply_stripe_event` + endpoint `/webhooks/stripe` (verifica firma, sync tenant.status). 8 tests.
- B4.4 ✅ endpoints `/billing/checkout` + `/billing/portal` (trial vía `STRIPE_TRIAL_DAYS`).
- B4.5 ✅ gating: `get_active_tenant` (402 si no active) en `/me/trades/count`;
  billing endpoints usan `get_current_tenant` (suspendido puede ir a pagar).
**Backend de B4 COMPLETO.** Para Stripe real: `BILLING_PROVIDER=stripe` + STRIPE_* en `.env`.
Falta (aparte): frontend (botones checkout/portal) + migración billing a prod. Baseline 354 passed.

**B5 (Audit log): en progreso.** Plan: [B5_AUDIT_PLAN.md](B5_AUDIT_PLAN.md). Decidido:
append-only por permisos, las 4 categorías, soft-fail.
- B5.1 ✅ tabla `audit_log` (RLS + append-only: app role solo INSERT+SELECT). 18/18 con RLS.
- B5.2 ✅ `borsenhirn/audit/` (`AuditLogger.record` + actor contextvar + soft-fail). 4 unit + 3 e2e.
- B5.3 ✅ hooks en las 4 categorías (credenciales set/get/delete, billing webhook,
  tenant lifecycle, kill-switch) + actor desde la auth dependency. Lazy + soft-fail.
- B5.4 ✅ endpoint `GET /me/audit` (el tenant ve su traza, RLS). e2e completo.
**Backend de B5 COMPLETO.** Falta (aparte): migración `audit_log` a prod (con B8). Baseline 361 passed.

**B6 (Worker isolation): framework COMPLETO.** Plan: [B6_WORKERS_PLAN.md](B6_WORKERS_PLAN.md).
Decidido: secuencial con aislamiento de errores. `borsenhirn/workers/`:
`load_broker_credentials` (vault + fallback), `TenantWorker` (contexto aislado),
`WorkerOrchestrator` (recorre activos, saltea HALT, try/except por tenant),
`run_all_tenants`/`make_halted_check`. 8 tests (7 unit + 1 e2e). Baseline 368.
Falta (aparte): wire-up del ciclo real del bot (reusar `main`) — el `cycle_fn` es inyectable.

**B7 (Legal): backend COMPLETO.** Plan: [B7_LEGAL_PLAN.md](B7_LEGAL_PLAN.md). Decidido:
gatear + Terms+Privacy. Tabla `legal_acceptance` (RLS + append-only), `borsenhirn/legal/`
(`record_acceptance`/`is_compliant`/`current_versions`), endpoints `/legal/current`,
`POST /me/legal/accept`, `GET /me/legal`, y gating `get_compliant_tenant` (451) en
`/me/trades/count`. Versiones en config. Suite integración completa: **35 passed**.
(De paso: fix de cleanups e2e por FK del hook de audit de B5.) Falta: migración a prod ("B1 Bloque 8").

**B8 (Kill switch): COMPLETO.** Per-tenant ya estaba (manual halt/clear + checks
automáticos; B6 lo respeta). Nuevo: kill-switch GLOBAL (`borsenhirn/safety/global_killswitch.py`
sobre el tenant SYSTEM), el orquestador saltea todo si está activo, endpoints admin
`/admin/killswitch/global` (GET/POST/clear, auth por `X-Admin-Key`=`ADMIN_API_KEY`).
Audita global_halt/clear. Suite integración: 37 passed. CLAUDE.md sincronizado.
Ojo numeración: "B1 Bloque 8" (aplicar a prod) ≠ "Roadmap B8 Kill switch".

**B9 (Backups): COMPLETO.** Plan: [B9_BACKUPS_PLAN.md](B9_BACKUPS_PLAN.md) ·
runbook: [B9_BACKUP_RUNBOOK.md](B9_BACKUP_RUNBOOK.md). `scripts/db_backup.sh`
(pg_dump -F c + verificación + retención KEEP, cron-friendly), `scripts/db_restore.sh`
(restore a DB nueva), y export por tenant (`borsenhirn/backups/export_tenant` +
`GET /me/export`, excluye user_credentials). Integración completa: 40 passed.
Falta (aparte): agendar cron + destino offsite en prod.

**B10 (Anomaly detection): COMPLETO.** Plan: [B10_ANOMALY_PLAN.md](B10_ANOMALY_PLAN.md).
`borsenhirn/anomaly/`: `build_snapshot` (audit_log + trading bajo RLS), reglas puras
(cred-access spike, killswitch burst, losing streak, volume spike), `AnomalyDetector.scan`
+ `scan_and_alert` (AlertManager; solo alerta — D1). Umbrales por env. 12 tests.
Integración completa: 41 passed.

## 🏁 ROADMAP SaaS COMPLETO (backends): B1..B10 ✅
Los 10 bloqueadores construidos y testeados en dev. **Pendientes operativos
(todos bloqueados por la decisión de despliegue — NO hay prod, ver ⛔ arriba):**
"B1 Bloque 8" + migraciones clerk_id/billing/audit/legal (scripts listos); keys
reales (Clerk/Stripe); cron de backups; frontend Next.js. Cierres: docs/B{n}_CLOSEOUT.md.

## Estado del Bloque 5 (refactor capa de app)
| Sub-bloque | Qué | Estado | Commit |
|---|---|---|---|
| 5.1 | `tenancy/constants.py` (SYSTEM/DEFAULT tenant UUIDs) | ✅ | `f02002d` |
| 5.2 | Rol `borsenhirn_app` (NOSUPERUSER/NOBYPASSRLS) + rename GUC `app.current_tenant_id` | ✅ | DB-only |
| 5.3 | `borsenhirn/db.py` (pools app/admin, `get_conn`, `bypass_rls`) | ✅ | `f02002d` |
| 5.4.a | refactor `bot_memory_pg.py` → tenant context | ✅ | `8ea2bb6` |
| 5.4.b | refactor `borsenhirn/security/credentials.py` | ✅ | `72ee927` |
| 5.4.c | refactor `borsenhirn/safety/state_store_pg.py` | ✅ | `64321ce` |
| 5.5.b | `bootstrap.py` + `api/main.py` wire-up | ✅ | `5678d24` |
| 5.5.a | `main.py` wire-up + fix bug import `_get_conn` | ✅ | `e6fec1a` |
| 5.6 | Tests integración RLS end-to-end (rol app real) | ✅ verificado | sin commit aún |
| 5.7 | Docs `B1_APP_LAYER.md` + cierre log Bloque 5 | ✅ | sin commit aún |

## Hecho (resumen físico en DB dev)
- 17 tablas con `tenant_id` NOT NULL + FK + index + RLS forzado + 2 policies c/u (34 policies).
- 128 filas legacy backfilled al default tenant `00000000-…001`.
- 4 legacy dropeadas en dev (`bot_state`, `entry_context`, `regime_stats`, `symbol_memory`).
- Rol `borsenhirn_app` creado; `config.py` lee `APP_DB_USER`/`APP_DB_PASSWORD` con fallback a admin.
- Bug latente arreglado: `main.py` importaba `_get_conn` borrado en 5.4.a → `import main` OK.

## ⏳ B1 Bloque 8 — BLOQUEADO: no hay prod desplegado (corregido 2026-06-11)
**Corrección importante:** la suposición previa de que "la prod real vive en otra
máquina/host inalcanzable" era **errónea**. Verificado en WSL (2026-06-11): NO hay
ningún server/VPS — `~/.ssh/config` no existe, `known_hosts` solo tiene GitHub, la
máquina nunca se conectó a ningún host. **No existe `borsenhirn` de producción en
ningún lado.** El único Postgres es el local (`borsenhirn_dev` + `postgres`).

**Por lo tanto B1 Bloque 8 NO se puede ni se debe ejecutar todavía** — no hay DB a
la que apuntar. Los scripts (`b1_block8_*` core + extras) están listos/validados y
esperan. **El paso previo obligatorio es la DECISIÓN de despliegue** (SaaS en VPS de
tercero sí/no — rompe local-first), que Uriel toma en frío. Ver el aviso ⛔ al inicio.

## Hallazgo RESUELTO (B7) — pool-leak en safety stack
`PostgresStateStore` sacaba conn con `self.get_conn()` y nunca la devolvía → el bot
agotaba el pool (max 10) tras ~10 iteraciones del loop. Fix: helper `_acquire` en
`state_store_pg.py` que entra/sale del context manager `bdb.get_conn` (devuelve la
conn al pool); `main._safety_get_conn` ahora devuelve `bdb.get_conn(role="app")`.
Backward-compat con conn plano (ks_admin/test_alerts) preservada. Test de regresión
`test_safety_no_pool_leak` (3× el pool sin agotarse).

## Métricas
- pytest baseline: **267 passed, 57 skipped** (los módulos de integración 5.6 +
  Bloque 6 se saltan por default sin `RUN_DB_INTEGRATION`).
- Integración (con `RUN_DB_INTEGRATION=1`): **13 passed** (6 de 5.6 + 7 de B6).
- `check_rls_coverage.py --strict`: 17/17 tablas con RLS, 0 sin RLS. Exit 0.
- Backup branch pre-sprint: `backup-pre-b1-20260426`.

## 5.6 — hecho (2026-06-05)
Artefactos: `tests/test_b1_rls_integration.py` (6 tests), gate en `tests/conftest.py`
(`RUN_DB_INTEGRATION`), `scripts/b1_block4_test_isolation.sh` (equivalente bash).
Resultado verificado contra `borsenhirn_dev` con el rol `borsenhirn_app` real:
sin contexto→0 · default→31 · UUID ajeno→0 · bypass_rls→31 · rol NOSUPERUSER+NOBYPASSRLS.
Correr: `RUN_DB_INTEGRATION=1 venv/bin/pytest tests/test_b1_rls_integration.py`
(tras `source .env.dev`), o `bash scripts/b1_block4_test_isolation.sh`.

**Pendiente de commit** (workflow manual): artefactos de 5.6 + 5.7 + Bloque 6
(`tests/test_b1_rls_isolation_full.py`) + fix `config.py` (alias `DB_PASS`) + docs.

## Notas / reglas vivas
- Prod `borsenhirn` intacta (vive en otro host; ver pendiente B8). Trabajo en `borsenhirn_dev`.
- Commits automáticos OK en local; **push a GitHub requiere confirmación**. Cosas de prod las corre Uriel.
- GUC canónico de RLS: `app.current_tenant_id` (alineado al módulo `tenancy/db.py` existente).
