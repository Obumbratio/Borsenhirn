#!/usr/bin/env bash
# scripts/b1_block8_verify.sh
#
# Verificacion post-migracion en PRODUCCION (GATE 3 del plan).
# - Read-only: cobertura RLS, legacy archivadas, default tenant, smoke como rol app.
# - Write-isolation con TENANT DE TEST temporal: todo dentro de BEGIN/ROLLBACK
#   (no persiste filas) + el tenant temporal se borra al final. El default NO se toca.
#
# Guards: B1_ALLOW_PROD=1 + DB_NAME=borsenhirn.
# Requiere en .env: DB_* (admin) y APP_DB_USER/APP_DB_PASSWORD (rol app, ya creado).
#
# Uso:  B1_ALLOW_PROD=1 bash scripts/b1_block8_verify.sh

set -uo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="${ENV_FILE:-.env}"
G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'
FAIL=0
pass(){ printf '  %bPASS%b %s\n' "$G" "$N" "$1"; }
fail(){ printf '  %bFAIL%b %s\n' "$R" "$N" "$1"; FAIL=$((FAIL+1)); }

[ "${B1_ALLOW_PROD:-}" = "1" ] || { echo "ABORT: B1_ALLOW_PROD=1 requerido." >&2; exit 2; }
[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE no existe." >&2; exit 2; }
set -a; source "$ENV_FILE"; set +a
: "${DB_HOST:?}"; : "${DB_PORT:=5432}"; : "${DB_NAME:?}"; : "${DB_USER:?}"; : "${DB_PASS:?}"
: "${APP_DB_USER:?APP_DB_USER no seteado (corre create_role primero)}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD no seteado}"
[ "$DB_NAME" = "borsenhirn" ] || { echo "ABORT: solo prod (DB_NAME=borsenhirn). Actual: $DB_NAME" >&2; exit 2; }

TEMP_TENANT="00000000-0000-0000-0000-0000000000aa"
qadmin(){ PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAXq -c "$1"; }
qapp(){ PGPASSWORD="$APP_DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$APP_DB_USER" -d "$DB_NAME" -tAXq -c "$1"; }

echo "== B1 Bloque 8 verify @ $DB_NAME =="

# ---------- A. Cobertura RLS (read-only) ----------
echo "-- A. check_rls_coverage --strict --"
if venv/bin/python scripts/check_rls_coverage.py --strict >/tmp/b8cov.txt 2>&1; then
    pass "17/17 tablas con RLS (0 sin RLS)"
else
    fail "check_rls_coverage --strict reporto tablas sin RLS (ver /tmp/b8cov.txt)"
fi

# ---------- B. Catalogo (read-only) ----------
echo "-- B. catalogo --"
N_FORCE=$(qadmin "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relforcerowsecurity AND EXISTS(SELECT 1 FROM information_schema.columns col WHERE col.table_name=c.relname AND col.column_name='tenant_id') AND c.relname<>'tenants'")
[ "$N_FORCE" = "17" ] && pass "FORCE RLS en 17 tablas" || fail "FORCE RLS en $N_FORCE (esperaba 17)"
N_LEG=$(qadmin "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE '\_legacy\_%'")
[ "$N_LEG" = "4" ] && pass "4 tablas _legacy_* archivadas" || fail "tablas _legacy_*: $N_LEG (esperaba 4)"
HAS_DEF=$(qadmin "SELECT EXISTS(SELECT 1 FROM tenants WHERE tenant_id='00000000-0000-0000-0000-000000000001')")
[ "$HAS_DEF" = "t" ] && pass "default tenant existe" || fail "falta el default tenant"

# ---------- C. Smoke como rol app (read-only) ----------
echo "-- C. smoke rol app (read-only) --"
ROLE_FLAGS=$(qadmin "SELECT rolsuper::int::text||rolbypassrls::int::text FROM pg_roles WHERE rolname='$APP_DB_USER'")
[ "$ROLE_FLAGS" = "00" ] && pass "rol app NOSUPERUSER+NOBYPASSRLS" || fail "rol app privilegiado ($ROLE_FLAGS)"
C_NONE=$(qapp "SELECT count(*) FROM bot_trade_outcomes")
[ "$C_NONE" = "0" ] && pass "sin contexto -> 0 filas" || fail "sin contexto vio $C_NONE (esperaba 0)"
C_DEF=$(qapp "SET app.current_tenant_id='00000000-0000-0000-0000-000000000001'; SELECT count(*) FROM bot_trade_outcomes")
C_BYP=$(qapp "SET app.bypass_rls='on'; SELECT count(*) FROM bot_trade_outcomes")
[ "$C_DEF" = "$C_BYP" ] && [ -n "$C_DEF" ] && pass "default ve todas sus filas ($C_DEF)" || fail "default=$C_DEF vs bypass=$C_BYP"

# ---------- D. Write-isolation con tenant de test (rollback, no persiste) ----------
echo "-- D. write-isolation con tenant temporal --"
qadmin "INSERT INTO tenants(tenant_id,slug,email,display_name) VALUES('$TEMP_TENANT','verify-b8','verify@test.local','Verify B8') ON CONFLICT (tenant_id) DO NOTHING" >/dev/null
# Bloque transaccional como rol app: inserta bajo el temp, valida aislamiento, rollback.
ISO_OUT=$(PGPASSWORD="$APP_DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$APP_DB_USER" -d "$DB_NAME" -tAXq -v ON_ERROR_STOP=1 <<SQL 2>&1
BEGIN;
SET LOCAL app.current_tenant_id='$TEMP_TENANT';
INSERT INTO bot_trade_outcomes(trade_date,symbol,buy_price,sell_price,qty,pnl,win)
  VALUES (CURRENT_DATE,'VERIFY',100,110,1,10,true);
DO \$\$ BEGIN
  IF (SELECT count(*) FROM bot_trade_outcomes) <> 1 THEN
     RAISE EXCEPTION 'temp tenant no ve su unica fila'; END IF;
END \$\$;
-- cross-tenant INSERT debe ser rechazado
DO \$\$ BEGIN
  BEGIN
    INSERT INTO bot_trade_outcomes(trade_date,symbol,buy_price,sell_price,qty,pnl,win,tenant_id)
      VALUES (CURRENT_DATE,'X',1,1,1,0,false,'00000000-0000-0000-0000-000000000001');
    RAISE EXCEPTION 'FALLO: insert cross-tenant NO fue rechazado';
  EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'ok cross-tenant rechazado';
  END;
END \$\$;
ROLLBACK;
SELECT 'ISO_OK';
SQL
)
if echo "$ISO_OUT" | grep -q "ISO_OK"; then
    pass "aislamiento de escritura OK (temp ve 1, cross-tenant rechazado, rollback)"
else
    fail "write-isolation fallo: $ISO_OUT"
fi
# limpieza del tenant temporal (las filas se fueron con el rollback)
qadmin "DELETE FROM tenants WHERE tenant_id='$TEMP_TENANT'" >/dev/null
RESID=$(qadmin "SELECT count(*) FROM tenants WHERE tenant_id='$TEMP_TENANT'")
[ "$RESID" = "0" ] && pass "tenant temporal borrado" || fail "tenant temporal residual ($RESID)"

echo ""
if [ "$FAIL" -eq 0 ]; then
    printf '%bGATE 3 OK%b — prod multi-tenant verificado. Podes re-arrancar el bot (--once primero).\n' "$G" "$N"
    exit 0
else
    printf '%b%d CHECK(S) FALLARON%b — NO re-arrancar el bot hasta resolver.\n' "$R" "$FAIL" "$N"
    exit 1
fi
