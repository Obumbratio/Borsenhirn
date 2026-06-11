# ESTADO — Börsenhirn
> Actualizar al cerrar sesión. Pegar al abrir un chat nuevo.
> Misión y decisiones de fondo: ver [PLAN.md](PLAN.md). Log por bloque: [B1_SESSION_LOG.md](B1_SESSION_LOG.md).

## Última actualización
2026-06-11

## 🔌 Wire-up del ciclo real del bot al worker multi-tenant (2026-06-11)
Hecho: la lógica del motor se extrajo de `main.run()` (656 líneas) a
`borsenhirn/engine.py::BotEngine` (setup en `__init__` + un ciclo en `run_cycle()`,
sin dormir). `main.py` quedó fino (61 líneas, misma firma `run(train,once,live)`
— no rompe `bot_api`). Nuevo `borsenhirn/workers/bot_cycle.py::make_bot_cycle_fn()`
cachea un `BotEngine` por tenant y lo inyecta a `run_all_tenants`/`WorkerOrchestrator`.
Tests: 392 passed (387 baseline + 5 wiring deterministas en `tests/test_bot_cycle.py`).
**Limitaciones conocidas (TODO):** `send_alert`/`log_trade`/`register_external_alerter`
son globales (un solo webhook Discord; solo el DEFAULT tenant registra el alerter);
el plan de usuario (`my_plan`) usa archivo global, no scopeado por tenant.
**Pendiente:** smoke real 2-tenants paper (coloca órdenes paper) — comando:
`python -c "from borsenhirn.workers.runner import run_all_tenants; from borsenhirn.workers.bot_cycle import make_bot_cycle_fn; print(run_all_tenants(make_bot_cycle_fn()))"`

## 🏁 Dónde voy — ROADMAP SaaS B1..B10 COMPLETO y MERGEADO A MAIN
Los 10 bloqueadores (backends) construidos y testeados en `borsenhirn_dev`, en
**PR #1 mergeado a `main`** (`e483556`). Tests: 387 baseline + 41 integración
(gated `RUN_DB_INTEGRATION`), todo verde. Producción `borsenhirn` **intacta**.
Cierres por bloque en `docs/B{n}_CLOSEOUT.md`.

### ✅ Pendientes OPERACIONALES (no es código nuevo; checklist próxima sesión)
- [ ] **Ejecutar "B1 Bloque 8"** en el host de prod — el SaaS NO está vivo hasta esto.
      (prod `borsenhirn` vive en otra máquina, no en localhost). Scripts:
      `scripts/b1_block8_*`. Plan: [B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md).
- [ ] **Migrar a prod** las tablas/columnas de B3..B9: `clerk_user_id`,
      billing en `tenants`, `audit_log`, `legal_acceptance` (con B8). Scripts:
      `scripts/b3_block1_*`, `b4_block1_*`, `b5_block1_*`, `b7_block1_*`.
- [ ] **Keys reales en `.env` de prod:** Clerk (`AUTH_VERIFIER=clerk`,
      `CLERK_ISSUER`, `CLERK_JWKS_URL`), Stripe (`BILLING_PROVIDER=stripe`,
      `STRIPE_*`), `ADMIN_API_KEY`, master key vía secret manager.
- [ ] **Cron de backups** (`scripts/db_backup.sh`) + destino offsite — [B9_BACKUP_RUNBOOK.md](B9_BACKUP_RUNBOOK.md).
- [ ] **Frontend Next.js** (Clerk + checkout/portal + modal legal) — esfuerzo aparte.
- [x] **Wire-up del ciclo real del bot** en el worker (`cycle_fn`) — hecho 2026-06-11
      (`BotEngine` + `make_bot_cycle_fn`). Falta: smoke real 2-tenants paper + `scan_and_alert` por tenant.

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
Los 10 bloqueadores construidos y testeados en dev. **Pendientes operativos:**
ejecutar "B1 Bloque 8" (aplicar a prod en el host de prod) + las migraciones de
clerk_id/billing/audit/legal; poner keys reales (Clerk/Stripe); cron de backups;
frontend Next.js. Cierres por bloque en docs/B{n}_CLOSEOUT.md.

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

## ⏳ PENDIENTE CLAVE — ejecutar B1 Bloque 8 en prod
Intentado 2026-06-06: **prod `borsenhirn` NO está en el Postgres de localhost**
(solo `borsenhirn_dev` + `postgres`). La prod real vive en otra máquina/host
(deployment), inalcanzable desde esta sesión, y el usuario no tiene a mano dónde/cómo.
**Acción cuando se retome:** correr en el host de prod (con un `.env` que apunte a
`borsenhirn`): `b1_block8_backup.sh` → `apply.sh` → `create_role.sh` → `verify.sh`.
Todo validado en dev; scripts en `scripts/b1_block8_*`. Plan: [B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md).

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
