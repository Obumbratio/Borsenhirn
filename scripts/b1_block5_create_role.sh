#!/usr/bin/env bash
# scripts/b1_block5_create_role.sh
#
# Wrapper to provision the borsenhirn_app role on borsenhirn_dev.
#
# Steps:
#   1. Load .env.dev. Refuse if DB_NAME = borsenhirn (production guard).
#   2. Smoke-test connection as the admin DB_USER (postgres).
#   3. Show pre-state (does the role already exist?).
#   4. Prompt the operator for the role password (silent + confirmation).
#   5. Reject password if shorter than 16 chars.
#   6. Apply scripts/b1_block5_create_role.sql with -1 + ON_ERROR_STOP.
#   7. Smoke-test connection as borsenhirn_app to confirm credentials work.
#   8. Print the lines to add to .env.dev (DOES NOT modify .env.dev).
#
# Generate a strong password BEFORE running this script:
#   openssl rand -base64 32
#
# Usage (from repo root, in WSL bash):
#   bash scripts/b1_block5_create_role.sh

set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env.dev"
SQL_FILE="scripts/b1_block5_create_role.sql"
ROLE_NAME="borsenhirn_app"

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
    echo "       Block 5 role provisioning only runs against borsenhirn_dev."
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

# ---------- Pre-state ----------

show_count () {
    local label="$1"
    local query="$2"
    local val
    if ! val=$("${PSQL_BASE[@]}" -v ON_ERROR_STOP=1 -t -A -c "$query" \
                | tr -d '[:space:]'); then
        printf '  %-50s ERROR\n' "$label"
        return 1
    fi
    printf '  %-50s %s\n' "$label" "$val"
}

echo ""
echo "============================================================"
echo "  Block 5 role - PRE-STATE"
echo "============================================================"
echo "  DB:    $DB_NAME @ $DB_HOST:$DB_PORT"
echo "  Admin: $DB_USER"
echo ""

show_count "$ROLE_NAME role exists (1=yes 0=no):" \
    "SELECT count(*) FROM pg_roles WHERE rolname = '$ROLE_NAME';"

echo ""

# ---------- Password prompt ----------

echo "Generate a strong password BEFORE this prompt if you have not yet:"
echo "  openssl rand -base64 32"
echo ""
echo "(Input is hidden. The password is sent ONLY to psql via -v role_password,"
echo " which on a single-user WSL is acceptable. Do not run on multi-user systems.)"
echo ""

# Read password silently.
# shellcheck disable=SC2162
read -rs -p "Paste password for $ROLE_NAME: " ROLE_PASSWORD
echo
read -rs -p "Confirm password:                " ROLE_PASSWORD_CONFIRM
echo

if [ "$ROLE_PASSWORD" != "$ROLE_PASSWORD_CONFIRM" ]; then
    echo "ERROR: passwords do not match. Aborting."
    exit 5
fi

if [ "${#ROLE_PASSWORD}" -lt 16 ]; then
    echo "ERROR: password too short (${#ROLE_PASSWORD} chars). Use at least 16."
    echo "       Re-run after generating with: openssl rand -base64 32"
    exit 6
fi

unset ROLE_PASSWORD_CONFIRM

# ---------- Confirm ----------

echo ""
echo "About to apply: $SQL_FILE"
echo "  - CREATE or ALTER role $ROLE_NAME (NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, LOGIN)"
echo "  - GRANT CRUD on the 17 A tables"
echo "  - GRANT SELECT (read-only) on tenants"
echo "  - GRANT USAGE,SELECT on all sequences in schema public"
echo "  - All inside ONE transaction. Failure = full rollback."
echo ""

read -r -p "Type 'yes' to apply: " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted by user."
    unset ROLE_PASSWORD
    exit 0
fi

# ---------- Apply ----------

echo ""
echo "============================================================"
echo "  Applying role provisioning..."
echo "============================================================"

"${PSQL_BASE[@]}" -v ON_ERROR_STOP=1 -v role_password="$ROLE_PASSWORD" -1 -f "$SQL_FILE"
RC=$?

if [ "$RC" -ne 0 ]; then
    echo "============================================================"
    echo "  Provisioning FAILED (exit $RC). Transaction rolled back."
    echo "============================================================"
    unset ROLE_PASSWORD
    exit "$RC"
fi

# ---------- Smoke test as the new role ----------

echo ""
echo "============================================================"
echo "  Smoke test: connecting as $ROLE_NAME"
echo "============================================================"

if PGPASSWORD="$ROLE_PASSWORD" psql \
        -h "$DB_HOST" -p "$DB_PORT" \
        -U "$ROLE_NAME" -d "$DB_NAME" \
        -X --quiet -t -A \
        -v ON_ERROR_STOP=1 \
        -c "SELECT current_user || ' / ' || current_database();"; then
    echo "  Connection OK."
else
    echo ""
    echo "WARNING: connection as $ROLE_NAME failed."
    echo "Possible causes:"
    echo "  - pg_hba.conf does not authorize $ROLE_NAME from your subnet."
    echo "  - Password contains characters mishandled by PGPASSWORD."
    echo "  - Postgres listen_addresses excludes the WSL2 subnet."
    echo "Check pg_hba.conf in the Postgres data directory."
fi

# ---------- Cleanup + instructions ----------

unset ROLE_PASSWORD

echo ""
echo "============================================================"
echo "  Done."
echo "============================================================"
echo ""
echo "Add the following lines to $ENV_FILE (NEVER commit them):"
echo ""
echo "    APP_DB_USER=$ROLE_NAME"
echo "    APP_DB_PASSWORD=<the password you just entered>"
echo ""
echo "Block 5.3 (borsenhirn/db.py) will read these at runtime."
echo ""
