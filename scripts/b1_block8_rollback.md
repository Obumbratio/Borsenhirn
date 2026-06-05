# B1 Bloque 8 — Procedimiento de ROLLBACK (producción)

> Qué hacer si algo sale mal al aplicar la migración a `borsenhirn`.
> Plan completo: [`../docs/B1_BLOCK8_PLAN.md`](../docs/B1_BLOCK8_PLAN.md).

## Decisión D-C (confirmada)
Restore de peor caso a **DB nueva `borsenhirn_restore`** (NO in-place), validar, y recién
entonces promover. Nunca restaurar pisando `borsenhirn` directo.

---

## Caso 1 — Falla DURANTE la migración (Paso 2)

La migración es una sola transacción (`BEGIN/COMMIT`). Cualquier error hace **rollback
automático**: producción queda exactamente como estaba. **No hay acción manual.**
El wrapper imprime `FALLO (rc=...). La transaccion hizo rollback`. Revisá el error,
corregí, y volvé a correr (es idempotente).

---

## Caso 2 — La migración commiteó pero algo anda mal después

Diagnosticá primero con `bash scripts/b1_block8_verify.sh`. Según el problema:

### 2a. El bot no opera bien con RLS / querés volver a single-user YA
Reversible en vivo, sin perder datos:

```sql
-- Como admin (postgres). Desactiva el filtrado RLS en las 17 tablas.
-- El esquema (tenant_id, FK, default) queda; solo se apaga el enforcement.
DO $$
DECLARE t TEXT;
BEGIN
  FOR t IN SELECT unnest(ARRAY[
    'bot_daily_state','bot_entry_context','bot_entry_prices','bot_ml_metrics',
    'bot_ml_training','bot_performance','bot_regime_stats','bot_symbol_scores',
    'bot_trade_outcomes','assistant_history','assistant_suggestions','daily_reports',
    'signals','trades','alerts_log','killswitch_state','user_credentials'])
  LOOP
    EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;
```

Y apuntá el bot al rol **admin** (no `borsenhirn_app`) temporalmente: en el `.env`
de prod, dejá `APP_DB_USER`/`APP_DB_PASSWORD` vacíos → `config.py` hace fallback a
`DB_USER`/`DB_PASSWORD` (admin, BYPASSRLS) y el bot opera como antes mientras diagnosticás.

Para re-activar RLS luego: re-correr `b1_block8_apply.sh` (idempotente; vuelve a
`ENABLE`+`FORCE`).

### 2b. Necesitás recuperar una tabla legacy archivada
Las legacy NO se borraron, sólo se renombraron. Para revertir el nombre:

```sql
ALTER TABLE _legacy_bot_state     RENAME TO bot_state;
ALTER TABLE _legacy_entry_context RENAME TO entry_context;
ALTER TABLE _legacy_regime_stats  RENAME TO regime_stats;
ALTER TABLE _legacy_symbol_memory RENAME TO symbol_memory;
```

### 2c. Rollback total al estado pre-migración (peor caso)
Usar el backup `backups/prod_pre_b8_*.dump` (GATE 1). **A una DB nueva, no in-place:**

```bash
# 1. Crear DB de restore y restaurar el backup ahí.
createdb -h "$DB_HOST" -U postgres borsenhirn_restore
pg_restore -h "$DB_HOST" -U postgres -d borsenhirn_restore --no-owner \
    backups/prod_pre_b8_YYYYMMDD_HHMM.dump

# 2. Validar borsenhirn_restore (row counts, sanity). Comparar con lo esperado.

# 3. Recién con todo validado, decidir la promoción:
#    - opción A: apuntar el bot a borsenhirn_restore (cambiar DB_NAME en .env).
#    - opción B: renombrar DBs (requiere 0 conexiones activas):
#        ALTER DATABASE borsenhirn RENAME TO borsenhirn_failed_b8;
#        ALTER DATABASE borsenhirn_restore RENAME TO borsenhirn;
```

---

## Checklist de rollback

- [ ] ¿El bot está detenido? (parar antes de cualquier reversa)
- [ ] ¿Qué caso aplica? (1 = automático / 2a / 2b / 2c)
- [ ] Si es 2c: ¿el dump `prod_pre_b8_*` existe y `pg_restore --list` lo lee?
- [ ] Tras revertir: correr `b1_block8_verify.sh` (o el health check) para confirmar estado.
- [ ] Documentar en `docs/B1_SESSION_LOG.md` qué pasó y qué se revirtió.
