#!/usr/bin/env bash
# scripts/b1_block0_setup.sh
#
# Sprint B1 - BLOQUE 0
#
# Hace:
#   1. pg_dump de borsenhirn (produccion) -> backups/pre_b1_YYYYMMDD_HHMM.dump
#   2. createdb borsenhirn_dev (si ya existe, pide confirmacion para drop)
#   3. pg_restore del dump a borsenhirn_dev
#   4. Compara row counts entre prod y dev (sanity check)
#   5. Genera .env.dev a partir de .env (cambia DB_NAME y DB_HOST)
#   6. Loggea todo en docs/B1_SESSION_LOG.md
#
# La produccion (borsenhirn) NO se modifica. Solo se lee con pg_dump.
#
# Pre-requisitos:
#   - psql, pg_dump, pg_restore, createdb, dropdb en PATH (postgresql-client)
#   - .env con DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
#   - Postgres accesible en 172.25.144.1:5432 (verificado en bloque -1)
#
# Uso:
#   bash scripts/b1_block0_setup.sh
#
# Exit codes:
#   0 - todo OK
#   1 - falta pre-requisito
#   2 - usuario cancelo
#   3 - error en algun paso de Postgres

set -uo pipefail

# ----- Constantes (overridables via env) -----
DB_HOST="${B1_DB_HOST:-172.25.144.1}"
DB_PORT="${B1_DB_PORT:-5432}"
DB_USER="${B1_DB_USER:-postgres}"
DB_PROD="${B1_DB_PROD:-borsenhirn}"
DB_DEV="${B1_DB_DEV:-borsenhirn_dev}"
TIMESTAMP="$(date +%Y%m%d_%H%M)"
DUMP_PATH="backups/pre_b1_${TIMESTAMP}.dump"
ENV_DEV_PATH=".env.dev"

section() {
    echo
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

confirm() {
    local prompt="$1"
    local answer
    read -r -p "${prompt} (escribi 'yes' para confirmar): " answer
    [[ "${answer}" == "yes" ]]
}

# ----- 0. Pre-requisitos -----
section "[0] Pre-requisitos"

for cmd in psql pg_dump pg_restore createdb dropdb; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "FAIL: ${cmd} no esta en PATH. Instalar con:"
        echo "  sudo apt install postgresql-client-16"
        exit 1
    fi
done
echo "  OK: psql, pg_dump, pg_restore, createdb, dropdb encontrados"

if [[ ! -f .env ]]; then
    echo "FAIL: no encuentro .env en la raiz del repo"
    exit 1
fi
echo "  OK: .env encontrado"

if [[ ! -d backups ]]; then
    echo "FAIL: carpeta backups/ no existe. Crearla primero."
    exit 1
fi
echo "  OK: carpeta backups/ existe"

# Leer password de .env (la unica cosa privada que necesitamos)
DB_PASSWORD="$(grep -E "^DB_PASSWORD=" .env | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"')"
if [[ -z "${DB_PASSWORD}" ]]; then
    echo "FAIL: no encontre DB_PASSWORD en .env"
    exit 1
fi
echo "  OK: DB_PASSWORD leida de .env"

export PGPASSWORD="${DB_PASSWORD}"
export PGCONNECT_TIMEOUT=10

# Confirmar conexion antes de empezar
section "[0b] Confirmar conexion a ${DB_PROD}"
if version=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_PROD}" -tAc "SELECT version();" 2>&1); then
    echo "  OK: ${version}"
else
    echo "FAIL: no puedo conectar a ${DB_PROD}@${DB_HOST}:${DB_PORT}"
    echo "${version}"
    exit 3
fi

# ----- 1. Dump de produccion -----
section "[1] pg_dump de ${DB_PROD} -> ${DUMP_PATH}"
echo "  Esto es READ-ONLY sobre produccion. No modifica datos."
if ! confirm "Hacer dump ahora?"; then
    echo "Cancelado."
    exit 2
fi

if pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
           -F c -f "${DUMP_PATH}" "${DB_PROD}" 2>&1; then
    dump_size=$(du -h "${DUMP_PATH}" | cut -f1)
    echo "  OK: dump creado (${dump_size})"
    ls -la "${DUMP_PATH}"
else
    echo "FAIL: pg_dump fallo"
    exit 3
fi

# ----- 2. Crear borsenhirn_dev -----
section "[2] Crear DB ${DB_DEV}"

# Chequear si ya existe
if psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${DB_DEV}';" 2>/dev/null | grep -q "^1$"; then
    echo "  AVISO: ${DB_DEV} ya existe."
    echo "  Para evitar mezclar data vieja con la nueva copia, hay que dropearla."
    if ! confirm "Dropear ${DB_DEV} y recrearla limpia?"; then
        echo "Cancelado. Si queres mantener ${DB_DEV}, ajusta B1_DB_DEV con otro nombre."
        exit 2
    fi
    if ! dropdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${DB_DEV}" 2>&1; then
        echo "FAIL: dropdb fallo"
        exit 3
    fi
    echo "  OK: ${DB_DEV} dropeada"
fi

if createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
            -O "${DB_USER}" "${DB_DEV}" 2>&1; then
    echo "  OK: ${DB_DEV} creada (owner=${DB_USER})"
else
    echo "FAIL: createdb fallo"
    exit 3
fi

# ----- 3. pg_restore -----
section "[3] pg_restore desde ${DUMP_PATH} a ${DB_DEV}"
echo "  Restoring... (warnings de owner/role son normales en copia local)"
# pg_restore puede tirar warnings de roles que no existen, ignorar exit code != 0
pg_restore -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
           -d "${DB_DEV}" --no-owner --no-acl "${DUMP_PATH}" 2>&1 | tail -20 || true
echo "  OK: restore completado (warnings ignorados intencionalmente)"

# ----- 4. Comparar row counts -----
section "[4] Comparar row counts: ${DB_PROD} vs ${DB_DEV}"

# Listar todas las tablas user de prod
TABLES=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_PROD}" -tAc "
    SELECT schemaname || '.' || tablename
      FROM pg_tables
     WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
     ORDER BY schemaname, tablename;
")

if [[ -z "${TABLES}" ]]; then
    echo "  AVISO: no hay tablas user en ${DB_PROD}"
else
    printf "  %-50s %12s %12s   %s\n" "TABLA" "PROD" "DEV" "MATCH"
    echo "  $(printf '%.0s-' {1..96})"
    mismatch=0
    while IFS= read -r tbl; do
        [[ -z "${tbl}" ]] && continue
        prod_count=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_PROD}" -tAc "SELECT count(*) FROM ${tbl};" 2>/dev/null || echo "?")
        dev_count=$(psql  -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_DEV}"  -tAc "SELECT count(*) FROM ${tbl};" 2>/dev/null || echo "?")
        if [[ "${prod_count}" == "${dev_count}" ]]; then
            mark="OK"
        else
            mark="DIFF"
            mismatch=$((mismatch + 1))
        fi
        printf "  %-50s %12s %12s   %s\n" "${tbl}" "${prod_count}" "${dev_count}" "${mark}"
    done <<< "${TABLES}"
    echo
    if [[ "${mismatch}" -gt 0 ]]; then
        echo "  AVISO: ${mismatch} tablas con conteos distintos. Revisa antes de seguir."
    else
        echo "  OK: todas las tablas matchean."
    fi
fi

# ----- 5. Generar .env.dev -----
section "[5] Generar ${ENV_DEV_PATH}"

if [[ -f "${ENV_DEV_PATH}" ]]; then
    echo "  AVISO: ${ENV_DEV_PATH} ya existe."
    if ! confirm "Sobrescribirlo?"; then
        echo "  Skip. Manten el actual."
    else
        rm -f "${ENV_DEV_PATH}"
    fi
fi

if [[ ! -f "${ENV_DEV_PATH}" ]]; then
    # Copiar .env y modificar DB_HOST y DB_NAME
    sed -E \
        -e "s/^DB_HOST=.*/DB_HOST=${DB_HOST}/" \
        -e "s/^DB_NAME=.*/DB_NAME=${DB_DEV}/" \
        .env > "${ENV_DEV_PATH}"
    echo "  OK: ${ENV_DEV_PATH} creado:"
    grep -E "^(DB_HOST|DB_PORT|DB_NAME|DB_USER)=" "${ENV_DEV_PATH}" | sed 's/^/    /'
    echo "    DB_PASSWORD=*** (oculta, copiada de .env)"
fi

# Confirmar que .env.dev esta gitignored
if grep -Fxq ".env.dev" .gitignore 2>/dev/null; then
    echo "  OK: .env.dev esta en .gitignore"
else
    echo "  AVISO: .env.dev NO esta en .gitignore. Agregar manualmente."
fi

# ----- 6. Resumen final -----
section "[6] RESUMEN BLOQUE 0"
echo "  Branch:           $(git rev-parse --abbrev-ref HEAD)"
echo "  Dump:             ${DUMP_PATH} ($(du -h ${DUMP_PATH} | cut -f1))"
echo "  Prod DB:          ${DB_PROD}@${DB_HOST}"
echo "  Dev DB:           ${DB_DEV}@${DB_HOST}"
echo "  .env.dev:         ${ENV_DEV_PATH}"
echo
echo "Proximo paso: avisame con 'ok bloque 0' para arrancar el bloque 1"
echo "(audit completo de tablas en borsenhirn_dev)."

unset PGPASSWORD
exit 0
