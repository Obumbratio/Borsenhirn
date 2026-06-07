-- scripts/b7_block1_legal_acceptance.sql
--
-- B7 Bloque 1: tabla legal_acceptance (append-only, tenant-scoped + RLS).
-- Registra qué versión de terms/privacy aceptó cada tenant, cuándo y desde dónde.
-- APPEND-ONLY: el rol app recibe solo INSERT + SELECT (sin UPDATE/DELETE).
--
-- IDEMPOTENTE. Guard: corre en dev (no prod).

DO $guard$
BEGIN
    IF current_database() = 'borsenhirn' THEN
        RAISE EXCEPTION 'ABORT: no correr en produccion. Correr en borsenhirn_dev.';
    END IF;
    RAISE NOTICE 'Guard OK. Database: %', current_database();
END
$guard$;

BEGIN;

CREATE TABLE IF NOT EXISTS legal_acceptance (
    id          bigserial   PRIMARY KEY,
    tenant_id   uuid        NOT NULL DEFAULT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid,
    document    text        NOT NULL CHECK (document IN ('terms', 'privacy')),
    version     text        NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT now(),
    actor       text        NOT NULL,
    metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb
);

DO $fk$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname='fk_legal_acceptance_tenant' AND conrelid='legal_acceptance'::regclass) THEN
        ALTER TABLE legal_acceptance ADD CONSTRAINT fk_legal_acceptance_tenant
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE RESTRICT;
    END IF;
END
$fk$;

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

DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='borsenhirn_app') THEN
        EXECUTE 'GRANT INSERT, SELECT ON legal_acceptance TO borsenhirn_app';
        EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE legal_acceptance_id_seq TO borsenhirn_app';
        EXECUTE 'REVOKE UPDATE, DELETE ON legal_acceptance FROM borsenhirn_app';
        RAISE NOTICE 'grants append-only a borsenhirn_app';
    END IF;
END
$grant$;

DO $verify$
DECLARE has_upd boolean; has_del boolean;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='borsenhirn_app') THEN
        has_upd := has_table_privilege('borsenhirn_app', 'legal_acceptance', 'UPDATE');
        has_del := has_table_privilege('borsenhirn_app', 'legal_acceptance', 'DELETE');
        IF has_upd OR has_del THEN RAISE EXCEPTION 'app role NO debe tener UPDATE/DELETE'; END IF;
        RAISE NOTICE 'OK: legal_acceptance append-only.';
    END IF;
END
$verify$;

COMMIT;
