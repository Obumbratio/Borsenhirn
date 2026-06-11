#!/usr/bin/env bash
# scripts/b1_block8_extras_apply.sh
#
# Wrapper de APLICACION A PRODUCCION de las EXTRAS de B1 Bloque 8
# (b1_block8_extras_prod_migration.sql): clerk_id + billing + audit_log + legal.
#
# TRIPLE GUARD (igual que el core):
#   1. Requiere B1_ALLOW_PROD=1.
#   2. Requiere DB_NAME=borsenhirn (y el SQL re-chequea current_database()).
#   3. Requiere tipear la frase de confirmacion exacta.
#
# ORDEN: correr DESPUES de apply.sh (core) + create_role.sh (rol) + verify.sh
# (GATE 3 core). El SQL aborta si el rol borsenhirn_app no existe.
#
# Uso:
#   B1_ALLOW_PROD=1 bash scripts/b1_block8_extras_apply.sh
#   (carga .env por default; override con ENV_FILE=/ruta/.env)

set -uo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env}"
SQL="scripts/b1_block8_extras_prod_migration.sql"

# ---------- Guard 1: opt-in explicito ----------
if [ "${B1_ALLOW_PROD:-}" != "1" ]; then
    echo "ABORT: este script toca PRODUCCION. Re-corre con: B1_ALLOW_PROD=1 bash $0" >&2
    exit 2
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE no encontrado (esperaba el .env de produccion)." >&2
    exit 2
fi
set -a; # shellcheck disable=SC1090
source "$ENV_FILE"; set +a

: "${DB_HOST:?DB_HOST no seteado en $ENV_FILE}"
: "${DB_PORT:=5432}"
: "${DB_NAME:?DB_NAME no seteado en $ENV_FILE}"
: "${DB_USER:?DB_USER no seteado en $ENV_FILE}"
: "${DB_PASS:?DB_PASS no seteado en $ENV_FILE}"

# ---------- Guard 2: debe ser produccion ----------
if [ "$DB_NAME" != "borsenhirn" ]; then
    echo "ABORT: este script es SOLO para produccion (DB_NAME=borsenhirn). Actual: $DB_NAME" >&2
    exit 2
fi

export PGPASSWORD="$DB_PASS"
PSQL=(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME")

echo "====================================================================="
echo "  B1 BLOQUE 8 EXTRAS -> APLICAR A PRODUCCION borsenhirn @ $DB_HOST"
echo "====================================================================="
if ! "${PSQL[@]}" -tAXc "SELECT 1" >/dev/null 2>&1; then
    echo "ERROR: no conecta a $DB_NAME como $DB_USER." >&2
    exit 2
fi

echo ""
echo "-- Pre-state --"
"${PSQL[@]}" -tAX -c "
  SELECT 'rol borsenhirn_app existe: ' || EXISTS(SELECT 1 FROM pg_roles WHERE rolname='borsenhirn_app');
  SELECT 'tenants.clerk_user_id existe: ' || EXISTS(SELECT 1 FROM information_schema.columns
     WHERE table_name='tenants' AND column_name='clerk_user_id');
  SELECT 'columnas billing en tenants: ' || count(*) FROM information_schema.columns
   WHERE table_name='tenants' AND column_name IN ('stripe_customer_id','stripe_subscription_id','plan','current_period_end');
  SELECT 'audit_log existe: ' || EXISTS(SELECT 1 FROM information_schema.tables
     WHERE table_schema='public' AND table_name='audit_log');
  SELECT 'legal_acceptance existe: ' || EXISTS(SELECT 1 FROM information_schema.tables
     WHERE table_schema='public' AND table_name='legal_acceptance');
"

echo ""
echo "ORDEN: esto va DESPUES de apply.sh (core) + create_role.sh + verify.sh (GATE 3)."
echo "Agrega: clerk_user_id + billing en tenants, y tablas audit_log + legal_acceptance"
echo "(RLS + append-only). Es atomico (rollback si algo falla). Aborta si falta el rol app."
echo ""
printf 'Escribi exactamente  APLICAR EXTRAS A PROD  para continuar: '
read -r CONFIRM
if [ "$CONFIRM" != "APLICAR EXTRAS A PROD" ]; then
    echo "Cancelado (no se escribio la frase exacta). Nada se aplico."
    exit 0
fi

echo ""
echo "-- Aplicando migracion EXTRAS --"
"${PSQL[@]}" -1 -v ON_ERROR_STOP=1 -f "$SQL"
RC=$?

echo ""
if [ $RC -eq 0 ]; then
    echo "-- Post-state --"
    "${PSQL[@]}" -tAX -c "
      SELECT 'tenants.clerk_user_id: ' || EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_name='tenants' AND column_name='clerk_user_id');
      SELECT 'columnas billing: ' || count(*) FROM information_schema.columns
       WHERE table_name='tenants' AND column_name IN ('stripe_customer_id','stripe_subscription_id','plan','current_period_end');
      SELECT 'audit_log RLS+FORCE: ' || coalesce((SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname='audit_log'), false);
      SELECT 'legal_acceptance RLS+FORCE: ' || coalesce((SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname='legal_acceptance'), false);
    "
    echo ""
    echo "OK. Extras aplicadas. Recorda: re-correr verify.sh ahora daria FORCE RLS=19"
    echo "(17 core + audit_log + legal_acceptance) — es lo esperado tras las extras."
else
    echo "FALLO (rc=$RC). La transaccion hizo rollback: prod quedo como estaba."
fi
exit $RC
