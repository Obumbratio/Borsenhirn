#!/usr/bin/env bash
# scripts/b1_block8_backup.sh
#
# GATE 1 del plan de Bloque 8: backup completo de PRODUCCION (borsenhirn)
# ANTES de aplicar la migracion. Es READ-ONLY sobre prod (pg_dump solo lee).
#
# Formato custom (-F c) = el que necesita pg_restore (rollback caso 2c).
# Sale en backups/prod_pre_b8_YYYYMMDD_HHMM.dump (ya en .gitignore).
#
# Toma los params de conexion de ENV_FILE (default .env.dev: mismo cluster
# que prod, creds admin). Dumpea SIEMPRE la DB `borsenhirn` (override con
# DUMP_TARGET=... si hiciera falta).
#
# Uso (desde la raiz del repo):
#   bash scripts/b1_block8_backup.sh

set -uo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env.dev}"
DUMP_TARGET="${DUMP_TARGET:-borsenhirn}"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE no encontrado (params de conexion)." >&2
    exit 2
fi
set -a; # shellcheck disable=SC1090
source "$ENV_FILE"; set +a
: "${DB_HOST:?DB_HOST no seteado en $ENV_FILE}"
: "${DB_PORT:=5432}"
: "${DB_USER:?DB_USER no seteado en $ENV_FILE}"
: "${DB_PASS:?DB_PASS no seteado en $ENV_FILE}"

export PGPASSWORD="$DB_PASS"
PSQL=(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DUMP_TARGET" -tAXq)

mkdir -p backups
STAMP=$(date +%Y%m%d_%H%M)
OUT="backups/prod_pre_b8_${STAMP}.dump"

echo "====================================================================="
echo "  B1 Bloque 8 - GATE 1: backup de PRODUCCION"
echo "====================================================================="
echo "  Server : $DB_HOST:$DB_PORT  (user: $DB_USER)"
echo "  DB     : $DUMP_TARGET   <-- se va a dumpear ESTA base"
echo "  Salida : $OUT"
echo "  Modo   : READ-ONLY (pg_dump no modifica nada)"
echo ""

# Pre-flight: la DB existe y conecta (read-only).
if ! "${PSQL[@]}" -c "SELECT 1" >/dev/null 2>&1; then
    echo "ERROR: no conecta a '$DUMP_TARGET' en $DB_HOST:$DB_PORT como $DB_USER." >&2
    echo "       Si '$DUMP_TARGET' aun no existe en este server, revisa el target." >&2
    exit 2
fi
NTABLES=$("${PSQL[@]}" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
echo "  '$DUMP_TARGET' alcanzable: $NTABLES tablas en schema public."
echo ""

printf 'Hacer el backup de %s ahora? escribi yes: ' "$DUMP_TARGET"
read -r CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelado. Nada se dumpeo."
    exit 0
fi

echo ""
echo "-- pg_dump (-F c) --"
if ! pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -F c -f "$OUT" "$DUMP_TARGET"; then
    echo "FAIL: pg_dump fallo. Revisa el error de arriba." >&2
    [ -f "$OUT" ] && rm -f "$OUT"
    exit 3
fi

# -- Verificacion del backup (GATE 1) --
echo ""
echo "-- Verificacion --"
SIZE=$(du -h "$OUT" | cut -f1)
BYTES=$(stat -c%s "$OUT" 2>/dev/null || echo 0)
if [ "$BYTES" -lt 1000 ]; then
    echo "FAIL: el dump es sospechosamente chico (${BYTES} bytes)." >&2
    exit 3
fi
NTOC=$(pg_restore --list "$OUT" 2>/dev/null | grep -cvE '^;|^$' || true)
if [ "${NTOC:-0}" -lt 1 ]; then
    echo "FAIL: pg_restore no pudo leer el TOC del dump (corrupto?)." >&2
    exit 3
fi

echo "  OK: $OUT  ($SIZE, ${NTOC} objetos en el TOC, legible por pg_restore)."
echo ""
echo "GATE 1 SUPERADO. Siguiente:"
echo "  B1_ALLOW_PROD=1 bash scripts/b1_block8_apply.sh"
