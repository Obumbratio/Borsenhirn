#!/usr/bin/env bash
# scripts/db_restore.sh
#
# Restore de un dump a una DB NUEVA (B9) — NUNCA in-place.
# Crea una DB destino nueva, restaura ahí, y valida. Vos decidís la promoción.
#
# Uso:  bash scripts/db_restore.sh <archivo.dump> [db_destino]
#   ENV_FILE=.env  (default .env.dev) para los params de conexión.

set -uo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env.dev}"
DUMP="${1:?uso: db_restore.sh <archivo.dump> [db_destino]}"
DEST="${2:-restore_$(date +%Y%m%d_%H%M%S)}"

[ -f "$DUMP" ] || { echo "ERROR: dump '$DUMP' no existe." >&2; exit 2; }
[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE no existe." >&2; exit 2; }
set -a; # shellcheck disable=SC1090
source "$ENV_FILE"; set +a
: "${DB_HOST:?}"; : "${DB_PORT:=5432}"; : "${DB_USER:?}"; : "${DB_PASS:?}"
export PGPASSWORD="$DB_PASS"

echo "Restore de '$DUMP'"
echo "  -> DB NUEVA '$DEST' @ $DB_HOST (NO toca ninguna DB existente)"
printf 'Confirmar (yes): '
read -r CONFIRM
[ "$CONFIRM" = "yes" ] || { echo "Cancelado."; exit 0; }

if ! createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DEST"; then
    echo "FAIL: createdb '$DEST' (¿ya existe? elegí otro nombre)." >&2
    exit 3
fi

if ! pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DEST" --no-owner "$DUMP"; then
    echo "WARN: pg_restore reportó errores (revisá arriba; algunos pueden ser benignos)." >&2
fi

NT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DEST" -tAXc \
     "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
echo "  '$DEST' tiene ${NT} tablas en public."
echo "OK. Validá '$DEST' y promové manualmente si corresponde (rename / repuntar la app)."
