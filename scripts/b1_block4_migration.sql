-- scripts/b1_block4_migration.sql
--
-- Sprint B1 - Block 4: enable Row-Level Security on the 17 target
-- tables (or 16, if user_credentials already has Phase A RLS).
--
-- Pre-condition: Block 3 ran successfully. tenant_id is NOT NULL on
-- all 17 tables, FK to tenants(tenant_id) is in place, default tenant
-- exists.
--
-- This migration is IDEMPOTENT and TRANSACTIONAL:
--   - ENABLE/FORCE RLS is a no-op if already set.
--   - DROP POLICY IF EXISTS + CREATE POLICY is the idempotent pattern
--     for policy upserts (PG has no CREATE POLICY ... IF NOT EXISTS).
--   - All operations happen inside a single BEGIN/COMMIT.
--   - Any failure rolls back the entire migration.
--
-- The migration installs TWO policies per table, both PERMISSIVE
-- (combined with OR):
--
--   1. tenant_isolation: rows visible / writable only when
--          tenant_id = nullif(current_setting('app.current_tenant', true), '')::uuid
--      Without app.current_tenant set, nullif returns NULL and
--      "tenant_id = NULL" is FALSE for every row -> zero rows visible.
--
--   2. admin_bypass: full access when
--          nullif(current_setting('app.bypass_rls', true), '') = 'on'
--      Used by admin/operational tasks that must read across tenants.
--
-- IMPORTANT: with FORCE ROW LEVEL SECURITY, RLS also applies to the
-- table owner. BUT roles with the BYPASSRLS attribute (typically
-- superuser 'postgres') still bypass RLS unconditionally. Functional
-- isolation tests at the end of this migration are skipped if the
-- current user has BYPASSRLS, with a notice on how to test properly.
--
-- Run with the wrapper:
--   bash scripts/b1_block4_apply.sh

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
\echo '  Block 4: Row-Level Security policies on 17 target tables'
\echo '====================================================================='
\echo ''

BEGIN;

-- =====================================================================
-- 0. Build the target table list (drops user_credentials if Phase A
--    already configured FORCE RLS + at least one policy on it).
-- =====================================================================
\echo '[0/4] Building target table list...'

CREATE TEMP TABLE _b1_b4_targets (
    table_name text PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO _b1_b4_targets VALUES
    ('bot_daily_state'), ('bot_entry_context'), ('bot_entry_prices'),
    ('bot_ml_metrics'), ('bot_ml_training'), ('bot_performance'),
    ('bot_regime_stats'), ('bot_symbol_scores'), ('bot_trade_outcomes'),
    ('assistant_history'), ('assistant_suggestions'), ('daily_reports'),
    ('signals'), ('trades'), ('alerts_log'), ('killswitch_state'),
    ('user_credentials');

DO $detect$
DECLARE
    rls_on    boolean;
    force_on  boolean;
    pol_count integer;
BEGIN
    SELECT c.relrowsecurity, c.relforcerowsecurity
    INTO rls_on, force_on
    FROM pg_class c
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public' AND c.relname = 'user_credentials';

    SELECT count(*) INTO pol_count
    FROM pg_policy p
    JOIN pg_class c ON p.polrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public' AND c.relname = 'user_credentials';

    RAISE NOTICE 'user_credentials state: rls=% force=% policies=%',
        rls_on, force_on, pol_count;

    IF rls_on AND force_on AND pol_count >= 1 THEN
        DELETE FROM _b1_b4_targets WHERE table_name = 'user_credentials';
        RAISE NOTICE 'user_credentials has Phase A RLS - SKIPPED. % policies preserved.',
            pol_count;
    ELSE
        RAISE NOTICE 'user_credentials does not have FORCE RLS yet - INCLUDED in Block 4.';
    END IF;
END
$detect$;

-- =====================================================================
-- 1. Apply ENABLE + FORCE + 2 policies on each target table.
-- =====================================================================
\echo '[1/4] Applying RLS to target tables...'

DO $apply$
DECLARE
    t text;
    n_targets integer;
    n_done    integer := 0;
BEGIN
    SELECT count(*) INTO n_targets FROM _b1_b4_targets;

    FOR t IN SELECT table_name FROM _b1_b4_targets ORDER BY table_name LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE  ROW LEVEL SECURITY', t);

        -- Idempotent policy upsert: PG has no CREATE POLICY IF NOT EXISTS.
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format('DROP POLICY IF EXISTS admin_bypass     ON %I', t);

        -- Policy 1: per-tenant isolation.
        --   nullif(setting, '') -> NULL when unset, so "= NULL" is FALSE
        --   and zero rows are visible without an explicit tenant context.
        EXECUTE format($pol$
            CREATE POLICY tenant_isolation ON %I
                AS PERMISSIVE
                FOR ALL
                USING (
                    tenant_id = nullif(current_setting('app.current_tenant', true), '')::uuid
                )
                WITH CHECK (
                    tenant_id = nullif(current_setting('app.current_tenant', true), '')::uuid
                )
        $pol$, t);

        -- Policy 2: admin bypass for cross-tenant operations.
        --   Set with: SELECT set_config('app.bypass_rls', 'on', true);
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
        RAISE NOTICE '  [%/%]  %  RLS + 2 policies applied',
            n_done, n_targets, rpad(t, 28);
    END LOOP;
END
$apply$;

-- =====================================================================
-- 2. Syntactic verifications. Aborts the transaction if anything is off.
-- =====================================================================
\echo '[2/4] Verifying RLS state + policy counts...'

DO $verify$
DECLARE
    n_targets    integer;
    n_rls_on     integer;
    n_force_on   integer;
    n_isolation  integer;
    n_bypass     integer;
BEGIN
    SELECT count(*) INTO n_targets FROM _b1_b4_targets;

    SELECT count(*) INTO n_rls_on
    FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relname IN (SELECT table_name FROM _b1_b4_targets)
      AND c.relrowsecurity = true;

    SELECT count(*) INTO n_force_on
    FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relname IN (SELECT table_name FROM _b1_b4_targets)
      AND c.relforcerowsecurity = true;

    SELECT count(*) INTO n_isolation
    FROM pg_policy p
    JOIN pg_class c ON p.polrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relname IN (SELECT table_name FROM _b1_b4_targets)
      AND p.polname = 'tenant_isolation';

    SELECT count(*) INTO n_bypass
    FROM pg_policy p
    JOIN pg_class c ON p.polrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relname IN (SELECT table_name FROM _b1_b4_targets)
      AND p.polname = 'admin_bypass';

    RAISE NOTICE '  target tables:                 %', n_targets;
    RAISE NOTICE '  ENABLE ROW LEVEL SECURITY  ->  %', n_rls_on;
    RAISE NOTICE '  FORCE  ROW LEVEL SECURITY  ->  %', n_force_on;
    RAISE NOTICE '  policy "tenant_isolation"  ->  %', n_isolation;
    RAISE NOTICE '  policy "admin_bypass"      ->  %', n_bypass;

    IF n_rls_on    <> n_targets THEN RAISE EXCEPTION 'RLS not enabled on all targets: % of %',     n_rls_on,    n_targets; END IF;
    IF n_force_on  <> n_targets THEN RAISE EXCEPTION 'RLS not forced on all targets: % of %',      n_force_on,  n_targets; END IF;
    IF n_isolation <> n_targets THEN RAISE EXCEPTION 'tenant_isolation missing on some: % of %',   n_isolation, n_targets; END IF;
    IF n_bypass    <> n_targets THEN RAISE EXCEPTION 'admin_bypass missing on some: % of %',       n_bypass,    n_targets; END IF;

    RAISE NOTICE 'Syntactic verifications: OK.';
END
$verify$;

-- =====================================================================
-- 3. Functional isolation tests against bot_trade_outcomes (31 rows).
--    Skipped if current_user has BYPASSRLS, in which case RLS does
--    not apply and the tests would be vacuous (or pass trivially).
-- =====================================================================
\echo '[3/4] Functional isolation tests...'

DO $functional$
DECLARE
    has_bypass boolean;
    n          integer;
BEGIN
    SELECT rolbypassrls INTO has_bypass
    FROM pg_roles WHERE rolname = current_user;

    IF has_bypass THEN
        RAISE NOTICE '';
        RAISE NOTICE 'WARNING: current user "%" has BYPASSRLS attribute.', current_user;
        RAISE NOTICE 'RLS does not apply to this role, so functional isolation';
        RAISE NOTICE 'tests would be vacuous. Skipping.';
        RAISE NOTICE '';
        RAISE NOTICE 'To test isolation properly, run:';
        RAISE NOTICE '  bash scripts/b1_block4_test_isolation.sh';
        RAISE NOTICE '(uses a non-privileged role, fails if anything is off)';
        RETURN;
    END IF;

    -- Test 1: no tenant context -> 0 visible rows.
    PERFORM set_config('app.current_tenant', '',  true);
    PERFORM set_config('app.bypass_rls',     '',  true);
    SELECT count(*) INTO n FROM bot_trade_outcomes;
    IF n <> 0 THEN
        RAISE EXCEPTION 'Test 1 FAIL: expected 0 visible rows w/o tenant context, got %', n;
    END IF;
    RAISE NOTICE '  Test 1 OK: 0 rows w/o tenant context.';

    -- Test 2: default tenant -> 31 visible rows (matches Block 3 backfill).
    PERFORM set_config('app.current_tenant', '00000000-0000-0000-0000-000000000001', true);
    SELECT count(*) INTO n FROM bot_trade_outcomes;
    IF n <> 31 THEN
        RAISE EXCEPTION 'Test 2 FAIL: expected 31 rows for default tenant, got %', n;
    END IF;
    RAISE NOTICE '  Test 2 OK: 31 rows for default tenant.';

    -- Test 3: non-existent tenant -> 0 visible rows.
    PERFORM set_config('app.current_tenant', 'ffffffff-ffff-ffff-ffff-ffffffffffff', true);
    SELECT count(*) INTO n FROM bot_trade_outcomes;
    IF n <> 0 THEN
        RAISE EXCEPTION 'Test 3 FAIL: expected 0 rows for unknown tenant, got %', n;
    END IF;
    RAISE NOTICE '  Test 3 OK: 0 rows for unknown tenant.';

    -- Test 4: bypass policy -> 31 visible rows.
    PERFORM set_config('app.current_tenant', '',   true);
    PERFORM set_config('app.bypass_rls',     'on', true);
    SELECT count(*) INTO n FROM bot_trade_outcomes;
    IF n <> 31 THEN
        RAISE EXCEPTION 'Test 4 FAIL: bypass should reveal 31 rows, got %', n;
    END IF;
    RAISE NOTICE '  Test 4 OK: bypass reveals all 31 rows.';

    -- Cleanup session vars.
    PERFORM set_config('app.current_tenant', '', true);
    PERFORM set_config('app.bypass_rls',     '', true);

    RAISE NOTICE 'Functional tests: OK.';
END
$functional$;

-- =====================================================================
-- 4. Final per-table snapshot for the audit log.
-- =====================================================================
\echo '[4/4] Final per-table RLS snapshot...'

\echo ''
\echo '--- RLS state per target table ---'
SELECT
    c.relname                              AS table_name,
    c.relrowsecurity                       AS rls_enabled,
    c.relforcerowsecurity                  AS rls_forced,
    (SELECT count(*) FROM pg_policy p
     WHERE p.polrelid = c.oid)             AS policy_count
FROM pg_class c
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname = 'public'
  AND c.relname IN (SELECT table_name FROM _b1_b4_targets)
ORDER BY c.relname;

COMMIT;

\echo ''
\echo '====================================================================='
\echo '  Block 4 committed. Next: Block 5 (app layer integration).'
\echo '====================================================================='
