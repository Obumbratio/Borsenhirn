# B1 Multi-tenancy Phase B — Session Log

**Sprint:** Fase B — Habilitar Row-Level Security en tablas legacy del bot
**Branch:** `feature/multi-tenancy-phase-b`
**Inicio:** _pendiente confirmación bloque -1_
**DB producción (NO TOCAR hasta bloque 8):** `borsenhirn`
**DB de trabajo:** `borsenhirn_dev` (copia de producción)

Cada entrada lleva: timestamp UTC, bloque, qué se hizo, resultado.
Este archivo es nuestro audit trail si algo falla.

---

## Entradas

### 2026-04-26 — Bloque -1: Setup previo

**Pendiente outputs del usuario.**

Lado-IA (completado por Claude):
- [ ] `docs/B1_SESSION_LOG.md` creado.
- [ ] `.gitignore` actualizado con `backups/`, `*.dump`, `*.sql.gz`, `.env.dev`, `.env.local`.
- [ ] Carpeta `backups/` creada con `.gitkeep`.
- [ ] `scripts/b1_env_check.ps1` generado (PowerShell para Windows/WSL).
- [ ] `scripts/b1_env_check.sh` generado (bash equivalente).

Lado-usuario (Uriel, en Windows/WSL):
- [ ] Correr `scripts/b1_env_check.ps1` (o `.sh`) y pegar output.
- [ ] Confirmar versión de Postgres + host:port + user para conexión.
- [ ] Confirmar que NO hay procesos del bot corriendo, o detenerlos.

---

<!-- Próximas entradas se agregan abajo -->

### 2026-04-26 — Bloque -1: Recovery from environment issues

**Problema detectado:** después del primer intento de Bloque -1 quedaron
3 issues bloqueantes:

1. **Lock fantasma `.git/index.lock`** que silenciosamente hacía fallar
   comandos como `git stash`, `git rm`, `git add`. Causa: comando git
   interrumpido (PyCharm o antivirus de Windows).
2. **Repo MUY desactualizado:** 42 modificados + 30+ untracked,
   incluyendo archivos críticos del proyecto (`borsenhirn/`, tests,
   docs nuevos del Sprint completo).
3. **Conexión Postgres por validar:** WSL2 sobre Windows con Postgres
   en Windows host. IP detectada `172.25.144.1` pero conexión no
   probada end-to-end con password real.

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_unlock_git.sh` — desbloquea `.git/index.lock` con
      confirmación explícita y diagnóstico de procesos git activos.
- [x] `scripts/b1_clean_git.sh` — refuerza `.gitignore` (idempotente) +
      destrackea archivos basura + crea rama `backup-pre-b1-YYYYMMDD`.
- [x] `scripts/b1_test_postgres.sh` — prueba conexión a Postgres con
      fallback automático a IP de Windows host.
- [x] `docs/B1_RECOVERY.md` — orden exacto de ejecución (5 pasos).

**Lado-usuario (Uriel, en WSL):**
- [x] Cerrar PyCharm. (asumido — el lock no apareció)
- [x] `b1_unlock_git.sh` no fue necesario (clean_git no abortó por lock).
- [x] `bash scripts/b1_clean_git.sh` → **OK**. 7 líneas agregadas a
      .gitignore (idempotente). `.idea/` (6 archivos) y
      `.claude/settings.local.json` destrackeados. Rama
      `backup-pre-b1-20260426` creada.
- [x] `bash scripts/b1_test_postgres.sh` → **FAIL**.
      - localhost: Connection refused
      - 172.25.144.1: Timeout expired
- [ ] Si todo OK → "ok recovery, arranca bloque 0".

**Análisis del fallo Postgres:** Postgres en Windows escucha solo en
localhost por default. Hay que abrir TCP a la subnet WSL2 antes de
poder hacer dump/restore desde WSL.

### 2026-04-26 — Bloque -1: Postgres listen_addresses fix

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_diagnose_postgres.ps1` — diagnóstico read-only (servicio,
      listen_addresses actual, pg_hba.conf reglas, firewall, IP host WSL).
- [x] `docs/B1_POSTGRES_FIX.md` — instrucciones manuales paso a paso
      (4 pasos) + Plan B (Postgres en WSL si Windows fix es muy doloroso).

**Lado-usuario (Uriel):**
- [ ] PowerShell admin → `b1_diagnose_postgres.ps1` → pegar output.
- [ ] Editar `postgresql.conf` → `listen_addresses = '*'`.
- [ ] Editar `pg_hba.conf` → agregar `host all all 172.16.0.0/12 scram-sha-256`.
- [ ] `Restart-Service postgresql-x64-18` (admin).
- [ ] (Si hace falta) Abrir firewall puerto 5432.
- [ ] Re-correr `b1_test_postgres.sh` → confirmar `HOST_BLOQUE_0=...`.

**Restricciones aplicadas en este lote:**
- Solo modificados/creados: `scripts/`, `docs/`, `.gitignore` (este
  último a través del propio script clean para que sea idempotente).
- NO se tocó código del proyecto (`borsenhirn/`, `main.py`, tests, etc.).
- NO se ejecutaron operaciones de red ni tocó Postgres real.
- NO se hicieron commits.

### 2026-04-26 — Bloque -1: CERRADO ✅

**Resultado de pasos del usuario:**
- [x] `b1_diagnose_postgres.ps1` (PowerShell admin) → output limpio.
- [x] Verificó: `listen_addresses = '*'` ya estaba (no requirió cambio).
- [x] `pg_hba.conf` editado: agregada línea `host all all 172.16.0.0/12 scram-sha-256`.
- [x] `Restart-Service postgresql-x64-18` → Status=Running OK.
- [x] Firewall: nueva regla `PostgreSQL WSL2 5432` con `RemoteAddress=172.16.0.0/12`.
- [x] `b1_test_postgres.sh` → **OK** desde `172.25.144.1` (PostgreSQL 18.3).

**Datos confirmados para bloque 0:**
- `DB_HOST=172.25.144.1`
- `DB_PORT=5432`
- `DB_USER=postgres`
- `DB_PROD=borsenhirn`
- Versión: PostgreSQL 18.3 on x86_64-windows.

**Commits realizados:**
- `61af2c5` — "Sprint completo: gaps 1-8 + auditoria + B1 setup" (161 archivos).
- `e422630` — "feat: track bot_memory_pg + circuit_breaker (untracked en commit anterior)".
- Branch: `feature/multi-tenancy-phase-b` (creada desde main + 2 commits arriba).
- Backup branch: `backup-pre-b1-20260426` (apunta al state pre-cleanup).

**Untracked aún (todos del sprint dashboard, no bloquean):**
- `.streamlit/config.toml`, `data/whale_cache.json`, `BITACORA_DESIGN.md`,
  `bitacora_preview.html`, `dashboard.py.backup`.

---

### 2026-04-26 — Bloque 0: setup git + dump + base de copia

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_block0_setup.sh` — script todo-en-uno: pg_dump,
      createdb, pg_restore, comparación de row counts, generación
      de `.env.dev`. Pide confirmación entre cada paso destructivo.
      Validado: 233 líneas, ASCII puro, 0 NULs, sintaxis OK.

**Lado-usuario (Uriel, en WSL bash):**
- [ ] `bash scripts/b1_block0_setup.sh` → confirmar cada `yes` cuando pregunte.
- [ ] Pegar output completo a Claude.

**Lo que va a hacer el script:**
1. Pre-flight: verifica psql/pg_dump/pg_restore en PATH + .env válido.
2. Confirma conexión a `borsenhirn@172.25.144.1` (read-only `SELECT version()`).
3. **pg_dump** (read-only) → `backups/pre_b1_YYYYMMDD_HHMM.dump`.
4. **createdb borsenhirn_dev** (si ya existe pide confirmar drop).
5. **pg_restore** del dump → `borsenhirn_dev`.
6. Compara row counts tabla por tabla entre prod y dev (sanity check).
7. Genera `.env.dev` (copia de `.env` cambiando DB_HOST y DB_NAME).
8. Resumen final.

**Garantías:**
- Producción `borsenhirn` solo se LEE (pg_dump). Cero escrituras.
- Si `borsenhirn_dev` ya existe, pide confirmación explícita antes de drop.
- Si `.env.dev` ya existe, pide confirmación antes de sobrescribir.
- Script puede correrse varias veces (idempotente respecto a producción).

---

### 2026-04-26 — Bloque 1: CERRADO ✅ (categorización final)

**Resumen:** clasificadas las 22 tablas de `borsenhirn_dev` en
A/B/DROP_DEV. Cero unknowns pendientes.

**Inspector ejecutado:**
- `scripts/b1_block1_inspect_unknown.sh` (360 líneas, ASCII puro,
  read-only) sobre las 9 tablas cat-D.
- Output a `docs/B1_TABLE_INSPECT.md`: rowcount real, columnas,
  rango de timestamps, sample 2 rows, FKs salientes, grep de uso
  en código (`main.py`, `bot_memory_pg.py`, `borsenhirn/`,
  `scripts/`, `tests/`).

**Decisiones tomadas (categorización final):**

Migrar a A (17 tablas):
- 9 originales del bot: `bot_daily_state`, `bot_entry_context`,
  `bot_entry_prices`, `bot_ml_metrics`, `bot_ml_training`,
  `bot_performance`, `bot_regime_stats`, `bot_symbol_scores`,
  `bot_trade_outcomes`.
- 5 reclasificadas desde cat-D con datos vivos o uso en código:
  `assistant_history` (12), `assistant_suggestions` (1),
  `daily_reports` (0), `signals` (0, feature futuro),
  `trades` (0, usada por `tenancy/db.py` como demo).
- 3 reclasificadas desde cat-C: `alerts_log` (3),
  `killswitch_state` (0), `user_credentials` (0).
  Razón: la fase A solo creó la infraestructura (`tenants` +
  helpers), no migró estas tablas. Quedaron pendientes.

DROP en `borsenhirn_dev` (4 tablas, 0 filas + 0 usos):
- `bot_state` → legacy de `bot_daily_state`.
- `entry_context` → legacy de `bot_entry_context`.
- `regime_stats` → legacy de `bot_regime_stats`.
- `symbol_memory` → legacy de `bot_symbol_scores`.
Confirmadas huérfanas: el inspector mostró 0 referencias en
todos los `.py` del repo.

NO TOCAR (1 tabla):
- `tenants` → es el destino del FK; ya tiene su lugar y no se
  referencia a sí misma.

**Política de DROP en producción (Bloque 8):**
Las 4 legacy NO se dropean directo en `borsenhirn`. Se renombran
a `_legacy_<nombre>` para revisión manual antes de borrado
definitivo. Razón: el dump es de un momento puntual; en
producción podrían haberse escrito filas después que el
inspector de dev no ve. Mejor archivar que borrar irreversible.

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_block1_inspect_unknown.sh` generado y validado
      (bash -n OK, ASCII puro, 0 NUL bytes).
- [x] `docs/B1_TABLE_AUDIT.md` reescrito con tabla de decisión
      final + listas Python listas para copiar a scripts.
- [x] Esta entrada agregada al SESSION_LOG.

**Lado-usuario (Uriel):**
- [x] Corrió `b1_block1_inspect_unknown.sh` y revisó output.
- [x] Decidió categorización A/DROP/no-tocar para las 12 tablas
      en discusión (9 cat-D + 3 cat-C).
- [x] Confirmó política de archivar-en-prod vs drop-en-dev.

---

### 2026-04-26 — Bloque 2: setup migration script

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_block2_migration.sql` — migración idempotente
      con safety guard (aborta si DB=`borsenhirn`). Operaciones
      en una sola transacción (`BEGIN`/`COMMIT`):
      1. INSERT del default tenant
         (`00000000-0000-0000-0000-000000000001`).
      2. DROP de las 4 legacy (CASCADE).
      3. ADD COLUMN `tenant_id UUID` NULL en las 17 tablas A.
      4. FK a `tenants(id)` ON DELETE RESTRICT (idempotente:
         drop-then-add por nombre).
      5. INDEX `ix_<tabla>_tenant_id` en cada una.
      6. Verificación final con SELECTs de control.
- [x] `scripts/b1_block2_apply.sh` — wrapper bash que carga
      `.env.dev`, valida que NO sea producción, muestra
      pre-state, pide `yes` explícito, y aplica con
      `psql -1 -v ON_ERROR_STOP=1`.

**Lado-usuario (Uriel, en WSL bash):**
- [x] Revisar `scripts/b1_block2_migration.sql`.
- [x] `bash scripts/b1_block2_apply.sh` → confirmar `yes`.
- [x] Pegar output completo (incluye verificaciones finales).

**Garantías:**
- Solo corre contra `borsenhirn_dev` (aborta si DB_NAME=`borsenhirn`,
  doble check: en bash y en SQL con `current_database()`).
- Atómico: una sola transacción. Si algo falla, rollback total.
- Idempotente: re-correrlo no rompe nada (todos los `IF NOT EXISTS`
  + drop-then-add para FKs).
- NO toca `.env`, `.env.example`, código del proyecto, ni producción.

---

### 2026-04-26 — Bloque 2: CERRADO ✅ (post fix)

**Issues encontrados por Uriel ANTES de aplicar (3 catches críticos):**

1. **Esquema real de `tenants` distinto al asumido.** PK es `tenant_id`
   (no `id`); además requiere `slug`, `email`, `display_name`, `status`,
   `metadata` como NOT NULL. El INSERT del default se reescribió con
   los 6 campos.
2. **`tenants` vacía** en `borsenhirn_dev` → confirmado que `ON CONFLICT
   (tenant_id) DO NOTHING` sigue siendo idempotente para re-runs.
3. **1 tabla preexistente con `tenant_id`** (Phase A creó
   `user_credentials` con su propio FK). Riesgo: el FK preexistente
   podía tener nombre o `ON DELETE` distinto al canónico.

**Fix robusto aplicado al loop `$fkidx$`:** ahora dropea CUALQUIER FK
existente desde la tabla a `tenants` (loop dinámico sobre
`pg_constraint`), antes de crear el FK canónico
`fk_<tabla>_tenant ... REFERENCES tenants(tenant_id) ON DELETE RESTRICT`.
Cada drop loguea un `RAISE NOTICE` para auditoría.

**Bug del wrapper detectado de paso:** la función `show_count` redirigía
`stderr` a `/dev/null`, lo que hizo que el primer run abortara
silenciosamente cuando una query tenía un column name inválido. Fix:
ahora propaga stderr y devuelve exit code claro.

**Resultado del run en `borsenhirn_dev`:**
- 17 tablas con `tenant_id` agregado (de 0 → 17).
- 17 FKs a `tenants(tenant_id)` con `ON DELETE RESTRICT`.
- 17 indexes `ix_<tabla>_tenant_id`.
- 4 tablas legacy dropeadas (`bot_state`, `entry_context`,
  `regime_stats`, `symbol_memory`).
- 1 default tenant insertado (UUID `00000000-...001`).
- "Misterio 18 vs 17" resuelto: la query de `tenants` con
  `tenant_id` PK contaba sobre la tabla destino. Filtro
  `WHERE table_name <> 'tenants'` devolvió 17 correctamente.

**Lado-IA (post-cierre):**
- [x] Migration SQL fixed (esquema real + FK robusto + verifs).
- [x] Wrapper bash fixed (stderr visible + ambas queries del
      default tenant con `tenant_id`).
- [x] Validado: ASCII puro, 0 NULs, `bash -n` OK, 0
      ocurrencias de `tenants(id)` literal.

---

### 2026-04-26 — Bloque 3: backfill + SET NOT NULL

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_block3_migration.sql` — migración idempotente
      con safety guard. 4 etapas en una sola transacción:
      0. Sanity: confirmar default tenant existe (sino aborta).
      1. UPDATE de las 17 tablas SET tenant_id = default
         WHERE tenant_id IS NULL (idempotente; loguea rows por
         tabla con `RAISE NOTICE`).
      2. Verify NULL = 0 (`RAISE EXCEPTION` si alguna tabla
         todavía tiene NULL → rollback).
      3. ALTER COLUMN tenant_id SET NOT NULL en las 17 tablas
         (no-op si ya NOT NULL).
      4. Per-table count assigned-to-default + verifs finales.
- [x] `scripts/b1_block3_apply.sh` — wrapper con mismo patrón
      que Bloque 2: load `.env.dev`, doble guard, smoke test,
      pre-state con NULL counts por tabla, confirma `yes`,
      aplica con `psql -1 -v ON_ERROR_STOP=1`, post-state.

**Lado-usuario (Uriel, en WSL bash):**
- [ ] Revisar `scripts/b1_block3_migration.sql`.
- [ ] `bash scripts/b1_block3_apply.sh` → confirmar `yes`.
- [ ] Pegar output completo.

**Datos esperados a backfilear (~128 filas distribuidas):**
- Bot core: bot_daily_state (17), bot_entry_context (12),
  bot_entry_prices (12), bot_performance (12), bot_symbol_scores (21),
  bot_trade_outcomes (31), bot_ml_training (4), bot_regime_stats (3).
- M5 Hirn: assistant_history (12), assistant_suggestions (1).
- Operativas: alerts_log (3).
- Tablas vacías que igual reciben SET NOT NULL: bot_ml_metrics,
  daily_reports, killswitch_state, signals, trades, user_credentials.

### 2026-04-26 — Bloque 3: CERRADO ✅

**Resultado del run en `borsenhirn_dev`:**
- Backfill exacto de **128 filas** al default tenant `00000000-...001`,
  match perfecto al pronóstico: 31 bot_trade_outcomes, 21 bot_symbol_scores,
  17 bot_daily_state, 12 bot_entry_context, 12 bot_entry_prices,
  12 bot_performance, 12 assistant_history, 4 bot_ml_training,
  3 bot_regime_stats, 3 alerts_log, 1 assistant_suggestions.
- Verify NULL = 0 pasó en las 17 tablas (sin `RAISE EXCEPTION`).
- `SET NOT NULL` aplicado a las 17 (las 6 vacías recibieron NOT NULL
  preventivo: bot_ml_metrics, daily_reports, killswitch_state,
  signals, trades, user_credentials).

**Garantía:** idempotente — re-run no reasigna nada (UPDATE filtra
`WHERE tenant_id IS NULL`).

---

### 2026-04-26 — Bloque 4: RLS policies

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_block4_migration.sql` + `b1_block4_apply.sh` —
      `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` en las
      17 tablas A, con 2 policies PERMISSIVE por tabla:
      - `tenant_isolation`: filas visibles solo si
        `tenant_id = current_setting(<guc>)::uuid`.
      - `admin_bypass`: acceso total si
        `current_setting('app.bypass_rls') = 'on'`.

**Lado-usuario (Uriel):**
- [x] Revisó y aplicó la migración.
- [x] **Catch crítico:** detectó que el Bloque 4 usó el GUC
      `app.current_tenant` mientras el módulo existente `tenancy/db.py`
      (Fase A) ya usaba `app.current_tenant_id`. Decidió **alinear la DB
      al código existente** (no al revés). → motivó el Bloque 4.5.

---

### 2026-04-26 — Bloque 4.5: rename del GUC ✅

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_block4_5_rename_guc.sql` + `b1_block4_5_apply.sh` —
      DROP + CREATE de las 34 policies usando el GUC canónico
      `app.current_tenant_id`.

**Resultado / verificación final:**
- 17/17 RLS enabled · 17/17 RLS forced · 17/17 `tenant_isolation` ·
  17/17 `admin_bypass`.
- GUC unificado en `app.current_tenant_id` en DB y código.

---

### 2026-04-27 — Bloque 5.1: Foundation ✅ (commit `f02002d`)

- [x] `borsenhirn/tenancy/constants.py` como source of truth de UUIDs:
      - `SYSTEM_TENANT_ID` = `00000000-...000` (sentinel cross-cutting,
        NO existe como fila — reservado para data shared global futura).
      - `DEFAULT_TENANT_UUID` = `00000000-...001` (tenant real del
        backfill, dueño de las 128 filas legacy hasta que llegue auth B3).
- [x] Reexports preservan contratos existentes. 31 tests de tenancy OK.

---

### 2026-04-27 — Bloque 5.2: rol Postgres + GUC ✅ (DB-only)

**Lado-IA:**
- [x] `scripts/b1_block5_create_role.sql` + `b1_block5_create_role.sh` —
      rol `borsenhirn_app` con `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB`.
      GRANTs: CONNECT en DB, USAGE en schema, CRUD en las 17 tablas A,
      **SELECT-only en `tenants`** (lifecycle es admin), USAGE,SELECT en
      sequences. Verificación que **aborta** si BYPASSRLS/SUPERUSER están
      seteados o si tiene INSERT en `tenants`. Wrapper pide password
      silencioso, valida >=16 chars, smoke test conectando como el rol.
- [x] `config.py` lee `APP_DB_USER` + `APP_DB_PASSWORD` con fallback a
      admin (preserva single-user dev sin setup extra).

**Lección (psql):** `:'var'` no se sustituye dentro de `DO` blocks.
Primer intento falló con syntax error. Solución: `\if/\gset` con
CREATE/ALTER ROLE en SQL plano.

---

### 2026-04-27 — Bloque 5.3: `borsenhirn/db.py` ✅ (commit `f02002d`)

- [x] Módulo nuevo top-level. API pública:
      - `get_app_pool()` / `get_admin_pool()` — pools lazy (no abren al import).
      - `get_conn(role='app')` — context manager del pool correcto.
      - `set_tenant` — alias de `TenantContext` (sintaxis user-friendly).
      - `bypass_rls(conn)` — context manager para admin cross-tenant.
      - `set_connection_factory()` — hook para tests que monkeypatchean.
- [x] Rollback automático si quedó txn abierta sin commit.
- [x] Cero callers (módulo inerte). pytest 267 passed.

---

### 2026-04-28 — Bloque 5.4: refactor de los 3 módulos de persistencia

- [x] **5.4.a `bot_memory_pg.py`** (commit `8ea2bb6`): constructor
      acepta `tenant_id = DEFAULT_TENANT_UUID`; elimina pool propio
      (`_get_pool`, `_get_conn`, `_pool` global); `_db()` ahora va por
      `bdb.get_conn(role='app')` + `set_tenant`. Bootstrap DDL usa pool
      **admin** (CREATE TABLE no permitido al rol app). 27 métodos
      públicos sin cambio estructural.
- [x] **5.4.b `borsenhirn/security/credentials.py`** (commit `72ee927`):
      constructor `tenant_id: Optional = None` (default None preserva
      backwards compat de 24 tests que mockean); helper `_scoped_cursor`
      envuelve cursor con TenantContext si hay tenant; los 6 métodos lo usan.
- [x] **5.4.c `borsenhirn/safety/state_store_pg.py`** (commit `64321ce`):
      mismo patrón. `PostgresStateStore` + `make_dashboard_db_write`
      aceptan tenant_id opcional. `ks_admin.py` no requiere cambios
      (default None).
- pytest se mantuvo en 267 passed durante los 3 refactors.

**Lección:** `tenant_id=None` por default fue la red de seguridad —
protegió cobertura desigual y backwards compat sin riesgo.

---

### 2026-04-29 — Bloque 5.5.b: bootstrap.py + api/main.py ✅ (commit `5678d24`)

- [x] `SafetyStack.init_from_config(get_conn_fn, tenant_id=None)` propaga
      tenant a `PostgresStateStore` y `make_dashboard_db_write`. Docstring
      actualizado con ejemplo usando `bdb.get_app_pool()`.
- [x] `api/main.py` recibe TODO comment para wire-up futuro de Clerk JWT
      (out of scope hasta Bloque B3 del roadmap SaaS).
- [x] Health check script read-only agregado (commit entre 5.5.b y 5.5.a).

---

### 2026-04-29 — Bloque 5.5.a: main.py ✅ (commit `e6fec1a`)

**Bug latente importante detectado en plan-only mode (ANTES de tocar nada):**
`main.py:14` importaba `from bot_memory_pg import BotMemory, _get_conn`,
pero `_get_conn` ya no existía desde 5.4.a. Ningún test importa `main.py`,
así que el `ImportError` no aparecía en pytest, pero el bot real fallaba al
startup.

**Fix (5 cambios):**
1. Elimina `_get_conn` del import.
2. Agrega imports de `bdb` y `DEFAULT_TENANT_UUID`.
3. Helper local `_safety_get_conn()` que devuelve conn del app pool.
4. `memory = BotMemory(tenant_id=DEFAULT_TENANT_UUID)`.
5. `safety = SafetyStack.init_from_config(_safety_get_conn, tenant_id=DEFAULT_TENANT_UUID)`.

**Verificación:** `python -c "import main"` OK · pytest 267 passed.
Registrado también en `docs/ERRORES.md`.

**Lección (Write tool):** `main.py` (637 líneas) se editó con Edits
incrementales, no Write monolítico — Write trunca archivos >500 líneas.

---

### Estado al cierre de 5.5.a — Bloque 5 al ~90%

Hecho: 5.1–5.5 ✅. **Pendiente: 5.6** (tests integración RLS end-to-end con
el rol `borsenhirn_app` real, sin BYPASSRLS) y **5.7** (docs `B1_APP_LAYER.md`
+ cierre de log). Detalle del plan de 5.6 en [ESTADO.md](ESTADO.md).
Misión y decisiones de fondo en [PLAN.md](PLAN.md).

---

### 2026-06-05 — Bloque 5.6: tests de integración RLS ✅ (sin commit aún)

**La prueba final del sprint: RLS aisla de verdad con el rol app real
(NOSUPERUSER + NOBYPASSRLS), no con superuser.**

**Lado-IA (completado por Claude):**
- [x] `tests/test_b1_rls_integration.py` — 6 tests sobre `bot_trade_outcomes`:
      guard de rol no-privilegiado + tabla de verdad (sin contexto→0,
      default→31, tenant ajeno→0, bypass_rls→31) + teardown. Se auto-salta
      si `DB_NAME != borsenhirn_dev` (defensa anti-prod, `allow_module_level`).
- [x] `tests/conftest.py` — hook `pytest_collection_modifyitems` que salta
      los tests `@pytest.mark.integration` salvo `RUN_DB_INTEGRATION=1`.
      Mantiene la baseline verde y evita golpear cualquier DB por accidente.
- [x] `scripts/b1_block4_test_isolation.sh` — equivalente bash puro (psql,
      sin pytest), READ-ONLY, conecta como rol app, se niega fuera de
      `borsenhirn_dev`. Self-validating: deriva el conteo "verdad" vía
      `admin_bypass` y compara.

**Bug encontrado y arreglado durante el run:** el check de rol en el script
usaba `rolsuper::int || rolbypassrls::int`; en Postgres `||` sobre enteros no
es concatenación → `operator does not exist: integer || integer`. Fix: cast a
texto (`::int::text`).

**Resultado verificado contra `borsenhirn_dev`:**
- `bash scripts/b1_block4_test_isolation.sh` → 5/5 checks PASS, exit 0.
- `RUN_DB_INTEGRATION=1 pytest tests/test_b1_rls_integration.py` → 6 passed.
- Baseline sin env → **267 passed, 56 skipped** (era 55; +1 = los 6 de 5.6
  saltados por default). Aislamiento confirmado end-to-end.

**Pendiente:** commit de los 3 artefactos + docs. Luego 5.7 (docs de cierre).

---

### 2026-06-05 — Bloque 5.7: docs de cierre + Bloque 5 COMPLETO ✅ (sin commit aún)

**Lado-IA (completado por Claude):**
- [x] `docs/B1_APP_LAYER.md` — doc de referencia de la capa de app post-B1:
      regla de oro (todo runtime por `borsenhirn/db.py` con tenant context),
      los 2 roles/pools, API de `db.py`, contrato de los 3 módulos de
      persistencia + wire-up, checklist para agregar tabla/módulo nuevo, cómo
      correr los tests de 5.6, y gotchas conocidos. No duplica MULTI_TENANCY.md
      (diseño), PLAN.md (decisiones) ni este log (cronología).
- [x] Indexado en `docs/00_INDEX.md`.

**Gotcha resuelto en el acto:** `config.py` leía `DB_PASSWORD` (default
`"uriel"`) pero `.env.dev` define `DB_PASS` → el pool **admin** y 7 scripts
admin tomaban el fallback. Fix: `config.py` ahora acepta `DB_PASS` como alias
(`getenv("DB_PASSWORD") or getenv("DB_PASS") or "uriel"`). Verificado:
3 casos de precedencia OK, baseline 267 passed, y el pool admin conecta como
`postgres@borsenhirn_dev`. Detalle en `docs/B1_APP_LAYER.md` §7.

**Estado del Bloque 5:** 5.1–5.7 ✅. **Bloque 5 (refactor de la capa de app)
COMPLETO.** El sprint B1 queda funcionalmente probado: RLS aísla end-to-end con
el rol no-privilegiado real.

**Siguiente:** Bloque 6 (tests amplios) → 7 (bot e2e contra `borsenhirn_dev`)
→ 8 (aplicar a prod `borsenhirn` con backup; legacy se RENAME no DROP)
→ 9 (docs final).

---

### 2026-06-05 — Bloque 6: tests amplios de aislamiento ✅ (sin commit aún)

Cubre la checklist "Tests obligatorios antes de mergear fase B" de
`MULTI_TENANCY.md` (el #3 FORCE-sin-contexto ya estaba en 5.6).

**Lado-IA (completado por Claude):**
- [x] `tests/test_b1_rls_isolation_full.py` — 7 tests integration, gated igual
      que 5.6, TODOS transaccionales (rollback → dev intacto):
      1. INSERT con tenant correcto funciona.
      2. INSERT cross-tenant rechazado (WITH CHECK, SQLSTATE 42501).
      3. UPDATE cross-tenant rechazado (42501).
      4. Aggregations (COUNT/SUM) respetan RLS.
      5. FK ON DELETE RESTRICT (admin) — ver hallazgo abajo.
      6. Dos tenants reales: B ve solo lo suyo, default sigue en 31
         (tenant B temporal creado vía admin + borrado en teardown).
      7. Cobertura: toda tabla con `tenant_id` (excepto `tenants`) tiene
         RLS enabled+forced+>=2 policies.

**Hallazgo (test #5):** `ON DELETE` sobre un tenant con filas devuelve SQLSTATE
**`23001` restrict_violation**, no `23503` foreign_key_violation. Confirma que el
FK es genuinamente `ON DELETE RESTRICT` (no un `NO ACTION`). Aserción ajustada.

**Hallazgo menor (doc):** el tenant SYSTEM `…000` **sí existe como fila** en
`tenants` (lo creó la migración de Fase A), pero el comentario en
`borsenhirn/tenancy/constants.py` dice "NO debe existir como fila". Inconsistencia
de comentario, no de datos. Pendiente de decidir: corregir el comentario o el
estado. No bloquea.

**Verificación contra `borsenhirn_dev`:**
- `pytest tests/test_b1_rls_isolation_full.py` → 7 passed.
- 5.6 + B6 juntos → 13 passed.
- `check_rls_coverage.py --strict` → 17/17 con RLS, 0 sin RLS, exit 0.
- Baseline sin env → **267 passed, 57 skipped**.
- Post-run: tenant B borrado (0), `bot_trade_outcomes` sigue en 31 — los
  rollbacks dejaron dev intacto.

**Estado:** Bloque 6 COMPLETO. Siguiente: Bloque 7 (bot run e2e contra dev).

---

### 2026-06-05 — Bloque 7: bot e2e (capa DB) ✅ + bug destapado y arreglado

Alcance elegido: **e2e de la capa DB** (no el loop completo). Ejercita
`BotMemory` y `SafetyStack` tal como `main.run()` los construye, contra
`borsenhirn_dev` con el rol app bajo RLS, sin red ni Alpaca. Todo bajo un
TENANT DE TEST temporal (`…00e7`) borrado en teardown.

**Lado-IA (completado por Claude):**
- [x] `tests/test_b1_bot_e2e.py` — 3 tests: round-trips de BotMemory
      (trade outcome, symbol score, daily state, ml metrics, entry price,
      log_summary), aislamiento (lo escrito por el tenant de test no toca el
      default, que sigue en 31), y kill switch read/write vía SafetyStack.

**🐛 Bug sistémico destapado (lo que B7 venía a buscar):** los ~17 INSERT de
los 3 módulos refactoreados (`bot_memory_pg` x14, `state_store_pg` x2,
`credentials` x1) **NO incluían `tenant_id`**. El refactor 5.4 agregó el
contexto de tenant (setea el GUC) pero no la columna en los INSERT → tenant_id
quedaba NULL → la policy WITH CHECK lo rechazaba (42501). Ningún test anterior
lo vio: los unit tests mockean la DB y el bot nunca había corrido e2e. Las
lecturas funcionaban (filtro USING), solo fallaban las escrituras.

**Fix (opción DB DEFAULT, elegida por Uriel):**
- [x] `scripts/b1_block7_default_migration.sql` — idempotente, atómica, guard
      anti-prod. `ALTER COLUMN tenant_id SET DEFAULT
      NULLIF(current_setting('app.current_tenant_id', true), '')::uuid` en las
      17 tablas. Cualquier INSERT que omita tenant_id hereda el tenant de
      sesión; WITH CHECK sigue validando. Cero cambios en Python.
- [x] Aplicada a `borsenhirn_dev`: 17/17 tablas con default. e2e → 3 passed.
- [ ] **Pendiente Bloque 8:** incluir esta migración en el apply a prod.

**Verificación:** e2e 3 passed · integración total (5.6+B6+B7) 16 passed ·
baseline 267 passed · dev intacto (default 31, 0 tenants de test residuales).

**⚠️→✅ Segundo bug: pool-leak en safety stack (RESUELTO en el acto).**
`PostgresStateStore.get/set/list_active/clear` sacaban conn con `self.get_conn()`
y nunca la devolvían; `_safety_get_conn` usaba `getconn()`. Cada `is_halted()`
filtraba una conn del pool (max 10) → un run real del loop lo agotaba tras ~10
iteraciones (`PoolError`).

**Fix (opción "get_conn_fn con devolución", elegida por Uriel):**
- [x] Helper `_acquire(get_conn)` en `state_store_pg.py`: si el factory devuelve
      un context manager (`bdb.get_conn()`), lo entra/sale → la conn vuelve al
      pool; si devuelve un conn plano (legacy ks_admin/test_alerts), lo cede tal
      cual (backward-compat). Aplicado a los 4 métodos del store +
      `make_dashboard_db_write`.
- [x] `main._safety_get_conn` ahora devuelve `bdb.get_conn(role="app")` (CM).
- [x] `tests/test_b1_bot_e2e.py::test_safety_no_pool_leak` — regresión: 3× el
      tamaño del pool sin agotarse.
- Verificado: e2e 4 passed, safety units 15 passed, integración 17 passed,
  baseline 267 passed.

**Estado:** Bloque 7 COMPLETO (capa DB, 2 bugs arreglados). Siguiente: Bloque 8
(aplicar a prod, incluyendo la migración DEFAULT del Bloque 7).

---

### 2026-06-05 — Bloque 8: scripts de aplicación a prod GENERADOS (sin ejecutar)

Plan + decisiones en [B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md) (D-A consolidada,
D-B openssl, D-D ventana OK, D-E verif completa, D-C restore a DB nueva).

**Lado-IA (completado por Claude) — 5 artefactos:**
- [x] `scripts/b1_block8_prod_migration.sql` — migración consolidada idempotente/
      atómica: default tenant, RENAME legacy→_legacy_*, tenant_id+FK+index,
      backfill+verify, NOT NULL, RLS enable+force+policies (GUC final), DEFAULT,
      verificación 17/17 intra-txn. Guard EXIGE `borsenhirn`.
- [x] `scripts/b1_block8_apply.sh` — wrapper prod: triple guard (B1_ALLOW_PROD=1
      + DB_NAME=borsenhirn + frase escrita "APLICAR A PROD"), recuerda el backup,
      pre/post-state.
- [x] `scripts/b1_block8_create_role.sql` + `.sh` — rol prod con openssl, valida
      >=16 chars, smoke test, imprime las APP creds para el `.env` de prod.
- [x] `scripts/b1_block8_verify.sh` — GATE 3: cobertura --strict, legacy archivadas,
      smoke rol app, y write-isolation con tenant temporal (rollback, no persiste).
- [x] `scripts/b1_block8_rollback.md` — casos 1/2a/2b/2c + restore a DB nueva.

**Validación (sin tocar prod):** `bash -n` OK en los 3 wrappers; el guard del SQL
aborta correctamente en dev; y el CUERPO completo del SQL se validó con un dry-run
idempotente (copia con guard→dev) sobre `borsenhirn_dev`: 17/17 NOT NULL/RLS/FORCE,
COMMIT, dev intacto (31 trades antes y después).

**Pendiente (lo hace Uriel en la ventana):** backup de prod → `apply.sh` →
`create_role.sh` → `verify.sh` → re-arranque `--once`. **Nada aplicado a prod aún.**

