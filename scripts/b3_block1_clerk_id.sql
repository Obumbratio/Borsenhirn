-- scripts/b3_block1_clerk_id.sql
--
-- B3 Bloque 1: mapeo identidad Clerk -> tenant.
-- Agrega `clerk_user_id` a tenants (modelo 1 usuario Clerk = 1 tenant).
--
--   - text UNIQUE: un clerk_user_id mapea a un solo tenant. La unique
--     constraint hace la provisión lazy race-safe (ON CONFLICT).
--   - nullable: los tenants system/default (legacy) lo tienen NULL; UNIQUE
--     en Postgres permite múltiples NULL.
--
-- IDEMPOTENTE. Guard: corre en dev (no prod). A prod va con su propio apply
-- (estilo B1 Bloque 8) cuando se decida.
--
-- Run:  bash scripts/b3_block1_apply.sh   (o psql directo en dev)

DO $guard$
BEGIN
    IF current_database() = 'borsenhirn' THEN
        RAISE EXCEPTION
          'ABORT: no correr en produccion "borsenhirn". Correr en borsenhirn_dev.';
    END IF;
    RAISE NOTICE 'Guard OK. Database: %', current_database();
END
$guard$;

BEGIN;

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS clerk_user_id text;

-- Unique constraint idempotente (solo si no existe ya).
DO $uniq$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'tenants_clerk_user_id_key'
          AND conrelid = 'tenants'::regclass
    ) THEN
        ALTER TABLE tenants ADD CONSTRAINT tenants_clerk_user_id_key
            UNIQUE (clerk_user_id);
        RAISE NOTICE 'unique constraint tenants_clerk_user_id_key creada';
    ELSE
        RAISE NOTICE 'unique constraint ya existe (no-op)';
    END IF;
END
$uniq$;

-- Verificación.
DO $verify$
DECLARE has_col boolean; has_uniq boolean;
BEGIN
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                  WHERE table_name='tenants' AND column_name='clerk_user_id') INTO has_col;
    SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='tenants_clerk_user_id_key') INTO has_uniq;
    IF NOT has_col  THEN RAISE EXCEPTION 'falta columna clerk_user_id'; END IF;
    IF NOT has_uniq THEN RAISE EXCEPTION 'falta unique constraint'; END IF;
    RAISE NOTICE 'OK: clerk_user_id (text, UNIQUE) presente en tenants.';
END
$verify$;

COMMIT;
