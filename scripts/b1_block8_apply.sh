#!/usr/bin/env bash
# scripts/b1_block8_apply.sh
#
# Wrapper de APLICACION A PRODUCCION de la migracion consolidada B1
# (b1_block8_prod_migration.sql).
#
# TRIPLE GUARD:
#   1. Requiere B1_ALLOW_PROD=1 en el entorno.
#   2. Requiere DB_NAME=borsenhirn (y el SQL re-chequea current_database()).
#   3. Requiere que tipees la frase de confirmacion exacta.
#
# PRE-REQUISITO: backup verificado (GATE 1 del plan). Este script lo
# RECUERDA y exige confirmarlo, pero no puede probarlo por vos.
#
# Uso:
#   B1_ALLOW_PROD=1 bash scripts/b1_block8_apply.sh
#   (carga .env por default; override con ENV_FILE=/ruta/.env)

set -uo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env}"
SQL="scripts/b1_block8_prod_migration.sql"

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
echo "  B1 BLOQUE 8 -> APLICAR A PRODUCCION borsenhirn @ $DB_HOST"
echo "====================================================================="
# Pre-flight: conexion read-only.
if ! "${PSQL[@]}" -tAXc "SELECT 1" >/dev/null 2>&1; then
    echo "ERROR: no conecta a $DB_NAME como $DB_USER." >&2
    exit 2
fi

echo ""
echo "-- Pre-state --"
"${PSQL[@]}" -tAX -c "
  SELECT 'tablas A con tenant_id: ' || count(*) FROM information_schema.columns
   WHERE table_schema='public' AND column_name='tenant_id';
  SELECT 'tablas con RLS: ' || count(*) FROM pg_class WHERE relrowsecurity;
  SELECT 'legacy aun sin archivar: ' || count(*) FROM information_schema.tables
   WHERE table_schema='public' AND table_name IN ('bot_state','entry_context','regime_stats','symbol_memory');
  SELECT 'default tenant existe: ' || EXISTS(SELECT 1 FROM tenants WHERE tenant_id='00000000-0000-0000-0000-000000000001');
"

echo ""
echo "ANTES DE CONTINUAR confirma que YA hiciste el backup verificado (GATE 1):"
echo "  pg_dump de borsenhirn a backups/prod_pre_b8_*.dump y validado con pg_restore --list."
echo ""
echo "Esto va a: archivar 4 legacy (RENAME), agregar tenant_id+FK+index+RLS+DEFAULT"
echo "en 17 tablas, backfill al default tenant. Es atomico (rollback si algo falla)."
echo ""
printf 'Escribi exactamente  APLICAR A PROD  para continuar: '
read -r CONFIRM
if [ "$CONFIRM" != "APLICAR A PROD" ]; then
    echo "Cancelado (no se escribio la frase exacta). Nada se aplico."
    exit 0
fi

echo ""
echo "-- Aplicando migracion --"
"${PSQL[@]}" -1 -v ON_ERROR_STOP=1 -f "$SQL"
RC=$?

echo ""
if [ $RC -eq 0 ]; then
    echo "-- Post-state --"
    "${PSQL[@]}" -tAX -c "
      SELECT 'tablas A NOT NULL: ' || count(*) FROM information_schema.columns
       WHERE table_schema='public' AND column_name='tenant_id' AND is_nullable='NO';
      SELECT 'tablas con FORCE RLS: ' || count(*) FROM pg_class WHERE relforcerowsecurity;
      SELECT 'tablas _legacy_*: ' || count(*) FROM information_schema.tables
       WHERE table_schema='public' AND table_name LIKE '\_legacy\_%';
    "
    echo ""
    echo "OK. Siguiente: bash scripts/b1_block8_create_role.sh  y  bash scripts/b1_block8_verify.sh"
else
    echo "FALLO (rc=$RC). La transaccion hizo rollback: prod quedo como estaba."
fi
exit $RC
