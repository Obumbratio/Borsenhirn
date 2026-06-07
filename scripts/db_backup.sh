#!/usr/bin/env bash
# scripts/db_backup.sh
#
# Backup reusable de la DB (B9): pg_dump -F c con verificación + retención.
# Apto para cron. READ-ONLY sobre la DB.
#
# Env (de ENV_FILE, default .env.dev):
#   DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME
# Override:
#   ENV_FILE=.env          (prod)
#   BACKUP_TARGET=borsenhirn   (qué DB dumpear; default DB_NAME)
#   BACKUP_KEEP=14         (cuántos dumps recientes conservar)
#
# Uso:        bash scripts/db_backup.sh
# Cron diario: 0 3 * * *  cd /ruta/repo && ENV_FILE=.env bash scripts/db_backup.sh >> backups/backup.log 2>&1

set -uo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env.dev}"
KEEP="${BACKUP_KEEP:-14}"

[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE no existe." >&2; exit 2; }
set -a; # shellcheck disable=SC1090
source "$ENV_FILE"; set +a
: "${DB_HOST:?DB_HOST}"; : "${DB_PORT:=5432}"; : "${DB_USER:?DB_USER}"; : "${DB_PASS:?DB_PASS}"
TARGET="${BACKUP_TARGET:-${DB_NAME:?DB_NAME}}"

export PGPASSWORD="$DB_PASS"
mkdir -p backups
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="backups/${TARGET}_${STAMP}.dump"

echo "[$(date '+%F %T')] backup de ${TARGET} @ ${DB_HOST} -> ${OUT}"
if ! pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -F c -f "$OUT" "$TARGET"; then
    echo "FAIL: pg_dump falló." >&2
    [ -f "$OUT" ] && rm -f "$OUT"
    exit 3
fi

# Verificación.
BYTES=$(stat -c%s "$OUT" 2>/dev/null || echo 0)
NTOC=$(pg_restore --list "$OUT" 2>/dev/null | grep -cvE '^;|^$' || true)
if [ "$BYTES" -lt 1000 ] || [ "${NTOC:-0}" -lt 1 ]; then
    echo "FAIL: verificación (bytes=$BYTES toc=$NTOC) — dump sospechoso." >&2
    exit 3
fi
echo "  OK: $(du -h "$OUT" | cut -f1), ${NTOC} objetos en el TOC."

# Retención: conservar los KEEP más recientes de este TARGET.
mapfile -t OLD < <(ls -t backups/${TARGET}_*.dump 2>/dev/null | tail -n +$((KEEP + 1)))
if [ "${#OLD[@]}" -gt 0 ]; then
    echo "  retención: borrando ${#OLD[@]} dump(s) viejos (conservo $KEEP)."
    rm -f "${OLD[@]}"
fi
echo "  dumps de ${TARGET}: $(ls backups/${TARGET}_*.dump 2>/dev/null | wc -l)."
