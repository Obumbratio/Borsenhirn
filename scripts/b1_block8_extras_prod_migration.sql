-- scripts/b1_block8_extras_prod_migration.sql
--
-- Sprint B1 - Block 8 (EXTRAS): migracion CONSOLIDADA a PRODUCCION de las
-- tablas/columnas de B3..B7 que acompañan al core multi-tenant:
--   * B3  -> tenants.clerk_user_id (text UNIQUE)        [mapeo Clerk -> tenant]
--   * B4  -> tenants.{stripe_customer_id (UNIQUE), stripe_subscription_id,
--            plan, current_period_end}                   [billing Stripe]
--   * B5  -> tabla audit_log (RLS + append-only)         [audit log]
--   * B7  -> tabla legal_acceptance (RLS + append-only)  [aceptacion legal]
--
-- Misma DDL ya probada en borsenhirn_dev (b3/b4/b5/b7_block1_*.sql), con el
-- guard INVERTIDO para prod (corre SOLO en `borsenhirn`).
--
-- ORDEN: correr DESPUES de:
--   1) b1_block8_apply.sh        (core 17 tablas)  -> tenants ya existe
--   2) b1_block8_create_role.sh  (rol)             -> borsenhirn_app ya existe
--   3) b1_block8_verify.sh       (GATE 3 core)     -> el conteo "17" de verify
--      asume que audit_log/legal_acceptance AUN no existen; por eso las extras
--      van DESPUES del verify core.
--
-- IDEMPOTENTE (IF NOT EXISTS / ON CONFLICT / drop-then-create policies).
-- ATOMICA: un solo BEGIN/COMMIT; cualquier fallo => rollback total.
-- REQUIERE el rol borsenhirn_app (los GRANTs append-only son obligatorios; si
-- el rol no existe la migracion ABORTA — corre create_role primero).
--
-- Correr con el wrapper:  B1_ALLOW_PROD=1 bash scripts/b1_block8_extras_apply.sh

-- =====================================================================
-- SAFETY GUARD: solo produccion + el rol app debe existir.
-- =====================================================================
DO $guard$
BEGIN
    IF current_database() <> 'borsenhirn' THEN
        RAISE EXCEPTION
          'ABORT: b1_block8_extras es solo para produccion "borsenhirn". DB actual: %', current_database();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'borsenhirn_app') THEN
        RAISE EXCEPTION
          'ABORT: falta el rol borsenhirn_app. Corre b1_block8_create_role.sh ANTES de las extras.';
    END IF;
    RAISE NOTICE 'Guard OK. Database: % (PRODUCCION), rol borsenhirn_app presente.', current_database();
END
$guard$;

\echo ''
\echo '====================================================================='
\echo '  Block 8 EXTRAS: clerk_id + billing + audit_log + legal -> PRODUCCION'
\echo '====================================================================='
\echo ''

BEGIN;

-- =====================================================================
-- B3. tenants.clerk_user_id (text UNIQUE, nullable).
-- =====================================================================
\echo '[1/4] B3: clerk_user_id en tenants...'
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS clerk_user_id text;
DO $b3uniq$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'tenants_clerk_user_id_key' AND conrelid = 'tenants'::regclass
    ) THEN
        ALTER TABLE tenants ADD CONSTRAINT tenants_clerk_user_id_key UNIQUE (clerk_user_id);
        RAISE NOTICE '  unique tenants_clerk_user_id_key creada';
    ELSE
        RAISE NOTICE '  unique clerk_user_id ya existe (no-op)';
    END IF;
END
$b3uniq$;

-- =====================================================================
-- B4. Columnas de billing (Stripe) en tenants.
-- =====================================================================
\echo '[2/4] B4: columnas de billing en tenants...'
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS stripe_customer_id     text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS stripe_subscription_id text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan                   text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS current_period_end     timestamptz;
DO $b4uniq$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'tenants_stripe_customer_id_key' AND conrelid = 'tenants'::regclass
    ) THEN
        ALTER TABLE tenants ADD CONSTRAINT tenants_stripe_customer_id_key UNIQUE (stripe_customer_id);
        RAISE NOTICE '  unique tenants_stripe_customer_id_key creada';
    ELSE
        RAISE NOTICE '  unique stripe_customer_id ya existe (no-op)';
    END IF;
END
$b4uniq$;

-- =====================================================================
-- B5. audit_log (RLS + append-only: el rol app solo INSERT + SELECT).
-- =====================================================================
\echo '[3/4] B5: tabla audit_log (RLS + append-only)...'
CREATE TABLE IF NOT EXISTS audit_log (
    id         bigserial   PRIMARY KEY,
    tenant_id  uuid        NOT NULL DEFAULT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid,
    actor      text        NOT NULL,
    action     text        NOT NULL,
    resource   text,
    at         timestamptz NOT NULL DEFAULT now(),
    metadata   jsonb       NOT NULL DEFAULT '{}'::jsonb
);
DO $b5fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_audit_log_tenant' AND conrelid = 'audit_log'::regclass
    ) THEN
        ALTER TABLE audit_log ADD CONSTRAINT fk_audit_log_tenant
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE RESTRICT;
    END IF;
END
$b5fk$;
CREATE INDEX IF NOT EXISTS ix_audit_log_tenant_at ON audit_log (tenant_id, at DESC);
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON audit_log;
DROP POLICY IF EXISTS admin_bypass     ON audit_log;
CREATE POLICY tenant_isolation ON audit_log AS PERMISSIVE FOR ALL
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid);
CREATE POLICY admin_bypass ON audit_log AS PERMISSIVE FOR ALL
    USING (nullif(current_setting('app.bypass_rls', true), '') = 'on')
    WITH CHECK (nullif(current_setting('app.bypass_rls', true), '') = 'on');
-- Append-only: solo INSERT + SELECT (sin UPDATE/DELETE).
GRANT INSERT, SELECT ON audit_log TO borsenhirn_app;
GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO borsenhirn_app;
REVOKE UPDATE, DELETE ON audit_log FROM borsenhirn_app;

-- =====================================================================
-- B7. legal_acceptance (RLS + append-only).
-- =====================================================================
\echo '[4/4] B7: tabla legal_acceptance (RLS + append-only)...'
CREATE TABLE IF NOT EXISTS legal_acceptance (
    id          bigserial   PRIMARY KEY,
    tenant_id   uuid        NOT NULL DEFAULT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid,
    document    text        NOT NULL CHECK (document IN ('terms', 'privacy')),
    version     text        NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT now(),
    actor       text        NOT NULL,
    metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb
);
DO $b7fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_legal_acceptance_tenant' AND conrelid = 'legal_acceptance'::regclass
    ) THEN
        ALTER TABLE legal_acceptance ADD CONSTRAINT fk_legal_acceptance_tenant
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE RESTRICT;
    END IF;
END
$b7fk$;
CREATE INDEX IF NOT EXISTS ix_legal_acceptance_tenant_doc
    ON legal_acceptance (tenant_id, document, version);
ALTER TABLE legal_acceptance ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_acceptance FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON legal_acceptance;
DROP POLICY IF EXISTS admin_bypass     ON legal_acceptance;
CREATE POLICY tenant_isolation ON legal_acceptance AS PERMISSIVE FOR ALL
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid);
CREATE POLICY admin_bypass ON legal_acceptance AS PERMISSIVE FOR ALL
    USING (nullif(current_setting('app.bypass_rls', true), '') = 'on')
    WITH CHECK (nullif(current_setting('app.bypass_rls', true), '') = 'on');
GRANT INSERT, SELECT ON legal_acceptance TO borsenhirn_app;
GRANT USAGE, SELECT ON SEQUENCE legal_acceptance_id_seq TO borsenhirn_app;
REVOKE UPDATE, DELETE ON legal_acceptance FROM borsenhirn_app;

-- =====================================================================
-- VERIFICACION FINAL (aborta -> rollback si algo falta).
-- =====================================================================
\echo '[verify] Chequeos finales intra-transaccion...'
DO $finalverify$
DECLARE
    has_clerk     boolean;
    has_clerk_u   boolean;
    n_billing     int;
    has_stripe_u  boolean;
    rls_audit     boolean;
    force_audit   boolean;
    pol_audit     int;
    rls_legal     boolean;
    force_legal   boolean;
    pol_legal     int;
    a_ins boolean; a_upd boolean; a_del boolean;
    l_ins boolean; l_upd boolean; l_del boolean;
BEGIN
    -- B3
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                  WHERE table_name='tenants' AND column_name='clerk_user_id') INTO has_clerk;
    SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='tenants_clerk_user_id_key') INTO has_clerk_u;
    IF NOT has_clerk   THEN RAISE EXCEPTION 'falta tenants.clerk_user_id'; END IF;
    IF NOT has_clerk_u THEN RAISE EXCEPTION 'falta unique clerk_user_id'; END IF;

    -- B4
    SELECT count(*) INTO n_billing FROM information_schema.columns
      WHERE table_name='tenants'
        AND column_name IN ('stripe_customer_id','stripe_subscription_id','plan','current_period_end');
    SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='tenants_stripe_customer_id_key') INTO has_stripe_u;
    IF n_billing <> 4    THEN RAISE EXCEPTION 'billing: % de 4 columnas', n_billing; END IF;
    IF NOT has_stripe_u  THEN RAISE EXCEPTION 'falta unique stripe_customer_id'; END IF;

    -- B5 audit_log
    SELECT relrowsecurity, relforcerowsecurity INTO rls_audit, force_audit
      FROM pg_class WHERE relname='audit_log';
    SELECT count(*) INTO pol_audit FROM pg_policy p JOIN pg_class c ON p.polrelid=c.oid
      WHERE c.relname='audit_log' AND p.polname IN ('tenant_isolation','admin_bypass');
    IF NOT rls_audit OR NOT force_audit THEN RAISE EXCEPTION 'audit_log sin RLS/FORCE'; END IF;
    IF pol_audit <> 2 THEN RAISE EXCEPTION 'audit_log policies: % de 2', pol_audit; END IF;
    a_ins := has_table_privilege('borsenhirn_app','audit_log','INSERT');
    a_upd := has_table_privilege('borsenhirn_app','audit_log','UPDATE');
    a_del := has_table_privilege('borsenhirn_app','audit_log','DELETE');
    IF NOT a_ins      THEN RAISE EXCEPTION 'app sin INSERT en audit_log'; END IF;
    IF a_upd OR a_del THEN RAISE EXCEPTION 'app con UPDATE/DELETE en audit_log (debe ser append-only)'; END IF;

    -- B7 legal_acceptance
    SELECT relrowsecurity, relforcerowsecurity INTO rls_legal, force_legal
      FROM pg_class WHERE relname='legal_acceptance';
    SELECT count(*) INTO pol_legal FROM pg_policy p JOIN pg_class c ON p.polrelid=c.oid
      WHERE c.relname='legal_acceptance' AND p.polname IN ('tenant_isolation','admin_bypass');
    IF NOT rls_legal OR NOT force_legal THEN RAISE EXCEPTION 'legal_acceptance sin RLS/FORCE'; END IF;
    IF pol_legal <> 2 THEN RAISE EXCEPTION 'legal_acceptance policies: % de 2', pol_legal; END IF;
    l_ins := has_table_privilege('borsenhirn_app','legal_acceptance','INSERT');
    l_upd := has_table_privilege('borsenhirn_app','legal_acceptance','UPDATE');
    l_del := has_table_privilege('borsenhirn_app','legal_acceptance','DELETE');
    IF NOT l_ins      THEN RAISE EXCEPTION 'app sin INSERT en legal_acceptance'; END IF;
    IF l_upd OR l_del THEN RAISE EXCEPTION 'app con UPDATE/DELETE en legal_acceptance (debe ser append-only)'; END IF;

    RAISE NOTICE 'VERIFICACION OK: clerk_id + 4 billing + audit_log + legal_acceptance (RLS+append-only).';
END
$finalverify$;

COMMIT;

\echo ''
\echo '====================================================================='
\echo '  Block 8 EXTRAS COMMIT OK. clerk_id/billing/audit/legal en prod.'
\echo '====================================================================='
