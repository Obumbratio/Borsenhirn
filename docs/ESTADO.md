# ESTADO — Börsenhirn
> Actualizar al cerrar sesión. Pegar al abrir un chat nuevo.
> Misión y decisiones de fondo: ver [PLAN.md](PLAN.md). Log por bloque: [B1_SESSION_LOG.md](B1_SESSION_LOG.md).

## Última actualización
2026-06-06

## Dónde voy
**B1 DEV-COMPLETE** (pendiente: ejecutar Bloque 8 en prod — 6 scripts listos, ver
[B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md) / [B1_CLOSEOUT.md](B1_CLOSEOUT.md)).
**Ahora: B2 Vault — en progreso.** Foco: sacar la master key de `.env`.
Hecho: (1) capa de secret providers (`secret_provider.py` — file/command/env,
`Vault.from_provider()`, `config` resuelve vía la cadena; 19 tests). (2) rotación
operacionalizada (`rotate_master_key.py`: keys vía provider, guard anti no-op que
exige rol admin con visibilidad cross-tenant, aviso 0-filas; 7 tests). Doc en
`SECRETS.md`. Baseline 293 passed. Branch `feature/multi-tenancy-phase-b`.
Pendiente B2 (opcional / depende de B3): envelope encryption per-tenant, modelo
user_id↔tenant_id, audit de acceso (probable B5).

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
- B4.4 ⏳ endpoints checkout/portal. B4.5 ⏳ gating por status. Baseline 347 passed.

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
