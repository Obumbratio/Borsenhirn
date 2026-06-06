-- scripts/b4_block1_billing_columns.sql
--
-- B4 Bloque 1: columnas de billing (Stripe) en tenants.
--   stripe_customer_id     text UNIQUE  — 1 customer Stripe por tenant
--   stripe_subscription_id text         — suscripción activa
--   plan                   text         — plan/tier contratado
--   current_period_end     timestamptz  — fin del período pago actual
--
-- El estado de pago se refleja en la columna `status` ya existente
-- (active/suspended/disabled/deleted) — B4 solo la mueve según Stripe.
--
-- IDEMPOTENTE. Guard: corre en dev (no prod). A prod va con su apply (estilo B8).

DO $guard$
BEGIN
    IF current_database() = 'borsenhirn' THEN
        RAISE EXCEPTION 'ABORT: no correr en produccion. Correr en borsenhirn_dev.';
    END IF;
    RAISE NOTICE 'Guard OK. Database: %', current_database();
END
$guard$;

BEGIN;

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS stripe_customer_id     text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS stripe_subscription_id text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan                   text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS current_period_end     timestamptz;

-- Unique en stripe_customer_id (idempotente; permite múltiples NULL).
DO $uniq$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'tenants_stripe_customer_id_key'
          AND conrelid = 'tenants'::regclass
    ) THEN
        ALTER TABLE tenants ADD CONSTRAINT tenants_stripe_customer_id_key
            UNIQUE (stripe_customer_id);
        RAISE NOTICE 'unique tenants_stripe_customer_id_key creada';
    ELSE
        RAISE NOTICE 'unique ya existe (no-op)';
    END IF;
END
$uniq$;

DO $verify$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_name='tenants'
       AND column_name IN ('stripe_customer_id','stripe_subscription_id','plan','current_period_end');
    IF n <> 4 THEN RAISE EXCEPTION 'esperaba 4 columnas de billing, hay %', n; END IF;
    RAISE NOTICE 'OK: 4 columnas de billing presentes en tenants.';
END
$verify$;

COMMIT;
