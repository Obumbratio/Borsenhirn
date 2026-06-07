-- scripts/b1_block8_create_role.sql
--
-- Sprint B1 - Block 8: provision del rol `borsenhirn_app` en PRODUCCION.
-- Mismo contenido que block5 (dev) pero el guard exige `borsenhirn`.
--
-- Password via psql var `role_password`. El wrapper
-- scripts/b1_block8_create_role.sh lo pide y valida >=16 chars.
--
-- IDEMPOTENTE y TRANSACCIONAL.

\if :{?role_password}
\else
    \echo 'ERROR: psql var role_password no provista. Usa el wrapper b1_block8_create_role.sh'
    \quit 1
\endif

-- =====================================================================
-- SAFETY GUARD: solo produccion.
-- =====================================================================
DO $guard$
BEGIN
    IF current_database() <> 'borsenhirn' THEN
        RAISE EXCEPTION 'ABORT: b1_block8 rol es solo para "borsenhirn". DB actual: %', current_database();
    END IF;
    RAISE NOTICE 'Guard OK. Database: % (PRODUCCION)', current_database();
END
$guard$;

\echo ''
\echo '====================================================================='
\echo '  Block 8: provision rol borsenhirn_app + GRANTs (PRODUCCION)'
\echo '====================================================================='
\echo ''

BEGIN;

\echo '[1/5] Creando o actualizando rol borsenhirn_app...'
SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='borsenhirn_app') AS role_exists \gset
\if :role_exists
    \echo '  Existe - rotando password + asegurando atributos.'
    ALTER ROLE borsenhirn_app WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB PASSWORD :'role_password';
\else
    \echo '  No existe - creando.'
    CREATE ROLE borsenhirn_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB PASSWORD :'role_password';
\endif

\echo '[2/5] GRANT CONNECT + USAGE schema...'
DO $conn$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO borsenhirn_app', current_database());
END
$conn$;
GRANT USAGE ON SCHEMA public TO borsenhirn_app;

\echo '[3/5] GRANT CRUD en las 17 tablas A + SELECT en tenants...'
DO $tablegrants$
DECLARE
    t TEXT;
    tables_a TEXT[] := ARRAY[
        'bot_daily_state','bot_entry_context','bot_entry_prices',
        'bot_ml_metrics','bot_ml_training','bot_performance',
        'bot_regime_stats','bot_symbol_scores','bot_trade_outcomes',
        'assistant_history','assistant_suggestions','daily_reports',
        'signals','trades','alerts_log','killswitch_state','user_credentials'
    ];
BEGIN
    FOREACH t IN ARRAY tables_a LOOP
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO borsenhirn_app', t);
    END LOOP;
    RAISE NOTICE '  CRUD en % tablas.', array_length(tables_a,1);
END
$tablegrants$;
GRANT SELECT ON tenants TO borsenhirn_app;

\echo '[4/5] GRANT sequences...'
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO borsenhirn_app;

\echo '[5/5] Verificando (aborta si BYPASSRLS/SUPERUSER o INSERT en tenants)...'
DO $verify$
DECLARE has_login boolean; has_bypass boolean; has_super boolean;
        crud boolean; sel_t boolean; ins_t boolean;
BEGIN
    SELECT rolcanlogin, rolbypassrls, rolsuper INTO has_login, has_bypass, has_super
      FROM pg_roles WHERE rolname='borsenhirn_app';
    IF NOT has_login THEN RAISE EXCEPTION 'borsenhirn_app sin LOGIN'; END IF;
    IF has_bypass THEN RAISE EXCEPTION 'borsenhirn_app tiene BYPASSRLS - RIESGO'; END IF;
    IF has_super  THEN RAISE EXCEPTION 'borsenhirn_app tiene SUPERUSER - RIESGO'; END IF;

    crud := has_table_privilege('borsenhirn_app','bot_trade_outcomes','SELECT')
        AND has_table_privilege('borsenhirn_app','bot_trade_outcomes','INSERT')
        AND has_table_privilege('borsenhirn_app','bot_trade_outcomes','UPDATE')
        AND has_table_privilege('borsenhirn_app','bot_trade_outcomes','DELETE');
    IF NOT crud THEN RAISE EXCEPTION 'falta CRUD en bot_trade_outcomes'; END IF;

    sel_t := has_table_privilege('borsenhirn_app','tenants','SELECT');
    ins_t := has_table_privilege('borsenhirn_app','tenants','INSERT');
    IF NOT sel_t THEN RAISE EXCEPTION 'falta SELECT en tenants'; END IF;
    IF ins_t THEN RAISE EXCEPTION 'borsenhirn_app NO debe tener INSERT en tenants'; END IF;

    RAISE NOTICE '  OK: LOGIN=t BYPASSRLS=f SUPERUSER=f; CRUD ok; tenants read-only.';
END
$verify$;

COMMIT;

\echo ''
\echo '====================================================================='
\echo '  Rol prod OK. Agrega APP_DB_USER + APP_DB_PASSWORD al .env de prod'
\echo '  (NO a git). Luego: bash scripts/b1_block8_verify.sh'
\echo '====================================================================='
