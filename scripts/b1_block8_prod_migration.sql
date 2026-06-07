-- scripts/b1_block8_prod_migration.sql
--
-- Sprint B1 - Block 8: migracion CONSOLIDADA a PRODUCCION (borsenhirn).
--
-- Aplica en una sola transaccion idempotente el estado final multi-tenant
-- ya probado en borsenhirn_dev (Bloques 2..7), con dos diferencias prod:
--   * Las 4 legacy se RENOMBRAN a _legacy_* (NO se dropean).
--   * Las RLS policies usan directo el GUC final `app.current_tenant_id`
--     (sin el paso intermedio del Bloque 4.5).
--
-- GUARD: solo corre contra `borsenhirn`. En cualquier otra DB aborta.
-- IDEMPOTENTE: ON CONFLICT / IF EXISTS / IF NOT EXISTS / drop-then-add.
-- ATOMICA: un solo BEGIN/COMMIT; cualquier fallo => rollback total.
--
-- PRE-REQUISITO OBLIGATORIO: backup verificado (GATE 1 del plan B8).
-- Correr con el wrapper:  B1_ALLOW_PROD=1 bash scripts/b1_block8_apply.sh

-- =====================================================================
-- SAFETY GUARD: esta migracion es SOLO para produccion.
-- =====================================================================
DO $guard$
BEGIN
    IF current_database() <> 'borsenhirn' THEN
        RAISE EXCEPTION
          'ABORT: b1_block8 es solo para produccion "borsenhirn". DB actual: %', current_database();
    END IF;
    RAISE NOTICE 'Guard OK. Database: % (PRODUCCION)', current_database();
END
$guard$;

\echo ''
\echo '====================================================================='
\echo '  Block 8: migracion consolidada multi-tenant -> PRODUCCION'
\echo '====================================================================='
\echo ''

BEGIN;

-- Lista canonica de las 17 tablas A (reusada por varios pasos).
CREATE TEMP TABLE _b8_targets (table_name text PRIMARY KEY) ON COMMIT DROP;
INSERT INTO _b8_targets VALUES
    ('bot_daily_state'),('bot_entry_context'),('bot_entry_prices'),
    ('bot_ml_metrics'),('bot_ml_training'),('bot_performance'),
    ('bot_regime_stats'),('bot_symbol_scores'),('bot_trade_outcomes'),
    ('assistant_history'),('assistant_suggestions'),('daily_reports'),
    ('signals'),('trades'),('alerts_log'),('killswitch_state'),
    ('user_credentials');

-- =====================================================================
-- 1. Default tenant (idempotente).
-- =====================================================================
\echo '[1/7] Asegurando default tenant...'
INSERT INTO tenants (tenant_id, slug, email, display_name, status, metadata)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'default', 'default@borsenhirn.local',
    'Default Tenant (legacy single-user data)', 'active',
    '{"note": "auto-created for B1 multi-tenancy phase B backfill"}'::jsonb
)
ON CONFLICT (tenant_id) DO NOTHING;

-- =====================================================================
-- 2. ARCHIVAR las 4 legacy: RENAME a _legacy_* (NO drop). Idempotente.
-- =====================================================================
\echo '[2/7] Archivando legacy (RENAME a _legacy_*)...'
DO $legacy$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT * FROM (VALUES
        ('bot_state','_legacy_bot_state'),
        ('entry_context','_legacy_entry_context'),
        ('regime_stats','_legacy_regime_stats'),
        ('symbol_memory','_legacy_symbol_memory')
    ) AS t(orig, arch) LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='public' AND table_name=r.orig) THEN
            EXECUTE format('ALTER TABLE %I RENAME TO %I', r.orig, r.arch);
            RAISE NOTICE '  archivada: % -> %', r.orig, r.arch;
        ELSE
            RAISE NOTICE '  skip: % no existe (ya archivada)', r.orig;
        END IF;
    END LOOP;
END
$legacy$;

-- =====================================================================
-- 3. ADD COLUMN tenant_id + FK ON DELETE RESTRICT + index. Idempotente.
--    Dropea cualquier FK preexistente a tenants antes del canonico.
-- =====================================================================
\echo '[3/7] tenant_id + FK + index en las 17 tablas...'
DO $fkidx$
DECLARE
    t TEXT; fk_name TEXT; ix_name TEXT; existing_fk RECORD;
BEGIN
    FOR t IN SELECT table_name FROM _b8_targets LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS tenant_id uuid', t);
        fk_name := 'fk_' || t || '_tenant';
        ix_name := 'ix_' || t || '_tenant_id';
        FOR existing_fk IN
            SELECT c.conname
            FROM pg_constraint c
            JOIN pg_class src ON c.conrelid = src.oid
            JOIN pg_namespace srcn ON src.relnamespace = srcn.oid
            JOIN pg_class dst ON c.confrelid = dst.oid
            WHERE c.contype='f' AND srcn.nspname='public'
              AND src.relname=t AND dst.relname='tenants'
        LOOP
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', t, existing_fk.conname);
            RAISE NOTICE '  drop FK preexistente: %.%', t, existing_fk.conname;
        END LOOP;
        EXECUTE format(
            'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (tenant_id) '
            'REFERENCES tenants(tenant_id) ON DELETE RESTRICT', t, fk_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (tenant_id)', ix_name, t);
    END LOOP;
END
$fkidx$;

-- =====================================================================
-- 4. Backfill al default tenant + verify 0 NULLs.
-- =====================================================================
\echo '[4/7] Backfill tenant_id = default donde sea NULL...'
DO $backfill$
DECLARE t TEXT; n BIGINT; total BIGINT := 0; nulls BIGINT;
BEGIN
    FOR t IN SELECT table_name FROM _b8_targets LOOP
        EXECUTE format(
            'UPDATE %I SET tenant_id = %L WHERE tenant_id IS NULL', t,
            '00000000-0000-0000-0000-000000000001');
        GET DIAGNOSTICS n = ROW_COUNT;
        IF n > 0 THEN RAISE NOTICE '  backfill %: % filas', t, n; END IF;
        total := total + n;
    END LOOP;
    RAISE NOTICE '  total backfilled: %', total;

    -- verify 0 NULLs
    FOR t IN SELECT table_name FROM _b8_targets LOOP
        EXECUTE format('SELECT count(*) FROM %I WHERE tenant_id IS NULL', t) INTO nulls;
        IF nulls > 0 THEN
            RAISE EXCEPTION 'ABORT: % aun tiene % filas con tenant_id NULL', t, nulls;
        END IF;
    END LOOP;
    RAISE NOTICE '  verify: 0 NULLs en las 17 tablas. OK.';
END
$backfill$;

-- =====================================================================
-- 5. SET NOT NULL en las 17.
-- =====================================================================
\echo '[5/7] SET NOT NULL en tenant_id...'
DO $notnull$
DECLARE t TEXT;
BEGIN
    FOR t IN SELECT table_name FROM _b8_targets LOOP
        EXECUTE format('ALTER TABLE %I ALTER COLUMN tenant_id SET NOT NULL', t);
    END LOOP;
END
$notnull$;

-- =====================================================================
-- 6. ENABLE + FORCE RLS + 2 policies (GUC final app.current_tenant_id).
-- =====================================================================
\echo '[6/7] RLS enable+force + policies (app.current_tenant_id)...'
DO $rls$
DECLARE t TEXT;
BEGIN
    FOR t IN SELECT table_name FROM _b8_targets LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE  ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format('DROP POLICY IF EXISTS admin_bypass     ON %I', t);
        EXECUTE format($pol$
            CREATE POLICY tenant_isolation ON %I AS PERMISSIVE FOR ALL
                USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid)
        $pol$, t);
        EXECUTE format($pol$
            CREATE POLICY admin_bypass ON %I AS PERMISSIVE FOR ALL
                USING (nullif(current_setting('app.bypass_rls', true), '') = 'on')
                WITH CHECK (nullif(current_setting('app.bypass_rls', true), '') = 'on')
        $pol$, t);
    END LOOP;
END
$rls$;

-- =====================================================================
-- 7. DEFAULT tenant_id desde el GUC de sesion (fix Bloque 7).
-- =====================================================================
\echo '[7/7] DEFAULT tenant_id desde el GUC...'
DO $default$
DECLARE t TEXT;
BEGIN
    FOR t IN SELECT table_name FROM _b8_targets LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN tenant_id SET DEFAULT '
            'NULLIF(current_setting(%L, true), %L)::uuid',
            t, 'app.current_tenant_id', '');
    END LOOP;
END
$default$;

-- =====================================================================
-- VERIFICACION FINAL (aborta -> rollback si algo falta).
-- =====================================================================
\echo '[verify] Chequeos finales intra-transaccion...'
DO $finalverify$
DECLARE
    n_targets   int;
    n_notnull   int;
    n_rls       int;
    n_force     int;
    n_iso       int;
    n_bypass    int;
    n_default   int;
    n_legacy    int;
    has_default boolean;
BEGIN
    SELECT count(*) INTO n_targets FROM _b8_targets;

    SELECT count(*) INTO n_notnull FROM information_schema.columns
      WHERE table_schema='public' AND column_name='tenant_id' AND is_nullable='NO'
        AND table_name IN (SELECT table_name FROM _b8_targets);

    SELECT count(*) INTO n_rls   FROM pg_class WHERE relname IN (SELECT table_name FROM _b8_targets) AND relrowsecurity;
    SELECT count(*) INTO n_force FROM pg_class WHERE relname IN (SELECT table_name FROM _b8_targets) AND relforcerowsecurity;

    SELECT count(*) INTO n_iso FROM pg_policy p JOIN pg_class c ON p.polrelid=c.oid
      WHERE c.relname IN (SELECT table_name FROM _b8_targets) AND p.polname='tenant_isolation'
        AND pg_get_expr(p.polqual, p.polrelid) LIKE '%app.current_tenant_id%';
    SELECT count(*) INTO n_bypass FROM pg_policy p JOIN pg_class c ON p.polrelid=c.oid
      WHERE c.relname IN (SELECT table_name FROM _b8_targets) AND p.polname='admin_bypass';

    SELECT count(*) INTO n_default FROM information_schema.columns
      WHERE table_schema='public' AND column_name='tenant_id' AND column_default IS NOT NULL
        AND table_name IN (SELECT table_name FROM _b8_targets);

    SELECT count(*) INTO n_legacy FROM information_schema.tables
      WHERE table_schema='public' AND table_name LIKE '\_legacy\_%';

    SELECT EXISTS(SELECT 1 FROM tenants WHERE tenant_id='00000000-0000-0000-0000-000000000001') INTO has_default;

    RAISE NOTICE '  tablas A: %  | NOT NULL: %  | RLS: %  | FORCE: %', n_targets, n_notnull, n_rls, n_force;
    RAISE NOTICE '  tenant_isolation: %  | admin_bypass: %  | DEFAULT: %', n_iso, n_bypass, n_default;
    RAISE NOTICE '  tablas _legacy_*: %  | default tenant existe: %', n_legacy, has_default;

    IF NOT has_default THEN RAISE EXCEPTION 'falta el default tenant'; END IF;
    IF n_notnull <> n_targets THEN RAISE EXCEPTION 'NOT NULL: % de %', n_notnull, n_targets; END IF;
    IF n_rls     <> n_targets THEN RAISE EXCEPTION 'RLS enabled: % de %', n_rls, n_targets; END IF;
    IF n_force   <> n_targets THEN RAISE EXCEPTION 'RLS forced: % de %', n_force, n_targets; END IF;
    IF n_iso     <> n_targets THEN RAISE EXCEPTION 'tenant_isolation: % de %', n_iso, n_targets; END IF;
    IF n_bypass  <> n_targets THEN RAISE EXCEPTION 'admin_bypass: % de %', n_bypass, n_targets; END IF;
    IF n_default <> n_targets THEN RAISE EXCEPTION 'DEFAULT: % de %', n_default, n_targets; END IF;
    RAISE NOTICE 'VERIFICACION OK: 17/17 en todo.';
END
$finalverify$;

COMMIT;

\echo ''
\echo '====================================================================='
\echo '  Block 8 COMMIT OK. Siguiente: crear rol (b1_block8_create_role.sh)'
\echo '  y verificar (b1_block8_verify.sh).'
\echo '====================================================================='
