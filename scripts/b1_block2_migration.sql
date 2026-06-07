-- scripts/b1_block2_migration.sql
--
-- Sprint B1 - Block 2: add tenant_id infrastructure to legacy tables.
--
-- This migration is IDEMPOTENT and TRANSACTIONAL:
--   - Re-running it produces the same final state.
--   - All operations happen inside a single BEGIN/COMMIT.
--   - Any failure rolls back the entire migration.
--
-- It does NOT backfill tenant_id values (that is Block 3).
-- It does NOT enable RLS or write policies (that is Block 4).
-- It does NOT touch the application code (Block 5).
--
-- Run it with the wrapper:
--   bash scripts/b1_block2_apply.sh
--
-- Or manually:
--   psql -h <host> -U <user> -d borsenhirn_dev \
--        -X --quiet -v ON_ERROR_STOP=1 -1 \
--        -f scripts/b1_block2_migration.sql

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
\echo '  Block 2: tenant_id infrastructure migration'
\echo '====================================================================='
\echo ''

BEGIN;

-- =====================================================================
-- 1. Default tenant (so Block 3 has a stable UUID to backfill with).
--    Idempotent via ON CONFLICT. Real schema (Phase A) requires:
--      tenant_id (uuid PK), slug, email, display_name, status, metadata.
-- =====================================================================
\echo '[1/5] Ensuring default tenant exists...'

INSERT INTO tenants (
    tenant_id, slug, email, display_name, status, metadata
)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'default',
    'default@borsenhirn.local',
    'Default Tenant (legacy single-user data)',
    'active',
    '{"note": "auto-created for B1 multi-tenancy phase B backfill"}'::jsonb
)
ON CONFLICT (tenant_id) DO NOTHING;

-- =====================================================================
-- 2. DROP the 4 legacy duplicate tables (dev only).
--    These were confirmed by inspector: 0 rows + 0 code references,
--    each shadowed by an active bot_* equivalent.
-- =====================================================================
\echo '[2/5] Dropping legacy duplicates (dev only)...'

DROP TABLE IF EXISTS bot_state       CASCADE;
DROP TABLE IF EXISTS entry_context   CASCADE;
DROP TABLE IF EXISTS regime_stats    CASCADE;
DROP TABLE IF EXISTS symbol_memory   CASCADE;

-- =====================================================================
-- 3. ADD COLUMN tenant_id UUID (NULL allowed for now).
--    Block 3 will backfill + ALTER COLUMN ... SET NOT NULL.
-- =====================================================================
\echo '[3/5] Adding tenant_id column to 17 tables...'

-- Core bot tables (9)
ALTER TABLE bot_daily_state       ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE bot_entry_context     ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE bot_entry_prices      ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE bot_ml_metrics        ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE bot_ml_training       ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE bot_performance       ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE bot_regime_stats      ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE bot_symbol_scores     ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE bot_trade_outcomes    ADD COLUMN IF NOT EXISTS tenant_id uuid;

-- M5 Hirn + reportes + features (5)
ALTER TABLE assistant_history     ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE assistant_suggestions ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE daily_reports         ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE signals               ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE trades                ADD COLUMN IF NOT EXISTS tenant_id uuid;

-- Reclasificadas desde cat-C (3)
ALTER TABLE alerts_log            ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE killswitch_state      ADD COLUMN IF NOT EXISTS tenant_id uuid;
ALTER TABLE user_credentials      ADD COLUMN IF NOT EXISTS tenant_id uuid;

-- =====================================================================
-- 4. Foreign keys to tenants(tenant_id) + indexes on tenant_id.
--    Robust idempotency: drops ANY pre-existing FK from this table to
--    tenants (regardless of name or definition), then adds the canonical
--    one. This handles the case where Phase A created a differently-named
--    constraint (e.g. user_credentials_tenant_id_fkey).
--    ON DELETE RESTRICT: deleting a tenant must fail if it still owns
--    rows. Safer default than CASCADE.
-- =====================================================================
\echo '[4/5] Adding FK constraints + indexes on tenant_id...'

DO $fkidx$
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
    fk_name TEXT;
    ix_name TEXT;
    existing_fk RECORD;
BEGIN
    FOREACH t IN ARRAY tables LOOP
        fk_name := 'fk_' || t || '_tenant';
        ix_name := 'ix_' || t || '_tenant_id';

        -- Drop ANY pre-existing FK from this table to tenants.
        -- (Regardless of constraint name - covers Phase A leftovers.)
        FOR existing_fk IN
            SELECT c.conname
            FROM pg_constraint c
            JOIN pg_class src      ON c.conrelid  = src.oid
            JOIN pg_namespace srcn  ON src.relnamespace = srcn.oid
            JOIN pg_class dst      ON c.confrelid = dst.oid
            WHERE c.contype = 'f'
              AND srcn.nspname = 'public'
              AND src.relname = t
              AND dst.relname = 'tenants'
        LOOP
            EXECUTE format(
                'ALTER TABLE %I DROP CONSTRAINT %I',
                t, existing_fk.conname
            );
            RAISE NOTICE 'Dropped pre-existing FK: %.%', t, existing_fk.conname;
        END LOOP;

        -- Add canonical FK with the project's naming convention.
        EXECUTE format(
            'ALTER TABLE %I ADD CONSTRAINT %I '
            'FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) '
            'ON DELETE RESTRICT',
            t, fk_name
        );

        -- Index on tenant_id (RLS policies will filter by it).
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I (tenant_id)',
            ix_name, t
        );
    END LOOP;
END
$fkidx$;

-- =====================================================================
-- 5. Verifications (final SELECTs are reported on stdout).
-- =====================================================================
\echo '[5/5] Verifications...'
\echo ''

\echo '--- tables with tenant_id column (expect 17) ---'
SELECT count(*) AS tables_with_tenant_id
FROM information_schema.columns
WHERE table_schema = 'public'
  AND column_name  = 'tenant_id'
  AND table_name <> 'tenants';

\echo ''
\echo '--- FK constraints to tenants(tenant_id) (expect 17) ---'
SELECT count(*) AS fk_to_tenants
FROM information_schema.table_constraints tc
JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND ccu.table_name     = 'tenants'
  AND tc.table_schema    = 'public'
  AND tc.table_name <> 'tenants';

\echo ''
\echo '--- indexes ix_*_tenant_id (expect 17) ---'
SELECT count(*) AS tenant_indexes
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname LIKE 'ix_%_tenant_id';

\echo ''
\echo '--- legacy tables still present (expect 0) ---'
SELECT count(*) AS legacy_remaining
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('bot_state','entry_context','regime_stats','symbol_memory');

\echo ''
\echo '--- default tenant present? (expect 1) ---'
SELECT count(*) AS default_tenant_count
FROM tenants
WHERE tenant_id = '00000000-0000-0000-0000-000000000001'::uuid;

COMMIT;

\echo ''
\echo '====================================================================='
\echo '  Migration committed. Next: Block 3 (backfill + NOT NULL).'
\echo '====================================================================='
