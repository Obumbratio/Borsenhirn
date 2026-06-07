-- scripts/b5_block1_audit_log.sql
--
-- B5 Bloque 1: tabla audit_log (append-only, tenant-scoped + RLS).
--   - RLS igual que las tablas A: tenant_isolation + admin_bypass,
--     GUC app.current_tenant_id, DEFAULT tenant_id desde el GUC (fix B7).
--   - APPEND-ONLY: el rol borsenhirn_app recibe SOLO INSERT + SELECT
--     (sin UPDATE ni DELETE) -> el runtime no puede alterar el historial.
--
-- IDEMPOTENTE. Guard: corre en dev (no prod). A prod va con su apply (B8-style).

DO $guard$
BEGIN
    IF current_database() = 'borsenhirn' THEN
        RAISE EXCEPTION 'ABORT: no correr en produccion. Correr en borsenhirn_dev.';
    END IF;
    RAISE NOTICE 'Guard OK. Database: %', current_database();
END
$guard$;

BEGIN;

CREATE TABLE IF NOT EXISTS audit_log (
    id         bigserial   PRIMARY KEY,
    tenant_id  uuid        NOT NULL DEFAULT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid,
    actor      text        NOT NULL,
    action     text        NOT NULL,
    resource   text,
    at         timestamptz NOT NULL DEFAULT now(),
    metadata   jsonb       NOT NULL DEFAULT '{}'::jsonb
);

-- FK + index (idempotente).
DO $fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_audit_log_tenant' AND conrelid = 'audit_log'::regclass
    ) THEN
        ALTER TABLE audit_log ADD CONSTRAINT fk_audit_log_tenant
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE RESTRICT;
    END IF;
END
$fk$;

CREATE INDEX IF NOT EXISTS ix_audit_log_tenant_at ON audit_log (tenant_id, at DESC);

-- RLS: enable + force + 2 policies (mismo patrón que las 17 tablas A).
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

-- APPEND-ONLY grants para el rol app: solo INSERT + SELECT (si el rol existe).
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'borsenhirn_app') THEN
        EXECUTE 'GRANT INSERT, SELECT ON audit_log TO borsenhirn_app';
        EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO borsenhirn_app';
        -- Asegurar que NO tenga UPDATE/DELETE (por si vinieran de un GRANT amplio).
        EXECUTE 'REVOKE UPDATE, DELETE ON audit_log FROM borsenhirn_app';
        RAISE NOTICE 'grants append-only (INSERT+SELECT) a borsenhirn_app';
    ELSE
        RAISE NOTICE 'rol borsenhirn_app no existe (skip grants)';
    END IF;
END
$grant$;

-- Verificación.
DO $verify$
DECLARE has_upd boolean; has_del boolean; has_ins boolean;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'borsenhirn_app') THEN
        has_ins := has_table_privilege('borsenhirn_app', 'audit_log', 'INSERT');
        has_upd := has_table_privilege('borsenhirn_app', 'audit_log', 'UPDATE');
        has_del := has_table_privilege('borsenhirn_app', 'audit_log', 'DELETE');
        IF NOT has_ins THEN RAISE EXCEPTION 'app role sin INSERT en audit_log'; END IF;
        IF has_upd OR has_del THEN RAISE EXCEPTION 'app role NO debe tener UPDATE/DELETE en audit_log'; END IF;
        RAISE NOTICE 'OK: audit_log append-only para borsenhirn_app (INSERT+SELECT, sin UPDATE/DELETE).';
    END IF;
END
$verify$;

COMMIT;
