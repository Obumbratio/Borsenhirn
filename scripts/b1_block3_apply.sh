#!/usr/bin/env bash
# scripts/b1_block3_apply.sh
#
# Wrapper to safely apply scripts/b1_block3_migration.sql against
# borsenhirn_dev. Same safety pattern as Block 2:
#   - load .env.dev
#   - refuse if DB_NAME = borsenhirn (production)
#   - smoke test connection
#   - show pre-state with NULL counts per target table
#   - require explicit "yes"
#   - run psql -1 -v ON_ERROR_STOP=1 (atomic)
#   - show post-state
#
# Usage (from repo root, in WSL bash):
#   bash scripts/b1_block3_apply.sh

set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env.dev"
SQL_FILE="scripts/b1_block3_migration.sql"
DEFAULT_TENANT_UUID="00000000-0000-0000-0000-000000000001"

# Same 17 tables as the SQL migration. Defined here only for pre/post-state
# reporting (not for the actual migration logic).
TABLES_A=(
    "bot_daily_state" "bot_entry_context" "bot_entry_prices"
    "bot_ml_metrics" "bot_ml_training" "bot_performance"
    "bot_regime_stats" "bot_symbol_scores" "bot_trade_outcomes"
    "assistant_history" "assistant_suggestions" "daily_reports"
    "signals" "trades" "alerts_log" "killswitch_state"
    "user_credentials"
)

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

# DOUBLE GUARD: never run on production
if [ "$DB_NAME" = "borsenhirn" ]; then
    echo "ABORT: DB_NAME is 'borsenhirn' (production)."
    echo "       Block 3 migration only runs against borsenhirn_dev."
    exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql not found in PATH."
    exit 3
fi

export PGPASSWORD="$DB_PASS"

PSQL_BASE=(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -X --quiet)

if ! "${PSQL_BASE[@]}" -t -A -c "SELECT 1;" >/dev/null 2>&1; then
    echo "ERROR: cannot connect to $DB_NAME@$DB_HOST:$DB_PORT as $DB_USER."
    exit 4
fi

# ---------- Helpers ----------

# Visible-stderr count helper (lesson from Block 2: silent stderr hides bugs).
show_count () {
    local label="$1"
    local query="$2"
    local val
    if ! val=$("${PSQL_BASE[@]}" -v ON_ERROR_STOP=1 -t -A -c "$query" \
                | tr -d '[:space:]'); then
        printf '  %-45s ERROR (see stderr above)\n' "$label"
        return 1
    fi
    printf '  %-45s %s\n' "$label" "$val"
}

# Print a per-table NULL-count snapshot.
per_table_null_snapshot () {
    local tbl
    for tbl in "${TABLES_A[@]}"; do
        local n
        n=$("${PSQL_BASE[@]}" -v ON_ERROR_STOP=1 -t -A \
            -c "SELECT count(*) FROM \"$tbl\" WHERE tenant_id IS NULL;" \
            | tr -d '[:space:]')
        printf '    %-30s NULL: %s\n' "$tbl" "$n"
    done
}

# Print a per-table assigned-to-default count snapshot.
per_table_assigned_snapshot () {
    local tbl
    for tbl in "${TABLES_A[@]}"; do
        local n
        n=$("${PSQL_BASE[@]}" -v ON_ERROR_STOP=1 -t -A \
            -c "SELECT count(*) FROM \"$tbl\" WHERE tenant_id = '$DEFAULT_TENANT_UUID'::uuid;" \
            | tr -d '[:space:]')
        printf '    %-30s assigned: %s\n' "$tbl" "$n"
    done
}

# ---------- Pre-state ----------

echo ""
echo "============================================================"
echo "  Block 3 migration - PRE-STATE"
echo "============================================================"
echo "  DB:    $DB_NAME @ $DB_HOST:$DB_PORT"
echo "  SQL:   $SQL_FILE"
echo "  User:  $DB_USER"
echo ""

show_count "default tenant present (expect 1):" \
    "SELECT count(*) FROM tenants
     WHERE tenant_id='$DEFAULT_TENANT_UUID'::uuid;"

show_count "tables with tenant_id (expect 17):" \
    "SELECT count(*) FROM information_schema.columns
     WHERE table_schema='public' AND column_name='tenant_id'
       AND table_name<>'tenants';"

show_count "tables with tenant_id NOT NULL (expect 0 or low):" \
    "SELECT count(*) FROM information_schema.columns
     WHERE table_schema='public' AND column_name='tenant_id'
       AND is_nullable='NO'
       AND table_name<>'tenants';"

show_count "rows with NULL tenant_id (target 17 tables):" \
    "SELECT COALESCE(SUM(c),0) FROM (
         SELECT count(*) c FROM bot_daily_state    WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM bot_entry_context  WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM bot_entry_prices   WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM bot_ml_metrics     WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM bot_ml_training    WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM bot_performance    WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM bot_regime_stats   WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM bot_symbol_scores  WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM bot_trade_outcomes WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM assistant_history     WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM assistant_suggestions WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM daily_reports         WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM signals               WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM trades                WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM alerts_log            WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM killswitch_state      WHERE tenant_id IS NULL UNION ALL
         SELECT count(*) c FROM user_credentials      WHERE tenant_id IS NULL
     ) sub;"

echo ""
echo "  Per-table NULL snapshot (pre-migration):"
per_table_null_snapshot

echo ""
echo "Expected POST-state:"
echo "  default tenant present:                  1"
echo "  tables with tenant_id:                   17"
echo "  tables with tenant_id NOT NULL:          17"
echo "  rows with NULL tenant_id:                0"
echo ""

# ---------- Confirm ----------

echo "This migration will:"
echo "  - Sanity-check default tenant exists (else abort)."
echo "  - UPDATE 17 tables: SET tenant_id = default WHERE tenant_id IS NULL"
echo "  - Verify zero NULLs remain across the 17 tables."
echo "  - ALTER COLUMN tenant_id SET NOT NULL on all 17 tables."
echo "  - Inside ONE transaction. Failure = full rollback."
echo "  - Idempotent: re-runs are safe (UPDATE skips, NOT NULL is no-op)."
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
    show_count "default tenant present:" \
        "SELECT count(*) FROM tenants
         WHERE tenant_id='$DEFAULT_TENANT_UUID'::uuid;"
    show_count "tables with tenant_id:" \
        "SELECT count(*) FROM information_schema.columns
         WHERE table_schema='public' AND column_name='tenant_id'
           AND table_name<>'tenants';"
    show_count "tables with tenant_id NOT NULL:" \
        "SELECT count(*) FROM information_schema.columns
         WHERE table_schema='public' AND column_name='tenant_id'
           AND is_nullable='NO'
           AND table_name<>'tenants';"
    show_count "rows with NULL tenant_id (target 17):" \
        "SELECT COALESCE(SUM(c),0) FROM (
             SELECT count(*) c FROM bot_daily_state    WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM bot_entry_context  WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM bot_entry_prices   WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM bot_ml_metrics     WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM bot_ml_training    WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM bot_performance    WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM bot_regime_stats   WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM bot_symbol_scores  WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM bot_trade_outcomes WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM assistant_history     WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM assistant_suggestions WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM daily_reports         WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM signals               WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM trades                WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM alerts_log            WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM killswitch_state      WHERE tenant_id IS NULL UNION ALL
             SELECT count(*) c FROM user_credentials      WHERE tenant_id IS NULL
         ) sub;"

    echo ""
    echo "  Per-table assigned-to-default snapshot (post-migration):"
    per_table_assigned_snapshot

    echo ""
    echo "Next: paste this output back to Claude. Then Block 4 (RLS policies)."
else
    echo "============================================================"
    echo "  Migration FAILED (exit $RC). Transaction rolled back."
    echo "============================================================"
    exit "$RC"
fi
