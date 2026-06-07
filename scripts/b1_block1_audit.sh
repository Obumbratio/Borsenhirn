#!/usr/bin/env bash
# scripts/b1_block1_audit.sh
#
# Sprint B1 - BLOQUE 1: audit completo de tablas en borsenhirn_dev.
#
# Hace:
#   1. Conecta a borsenhirn_dev (NO a produccion) usando .env.dev.
#   2. Lista TODAS las tablas user (excluye pg_catalog, information_schema).
#   3. Para cada tabla recolecta: rowcount, has tenant_id, RLS habilitado,
#      RLS forzado, count de policies.
#   4. Categoriza cada tabla en A/B/C/D segun whitelists conocidas.
#   5. Genera docs/B1_TABLE_AUDIT.md con la clasificacion completa.
#   6. Imprime resumen por categoria a stdout.
#
# NO modifica ninguna tabla. Solo SELECTs.
#
# Uso (desde la raiz del repo, en WSL bash):
#   bash scripts/b1_block1_audit.sh
#
# Exit codes:
#   0 - OK, audit completo, B1_TABLE_AUDIT.md generado
#   1 - falta .env.dev o psql
#   2 - error de conexion a borsenhirn_dev
#   3 - hay tablas categoria D (caso especial) - revisar antes de bloque 2

set -uo pipefail

# ----- Configuracion ----------------------------------------
ENV_FILE=".env.dev"
OUT_FILE="docs/B1_TABLE_AUDIT.md"

# Whitelists (ajustar si descubrimos algo en el output)
# Categoria A: tablas legacy del bot que necesitan tenant_id + RLS.
TABLES_A=(
    "bot_daily_state"
    "bot_entry_context"
    "bot_entry_prices"
    "bot_ml_metrics"
    "bot_ml_training"
    "bot_performance"
    "bot_regime_stats"
    "bot_symbol_scores"
    "bot_trade_outcomes"
)

# Categoria B: tablas SHARED globales (sin tenant_id por diseno).
TABLES_B=(
    "tenants"          # tabla central de tenants, shared por definicion
)

# Categoria C: tablas de tenancy foundation que YA tienen tenant_id + RLS
# (creadas ya con multi-tenant en mente).
TABLES_C=(
    "killswitch_state"
    "alerts_log"
    "user_credentials"
)

# ----- Helpers ----------------------------------------------
section() {
    echo
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

contains() {
    # contains <element> <array...>
    local needle="$1"
    shift
    local item
    for item in "$@"; do
        [[ "${item}" == "${needle}" ]] && return 0
    done
    return 1
}

# ----- Pre-requisitos --------------------------------------
section "[0] Pre-requisitos"

if ! command -v psql >/dev/null 2>&1; then
    echo "FAIL: psql no esta en PATH"
    exit 1
fi
echo "  OK: psql encontrado"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "FAIL: no encontre ${ENV_FILE}. Corre primero scripts/b1_block0_setup.sh"
    exit 1
fi
echo "  OK: ${ENV_FILE} existe"

read_env() {
    local key="$1"
    local default="${2:-}"
    local val
    val="$(grep -E "^${key}=" "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"')"
    if [[ -z "${val}" ]]; then echo "${default}"; else echo "${val}"; fi
}

DB_HOST="$(read_env DB_HOST)"
DB_PORT="$(read_env DB_PORT 5432)"
DB_USER="$(read_env DB_USER postgres)"
DB_NAME="$(read_env DB_NAME)"
DB_PASSWORD="$(read_env DB_PASSWORD)"

if [[ -z "${DB_HOST}" || -z "${DB_NAME}" || -z "${DB_PASSWORD}" ]]; then
    echo "FAIL: ${ENV_FILE} no tiene DB_HOST / DB_NAME / DB_PASSWORD"
    exit 1
fi
echo "  OK: target = ${DB_NAME}@${DB_HOST}:${DB_PORT} (user=${DB_USER})"

# Salvaguarda: confirmar que NO estamos apuntando a produccion
if [[ "${DB_NAME}" == "borsenhirn" ]]; then
    echo "FAIL: ${ENV_FILE} apunta a 'borsenhirn' (produccion)."
    echo "  Este script SOLO debe correr contra borsenhirn_dev."
    echo "  Revisa scripts/b1_block0_setup.sh si la copia no se creo."
    exit 1
fi
echo "  OK: target NO es produccion"

export PGPASSWORD="${DB_PASSWORD}"
export PGCONNECT_TIMEOUT=10

# ----- Conexion --------------------------------------------
section "[1] Conexion a ${DB_NAME}"
if ! psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        -tAc "SELECT current_database(), current_user, version();" 2>/tmp/b1_conn_err; then
    echo "FAIL: no puedo conectar"
    cat /tmp/b1_conn_err
    rm -f /tmp/b1_conn_err
    exit 2
fi
rm -f /tmp/b1_conn_err
echo "  OK: conectado"

# ----- Inventario completo ---------------------------------
section "[2] Inventario de tablas"

# Una sola query SQL que devuelve todo lo que necesitamos por tabla.
# Salida (separada por '|'): schema|table|rowcount|has_tenant_id|rls_enabled|rls_forced|n_policies
SQL=$(cat <<'SQL'
WITH user_tables AS (
    SELECT n.nspname AS schemaname, c.relname AS tablename, c.oid
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind = 'r'
       AND n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND n.nspname NOT LIKE 'pg_toast%'
),
counts AS (
    SELECT schemaname, tablename,
           (xpath('/row/cnt/text()',
                  query_to_xml(format('SELECT count(*) AS cnt FROM %I.%I',
                                      schemaname, tablename),
                               true, false, '')))[1]::text::bigint AS rowcount
      FROM user_tables
),
columns_check AS (
    SELECT t.schemaname, t.tablename,
           EXISTS (
               SELECT 1 FROM pg_attribute a
                WHERE a.attrelid = t.oid
                  AND a.attname = 'tenant_id'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
           ) AS has_tenant_id
      FROM user_tables t
),
rls_info AS (
    SELECT t.schemaname, t.tablename,
           c.relrowsecurity AS rls_enabled,
           c.relforcerowsecurity AS rls_forced,
           (SELECT count(*) FROM pg_policies p
             WHERE p.tablename = t.tablename
               AND p.schemaname = t.schemaname) AS n_policies
      FROM user_tables t
      JOIN pg_class c ON c.oid = t.oid
)
SELECT  cnt.schemaname || '|' ||
        cnt.tablename || '|' ||
        COALESCE(cnt.rowcount::text, '?') || '|' ||
        cc.has_tenant_id::text || '|' ||
        rls.rls_enabled::text || '|' ||
        rls.rls_forced::text || '|' ||
        rls.n_policies::text
  FROM counts cnt
  JOIN columns_check cc USING (schemaname, tablename)
  JOIN rls_info rls USING (schemaname, tablename)
 ORDER BY cnt.schemaname, cnt.tablename;
SQL
)

INVENTORY="$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -tAc "${SQL}" 2>&1)"
if [[ $? -ne 0 ]]; then
    echo "FAIL: inventario SQL fallo"
    echo "${INVENTORY}"
    exit 2
fi

if [[ -z "${INVENTORY}" ]]; then
    echo "AVISO: no hay tablas user en ${DB_NAME}"
    exit 0
fi

# Imprimir tabla legible y categorizar
printf "  %-3s %-30s %-8s %-12s %-8s %-8s %-9s %s\n" \
    "CAT" "TABLA" "ROWS" "TENANT_ID" "RLS_EN" "RLS_FORCE" "POLICIES" "NOTAS"
echo "  $(printf '%.0s-' {1..120})"

declare -a CAT_A_OUT=()
declare -a CAT_B_OUT=()
declare -a CAT_C_OUT=()
declare -a CAT_D_OUT=()

while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    IFS='|' read -r schema tbl rows has_tid rls_en rls_force n_pol <<< "${line}"
    full_name="${tbl}"

    # Categorizar
    cat="?"
    note=""
    if contains "${tbl}" "${TABLES_A[@]}"; then
        cat="A"
        if [[ "${has_tid}" == "true" && "${rls_en}" == "true" ]]; then
            note="ya migrada"
        elif [[ "${has_tid}" == "true" ]]; then
            note="tiene tenant_id pero falta RLS"
        else
            note="necesita migracion"
        fi
    elif contains "${tbl}" "${TABLES_B[@]}"; then
        cat="B"
        note="shared (sin tenant_id por diseno)"
    elif contains "${tbl}" "${TABLES_C[@]}"; then
        cat="C"
        if [[ "${has_tid}" == "true" && "${rls_en}" == "true" ]]; then
            note="OK"
        else
            note="REVISAR: foundation pero falta tenant_id/RLS"
        fi
    else
        cat="D"
        note="DESCONOCIDA - decidir"
    fi

    printf "  [%s] %-30s %-8s %-12s %-8s %-8s %-9s %s\n" \
        "${cat}" "${full_name}" "${rows}" "${has_tid}" "${rls_en}" "${rls_force}" "${n_pol}" "${note}"

    line_out="${schema}.${tbl}|${rows}|${has_tid}|${rls_en}|${rls_force}|${n_pol}|${note}"
    case "${cat}" in
        A) CAT_A_OUT+=("${line_out}") ;;
        B) CAT_B_OUT+=("${line_out}") ;;
        C) CAT_C_OUT+=("${line_out}") ;;
        D) CAT_D_OUT+=("${line_out}") ;;
    esac
done <<< "${INVENTORY}"

# ----- Resumen por categoria -------------------------------
section "[3] Resumen por categoria"
echo "  A) Necesitan tenant_id + RLS (legacy bot): ${#CAT_A_OUT[@]} tablas"
echo "  B) Shared (sin tenant_id por diseno):      ${#CAT_B_OUT[@]} tablas"
echo "  C) Foundation (deberian tener RLS ya):     ${#CAT_C_OUT[@]} tablas"
echo "  D) DESCONOCIDAS (decidir):                 ${#CAT_D_OUT[@]} tablas"

# ----- Generar B1_TABLE_AUDIT.md ---------------------------
section "[4] Generar ${OUT_FILE}"

mkdir -p docs
{
    echo "# B1 Table Audit - $(date +%Y-%m-%d)"
    echo
    echo "**DB auditada:** \`${DB_NAME}\`@\`${DB_HOST}\`"
    echo "**Generado por:** \`scripts/b1_block1_audit.sh\`"
    echo
    echo "## Categorias"
    echo "- **A** = Tabla legacy del bot. Necesita \`tenant_id\` + RLS en bloque 2-4."
    echo "- **B** = Shared global. NO lleva \`tenant_id\` por diseno."
    echo "- **C** = Tenancy foundation. Ya deberia tener \`tenant_id\` + RLS."
    echo "- **D** = Desconocida. Decidir antes del bloque 2."
    echo
    echo "## Tabla resumen"
    echo
    echo "| CAT | Tabla | Rows | tenant_id | RLS_en | RLS_force | Policies | Notas |"
    echo "|-----|-------|------|-----------|--------|-----------|----------|-------|"
    for arr_name in CAT_A_OUT CAT_B_OUT CAT_C_OUT CAT_D_OUT; do
        cat_letter="${arr_name:4:1}"
        eval "arr=(\"\${${arr_name}[@]}\")"
        for entry in "${arr[@]}"; do
            IFS='|' read -r tbl rows has_tid rls_en rls_force n_pol note <<< "${entry}"
            echo "| ${cat_letter} | \`${tbl}\` | ${rows} | ${has_tid} | ${rls_en} | ${rls_force} | ${n_pol} | ${note} |"
        done
    done
    echo
    echo "## Categoria A - tablas a migrar en bloques 2-4"
    echo
    if [[ ${#CAT_A_OUT[@]} -eq 0 ]]; then
        echo "_Ninguna._"
    else
        for entry in "${CAT_A_OUT[@]}"; do
            IFS='|' read -r tbl rows _ _ _ _ _ <<< "${entry}"
            echo "- \`${tbl}\` (${rows} filas)"
        done
    fi
    echo
    echo "## Categoria D - DESCONOCIDAS (requieren decision)"
    echo
    if [[ ${#CAT_D_OUT[@]} -eq 0 ]]; then
        echo "_Ninguna. Pasar al bloque 2._"
    else
        echo "Las siguientes tablas no estan en ninguna whitelist conocida."
        echo "Hay que decidir caso por caso si:"
        echo "- Es legacy del bot -> agregar a TABLES_A en \`scripts/b1_block1_audit.sh\` y categoria A."
        echo "- Es shared -> agregar a TABLES_B y categoria B."
        echo "- Es foundation pero quedo afuera -> agregar a TABLES_C."
        echo "- Es basura -> dropear o ignorar."
        echo
        for entry in "${CAT_D_OUT[@]}"; do
            IFS='|' read -r tbl rows has_tid rls_en _ _ _ <<< "${entry}"
            echo "- \`${tbl}\` (${rows} filas, tenant_id=${has_tid}, RLS=${rls_en})"
        done
    fi
    echo
    echo "## Categoria C - foundation (verificacion)"
    echo
    if [[ ${#CAT_C_OUT[@]} -eq 0 ]]; then
        echo "_Ninguna tabla foundation encontrada en esta DB._"
        echo
        echo "**AVISO:** las tablas foundation (\`killswitch_state\`,"
        echo "\`alerts_log\`, \`user_credentials\`) deberian estar."
        echo "Si no estan, es porque \`borsenhirn/safety/migrations.sql\` y"
        echo "\`borsenhirn/security/migrations.sql\` aun no se aplicaron a"
        echo "esta DB. Aplicalas antes de seguir."
    else
        for entry in "${CAT_C_OUT[@]}"; do
            IFS='|' read -r tbl rows has_tid rls_en _ _ note <<< "${entry}"
            echo "- \`${tbl}\` -> ${note}"
        done
    fi
    echo
    echo "## Proximo paso"
    echo
    echo "Si Categoria D esta vacia y Categoria A es la lista esperada"
    echo "del bot, avisame con \"ok bloque 1\" y arranco bloque 2"
    echo "(generar scripts/migrations/b1_create_default_tenant.sql y"
    echo "b1_add_tenant_id.sql)."
} > "${OUT_FILE}"

echo "  OK: ${OUT_FILE} generado ($(wc -l < ${OUT_FILE}) lineas)"

# ----- Decision final --------------------------------------
section "[5] Decision"
if [[ ${#CAT_D_OUT[@]} -gt 0 ]]; then
    echo "  AVISO: hay ${#CAT_D_OUT[@]} tabla(s) en categoria D."
    echo "  Revisa ${OUT_FILE} y avisa a Claude que decision tomar."
    exit 3
else
    echo "  OK: cero tablas en categoria D. Listo para bloque 2."
fi

unset PGPASSWORD
exit 0
