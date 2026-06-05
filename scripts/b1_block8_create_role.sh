#!/usr/bin/env bash
# scripts/b1_block8_create_role.sh
#
# Wrapper PRODUCCION para crear/actualizar el rol borsenhirn_app.
# Pide el password en silencio, valida >=16 chars, corre el SQL como admin,
# y hace un smoke test conectando como el rol nuevo.
#
# Guards: B1_ALLOW_PROD=1 + DB_NAME=borsenhirn (+ el SQL re-chequea).
#
# Uso:
#   B1_ALLOW_PROD=1 bash scripts/b1_block8_create_role.sh
#   (genera un password sugerido con openssl si no tipeas uno)

set -uo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env}"
SQL="scripts/b1_block8_create_role.sql"

if [ "${B1_ALLOW_PROD:-}" != "1" ]; then
    echo "ABORT: toca PRODUCCION. Re-corre con: B1_ALLOW_PROD=1 bash $0" >&2
    exit 2
fi
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE no encontrado." >&2; exit 2
fi
set -a; # shellcheck disable=SC1090
source "$ENV_FILE"; set +a
: "${DB_HOST:?}"; : "${DB_PORT:=5432}"; : "${DB_NAME:?}"; : "${DB_USER:?}"; : "${DB_PASS:?}"
if [ "$DB_NAME" != "borsenhirn" ]; then
    echo "ABORT: solo produccion (DB_NAME=borsenhirn). Actual: $DB_NAME" >&2; exit 2
fi

# Sugerencia de password (openssl) si el usuario no tipea uno.
SUGGESTED="$(openssl rand -base64 24 2>/dev/null | tr -d '/+=' | cut -c1-24)"
echo "Password para borsenhirn_app (>=16 chars). Enter vacio = usar sugerido."
[ -n "$SUGGESTED" ] && echo "  sugerido (openssl): $SUGGESTED"
printf 'Password: '
read -rs ROLE_PW; echo
if [ -z "$ROLE_PW" ]; then ROLE_PW="$SUGGESTED"; fi
if [ "${#ROLE_PW}" -lt 16 ]; then
    echo "ERROR: password de ${#ROLE_PW} chars (<16). Abortando." >&2; exit 2
fi

export PGPASSWORD="$DB_PASS"
echo "-- Creando rol (como admin $DB_USER) --"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
     -1 -v ON_ERROR_STOP=1 -v role_password="$ROLE_PW" -f "$SQL"
RC=$?
[ $RC -ne 0 ] && { echo "FALLO creando el rol (rc=$RC)."; exit $RC; }

echo ""
echo "-- Smoke test: conectar como borsenhirn_app --"
if PGPASSWORD="$ROLE_PW" psql -h "$DB_HOST" -p "$DB_PORT" -U borsenhirn_app -d "$DB_NAME" \
       -tAXc "SELECT 'conecta OK como ' || current_user" 2>/dev/null; then
    echo ""
    echo "Rol listo. Agrega al .env de PRODUCCION (NO a git):"
    echo "  APP_DB_USER=borsenhirn_app"
    echo "  APP_DB_PASSWORD=$ROLE_PW"
else
    echo "WARN: el rol se creo pero el smoke test no conecto. Revisa pg_hba.conf para borsenhirn_app." >&2
fi
