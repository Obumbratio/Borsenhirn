#!/usr/bin/env bash
# scripts/b1_block4_test_isolation.sh
#
# B1 Bloque 5.6 — Verificacion end-to-end del aislamiento RLS desde shell,
# sin pytest. Conecta como el rol APP (borsenhirn_app, NOSUPERUSER +
# NOBYPASSRLS) y prueba la tabla de verdad sobre bot_trade_outcomes.
#
# Equivalente bash del test tests/test_b1_rls_integration.py.
#
# READ-ONLY: solo hace SELECTs. No escribe ninguna fila. Solo contra
# borsenhirn_dev (se niega a correr contra otra DB).
#
# Uso (desde la raiz del repo):
#   bash scripts/b1_block4_test_isolation.sh
#
# Exit codes:
#   0 = todos los checks PASS
#   1 = al menos un check FAIL
#   2 = error de pre-flight (env, conexion, rol, DB equivocada)

set -uo pipefail
cd "$(dirname "$0")/.."

G='\033[0;32m'; R='\033[0;31m'; Y='\033[0;33m'; N='\033[0m'
FAIL_COUNT=0

pass () { printf '  %bPASS%b  %-34s %s\n' "$G" "$N" "$1" "${2:-}"; }
fail () { printf '  %bFAIL%b  %-34s %s\n' "$R" "$N" "$1" "${2:-}"; FAIL_COUNT=$((FAIL_COUNT+1)); }

# ---------- Pre-flight ----------

if [ ! -f .env.dev ]; then
    echo "ERROR: .env.dev no encontrado en la raiz del repo." >&2
    exit 2
fi

set -a
# shellcheck disable=SC1091
source .env.dev
set +a

: "${DB_HOST:?DB_HOST no seteado en .env.dev}"
: "${DB_PORT:=5432}"
: "${DB_NAME:?DB_NAME no seteado en .env.dev}"
: "${APP_DB_USER:?APP_DB_USER no seteado en .env.dev}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD no seteado en .env.dev}"

# Defensa anti-produccion: SOLO borsenhirn_dev.
if [ "$DB_NAME" != "borsenhirn_dev" ]; then
    echo "ERROR: este script solo corre contra borsenhirn_dev (DB_NAME=$DB_NAME)." >&2
    exit 2
fi

DEFAULT_TENANT="00000000-0000-0000-0000-000000000001"
FOREIGN_TENANT="0000ffff-0000-0000-0000-0000000000ff"
TABLE="bot_trade_outcomes"

export PGPASSWORD="$APP_DB_PASSWORD"
PSQL=(psql -h "$DB_HOST" -p "$DB_PORT" -U "$APP_DB_USER" -d "$DB_NAME" -tAX -q)

# q "<sql>" -> imprime la salida sin espacios; aborta el script si psql falla.
q () {
    local out
    if ! out=$("${PSQL[@]}" -c "$1" 2>&1); then
        echo "ERROR psql: $out" >&2
        exit 2
    fi
    printf '%s' "$out" | tr -d '[:space:]'
}

echo "== B1 5.6 — RLS isolation (rol APP: $APP_DB_USER @ $DB_NAME) =="

# Check 0: la conexion funciona.
if ! q "SELECT 1" >/dev/null; then
    echo "ERROR: no conecta como $APP_DB_USER. Revisa APP_DB_PASSWORD en .env.dev." >&2
    exit 2
fi

# Check 1: el rol NO debe ser superuser ni bypassrls (sino RLS es ficcion).
ROLE_FLAGS=$(q "SELECT rolsuper::int::text || rolbypassrls::int::text FROM pg_roles WHERE rolname = current_user")
if [ "$ROLE_FLAGS" = "00" ]; then
    pass "rol no privilegiado" "rolsuper=0 rolbypassrls=0"
else
    fail "rol no privilegiado" "rolsuper||bypass=$ROLE_FLAGS — RLS NO se esta probando"
    echo "Abortando: con un rol privilegiado todos los checks darian 31." >&2
    exit 2
fi

# Verdad: cuantas filas hay realmente (via policy admin_bypass, sin superuser).
TRUTH=$(q "SET app.bypass_rls = 'on'; SELECT count(*) FROM $TABLE")

# ---------- Tabla de verdad ----------

# 1) Sin contexto -> 0
C_NONE=$(q "SELECT count(*) FROM $TABLE")
[ "$C_NONE" = "0" ] && pass "sin tenant context = 0" || fail "sin tenant context = 0" "vi $C_NONE"

# 2) Tenant default -> todas
C_DEF=$(q "SET app.current_tenant_id = '$DEFAULT_TENANT'; SELECT count(*) FROM $TABLE")
if [ "$C_DEF" = "$TRUTH" ] && [ "$C_DEF" != "0" ]; then
    pass "tenant default = todas" "$C_DEF filas"
else
    fail "tenant default = todas" "vi $C_DEF, esperaba $TRUTH"
fi
[ "$C_DEF" = "31" ] || printf '  %b(nota)%b esperado documentado: 31 filas; en dev hay %s\n' "$Y" "$N" "$C_DEF"

# 3) Tenant ajeno -> 0
C_FOR=$(q "SET app.current_tenant_id = '$FOREIGN_TENANT'; SELECT count(*) FROM $TABLE")
[ "$C_FOR" = "0" ] && pass "tenant ajeno = 0" || fail "tenant ajeno = 0" "vi $C_FOR"

# 4) bypass_rls -> todas
C_BYP=$(q "SET app.bypass_rls = 'on'; SELECT count(*) FROM $TABLE")
[ "$C_BYP" = "$TRUTH" ] && [ "$C_BYP" != "0" ] && pass "bypass_rls = todas" "$C_BYP filas" \
    || fail "bypass_rls = todas" "vi $C_BYP"

# ---------- Resumen ----------
echo
if [ "$FAIL_COUNT" -eq 0 ]; then
    printf '%bTODOS LOS CHECKS PASARON%b — RLS aisla correctamente con el rol app.\n' "$G" "$N"
    exit 0
else
    printf '%b%d CHECK(S) FALLARON%b\n' "$R" "$FAIL_COUNT" "$N"
    exit 1
fi
