#!/usr/bin/env bash
# scripts/b1_block4_apply.sh
#
# Wrapper to safely apply scripts/b1_block4_migration.sql against
# borsenhirn_dev. Same safety pattern as Blocks 2 and 3.
#
# Usage (from repo root, in WSL bash):
#   bash scripts/b1_block4_apply.sh

set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env.dev"
SQL_FILE="scripts/b1_block4_migration.sql"
DEFAULT_TENANT_UUID="00000000-0000-0000-0000-000000000001"

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

if [ "$DB_NAME" = "borsenhirn" ]; then
    echo "ABORT: DB_NAME is 'borsenhirn' (production)."
    echo "       Block 4 migration only runs against borsenhirn_dev."
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

# Per-table RLS snapshot.
per_table_rls_snapshot () {
    "${PSQL_BASE[@]}" -v ON_ERROR_STOP=1 -c "
        SELECT
            c.relname                   AS table_name,
            c.relrowsecurity            AS rls_on,
            c.relforcerowsecurity       AS rls_force,
            (SELECT count(*) FROM pg_policy p
             WHERE p.polrelid = c.oid)  AS policies
        FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'public'
          AND c.relname IN (
            'bot_daily_state','bot_entry_context','bot_entry_prices',
            'bot_ml_metrics','bot_ml_training','bot_performance',
            'bot_regime_stats','bot_symbol_scores','bot_trade_outcomes',
            'assistant_history','assistant_suggestions','daily_reports',
            'signals','trades','alerts_log','killswitch_state',
            'user_credentials'
          )
        ORDER BY c.relname;
    "
}

# ---------- Pre-state ----------

echo ""
echo "============================================================"
echo "  Block 4 migration - PRE-STATE"
echo "============================================================"
echo "  DB:    $DB_NAME @ $DB_HOST:$DB_PORT"
echo "  SQL:   $SQL_FILE"
echo "  User:  $DB_USER"
echo ""

show_count "current_user has BYPASSRLS:" \
    "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user;"

show_count "tables with relrowsecurity=true (target 17):" \
    "SELECT count(*) FROM pg_class c
     JOIN pg_namespace n ON c.relnamespace = n.oid
     WHERE n.nspname='public'
       AND c.relname IN ('bot_daily_state','bot_entry_context','bot_entry_prices',
           'bot_ml_metrics','bot_ml_training','bot_performance','bot_regime_stats',
           'bot_symbol_scores','bot_trade_outcomes','assistant_history',
           'assistant_suggestions','daily_reports','signals','trades',
           'alerts_log','killswitch_state','user_credentials')
       AND c.relrowsecurity = true;"

show_count "tables with relforcerowsecurity=true (target 17):" \
    "SELECT count(*) FROM pg_class c
     JOIN pg_namespace n ON c.relnamespace = n.oid
     WHERE n.nspname='public'
       AND c.relname IN ('bot_daily_state','bot_entry_context','bot_entry_prices',
           'bot_ml_metrics','bot_ml_training','bot_performance','bot_regime_stats',
           'bot_symbol_scores','bot_trade_outcomes','assistant_history',
           'assistant_suggestions','daily_reports','signals','trades',
           'alerts_log','killswitch_state','user_credentials')
       AND c.relforcerowsecurity = true;"

show_count "policies on target tables (target 34: 2x17):" \
    "SELECT count(*) FROM pg_policy p
     JOIN pg_class c ON p.polrelid = c.oid
     JOIN pg_namespace n ON c.relnamespace = n.oid
     WHERE n.nspname='public'
       AND c.relname IN ('bot_daily_state','bot_entry_context','bot_entry_prices',
           'bot_ml_metrics','bot_ml_training','bot_performance','bot_regime_stats',
           'bot_symbol_scores','bot_trade_outcomes','assistant_history',
           'assistant_suggestions','daily_reports','signals','trades',
           'alerts_log','killswitch_state','user_credentials');"

echo ""
echo "  Per-table snapshot (pre-migration):"
per_table_rls_snapshot

echo ""
echo "Expected POST-state:"
echo "  tables with relrowsecurity=true:        17"
echo "  tables with relforcerowsecurity=true:   17"
echo "  policies on target tables:              17 to 34"
echo ""
echo "  (If user_credentials kept its Phase A policies, total may be"
echo "   16x2 + N_phaseA. The migration logs the exact decision.)"
echo ""

# ---------- Confirm ----------

echo "This migration will:"
echo "  - Detect user_credentials state. If it already has FORCE RLS"
echo "    + at least one policy from Phase A, SKIP it."
echo "  - On 16 (or 17) target tables: ENABLE + FORCE row-level security."
echo "  - DROP IF EXISTS + CREATE 2 PERMISSIVE policies per table:"
echo "      tenant_isolation  - rows visible only when"
echo "                          tenant_id = current_setting('app.current_tenant')"
echo "      admin_bypass      - all rows visible when"
echo "                          current_setting('app.bypass_rls') = 'on'"
echo "  - Run syntactic checks. Aborts the transaction if any are off."
echo "  - Run functional isolation tests if current_user does NOT have"
echo "    BYPASSRLS (otherwise notice + skip; see test_isolation.sh)."
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
    show_count "tables with relrowsecurity=true:" \
        "SELECT count(*) FROM pg_class c
         JOIN pg_namespace n ON c.relnamespace = n.oid
         WHERE n.nspname='public'
           AND c.relname IN ('bot_daily_state','bot_entry_context','bot_entry_prices',
               'bot_ml_metrics','bot_ml_training','bot_performance','bot_regime_stats',
               'bot_symbol_scores','bot_trade_outcomes','assistant_history',
               'assistant_suggestions','daily_reports','signals','trades',
               'alerts_log','killswitch_state','user_credentials')
           AND c.relrowsecurity = true;"

    show_count "tables with relforcerowsecurity=true:" \
        "SELECT count(*) FROM pg_class c
         JOIN pg_namespace n ON c.relnamespace = n.oid
         WHERE n.nspname='public'
           AND c.relname IN ('bot_daily_state','bot_entry_context','bot_entry_prices',
               'bot_ml_metrics','bot_ml_training','bot_performance','bot_regime_stats',
               'bot_symbol_scores','bot_trade_outcomes','assistant_history',
               'assistant_suggestions','daily_reports','signals','trades',
               'alerts_log','killswitch_state','user_credentials')
           AND c.relforcerowsecurity = true;"

    show_count "policies tenant_isolation (count):" \
        "SELECT count(*) FROM pg_policy p
         JOIN pg_class c ON p.polrelid = c.oid
         JOIN pg_namespace n ON c.relnamespace = n.oid
         WHERE n.nspname='public' AND p.polname='tenant_isolation';"

    show_count "policies admin_bypass (count):" \
        "SELECT count(*) FROM pg_policy p
         JOIN pg_class c ON p.polrelid = c.oid
         JOIN pg_namespace n ON c.relnamespace = n.oid
         WHERE n.nspname='public' AND p.polname='admin_bypass';"

    echo ""
    echo "  Per-table snapshot (post-migration):"
    per_table_rls_snapshot

    echo ""
    echo "Notes:"
    echo "  - If functional tests were skipped (BYPASSRLS), run:"
    echo "      bash scripts/b1_block4_test_isolation.sh"
    echo "    once you have a non-privileged role configured."
    echo "  - Next: Block 5 (app layer integration in tenancy/db.py)."
else
    echo "============================================================"
    echo "  Migration FAILED (exit $RC). Transaction rolled back."
    echo "============================================================"
    exit "$RC"
fi
