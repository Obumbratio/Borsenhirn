#!/usr/bin/env bash
# scripts/b1_block4_5_apply.sh
#
# Wrapper to safely apply scripts/b1_block4_5_rename_guc.sql against
# borsenhirn_dev. Same safety pattern as Block 4.
#
# Usage (from repo root, in WSL bash):
#   bash scripts/b1_block4_5_apply.sh

set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env.dev"
SQL_FILE="scripts/b1_block4_5_rename_guc.sql"

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

if [ "$DB_NAME" = "borsenhirn" ]; then
    echo "ABORT: DB_NAME is 'borsenhirn' (production)."
    echo "       Block 4.5 rename only runs against borsenhirn_dev."
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

show_count () {
    local label="$1"
    local query="$2"
    local val
    if ! val=$("${PSQL_BASE[@]}" -v ON_ERROR_STOP=1 -t -A -c "$query" \
                | tr -d '[:space:]'); then
        printf '  %-50s ERROR (see stderr above)\n' "$label"
        return 1
    fi
    printf '  %-50s %s\n' "$label" "$val"
}

# ---------- Pre-state ----------

echo ""
echo "============================================================"
echo "  Block 4.5 rename - PRE-STATE"
echo "============================================================"
echo "  DB:    $DB_NAME @ $DB_HOST:$DB_PORT"
echo "  SQL:   $SQL_FILE"
echo ""

show_count "policies on target 17 tables (target 34):" \
    "SELECT count(*) FROM pg_policy p
     JOIN pg_class c ON p.polrelid = c.oid
     JOIN pg_namespace n ON c.relnamespace = n.oid
     WHERE n.nspname='public'
       AND c.relname IN ('bot_daily_state','bot_entry_context','bot_entry_prices',
           'bot_ml_metrics','bot_ml_training','bot_performance','bot_regime_stats',
           'bot_symbol_scores','bot_trade_outcomes','assistant_history',
           'assistant_suggestions','daily_reports','signals','trades',
           'alerts_log','killswitch_state','user_credentials');"

show_count "tenant_isolation w/ OLD guc (current_tenant):" \
    "SELECT count(*) FROM pg_policy p
     JOIN pg_class c ON p.polrelid = c.oid
     JOIN pg_namespace n ON c.relnamespace = n.oid
     WHERE n.nspname='public'
       AND p.polname = 'tenant_isolation'
       AND pg_get_expr(p.polqual, p.polrelid) ~ 'app\.current_tenant(?!_id)';"

show_count "tenant_isolation w/ NEW guc (current_tenant_id):" \
    "SELECT count(*) FROM pg_policy p
     JOIN pg_class c ON p.polrelid = c.oid
     JOIN pg_namespace n ON c.relnamespace = n.oid
     WHERE n.nspname='public'
       AND p.polname = 'tenant_isolation'
       AND pg_get_expr(p.polqual, p.polrelid) LIKE '%app.current_tenant_id%';"

echo ""
echo "Expected POST-state:"
echo "  policies on target 17 tables:           34"
echo "  tenant_isolation w/ OLD guc:             0"
echo "  tenant_isolation w/ NEW guc:            17"
echo ""

# ---------- Confirm ----------

echo "This migration will:"
echo "  - DROP IF EXISTS + CREATE 2 policies on each of the 17 tables."
echo "  - tenant_isolation:  GUC renamed app.current_tenant -> app.current_tenant_id"
echo "  - admin_bypass:      unchanged content (recreated for atomic idempotency)"
echo "  - Inside ONE transaction. Failure = full rollback."
echo "  - Idempotent: re-runs are safe."
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
    show_count "policies on target 17 tables:" \
        "SELECT count(*) FROM pg_policy p
         JOIN pg_class c ON p.polrelid = c.oid
         JOIN pg_namespace n ON c.relnamespace = n.oid
         WHERE n.nspname='public'
           AND c.relname IN ('bot_daily_state','bot_entry_context','bot_entry_prices',
               'bot_ml_metrics','bot_ml_training','bot_performance','bot_regime_stats',
               'bot_symbol_scores','bot_trade_outcomes','assistant_history',
               'assistant_suggestions','daily_reports','signals','trades',
               'alerts_log','killswitch_state','user_credentials');"

    show_count "tenant_isolation w/ OLD guc:" \
        "SELECT count(*) FROM pg_policy p
         JOIN pg_class c ON p.polrelid = c.oid
         JOIN pg_namespace n ON c.relnamespace = n.oid
         WHERE n.nspname='public'
           AND p.polname = 'tenant_isolation'
           AND pg_get_expr(p.polqual, p.polrelid) ~ 'app\.current_tenant(?!_id)';"

    show_count "tenant_isolation w/ NEW guc:" \
        "SELECT count(*) FROM pg_policy p
         JOIN pg_class c ON p.polrelid = c.oid
         JOIN pg_namespace n ON c.relnamespace = n.oid
         WHERE n.nspname='public'
           AND p.polname = 'tenant_isolation'
           AND pg_get_expr(p.polqual, p.polrelid) LIKE '%app.current_tenant_id%';"

    echo ""
    echo "Next: run scripts/b1_block5_create_role.sh to provision borsenhirn_app."
else
    echo "============================================================"
    echo "  Migration FAILED (exit $RC). Transaction rolled back."
    echo "============================================================"
    exit "$RC"
fi
