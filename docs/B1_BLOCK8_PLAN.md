# B1 Bloque 8 — Plan de aplicación a PRODUCCIÓN

> ⚠️ **Este es el único bloque que toca `borsenhirn` (producción).** Documento
> de PLAN para revisar **antes** de ejecutar nada. Workflow estricto: Claude
> genera los scripts con guards; **Uriel los corre y pega el output**.
> Estado vivo: [ESTADO.md](ESTADO.md). Qué cambió la capa de app: [B1_APP_LAYER.md](B1_APP_LAYER.md).

---

## 1. Objetivo

Llevar a producción el mismo estado multi-tenant ya probado en `borsenhirn_dev`:
17 tablas con `tenant_id` NOT NULL + FK + index + RLS forzado + 2 policies +
DEFAULT desde el GUC, default tenant dueño de las filas legacy, y el rol
`borsenhirn_app` (NOSUPERUSER + NOBYPASSRLS) para el runtime.

**Garantía de seguridad #1:** backup completo ANTES de cualquier cambio.
**Garantía #2:** las 4 legacy se **RENOMBRAN a `_legacy_*`**, NO se dropean.

---

## 2. Diferencias dev → prod (lo que cambia respecto a lo ya corrido)

| Tema | En dev (hecho) | En prod (Bloque 8) |
|---|---|---|
| 4 tablas legacy | `DROP ... CASCADE` | **`ALTER TABLE ... RENAME TO _legacy_*`** (archivar, no borrar) |
| Guards de los scripts | abortan si `DB_NAME=borsenhirn` | **invertir**: correr SOLO si es `borsenhirn`, con confirmación extra |
| GUC de RLS | Block 4 usó `app.current_tenant`, luego 4.5 lo renombró a `app.current_tenant_id` | aplicar **directo `app.current_tenant_id`** (consolidado, sin el paso intermedio) |
| Backfill | 128 filas conocidas | las que haya en prod (puede ser más; la migración es idempotente y cuenta lo que encuentre) |
| Password del rol | generado para dev | **password nuevo de prod** (≥16 chars), va al `.env` de prod |

---

## 3. Enfoque recomendado: UNA migración consolidada

En vez de re-ejecutar los 6 scripts del historial de dev (incluida la corrección
4→4.5 y el DROP dev-only), aplicar **una sola migración prod idempotente y
atómica** que refleje el estado FINAL. Más fácil de revisar, verificar y
rollbackear que 6 pasos sueltos.

**Decisión a confirmar (D-A):** consolidado (recomendado) vs. replay de los 6
scripts adaptados. El resto del plan asume consolidado.

Artefactos a generar (cuando apruebes):
1. `scripts/b1_block8_prod_migration.sql` — la transformación completa en un
   `BEGIN/COMMIT`, idempotente, con guard que exige `current_database()='borsenhirn'`.
2. `scripts/b1_block8_apply.sh` — wrapper que carga `.env` (prod), exige
   `B1_ALLOW_PROD=1`, muestra pre-state, pide confirmación escrita (`APLICAR A PROD`),
   corre con `psql -1 -v ON_ERROR_STOP=1`, muestra post-state.
3. `scripts/b1_block8_create_role.sh` + `.sql` — variante prod del rol (mismo
   contenido que block5, guard prod, password de prod).
4. `scripts/b1_block8_verify.sh` — verificación read-only post-migración.
5. `scripts/b1_block8_rollback.md` — procedimiento de reversa.

---

## 4. Secuencia paso a paso

### Paso 0 — Pre-flight (read-only, sin cambios)
- [ ] Confirmar que **el bot está detenido** (ningún proceso escribiendo a prod).
- [ ] `scripts/b1_health_check.sh` apuntando a prod → foto del estado actual.
- [ ] Verificar estado real de prod vs el dump de abril: row counts de las 17
      tablas + de las 4 legacy (¿escribieron filas desde el dump?).
- [ ] Confirmar que NO existen ya objetos B1 a medio aplicar (columna tenant_id,
      policies). Si los hubiera, la migración idempotente los respeta.

### Paso 1 — Backup completo (CRÍTICO)
- [ ] `bash scripts/b1_block8_backup.sh` → `pg_dump -F c` de `borsenhirn` a
      `backups/prod_pre_b8_YYYYMMDD_HHMM.dump`, con confirmación y verificación
      (tamaño + `pg_restore --list`) incluidas.
- [ ] Branch/tag git de respaldo del código (ya existe `backup-pre-b1-20260426`).
- **GATE 1:** sin backup verificado, NO se sigue.

### Paso 2 — Migración de datos/esquema (transaccional)
`bash scripts/b1_block8_apply.sh` → corre `b1_block8_prod_migration.sql`:
1. INSERT default tenant `…001` (`ON CONFLICT DO NOTHING`).
2. **RENAME** `bot_state`,`entry_context`,`regime_stats`,`symbol_memory`
   → `_legacy_*` (`IF EXISTS`, idempotente).
3. `ADD COLUMN IF NOT EXISTS tenant_id` en las 17 tablas A + FK
   `ON DELETE RESTRICT` + index.
4. Backfill `SET tenant_id = default WHERE tenant_id IS NULL` + verify 0 NULLs.
5. `SET NOT NULL` en las 17.
6. `ENABLE` + `FORCE` RLS + 2 policies (`tenant_isolation`, `admin_bypass`) con
   GUC **`app.current_tenant_id`**.
7. `SET DEFAULT` de tenant_id desde el GUC (fix del Bloque 7).
8. Verificaciones finales dentro de la txn (counts, 0 NULLs, 17/17 RLS).
- **GATE 2:** si cualquier verificación falla → rollback automático (la txn no commitea).

### Paso 3 — Rol de aplicación
`bash scripts/b1_block8_create_role.sh`:
- CREATE/ALTER `borsenhirn_app` (LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB) con
  password de prod; GRANTs CRUD en las 17, SELECT en `tenants`, USAGE/SELECT en
  sequences; verificación que aborta si quedó SUPERUSER/BYPASSRLS.
- [ ] Guardar el password en el gestor de secrets (Bloque B2) y en `.env` de prod
      como `APP_DB_USER`/`APP_DB_PASSWORD`.

### Paso 4 — Verificación post-migración (read-only)
`bash scripts/b1_block8_verify.sh` + pruebas:
- [ ] `check_rls_coverage.py --strict` contra prod → 17/17, 0 sin RLS.
- [ ] Tests de aislamiento (5.6/B6/B7) apuntando a prod **con un tenant de test
      temporal** (escrituras con rollback / teardown; el default no se toca).
- [ ] Smoke: conectar como `borsenhirn_app`, sin contexto → 0 filas; con default
      → counts esperados; bypass → todas.
- [ ] Las 4 `_legacy_*` siguen ahí con su data intacta.
- **GATE 3:** todo verde antes de re-arrancar el bot.

### Paso 4.5 — EXTRAS B3..B7 (clerk_id + billing + audit_log + legal)
`B1_ALLOW_PROD=1 bash scripts/b1_block8_extras_apply.sh` → corre
`b1_block8_extras_prod_migration.sql` (atómico/idempotente, guard prod):
- B3: `tenants.clerk_user_id` (UNIQUE). B4: 4 columnas billing (`stripe_customer_id`
  UNIQUE, `stripe_subscription_id`, `plan`, `current_period_end`).
- B5: tabla `audit_log` (RLS + append-only). B7: tabla `legal_acceptance` (RLS + append-only).
- **Orden:** va DESPUÉS del rol (Paso 3, los GRANTs append-only lo requieren — aborta si
  falta) y DESPUÉS del verify core (Paso 4): el conteo "17" de `verify.sh` asume que
  `audit_log`/`legal_acceptance` aún no existen. Tras las extras, FORCE RLS = 19 (esperado).
- Validado en DB scratch local (creación + idempotencia) y guard probado contra dev.
- **GATE 2b:** verificación intra-txn (clerk+billing+ambas tablas RLS+append-only) o rollback.

### Paso 5 — Re-arranque controlado
- [ ] Arrancar el bot apuntando a prod con las APP creds, en modo `--once` primero.
- [ ] Confirmar que escribe/lee bien (un run real corto).
- [ ] Recién entonces, operación normal.

---

## 5. Plan de rollback

- **Durante la migración (Paso 2):** es una sola transacción → cualquier fallo
  hace rollback total, prod queda como estaba. Sin acción manual.
- **Después del commit, si algo anda mal:**
  - Reversible en vivo: `DISABLE ROW LEVEL SECURITY` en las 17 + revertir el bot
    al rol admin (vuelve al comportamiento single-user) mientras se diagnostica.
  - Las `_legacy_*` permiten volver a renombrarlas a su nombre original.
  - **Última instancia:** restore del backup `prod_pre_b8_*.dump` a un
    `borsenhirn_restore`, validar, y promover. (Definir si se restaura in-place
    o a DB nueva — ver D-C.)

---

## 6. Decisiones (CONFIRMADAS 2026-06-05)

- **D-A ✅ Consolidada.** Una sola migración SQL idempotente/atómica con el estado final.
- **D-B ✅ openssl ad-hoc.** Password del rol generado con openssl al momento, guardado
  en el `.env` de prod (igual que dev). El gestor de secrets queda para B2.
- **D-C → default seguro (no preguntado):** en el peor caso, restore a una DB nueva
  `borsenhirn_restore`, validar, y recién entonces promover. NO in-place. (Marcar si se
  prefiere otra cosa.)
- **D-D ✅ Sí, se detiene el bot.** Hay ventana: parar el bot, migrar y verificar sin
  escrituras concurrentes.
- **D-E ✅ Verificación completa con tenant de test.** Correr 5.6/B6/B7 contra prod con
  un tenant temporal (escrituras con rollback/teardown; el default no se toca).

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Prod tiene filas nuevas desde el dump | migración idempotente; backfill cuenta lo que haya; backup previo |
| FK preexistente en alguna tabla (como pasó en dev con `user_credentials`) | loop que dropea cualquier FK a `tenants` antes del canónico (ya resuelto en dev) |
| El bot escribe durante la migración | detenerlo en Paso 0; `FORCE RLS` no aplica hasta commit |
| Password del rol débil/filtrado | validación ≥16 chars; va solo a `.env` + gestor de secrets |
| Olvido de un objeto (policy/default) | verificación dentro de la txn aborta si falta algo; `check_rls_coverage --strict` post |

---

## 8. Resumen de gates

1. **GATE 1** — backup verificado antes de tocar nada.
2. **GATE 2** — todas las verificaciones intra-transacción pasan (sino rollback).
3. **GATE 3** — RLS 17/17 + tests de aislamiento + legacy archivadas, antes de re-arrancar el bot.
