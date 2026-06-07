-- scripts/b1_block5_create_role.sql
--
-- Sprint B1 - Block 5: provision the application-level role
-- `borsenhirn_app` with the minimal privileges needed for normal
-- runtime (queries against the 17 A tables + read-only tenants),
-- and explicitly without BYPASSRLS / SUPERUSER.
--
-- The role's password is provided via psql variable `role_password`.
-- The wrapper scripts/b1_block5_create_role.sh prompts for it AND
-- enforces a >=16 char minimum (so the SQL file does not duplicate
-- that check - it would require a DO block, where psql vars cannot
-- be substituted).
--
-- Run this SQL file directly only if you really know what you are doing:
--   psql ... -v role_password='xxx' -1 -f b1_block5_create_role.sql
--
-- This script is IDEMPOTENT and TRANSACTIONAL:
--   - If the role already exists, ALTER refreshes attributes + password.
--   - If the role does not exist, CREATE provisions it.
--   - GRANTs are additive; re-running them is harmless.
--   - All operations happen inside a single BEGIN/COMMIT.

-- =====================================================================
-- Pre-flight: psql variable role_password must be defined.
-- =====================================================================
\if :{?role_password}
\else
    \echo 'ERROR: psql variable role_password not provided.'
    \echo '       Run via the wrapper: bash scripts/b1_block5_create_role.sh'
    \quit 1
\endif

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
\echo '  Block 5: provision borsenhirn_app role + GRANTs'
\echo '====================================================================='
\echo ''

BEGIN;

-- =====================================================================
-- 1. Create or update the role.
--    Branch on existence using \gset + \if (psql client-side conditional)
--    so the password psql variable can be substituted directly into the
--    CREATE / ALTER statements (which do not allow this inside DO blocks).
--    Attributes: LOGIN, NOSUPERUSER, NOBYPASSRLS, NOCREATEDB.
-- =====================================================================
\echo '[1/5] Creating or updating role borsenhirn_app...'

SELECT EXISTS(
    SELECT 1 FROM pg_roles WHERE rolname = 'borsenhirn_app'
) AS role_exists \gset

\if :role_exists
    \echo '  Role borsenhirn_app already exists - rotating password + ensuring attributes.'
    ALTER ROLE borsenhirn_app WITH
        LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB
        PASSWORD :'role_password';
\else
    \echo '  Role borsenhirn_app does not exist - creating fresh.'
    CREATE ROLE borsenhirn_app
        LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB
        PASSWORD :'role_password';
\endif

-- =====================================================================
-- 2. Grant CONNECT on this database + USAGE on schema public.
-- =====================================================================
\echo '[2/5] Granting CONNECT + schema USAGE...'

DO $conn$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO borsenhirn_app', current_database());
    RAISE NOTICE '  GRANT CONNECT ON % to borsenhirn_app', current_database();
END
$conn$;

GRANT USAGE ON SCHEMA public TO borsenhirn_app;

-- =====================================================================
-- 3. Per-table privileges on the 17 A tables.
--    SELECT, INSERT, UPDATE, DELETE on each.
-- =====================================================================
\echo '[3/5] Granting CRUD on the 17 A tables...'

DO $tablegrants$
DECLARE
    t TEXT;
    tables_a TEXT[] := ARRAY[
        'bot_daily_state','bot_entry_context','bot_entry_prices',
        'bot_ml_metrics','bot_ml_training','bot_performance',
        'bot_regime_stats','bot_symbol_scores','bot_trade_outcomes',
        'assistant_history','assistant_suggestions','daily_reports',
        'signals','trades','alerts_log','killswitch_state',
        'user_credentials'
    ];
BEGIN
    FOREACH t IN ARRAY tables_a LOOP
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO borsenhirn_app',
            t
        );
    END LOOP;
    RAISE NOTICE '  Granted CRUD on % tables.', array_length(tables_a, 1);
END
$tablegrants$;

-- tenants is read-only for the application role. Tenant lifecycle
-- (create/suspend/delete) is the job of TenantManager run with admin
-- credentials, never the regular runtime role.
GRANT SELECT ON tenants TO borsenhirn_app;

-- =====================================================================
-- 4. Sequence privileges (USAGE for nextval on SERIAL/IDENTITY columns).
-- =====================================================================
\echo '[4/5] Granting sequence USAGE...'

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO borsenhirn_app;

-- =====================================================================
-- 5. Verifications. RAISE EXCEPTION on any anomaly -> rollback.
-- =====================================================================
\echo '[5/5] Verifying role + privileges...'

DO $verify$
DECLARE
    has_login          boolean;
    has_bypass         boolean;
    has_super          boolean;
    can_select_btoutc  boolean;
    can_insert_btoutc  boolean;
    can_update_btoutc  boolean;
    can_delete_btoutc  boolean;
    can_select_tenants boolean;
    can_insert_tenants boolean;
BEGIN
    SELECT rolcanlogin, rolbypassrls, rolsuper
    INTO has_login, has_bypass, has_super
    FROM pg_roles WHERE rolname = 'borsenhirn_app';

    IF NOT has_login THEN RAISE EXCEPTION 'borsenhirn_app missing LOGIN attribute'; END IF;
    IF has_bypass    THEN RAISE EXCEPTION 'borsenhirn_app HAS BYPASSRLS - SECURITY RISK'; END IF;
    IF has_super     THEN RAISE EXCEPTION 'borsenhirn_app HAS SUPERUSER - SECURITY RISK'; END IF;

    can_select_btoutc := has_table_privilege('borsenhirn_app', 'bot_trade_outcomes', 'SELECT');
    can_insert_btoutc := has_table_privilege('borsenhirn_app', 'bot_trade_outcomes', 'INSERT');
    can_update_btoutc := has_table_privilege('borsenhirn_app', 'bot_trade_outcomes', 'UPDATE');
    can_delete_btoutc := has_table_privilege('borsenhirn_app', 'bot_trade_outcomes', 'DELETE');

    IF NOT (can_select_btoutc AND can_insert_btoutc AND can_update_btoutc AND can_delete_btoutc) THEN
        RAISE EXCEPTION 'borsenhirn_app missing CRUD on bot_trade_outcomes (sample)';
    END IF;

    can_select_tenants := has_table_privilege('borsenhirn_app', 'tenants', 'SELECT');
    can_insert_tenants := has_table_privilege('borsenhirn_app', 'tenants', 'INSERT');

    IF NOT can_select_tenants THEN RAISE EXCEPTION 'borsenhirn_app missing SELECT on tenants'; END IF;
    IF can_insert_tenants     THEN RAISE EXCEPTION 'borsenhirn_app should NOT have INSERT on tenants (must stay read-only)'; END IF;

    RAISE NOTICE '  role attributes:    LOGIN=t  BYPASSRLS=f  SUPERUSER=f';
    RAISE NOTICE '  bot_trade_outcomes: SELECT=t  INSERT=t  UPDATE=t  DELETE=t';
    RAISE NOTICE '  tenants:            SELECT=t  INSERT=f (read-only - OK)';
    RAISE NOTICE 'Verifications OK.';
END
$verify$;

\echo ''
\echo '--- Privilege summary on the 17 A tables ---'
SELECT
    table_name,
    has_table_privilege('borsenhirn_app', table_name, 'SELECT') AS can_select,
    has_table_privilege('borsenhirn_app', table_name, 'INSERT') AS can_insert,
    has_table_privilege('borsenhirn_app', table_name, 'UPDATE') AS can_update,
    has_table_privilege('borsenhirn_app', table_name, 'DELETE') AS can_delete
FROM (VALUES
    ('bot_daily_state'),('bot_entry_context'),('bot_entry_prices'),
    ('bot_ml_metrics'),('bot_ml_training'),('bot_performance'),
    ('bot_regime_stats'),('bot_symbol_scores'),('bot_trade_outcomes'),
    ('assistant_history'),('assistant_suggestions'),('daily_reports'),
    ('signals'),('trades'),('alerts_log'),('killswitch_state'),
    ('user_credentials')
) AS t(table_name)
ORDER BY table_name;

\echo ''
\echo '--- tenants (read-only) ---'
SELECT
    has_table_privilege('borsenhirn_app', 'tenants', 'SELECT') AS can_select,
    has_table_privilege('borsenhirn_app', 'tenants', 'INSERT') AS can_insert,
    has_table_privilege('borsenhirn_app', 'tenants', 'UPDATE') AS can_update,
    has_table_privilege('borsenhirn_app', 'tenants', 'DELETE') AS can_delete;

COMMIT;

\echo ''
\echo '====================================================================='
\echo '  Block 5 role + GRANTs committed.'
\echo '  Add APP_DB_USER + APP_DB_PASSWORD to .env.dev (NOT to git).'
\echo '====================================================================='
