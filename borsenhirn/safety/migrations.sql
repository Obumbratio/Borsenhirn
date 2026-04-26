-- borsenhirn/safety/migrations.sql
-- Schema para kill switches persistentes y log de alertas.
-- Ejecutar una vez contra la DB principal del bot.

-- ────────────────────────────────────────────────────────
-- Estado de kill switches.
-- Una fila por tipo de kill (max_daily_loss, manual_halt, etc.).
-- triggered=true significa que el bot debe estar en HALT.
-- ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS killswitch_state (
    key            text         PRIMARY KEY,
    triggered      boolean      NOT NULL DEFAULT false,
    reason         text,
    data           jsonb        DEFAULT '{}'::jsonb,
    triggered_at   timestamptz,
    cleared_at     timestamptz,
    updated_at     timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_killswitch_triggered
    ON killswitch_state(triggered)
    WHERE triggered = true;


-- ────────────────────────────────────────────────────────
-- Log de alertas enviadas.
-- Lo usa DashboardChannel para que el dashboard muestre banner.
-- ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts_log (
    id             bigserial    PRIMARY KEY,
    created_at     timestamptz  NOT NULL DEFAULT now(),
    level          text         NOT NULL CHECK (level IN ('INFO','WARN','CRITICAL')),
    subject        text         NOT NULL,
    body           text,
    meta           jsonb        DEFAULT '{}'::jsonb,
    acknowledged   boolean      NOT NULL DEFAULT false,
    ack_at         timestamptz,
    ack_note       text
);

CREATE INDEX IF NOT EXISTS idx_alerts_unacked
    ON alerts_log(created_at DESC)
    WHERE acknowledged = false;

CREATE INDEX IF NOT EXISTS idx_alerts_level_time
    ON alerts_log(level, created_at DESC);


-- ────────────────────────────────────────────────────────
-- Helper: función para "acknowledge" alertas desde el dashboard.
-- ────────────────────────────────────────────────────────
-- (opcional; el dashboard puede hacer UPDATE directo)
-- CREATE OR REPLACE FUNCTION ack_alerts(ids bigint[], note text DEFAULT '')
-- RETURNS int AS $$
--     WITH upd AS (
--         UPDATE alerts_log
--            SET acknowledged = true, ack_at = now(), ack_note = $2
--          WHERE id = ANY($1) AND acknowledged = false
--      RETURNING id
--     )
--     SELECT count(*)::int FROM upd;
-- $$ LANGUAGE sql;
