-- scripts/b1_block7_default_migration.sql
--
-- Sprint B1 - Block 7: tenant_id column DEFAULT from session GUC.
--
-- Motivo: el refactor 5.4 dejó los INSERT de la capa de app SIN la
-- columna tenant_id. Como tenant_id es NOT NULL y no tenía default,
-- todo INSERT quedaba con tenant_id NULL y la policy WITH CHECK lo
-- rechazaba (42501). Detectado por el e2e del Bloque 7.
--
-- Fix: poner un DEFAULT que toma el tenant del contexto de sesión RLS.
-- Así cualquier INSERT que omita tenant_id (los ~17 existentes y los
-- futuros) hereda el tenant activo. WITH CHECK sigue validando que
-- coincida con app.current_tenant_id, así que no se debilita nada.
--
--   DEFAULT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
--
--   - current_setting(..., true): missing_ok → NULL si el GUC no está
--     seteado (en vez de error).
--   - NULLIF(..., ''): trata el string vacío como NULL.
--   - Si no hay tenant context → NULL → NOT NULL violation (error claro:
--     no se debe insertar sin tenant). No cae en RLS.
--
-- IDEMPOTENTE (SET DEFAULT es repetible) y TRANSACCIONAL (BEGIN/COMMIT).
--
-- Run con el wrapper:  bash scripts/b1_block7_apply.sh

-- =====================================================================
-- SAFETY GUARD: refuse to run on production.
-- =====================================================================
DO $guard$
BEGIN
    IF current_database() = 'borsenhirn' THEN
        RAISE EXCEPTION
          'ABORT: esta migracion NO debe correr en produccion "borsenhirn". Correr en borsenhirn_dev.';
    END IF;
    RAISE NOTICE 'Safety guard OK. Database: %', current_database();
END
$guard$;

\echo ''
\echo '====================================================================='
\echo '  Block 7: tenant_id DEFAULT desde el GUC de sesion'
\echo '====================================================================='
\echo ''

BEGIN;

DO $mig$
DECLARE
    t text;
    tables text[] := ARRAY[
        'bot_daily_state','bot_entry_context','bot_entry_prices',
        'bot_ml_metrics','bot_ml_training','bot_performance',
        'bot_regime_stats','bot_symbol_scores','bot_trade_outcomes',
        'assistant_history','assistant_suggestions','daily_reports',
        'signals','trades','alerts_log','killswitch_state',
        'user_credentials'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN tenant_id SET DEFAULT '
            'NULLIF(current_setting(%L, true), %L)::uuid',
            t, 'app.current_tenant_id', ''
        );
        RAISE NOTICE 'DEFAULT seteado en %', t;
    END LOOP;
END
$mig$;

-- Verificacion: las 17 tablas deben tener un default en tenant_id.
SELECT count(*) AS tablas_con_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND column_name  = 'tenant_id'
  AND column_default IS NOT NULL
  AND table_name IN (
        'bot_daily_state','bot_entry_context','bot_entry_prices',
        'bot_ml_metrics','bot_ml_training','bot_performance',
        'bot_regime_stats','bot_symbol_scores','bot_trade_outcomes',
        'assistant_history','assistant_suggestions','daily_reports',
        'signals','trades','alerts_log','killswitch_state',
        'user_credentials'
      );

COMMIT;

\echo ''
\echo '====================================================================='
\echo '  Block 7 committed. Esperado: tablas_con_default = 17.'
\echo '====================================================================='
