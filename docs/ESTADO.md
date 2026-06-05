# ESTADO — Börsenhirn
> Actualizar al cerrar sesión. Pegar al abrir un chat nuevo.
> Misión y decisiones de fondo: ver [PLAN.md](PLAN.md). Log por bloque: [B1_SESSION_LOG.md](B1_SESSION_LOG.md).

## Última actualización
2026-06-05

## Dónde voy
Sprint B1 multi-tenancy Phase B · **DEV-COMPLETE** (Bloques -1..7 + 9) · branch `feature/multi-tenancy-phase-b`
Única acción pendiente: **ejecutar Bloque 8** (aplicar a prod). Los 6 scripts están
generados y validados (dry-run idempotente sobre dev OK), esperando la ventana de
mantenimiento. **Nada aplicado a prod todavía.**
Cierre del sprint: [B1_CLOSEOUT.md](B1_CLOSEOUT.md) · Plan prod: [B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md).

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

## Qué falta para "misión cumplida"
**Bloque 8 (aplicar a prod `borsenhirn` con backup; legacy se RENAME no DROP — incluir
la migración DEFAULT del Bloque 7)** → Bloque 9 (docs final).

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
- Prod `borsenhirn` intacta. Todo el trabajo contra `borsenhirn_dev`. Workflow manual (yo corro, pego output).
- NUNCA commits/push automáticos.
- GUC canónico de RLS: `app.current_tenant_id` (alineado al módulo `tenancy/db.py` existente).
