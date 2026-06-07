-- scripts/b1_block4_5_rename_guc.sql
--
-- Sprint B1 - Block 4.5: rename the RLS GUC from `app.current_tenant`
-- to `app.current_tenant_id` to align the database with the existing
-- code in borsenhirn/tenancy/db.py (which already uses the longer name).
--
-- Reason this is a separate sub-block:
--   Block 4 was applied with `app.current_tenant`; the existing tenancy
--   module ships `app.current_tenant_id`. To avoid touching code that
--   already has 31 passing tests, we re-align the DB to the code.
--
-- The 17 admin_bypass policies are also dropped + recreated unchanged.
-- They reference `app.bypass_rls` which is NOT renamed - this is on
-- purpose, only to keep the migration idempotent at the policy level.
--
-- This migration is IDEMPOTENT and TRANSACTIONAL.
--
-- Run with the wrapper:
--   bash scripts/b1_block4_5_apply.sh

-- =====================================================================
-- SAFETY GUARD
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
\echo '  Block 4.5: rename app.current_tenant -> app.current_tenant_id'
\echo '====================================================================='
\echo ''

BEGIN;

-- =====================================================================
-- 0. Build target table list (same 17 as Block 4).
-- =====================================================================
\echo '[0/3] Building target table list...'

CREATE TEMP TABLE _b1_b45_targets (
    table_name text PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO _b1_b45_targets VALUES
    ('bot_daily_state'), ('bot_entry_context'), ('bot_entry_prices'),
    ('bot_ml_metrics'), ('bot_ml_training'), ('bot_performance'),
    ('bot_regime_stats'), ('bot_symbol_scores'), ('bot_trade_outcomes'),
    ('assistant_history'), ('assistant_suggestions'), ('daily_reports'),
    ('signals'), ('trades'), ('alerts_log'), ('killswitch_state'),
    ('user_credentials');

-- =====================================================================
-- 1. Drop + recreate both policies on each target.
--    tenant_isolation: changes GUC name from current_tenant to current_tenant_id.
--    admin_bypass:     unchanged content, but recreated for atomic idempotency.
-- =====================================================================
\echo '[1/3] Renaming policies on 17 target tables...'

DO $rename$
DECLARE
    t text;
    n_targets integer;
    n_done    integer := 0;
BEGIN
    SELECT count(*) INTO n_targets FROM _b1_b45_targets;

    FOR t IN SELECT table_name FROM _b1_b45_targets ORDER BY table_name LOOP
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format('DROP POLICY IF EXISTS admin_bypass     ON %I', t);

        -- Tenant isolation: NEW GUC name `app.current_tenant_id`.
        EXECUTE format($pol$
            CREATE POLICY tenant_isolation ON %I
                AS PERMISSIVE
                FOR ALL
                USING (
                    tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid
                )
                WITH CHECK (
                    tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid
                )
        $pol$, t);

        -- Admin bypass: unchanged.
        EXECUTE format($pol$
            CREATE POLICY admin_bypass ON %I
                AS PERMISSIVE
                FOR ALL
                USING (
                    nullif(current_setting('app.bypass_rls', true), '') = 'on'
                )
                WITH CHECK (
                    nullif(current_setting('app.bypass_rls', true), '') = 'on'
                )
        $pol$, t);

        n_done := n_done + 1;
        RAISE NOTICE '  [%/%]  %  policies renamed',
            n_done, n_targets, rpad(t, 28);
    END LOOP;
END
$rename$;

-- =====================================================================
-- 2. Verify: all 17 tenant_isolation policies reference the NEW GUC,
--    and zero reference the OLD GUC.
-- =====================================================================
\echo '[2/3] Verifying policy expressions...'

DO $verify$
DECLARE
    n_targets   integer;
    n_new_guc   integer;
    n_old_guc   integer;
    n_bypass    integer;
BEGIN
    SELECT count(*) INTO n_targets FROM _b1_b45_targets;

    -- Policies whose definition mentions the NEW GUC name.
    SELECT count(*) INTO n_new_guc
    FROM pg_policy p
    JOIN pg_class c ON p.polrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relname IN (SELECT table_name FROM _b1_b45_targets)
      AND p.polname = 'tenant_isolation'
      AND pg_get_expr(p.polqual, p.polrelid) LIKE '%app.current_tenant_id%';

    -- Policies whose definition mentions the OLD GUC name (and not the new).
    -- The old name is a strict substring of the new, so we use a regex with
    -- a negative lookahead-style trick: match `current_tenant` not followed
    -- by `_id`.
    SELECT count(*) INTO n_old_guc
    FROM pg_policy p
    JOIN pg_class c ON p.polrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relname IN (SELECT table_name FROM _b1_b45_targets)
      AND p.polname = 'tenant_isolation'
      AND pg_get_expr(p.polqual, p.polrelid) ~ 'app\.current_tenant(?!_id)';

    SELECT count(*) INTO n_bypass
    FROM pg_policy p
    JOIN pg_class c ON p.polrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relname IN (SELECT table_name FROM _b1_b45_targets)
      AND p.polname = 'admin_bypass';

    RAISE NOTICE '  target tables:                               %', n_targets;
    RAISE NOTICE '  tenant_isolation referencing NEW guc:        %', n_new_guc;
    RAISE NOTICE '  tenant_isolation referencing OLD guc:        %', n_old_guc;
    RAISE NOTICE '  admin_bypass policies (unchanged content):   %', n_bypass;

    IF n_new_guc <> n_targets THEN
        RAISE EXCEPTION 'tenant_isolation NEW guc count mismatch: % of %', n_new_guc, n_targets;
    END IF;
    IF n_old_guc <> 0 THEN
        RAISE EXCEPTION '% policies still reference OLD guc app.current_tenant', n_old_guc;
    END IF;
    IF n_bypass <> n_targets THEN
        RAISE EXCEPTION 'admin_bypass count mismatch: % of %', n_bypass, n_targets;
    END IF;

    RAISE NOTICE 'Verifications: OK.';
END
$verify$;

-- =====================================================================
-- 3. Final per-table snapshot for the audit log.
-- =====================================================================
\echo '[3/3] Final per-table snapshot...'

\echo ''
\echo '--- Policies after rename ---'
SELECT
    c.relname  AS table_name,
    p.polname  AS policy_name,
    -- Truncate the expression for readable output.
    substr(pg_get_expr(p.polqual, p.polrelid), 1, 80) AS using_expr_preview
FROM pg_policy p
JOIN pg_class c ON p.polrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname = 'public'
  AND c.relname IN (SELECT table_name FROM _b1_b45_targets)
ORDER BY c.relname, p.polname;

COMMIT;

\echo ''
\echo '====================================================================='
\echo '  Block 4.5 committed. The DB now uses app.current_tenant_id,'
\echo '  matching borsenhirn/tenancy/db.py.'
\echo '====================================================================='
