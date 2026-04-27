-- scripts/b1_block3_migration.sql
--
-- Sprint B1 - Block 3: backfill tenant_id with default tenant UUID,
-- then ALTER COLUMN ... SET NOT NULL on all 17 tables.
--
-- Pre-condition: Block 2 ran successfully. tenant_id column exists
-- (NULL allowed) on the 17 target tables, FK to tenants(tenant_id)
-- is in place, default tenant row exists.
--
-- This migration is IDEMPOTENT and TRANSACTIONAL:
--   - UPDATE ... WHERE tenant_id IS NULL skips rows already backfilled.
--   - SET NOT NULL is a no-op if the column is already NOT NULL.
--   - All operations happen inside a single BEGIN/COMMIT.
--   - Any failure rolls back the entire migration.
--
-- Run it with the wrapper:
--   bash scripts/b1_block3_apply.sh

-- =====================================================================
-- SAFETY GUARD: refuse to run on production.
-- =====================================================================
DO $guard$
BEGIN
    IF current_database() = 'borsenhirn' THEN
        RAISE EXCEPTION
          'ABORT: this migration must NOT run on production database "borsenhirn". Run it on borsenhirn_dev.';
    END IF;
    RAISE NOTICE 'Safety guard OK. Database: %', current_database();
END
$guard$;

\echo ''
\echo '====================================================================='
\echo '  Block 3: backfill tenant_id + SET NOT NULL'
\echo '====================================================================='
\echo ''

BEGIN;

-- =====================================================================
-- 0. Sanity: default tenant must exist (Block 2 created it).
--    Refuse to backfill against a missing tenant - would just NULL-out
--    the FK constraint silently if RESTRICT was not in place.
-- =====================================================================
\echo '[0/4] Sanity: verifying default tenant exists...'

DO $sanity$
DECLARE
    c INTEGER;
BEGIN
    SELECT count(*) INTO c
    FROM tenants
    WHERE tenant_id = '00000000-0000-0000-0000-000000000001'::uuid;

    IF c <> 1 THEN
        RAISE EXCEPTION 'Default tenant 00000000-...001 not found. Run Block 2 first.';
    END IF;
    RAISE NOTICE 'Default tenant present (count=%).', c;
END
$sanity$;

-- =====================================================================
-- 1. Backfill: assign default tenant to any rows with tenant_id NULL.
--    Idempotent: re-runs update 0 rows if already backfilled.
-- =====================================================================
\echo '[1/4] Backfilling tenant_id on rows with NULL...'

DO $backfill$
DECLARE
    t TEXT;
    tables TEXT[] := ARRAY[
        'bot_daily_state','bot_entry_context','bot_entry_prices',
        'bot_ml_metrics','bot_ml_training','bot_performance',
        'bot_regime_stats','bot_symbol_scores','bot_trade_outcomes',
        'assistant_history','assistant_suggestions','daily_reports',
        'signals','trades','alerts_log','killswitch_state',
        'user_credentials'
    ];
    rows_updated INTEGER;
    total_updated INTEGER := 0;
BEGIN
    FOREACH t IN ARRAY tables LOOP
        EXECUTE format(
            'UPDATE %I SET tenant_id = $1 WHERE tenant_id IS NULL',
            t
        ) USING '00000000-0000-0000-0000-000000000001'::uuid;

        GET DIAGNOSTICS rows_updated = ROW_COUNT;
        total_updated := total_updated + rows_updated;

        IF rows_updated > 0 THEN
            RAISE NOTICE '  %-30s  backfilled % rows', t, rows_updated;
        ELSE
            RAISE NOTICE '  %-30s  (no rows needed backfill)', t;
        END IF;
    END LOOP;

    RAISE NOTICE 'Total rows backfilled this run: %', total_updated;
END
$backfill$;

-- =====================================================================
-- 2. Verify zero NULLs remain on any of the 17 tables.
--    Belt-and-suspenders before SET NOT NULL.
-- =====================================================================
\echo '[2/4] Verifying no NULL tenant_id remains...'

DO $verify_null$
DECLARE
    t TEXT;
    tables TEXT[] := ARRAY[
        'bot_daily_state','bot_entry_context','bot_entry_prices',
        'bot_ml_metrics','bot_ml_training','bot_performance',
        'bot_regime_stats','bot_symbol_scores','bot_trade_outcomes',
        'assistant_history','assistant_suggestions','daily_reports',
        'signals','trades','alerts_log','killswitch_state',
        'user_credentials'
    ];
    null_count INTEGER;
    total_nulls INTEGER := 0;
BEGIN
    FOREACH t IN ARRAY tables LOOP
        EXECUTE format(
            'SELECT count(*) FROM %I WHERE tenant_id IS NULL',
            t
        ) INTO null_count;

        IF null_count > 0 THEN
            total_nulls := total_nulls + null_count;
            RAISE WARNING '  %-30s  has % NULL tenant_id rows', t, null_count;
        END IF;
    END LOOP;

    IF total_nulls > 0 THEN
        RAISE EXCEPTION 'Aborting: % NULL tenant_id rows remain. Cannot SET NOT NULL.', total_nulls;
    END IF;
    RAISE NOTICE 'OK: zero NULLs across all 17 tables.';
END
$verify_null$;

-- =====================================================================
-- 3. ALTER COLUMN tenant_id SET NOT NULL on all 17 tables.
--    Idempotent: no-op if already NOT NULL.
-- =====================================================================
\echo '[3/4] Setting tenant_id NOT NULL on all 17 tables...'

DO $not_null$
DECLARE
    t TEXT;
    tables TEXT[] := ARRAY[
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
            'ALTER TABLE %I ALTER COLUMN tenant_id SET NOT NULL',
            t
        );
    END LOOP;
    RAISE NOTICE 'Done: tenant_id is NOT NULL on all 17 tables.';
END
$not_null$;

-- =====================================================================
-- 4. Per-table count of rows assigned to default tenant + final checks.
-- =====================================================================
\echo '[4/4] Per-table counts (assigned to default tenant)...'

DO $counts$
DECLARE
    t TEXT;
    tables TEXT[] := ARRAY[
        'bot_daily_state','bot_entry_context','bot_entry_prices',
        'bot_ml_metrics','bot_ml_training','bot_performance',
        'bot_regime_stats','bot_symbol_scores','bot_trade_outcomes',
        'assistant_history','assistant_suggestions','daily_reports',
        'signals','trades','alerts_log','killswitch_state',
        'user_credentials'
    ];
    n INTEGER;
    total INTEGER := 0;
BEGIN
    FOREACH t IN ARRAY tables LOOP
        EXECUTE format(
            'SELECT count(*) FROM %I WHERE tenant_id = $1',
            t
        ) INTO n
        USING '00000000-0000-0000-0000-000000000001'::uuid;

        RAISE NOTICE '  %-30s  % rows', t, n;
        total := total + n;
    END LOOP;
    RAISE NOTICE '  ----------------------------------------------------';
    RAISE NOTICE '  TOTAL                          % rows on default tenant', total;
END
$counts$;

\echo ''
\echo '--- Final: tables with tenant_id NOT NULL (expect 17) ---'
SELECT count(*) AS not_null_columns
FROM information_schema.columns
WHERE table_schema = 'public'
  AND column_name  = 'tenant_id'
  AND is_nullable  = 'NO'
  AND table_name <> 'tenants';

\echo ''
\echo '--- Final: tables with tenant_id NULL allowed (expect 0 of 17 target tables) ---'
SELECT count(*) AS still_nullable_target
FROM information_schema.columns
WHERE table_schema = 'public'
  AND column_name  = 'tenant_id'
  AND is_nullable  = 'YES'
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
\echo '  Block 3 committed. Next: Block 4 (RLS policies + FORCE RLS).'
\echo '====================================================================='
