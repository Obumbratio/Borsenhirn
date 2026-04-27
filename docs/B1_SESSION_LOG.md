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

