-- ============================================================================
-- b5_block2_noticias_cache.sql — cache COMPARTIDA del feed de noticias (M-Noticias)
-- ----------------------------------------------------------------------------
-- El feed de noticias es IMPERSONAL: idéntico para todos los tenants (mismo
-- modelo que /signals). Por eso la tabla es GLOBAL (sin tenant_id) y la RLS va
-- DESHABILITADA — no hay nada que aislar por tenant; son hechos públicos de
-- terceros (Benzinga vía Alpaca) servidos igual a todos.
--
-- COPYRIGHT: se persiste SOLO headline + summary + metadatos + link. NUNCA el
-- cuerpo completo del artículo (no hay columna `content`).
--
-- Idempotente. Guard anti-prod: NO corre sobre la base "borsenhirn".
-- Target: borsenhirn_dev.
-- ============================================================================

DO $guard$
BEGIN
    IF current_database() = 'borsenhirn' THEN
        RAISE EXCEPTION
          'ABORT: esta migracion NO debe correr en la base de produccion "borsenhirn". Correla en borsenhirn_dev.';
    END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS noticias_cache (
    id            BIGINT       PRIMARY KEY,             -- id del artículo en Alpaca
    headline      TEXT         NOT NULL,
    summary       TEXT,
    source        TEXT,
    url           TEXT,
    symbols       TEXT[]       NOT NULL DEFAULT '{}',
    images        JSONB        NOT NULL DEFAULT '[]',
    published_at  TIMESTAMPTZ  NOT NULL,                -- created_at de Alpaca
    fetched_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    -- SIN columna `content`: no se guarda el cuerpo del artículo (copyright).
);

CREATE INDEX IF NOT EXISTS idx_noticias_published
    ON noticias_cache (published_at DESC);

CREATE INDEX IF NOT EXISTS idx_noticias_symbols
    ON noticias_cache USING GIN (symbols);

-- Tabla GLOBAL/compartida → RLS deshabilitada a propósito (no hay tenant_id).
ALTER TABLE noticias_cache DISABLE ROW LEVEL SECURITY;

-- El rol de la app (borsenhirn_app, NOBYPASSRLS) necesita CRUD explícito.
GRANT SELECT, INSERT, UPDATE, DELETE ON noticias_cache TO borsenhirn_app;
