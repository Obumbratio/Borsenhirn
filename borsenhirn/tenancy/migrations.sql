-- borsenhirn/tenancy/migrations.sql
-- Schema base para multi-tenancy con Row-Level Security.
-- Aplicar UNA vez. Aplicación de RLS a tablas existentes se hace
-- via la función helper `borsenhirn_enable_rls(table_name)` en este script.

-- ────────────────────────────────────────────────────────
-- Tabla central: tenants
-- ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id     uuid          PRIMARY KEY,
    slug          text          NOT NULL UNIQUE,
    email         text          NOT NULL,
    display_name  text          NOT NULL,
    status        text          NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','suspended','disabled','deleted')),
    created_at    timestamptz   NOT NULL DEFAULT now(),
    updated_at    timestamptz   NOT NULL DEFAULT now(),
    suspended_at  timestamptz,
    metadata      jsonb         NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_tenants_status
    ON tenants(status)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_tenants_email
    ON tenants(lower(email));


-- ────────────────────────────────────────────────────────
-- Tenant del sistema: para datos pre-multi-tenant (single-user histórico).
-- ────────────────────────────────────────────────────────
INSERT INTO tenants (tenant_id, slug, email, display_name, status, metadata)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    'system',
    'system@borsenhirn.local',
    'System Tenant (legacy single-user data)',
    'active',
    '{"system": true, "note": "auto-created for backwards compatibility"}'::jsonb
)
ON CONFLICT (tenant_id) DO NOTHING;


-- ────────────────────────────────────────────────────────
-- Trigger: updated_at automático en tenants
-- ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION _tenants_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tenants_updated_at ON tenants;
CREATE TRIGGER tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION _tenants_set_updated_at();


-- ────────────────────────────────────────────────────────
-- Helper: agregar tenant_id + RLS a una tabla existente.
-- ────────────────────────────────────────────────────────
-- Uso (desde psql):
--     SELECT borsenhirn_enable_rls('trades');
--     SELECT borsenhirn_enable_rls('positions');
--     SELECT borsenhirn_enable_rls('hirn_memory');
--
-- Lo que hace:
--   1. Agrega columna tenant_id si no existe.
--   2. Backfillea NULL → SYSTEM_TENANT_ID.
--   3. NOT NULL + FK a tenants.
--   4. Index sobre tenant_id.
--   5. Habilita RLS + FORCE RLS (aplica también a owner del schema).
--   6. Crea policy 'tenant_isolation' que filtra por
--      current_setting('app.current_tenant_id').
--
-- Idempotente — podés correrlo varias veces sin daño.
-- ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION borsenhirn_enable_rls(target_table text)
RETURNS void AS $$
DECLARE
    has_column boolean;
    policy_name text := 'tenant_isolation';
BEGIN
    -- 1. ¿Existe ya la columna tenant_id?
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = target_table
           AND column_name = 'tenant_id'
    ) INTO has_column;

    IF NOT has_column THEN
        EXECUTE format('ALTER TABLE %I ADD COLUMN tenant_id uuid', target_table);
        EXECUTE format(
            'UPDATE %I SET tenant_id = %L WHERE tenant_id IS NULL',
            target_table, '00000000-0000-0000-0000-000000000000'
        );
        EXECUTE format('ALTER TABLE %I ALTER COLUMN tenant_id SET NOT NULL',
                       target_table);
        EXECUTE format(
            'ALTER TABLE %I ADD CONSTRAINT %I_tenant_fk
             FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
             ON DELETE RESTRICT',
            target_table, target_table
        );
        EXECUTE format(
            'CREATE INDEX %I ON %I(tenant_id)',
            'idx_' || target_table || '_tenant', target_table
        );
    END IF;

    -- 2. Habilitar RLS + FORCE RLS
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', target_table);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', target_table);

    -- 3. Crear policy si no existe
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE tablename = target_table AND policyname = policy_name
    ) THEN
        EXECUTE format(
            'CREATE POLICY %I ON %I
                 FOR ALL
                 USING (tenant_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::uuid)
                 WITH CHECK (tenant_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::uuid)',
            policy_name, target_table
        );
    END IF;

    RAISE NOTICE 'RLS habilitado en %', target_table;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────
-- Helper: deshabilitar RLS (para emergencias o tests).
-- NO usar en producción sin entender consecuencias.
-- ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION borsenhirn_disable_rls(target_table text)
RETURNS void AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', target_table);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', target_table);
    RAISE NOTICE 'RLS deshabilitado en % (¡cuidado!)', target_table;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────
-- Vista: current_tenant_id para debugging
-- ────────────────────────────────────────────────────────
-- Uso: SELECT * FROM current_tenant_info;
CREATE OR REPLACE VIEW current_tenant_info AS
SELECT
    NULLIF(current_setting('app.current_tenant_id', true), '')::uuid AS tenant_id,
    current_user                                                       AS db_user,
    session_user                                                       AS session_user,
    pg_backend_pid()                                                   AS pid;
