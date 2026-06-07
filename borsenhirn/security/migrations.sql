-- borsenhirn/security/migrations.sql
-- Schema para almacenamiento encriptado de credenciales de broker.
-- Aplicar UNA vez antes de usar CredentialStore.

-- ────────────────────────────────────────────────────────
-- Tabla user_credentials
-- ────────────────────────────────────────────────────────
-- Una fila por (user_id, provider).
-- - api_key_ciphertext / api_secret_ciphertext: bytea con output de
--   Vault.encrypt() — Fernet token en bytes (NUNCA texto plano).
-- - encryption_version permite migración futura del esquema de cifrado
--   sin romper filas viejas.
-- - rotated_at se llena solo cuando un script de rotación reencripta
--   esta fila.
-- ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_credentials (
    user_id                uuid         NOT NULL,
    provider               text         NOT NULL,
    api_key_ciphertext     bytea        NOT NULL,
    api_secret_ciphertext  bytea        NOT NULL,
    encryption_version     integer      NOT NULL DEFAULT 1,
    created_at             timestamptz  NOT NULL DEFAULT now(),
    updated_at             timestamptz  NOT NULL DEFAULT now(),
    rotated_at             timestamptz,
    PRIMARY KEY (user_id, provider),
    CHECK (length(api_key_ciphertext) > 0),
    CHECK (length(api_secret_ciphertext) > 0),
    CHECK (encryption_version >= 1)
);

CREATE INDEX IF NOT EXISTS idx_user_credentials_user
    ON user_credentials(user_id);

CREATE INDEX IF NOT EXISTS idx_user_credentials_version
    ON user_credentials(encryption_version)
    WHERE encryption_version > 1;


-- ────────────────────────────────────────────────────────
-- Cleanup automático opcional: trigger que actualiza updated_at
-- ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION _user_credentials_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS user_credentials_updated_at ON user_credentials;
CREATE TRIGGER user_credentials_updated_at
    BEFORE UPDATE ON user_credentials
    FOR EACH ROW
    EXECUTE FUNCTION _user_credentials_set_updated_at();


-- ────────────────────────────────────────────────────────
-- (Opcional) Auditoría de accesos a credenciales
-- ────────────────────────────────────────────────────────
-- Descomentar si querés trazabilidad completa (cuándo se leyó cada
-- credencial). Costoso pero útil para compliance.
--
-- CREATE TABLE IF NOT EXISTS user_credentials_audit (
--     id          bigserial   PRIMARY KEY,
--     user_id     uuid        NOT NULL,
--     provider    text        NOT NULL,
--     action      text        NOT NULL CHECK (action IN ('read','write','delete','rotate')),
--     accessed_at timestamptz NOT NULL DEFAULT now(),
--     accessor    text        -- p.ej. nombre del proceso / IP
-- );
--
-- CREATE INDEX idx_credentials_audit_user_time
--     ON user_credentials_audit(user_id, accessed_at DESC);
