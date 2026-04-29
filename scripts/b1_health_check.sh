#!/usr/bin/env bash
# TODO: fix ANSI color rendering using $'\033[0;32m' or tput (cosmetic only)
# scripts/b1_health_check.sh
#
# Health check completo del Sprint B1 (multi-tenancy phase B).
# READ-ONLY sobre ambas DBs (borsenhirn y borsenhirn_dev).
# No modifica archivos del repo.
# No ejecuta el bot ni los scripts de migracion.
#
# Uso (desde la raiz del repo):
#   bash scripts/b1_health_check.sh
#
# Exit codes:
#   0 = todos los checks PASS
#   1 = al menos un check FAIL
#   2 = error de pre-flight (env, conexion, etc.)

# NOTA: NO usamos `set -e` porque queremos seguir aunque un check falle.
set -uo pipefail

cd "$(dirname "$0")/.."

# ANSI colors
G='\033[0;32m'   # green
R='\033[0;31m'   # red
Y='\033[0;33m'   # yellow
N='\033[0m'      # reset

declare -a RESULTS  # array de "label|status|details"
FAIL_COUNT=0

record_pass () {
    local label="$1"
    local details="${2:-}"
    RESULTS+=("${label}|PASS|${details}")
    if [ -n "$details" ]; then
        printf '  %bPASS%b  %-40s  %s\n' "$G" "$N" "$label" "$details"
    else
        printf '  %bPASS%b  %s\n' "$G" "$N" "$label"
    fi
}

record_fail () {
    local label="$1"
    local details="${2:-}"
    RESULTS+=("${label}|FAIL|${details}")
    FAIL_COUNT=$((FAIL_COUNT + 1))
    if [ -n "$details" ]; then
        printf '  %bFAIL%b  %-40s  %s\n' "$R" "$N" "$label" "$details"
    else
        printf '  %bFAIL%b  %s\n' "$R" "$N" "$label"
    fi
}

# ---------- Pre-flight ----------

if [ ! -f .env.dev ]; then
    echo "ERROR: .env.dev not found in repo root."
    exit 2
fi

set -a
# shellcheck disable=SC1091
source .env.dev
set +a

: "${DB_HOST:?DB_HOST not set in .env.dev}"
: "${DB_PORT:=5432}"
: "${DB_USER:?DB_USER not set in .env.dev}"
: "${DB_PASS:?DB_PASS not set in .env.dev}"

# DB_NAME en .env.dev apunta a borsenhirn_dev. Para prod usamos override.
DEV_DB="${DB_NAME:-borsenhirn_dev}"
PROD_DB="borsenhirn"
DEFAULT_TENANT_UUID="00000000-0000-0000-0000-000000000001"

if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql not found in PATH"
    exit 2
fi

export PGPASSWORD="$DB_PASS"

# Helper: query plana, devuelve string trimeado.
# Args: db_name, sql
psql_q () {
    local db="$1"
    local sql="$2"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$db" \
        -X --quiet -t -A -c "$sql" 2>/dev/null \
        | tr -d '[:space:]'
}

# Smoke test de conectividad a ambas DBs.
if ! psql_q "$DEV_DB" "SELECT 1;" >/dev/null 2>&1; then
    echo "ERROR: cannot connect to dev DB '$DEV_DB' as $DB_USER@$DB_HOST"
    exit 2
fi
if [ "$(psql_q "$DEV_DB" 'SELECT 1;')" != "1" ]; then
    echo "ERROR: dev DB connection probe failed"
    exit 2
fi
# Prod connection test - non-fatal: si no hay acceso, marcamos los
# checks 4a/4b como FAIL pero no abortamos.
PROD_REACHABLE=1
if [ "$(psql_q "$PROD_DB" 'SELECT 1;' 2>/dev/null)" != "1" ]; then
    PROD_REACHABLE=0
fi

echo ""
echo "================================================================"
echo "  Sprint B1 - Health Check"
echo "================================================================"
echo "  Repo:    $(pwd)"
echo "  DB host: $DB_HOST:$DB_PORT"
echo "  Dev DB:  $DEV_DB"
echo "  Prod DB: $PROD_DB$([ "$PROD_REACHABLE" -eq 0 ] && echo ' (UNREACHABLE - 4a/4b will fail)')"
echo "================================================================"
echo ""

# =====================================================================
# Check 1: Git state
# =====================================================================
echo "[1] Git state"

CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || echo '')"
if [ "$CURRENT_BRANCH" = "feature/multi-tenancy-phase-b" ]; then
    record_pass "1a. on feature branch" "$CURRENT_BRANCH"
else
    record_fail "1a. on feature branch" "got '$CURRENT_BRANCH', expected 'feature/multi-tenancy-phase-b'"
fi

UNCOMMITTED="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
if [ "$UNCOMMITTED" = "0" ]; then
    record_pass "1b. working tree clean" "0 uncommitted changes"
else
    # Mostramos los archivos modificados para context.
    DIRTY=$(git status --porcelain | head -10 | sed 's/^/    /')
    record_fail "1b. working tree clean" "$UNCOMMITTED uncommitted file(s)"
    echo -e "$DIRTY"
fi

echo ""
echo "  Last 10 commits:"
git log --oneline -10 2>/dev/null | sed 's/^/    /' || echo "    (git log failed)"
record_pass "1c. last 10 commits visible" ""
echo ""

# =====================================================================
# Check 2: pytest -q
# =====================================================================
echo "[2] pytest baseline"

if ! command -v pytest >/dev/null 2>&1; then
    record_fail "2. pytest baseline" "pytest not found in PATH"
else
    PYTEST_OUT="$(pytest -q --no-header 2>&1 | tail -3)"
    # Buscamos linea tipo "267 passed, 55 skipped in X.XXs"
    PASSED="$(echo "$PYTEST_OUT" | grep -oE '[0-9]+ passed' | head -1 | grep -oE '[0-9]+' || echo 0)"
    SKIPPED="$(echo "$PYTEST_OUT" | grep -oE '[0-9]+ skipped' | head -1 | grep -oE '[0-9]+' || echo 0)"
    FAILED="$(echo "$PYTEST_OUT" | grep -oE '[0-9]+ failed' | head -1 | grep -oE '[0-9]+' || echo 0)"
    ERRORS="$(echo "$PYTEST_OUT" | grep -oE '[0-9]+ error' | head -1 | grep -oE '[0-9]+' || echo 0)"

    if [ "$PASSED" = "267" ] && [ "$SKIPPED" = "55" ] && [ "$FAILED" = "0" ] && [ "$ERRORS" = "0" ]; then
        record_pass "2. pytest baseline" "$PASSED passed, $SKIPPED skipped"
    else
        record_fail "2. pytest baseline" \
            "got passed=$PASSED skipped=$SKIPPED failed=$FAILED errors=$ERRORS, expected 267/55/0/0"
    fi
fi
echo ""

# =====================================================================
# Check 3: borsenhirn_dev health
# =====================================================================
echo "[3] borsenhirn_dev health"

# Lista de las 17 tablas A para reuso.
TARGETS_SQL="('bot_daily_state','bot_entry_context','bot_entry_prices','bot_ml_metrics','bot_ml_training','bot_performance','bot_regime_stats','bot_symbol_scores','bot_trade_outcomes','assistant_history','assistant_suggestions','daily_reports','signals','trades','alerts_log','killswitch_state','user_credentials')"

# 3a: tenant_id NOT NULL en las 17
N="$(psql_q "$DEV_DB" "
SELECT count(*) FROM information_schema.columns
WHERE table_schema='public'
  AND column_name='tenant_id'
  AND is_nullable='NO'
  AND table_name IN $TARGETS_SQL;
")"
if [ "$N" = "17" ]; then
    record_pass "3a. tenant_id NOT NULL" "$N/17"
else
    record_fail "3a. tenant_id NOT NULL" "$N/17"
fi

# 3b: relrowsecurity = true
N="$(psql_q "$DEV_DB" "
SELECT count(*) FROM pg_class c
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname='public'
  AND c.relname IN $TARGETS_SQL
  AND c.relrowsecurity = true;
")"
if [ "$N" = "17" ]; then
    record_pass "3b. RLS enabled" "$N/17"
else
    record_fail "3b. RLS enabled" "$N/17"
fi

# 3c: relforcerowsecurity = true
N="$(psql_q "$DEV_DB" "
SELECT count(*) FROM pg_class c
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname='public'
  AND c.relname IN $TARGETS_SQL
  AND c.relforcerowsecurity = true;
")"
if [ "$N" = "17" ]; then
    record_pass "3c. RLS forced" "$N/17"
else
    record_fail "3c. RLS forced" "$N/17"
fi

# 3d: 34 policies totales (2 por tabla)
N="$(psql_q "$DEV_DB" "
SELECT count(*) FROM pg_policy p
JOIN pg_class c ON p.polrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname='public'
  AND c.relname IN $TARGETS_SQL;
")"
if [ "$N" = "34" ]; then
    record_pass "3d. total policies" "$N/34"
else
    record_fail "3d. total policies" "$N/34"
fi

# 3e: default tenant existe
N="$(psql_q "$DEV_DB" "
SELECT count(*) FROM tenants
WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid;
")"
if [ "$N" = "1" ]; then
    record_pass "3e. default tenant present" "$N/1"
else
    record_fail "3e. default tenant present" "$N/1"
fi

# 3f: total filas con default tenant across las 17 tablas (esperado 128)
N="$(psql_q "$DEV_DB" "
SELECT COALESCE(SUM(c), 0) FROM (
    SELECT count(*) c FROM bot_daily_state       WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM bot_entry_context     WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM bot_entry_prices      WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM bot_ml_metrics        WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM bot_ml_training       WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM bot_performance       WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM bot_regime_stats      WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM bot_symbol_scores     WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM bot_trade_outcomes    WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM assistant_history     WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM assistant_suggestions WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM daily_reports         WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM signals               WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM trades                WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM alerts_log            WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM killswitch_state      WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid UNION ALL
    SELECT count(*) c FROM user_credentials      WHERE tenant_id = '${DEFAULT_TENANT_UUID}'::uuid
) sub;
")"
if [ "$N" = "128" ]; then
    record_pass "3f. backfill rows" "$N/128"
else
    record_fail "3f. backfill rows" "$N/128"
fi
echo ""

# =====================================================================
# Check 4: borsenhirn (produccion - read-only)
# =====================================================================
echo "[4] borsenhirn (produccion - read-only)"

if [ "$PROD_REACHABLE" -eq 0 ]; then
    record_fail "4a. prod RLS untouched" "prod DB unreachable"
    record_fail "4b. prod legacy still present" "prod DB unreachable"
else
    # 4a: 0 tablas con RLS enabled (B1 NO se aplico a prod todavia)
    N="$(psql_q "$PROD_DB" "
    SELECT count(*) FROM pg_class c
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname='public'
      AND c.relrowsecurity = true;
    ")"
    if [ "$N" = "0" ]; then
        record_pass "4a. prod RLS untouched" "$N tables with RLS"
    else
        record_fail "4a. prod RLS untouched" "$N tables with RLS (expected 0)"
    fi

    # 4b: las 4 legacy aun presentes
    N="$(psql_q "$PROD_DB" "
    SELECT count(*) FROM information_schema.tables
    WHERE table_schema='public'
      AND table_name IN ('bot_state','entry_context','regime_stats','symbol_memory');
    ")"
    if [ "$N" = "4" ]; then
        record_pass "4b. prod legacy present" "$N/4"
    else
        record_fail "4b. prod legacy present" "$N/4"
    fi
fi
echo ""

# =====================================================================
# Check 5: Backup
# =====================================================================
echo "[5] Backup pre-sprint"

# 5a: backup branch existe
BACKUP_BRANCH="$(git branch --list 'backup-pre-b1-*' | head -1 | tr -d ' *')"
if [ -n "$BACKUP_BRANCH" ]; then
    BACKUP_SHA="$(git rev-parse --short "$BACKUP_BRANCH" 2>/dev/null || echo unknown)"
    record_pass "5a. backup branch exists" "$BACKUP_BRANCH @ $BACKUP_SHA"
else
    record_fail "5a. backup branch exists" "no branch matching 'backup-pre-b1-*'"
fi

# 5b: al menos 1 dump en backups/
DUMP_COUNT=0
if [ -d backups ]; then
    DUMP_COUNT="$(find backups -maxdepth 1 -type f \( -name '*.dump' -o -name '*.sql.gz' -o -name '*.sql' \) 2>/dev/null | wc -l | tr -d ' ')"
fi
if [ "$DUMP_COUNT" -ge 1 ]; then
    LATEST_DUMP="$(find backups -maxdepth 1 -type f \( -name '*.dump' -o -name '*.sql.gz' -o -name '*.sql' \) -printf '%f\n' 2>/dev/null | head -1)"
    record_pass "5b. backups/ has dump" "$DUMP_COUNT file(s), latest: $LATEST_DUMP"
else
    record_fail "5b. backups/ has dump" "0 files in backups/ (expected at least 1)"
fi
echo ""

# =====================================================================
# Check 6: Smoke test imports (no side effects)
# =====================================================================
echo "[6] Imports smoke test"

run_import () {
    local label="$1"
    local code="$2"
    if python -c "$code" 2>/dev/null; then
        record_pass "6. $label" ""
    else
        local err
        err="$(python -c "$code" 2>&1 | tail -1)"
        record_fail "6. $label" "$err"
    fi
}

run_import "tenancy.DEFAULT_TENANT_UUID"  "from borsenhirn.tenancy import DEFAULT_TENANT_UUID; assert DEFAULT_TENANT_UUID"
run_import "borsenhirn.db"                "from borsenhirn import db as bdb; assert hasattr(bdb,'get_conn')"
run_import "bot_memory_pg"                "import bot_memory_pg; assert hasattr(bot_memory_pg,'BotMemory')"
run_import "borsenhirn.safety.bootstrap"  "from borsenhirn.safety.bootstrap import SafetyStack; assert hasattr(SafetyStack,'init_from_config')"
echo ""

# =====================================================================
# Summary table
# =====================================================================
echo "================================================================"
echo "  SUMMARY"
echo "================================================================"
printf '  %-40s %s\n' "Check" "Status"
echo "  -------------------------------------------------------------"
for entry in "${RESULTS[@]}"; do
    label="$(echo "$entry" | cut -d'|' -f1)"
    status="$(echo "$entry" | cut -d'|' -f2)"
    details="$(echo "$entry" | cut -d'|' -f3-)"
    if [ "$status" = "PASS" ]; then
        printf '  %-40s %bPASS%b' "$label" "$G" "$N"
    else
        printf '  %-40s %bFAIL%b' "$label" "$R" "$N"
    fi
    if [ -n "$details" ]; then
        printf ' (%s)' "$details"
    fi
    echo
done
echo "  -------------------------------------------------------------"

TOTAL="${#RESULTS[@]}"
PASS_COUNT=$((TOTAL - FAIL_COUNT))

if [ "$FAIL_COUNT" -eq 0 ]; then
    printf '  %bAll %d/%d checks PASS. Sprint B1 healthy.%b\n' "$G" "$PASS_COUNT" "$TOTAL" "$N"
    echo "================================================================"
    exit 0
else
    printf '  %b%d/%d checks FAIL. Diagnose before continuing.%b\n' "$R" "$FAIL_COUNT" "$TOTAL" "$N"
    echo "================================================================"
    exit 1
fi
