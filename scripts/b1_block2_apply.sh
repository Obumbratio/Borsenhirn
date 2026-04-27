#!/usr/bin/env bash
# scripts/b1_block2_apply.sh
#
# Wrapper to safely apply scripts/b1_block2_migration.sql against
# borsenhirn_dev. Loads .env.dev, validates we are NOT pointing at
# production, shows pre-state, asks for explicit confirmation,
# then runs psql with -1 (single transaction) and ON_ERROR_STOP=1.
#
# Usage (from repo root, in WSL bash):
#   bash scripts/b1_block2_apply.sh

set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env.dev"
SQL_FILE="scripts/b1_block2_migration.sql"

# ---------- Pre-flight ----------

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found. Run from repo root."
    exit 1
fi
if [ ! -f "$SQL_FILE" ]; then
    echo "ERROR: $SQL_FILE not found."
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${DB_HOST:?DB_HOST not set in $ENV_FILE}"
: "${DB_PORT:=5432}"
: "${DB_USER:?DB_USER not set in $ENV_FILE}"
: "${DB_NAME:?DB_NAME not set in $ENV_FILE}"
: "${DB_PASS:?DB_PASS not set in $ENV_FILE}"

# DOUBLE GUARD: never run on production (also enforced inside the SQL).
if [ "$DB_NAME" = "borsenhirn" ]; then
    echo "ABORT: DB_NAME is 'borsenhirn' (production)."
    echo "       Block 2 migration only runs against borsenhirn_dev."
    exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql not found in PATH."
    exit 3
fi

export PGPASSWORD="$DB_PASS"

PSQL_BASE=(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -X --quiet)

# Smoke test
if ! "${PSQL_BASE[@]}" -t -A -c "SELECT 1;" >/dev/null 2>&1; then
    echo "ERROR: cannot connect to $DB_NAME@$DB_HOST:$DB_PORT as $DB_USER."
    exit 4
fi

# ---------- Pre-state ----------

echo ""
echo "============================================================"
echo "  Block 2 migration - PRE-STATE"
echo "============================================================"
echo "  DB:    $DB_NAME @ $DB_HOST:$DB_PORT"
echo "  SQL:   $SQL_FILE"
echo "  User:  $DB_USER"
echo ""

show_count () {
    local label="$1"
    local query="$2"
    local val
    # Do NOT redirect stderr. Previous run aborted silently because a
    # bad column reference returned a psql error to /dev/null and only
    # `set -e` saw the failure. Visible stderr makes future bugs obvious.
    if ! val=$("${PSQL_BASE[@]}" -v ON_ERROR_STOP=1 -t -A -c "$query" \
                | tr -d '[:space:]'); then
        printf '  %-40s ERROR (see stderr above)\n' "$label"
        return 1
    fi
    printf '  %-40s %s\n' "$label" "$val"
}

show_count "tables with tenant_id column:" \
    "SELECT count(*) FROM information_schema.columns
     WHERE table_schema='public' AND column_name='tenant_id'
       AND table_name<>'tenants';"

show_count "FKs to tenants(id):" \
    "SELECT count(*) FROM information_schema.table_constraints tc
     JOIN information_schema.constraint_column_usage ccu
       ON tc.constraint_name=ccu.constraint_name
     WHERE tc.constraint_type='FOREIGN KEY'
       AND ccu.table_name='tenants'
       AND tc.table_schema='public'
       AND tc.table_name<>'tenants';"

show_count "ix_*_tenant_id indexes:" \
    "SELECT count(*) FROM pg_indexes
     WHERE schemaname='public' AND indexname LIKE 'ix_%_tenant_id';"

show_count "legacy tables present (4 to drop):" \
    "SELECT count(*) FROM information_schema.tables
     WHERE table_schema='public'
       AND table_name IN ('bot_state','entry_context','regime_stats','symbol_memory');"

show_count "default tenant present:" \
    "SELECT count(*) FROM tenants
     WHERE tenant_id='00000000-0000-0000-0000-000000000001'::uuid;"

echo ""
echo "Expected POST-state:"
echo "  tables with tenant_id column:           17"
echo "  FKs to tenants(id):                     17"
echo "  ix_*_tenant_id indexes:                 17"
echo "  legacy tables present (4 to drop):       0"
echo "  default tenant present:                  1"
echo ""

# ---------- Confirm ----------

echo "This migration will:"
echo "  - INSERT default tenant (idempotent)"
echo "  - DROP TABLE bot_state, entry_context, regime_stats, symbol_memory"
echo "  - ALTER 17 tables: ADD COLUMN tenant_id uuid (nullable)"
echo "  - ADD 17 FKs to tenants(id) ON DELETE RESTRICT"
echo "  - CREATE 17 indexes on tenant_id"
echo "  - All inside ONE transaction. Failure = full rollback."
echo ""

read -r -p "Type 'yes' to apply: " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted by user."
    exit 0
fi

# ---------- Apply ----------

echo ""
echo "============================================================"
echo "  Applying migration..."
echo "============================================================"

"${PSQL_BASE[@]}" -v ON_ERROR_STOP=1 -1 -f "$SQL_FILE"
RC=$?

echo ""
if [ "$RC" -eq 0 ]; then
    echo "============================================================"
    echo "  Migration applied successfully (exit 0)."
    echo "============================================================"
    echo ""
    echo "POST-state:"
    show_count "tables with tenant_id column:" \
        "SELECT count(*) FROM information_schema.columns
         WHERE table_schema='public' AND column_name='tenant_id'
           AND table_name<>'tenants';"
    show_count "FKs to tenants(id):" \
        "SELECT count(*) FROM information_schema.table_constraints tc
         JOIN information_schema.constraint_column_usage ccu
           ON tc.constraint_name=ccu.constraint_name
         WHERE tc.constraint_type='FOREIGN KEY'
           AND ccu.table_name='tenants'
           AND tc.table_schema='public'
           AND tc.table_name<>'tenants';"
    show_count "ix_*_tenant_id indexes:" \
        "SELECT count(*) FROM pg_indexes
         WHERE schemaname='public' AND indexname LIKE 'ix_%_tenant_id';"
    show_count "legacy tables present:" \
        "SELECT count(*) FROM information_schema.tables
         WHERE table_schema='public'
           AND table_name IN ('bot_state','entry_context','regime_stats','symbol_memory');"
    show_count "default tenant present:" \
        "SELECT count(*) FROM tenants
         WHERE tenant_id='00000000-0000-0000-0000-000000000001'::uuid;"
    echo ""
    echo "Next: paste this output back to Claude. Then Block 3 (backfill)."
else
    echo "============================================================"
    echo "  Migration FAILED (exit $RC). Transaction rolled back."
    echo "============================================================"
    exit "$RC"
fi
