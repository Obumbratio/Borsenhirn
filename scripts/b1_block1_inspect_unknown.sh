#!/usr/bin/env bash
# scripts/b1_block1_inspect_unknown.sh
#
# Read-only inspector for the 9 cat-D unknown tables of Sprint B1.
# Goal: produce real data so we can decide A / B / DROP per table
# without guessing by name.
#
# Hard guarantees:
#   - Only SELECT queries + grep over the local repo.
#   - NEVER touches production: aborts if .env.dev points to 'borsenhirn'.
#   - Does not write to any DB table; output goes to docs/B1_TABLE_INSPECT.md
#     and stdout only.
#
# Usage (from repo root, in WSL bash):
#   bash scripts/b1_block1_inspect_unknown.sh
#
# Then paste docs/B1_TABLE_INSPECT.md back to Claude (full file or relevant
# sections) to decide categorization.

set -euo pipefail

# Move to repo root (script lives in scripts/)
cd "$(dirname "$0")/.."

ENV_FILE=".env.dev"
OUT_FILE="docs/B1_TABLE_INSPECT.md"

# The 9 cat-D tables flagged by b1_block1_audit.sh
UNKNOWN_TABLES=(
    "assistant_history"
    "assistant_suggestions"
    "bot_state"
    "daily_reports"
    "entry_context"
    "regime_stats"
    "signals"
    "symbol_memory"
    "trades"
)

# ---------- Pre-flight ----------

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found. Run from repo root."
    exit 1
fi

# Load .env.dev safely
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${DB_HOST:?DB_HOST not set in $ENV_FILE}"
: "${DB_PORT:=5432}"
: "${DB_USER:?DB_USER not set in $ENV_FILE}"
: "${DB_NAME:?DB_NAME not set in $ENV_FILE}"
: "${DB_PASS:?DB_PASS not set in $ENV_FILE}"

# SAFETY: never run inspector against production
if [ "$DB_NAME" = "borsenhirn" ]; then
    echo "ABORT: DB_NAME is 'borsenhirn' (production)."
    echo "       Inspector only allowed against borsenhirn_dev."
    exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql not found in PATH."
    exit 3
fi

export PGPASSWORD="$DB_PASS"

# Smoke test the connection
if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -X --quiet -t -A -c "SELECT 1;" >/dev/null 2>&1; then
    echo "ERROR: cannot connect to $DB_NAME@$DB_HOST:$DB_PORT as $DB_USER."
    exit 4
fi

mkdir -p docs

# ---------- Helpers ----------

# Run psql in "raw value" mode (-t -A): tuples only, unaligned, no header.
psql_raw () {
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -X --quiet -t -A -c "$1"
}

# Run psql in pretty/aligned mode for human-readable blocks in the report.
psql_pretty () {
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -X --quiet -c "$1"
}

# ---------- Output header ----------

{
    echo "# B1 Sprint - Inspect cat-D Unknown Tables"
    echo ""
    echo "Generated: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
    echo "Database: \`$DB_NAME\` @ \`$DB_HOST:$DB_PORT\`"
    echo "Tables inspected: ${#UNKNOWN_TABLES[@]}"
    echo ""
    echo "Each section reports for one table:"
    echo "1. Exact row count (\`SELECT count(*)\`)"
    echo "2. Columns + types (information_schema)"
    echo "3. Timestamp/date range (if any timestamp-like column)"
    echo "4. Sample 2 rows (most recent first if a timestamp exists)"
    echo "5. Outgoing foreign keys"
    echo "6. Code usage (grep over main.py + bot_memory_pg.py + borsenhirn/ + scripts/ + tests/)"
    echo ""
    echo "**Recommendation** is left empty - Claude fills it after reviewing this report."
    echo ""
    echo "---"
    echo ""
} > "$OUT_FILE"

inspect_table () {
    local TBL="$1"

    echo ""
    echo "============================================================"
    echo "  Inspecting: $TBL"
    echo "============================================================"

    # Section header
    {
        echo "## \`$TBL\`"
        echo ""
    } >> "$OUT_FILE"

    # Existence check
    local EXISTS
    EXISTS=$(psql_raw "
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = '$TBL';
    " 2>/dev/null | tr -d '[:space:]')

    if [ "$EXISTS" != "1" ]; then
        {
            echo "_Table does not exist in \`$DB_NAME\`._"
            echo ""
            echo "### Recommendation"
            echo ""
            echo "_Pending - Claude will fill after reviewing this output._"
            echo ""
            echo "---"
            echo ""
        } >> "$OUT_FILE"
        echo "  (does not exist - skipped)"
        return
    fi

    # ---- (1) Exact row count ----
    local ROWCOUNT
    ROWCOUNT=$(psql_raw "SELECT count(*) FROM \"$TBL\";" 2>&1 \
        | tr -d '[:space:]' || echo "ERROR")

    {
        echo "### 1. Row count"
        echo ""
        echo '```'
        echo "$ROWCOUNT"
        echo '```'
        echo ""
    } >> "$OUT_FILE"

    echo "  rows: $ROWCOUNT"

    # ---- (2) Columns + types ----
    {
        echo "### 2. Columns"
        echo ""
        echo '```'
    } >> "$OUT_FILE"

    psql_pretty "
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = '$TBL'
        ORDER BY ordinal_position;
    " >> "$OUT_FILE" 2>&1 || echo "(error reading columns)" >> "$OUT_FILE"

    {
        echo '```'
        echo ""
    } >> "$OUT_FILE"

    # ---- (3) Timestamp range ----
    # Detect first column that is a timestamp/date, with mild preference
    # ordering for common audit-trail names.
    local TS_COL
    TS_COL=$(psql_raw "
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = '$TBL'
          AND data_type IN (
                'timestamp without time zone',
                'timestamp with time zone',
                'date'
              )
        ORDER BY
          CASE column_name
            WHEN 'created_at'   THEN 1
            WHEN 'updated_at'   THEN 2
            WHEN 'recorded_at'  THEN 3
            WHEN 'timestamp'    THEN 4
            WHEN 'ts'           THEN 5
            WHEN 'date'         THEN 6
            WHEN 'entry_time'   THEN 7
            WHEN 'exit_time'    THEN 8
            ELSE 99
          END,
          ordinal_position
        LIMIT 1;
    " 2>/dev/null | tr -d '[:space:]')

    if [ -n "$TS_COL" ]; then
        {
            echo "### 3. Timestamp range (column: \`$TS_COL\`)"
            echo ""
            echo '```'
        } >> "$OUT_FILE"

        psql_pretty "
            SELECT MIN(\"$TS_COL\") AS min_ts,
                   MAX(\"$TS_COL\") AS max_ts
            FROM \"$TBL\";
        " >> "$OUT_FILE" 2>&1 || echo "(error reading min/max)" >> "$OUT_FILE"

        {
            echo '```'
            echo ""
        } >> "$OUT_FILE"
    else
        {
            echo "### 3. Timestamp range"
            echo ""
            echo "_No timestamp/date column detected._"
            echo ""
        } >> "$OUT_FILE"
    fi

    # ---- (4) Sample 2 rows ----
    {
        echo "### 4. Sample (2 rows)"
        echo ""
        echo '```'
    } >> "$OUT_FILE"

    if [ "$ROWCOUNT" = "0" ]; then
        echo "(table is empty)" >> "$OUT_FILE"
    elif [ -n "$TS_COL" ]; then
        psql_pretty "
            SELECT *
            FROM \"$TBL\"
            ORDER BY \"$TS_COL\" DESC NULLS LAST
            LIMIT 2;
        " >> "$OUT_FILE" 2>&1 || echo "(error sampling rows)" >> "$OUT_FILE"
    else
        psql_pretty "SELECT * FROM \"$TBL\" LIMIT 2;" \
            >> "$OUT_FILE" 2>&1 || echo "(error sampling rows)" >> "$OUT_FILE"
    fi

    {
        echo '```'
        echo ""
    } >> "$OUT_FILE"

    # ---- (5) Outgoing foreign keys ----
    {
        echo "### 5. Outgoing foreign keys"
        echo ""
        echo '```'
    } >> "$OUT_FILE"

    psql_pretty "
        SELECT
            tc.constraint_name,
            kcu.column_name AS local_column,
            ccu.table_name  AS foreign_table,
            ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema    = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
           AND ccu.table_schema    = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema    = 'public'
          AND tc.table_name      = '$TBL'
        ORDER BY tc.constraint_name;
    " >> "$OUT_FILE" 2>&1 || echo "(error reading FKs)" >> "$OUT_FILE"

    {
        echo '```'
        echo ""
    } >> "$OUT_FILE"

    # ---- (6) Code usage ----
    {
        echo "### 6. Code usage (grep)"
        echo ""
        echo '```'
    } >> "$OUT_FILE"

    local SEARCH_PATHS=()
    for p in main.py bot_memory_pg.py borsenhirn scripts tests; do
        [ -e "$p" ] && SEARCH_PATHS+=("$p")
    done

    if [ ${#SEARCH_PATHS[@]} -gt 0 ]; then
        # Case-insensitive so we catch "FROM Trades" etc.
        if ! grep -rni -E \
                "FROM[[:space:]]+${TBL}|INTO[[:space:]]+${TBL}|UPDATE[[:space:]]+${TBL}|DELETE[[:space:]]+FROM[[:space:]]+${TBL}" \
                --include="*.py" "${SEARCH_PATHS[@]}" \
                >> "$OUT_FILE" 2>/dev/null; then
            echo "(no SQL references found)" >> "$OUT_FILE"
        fi
    else
        echo "(no Python search paths found)" >> "$OUT_FILE"
    fi

    {
        echo '```'
        echo ""
        echo "### 7. Recommendation"
        echo ""
        echo "_Pending - Claude will fill after reviewing this output._"
        echo ""
        echo "---"
        echo ""
    } >> "$OUT_FILE"
}

# ---------- Run ----------

echo "Inspector starting."
echo "  DB:     $DB_NAME @ $DB_HOST:$DB_PORT"
echo "  Output: $OUT_FILE"
echo "  Tables: ${#UNKNOWN_TABLES[@]}"

for tbl in "${UNKNOWN_TABLES[@]}"; do
    inspect_table "$tbl"
done

echo ""
echo "============================================================"
echo "DONE."
echo "  Report: $OUT_FILE"
echo "  Lines:  $(wc -l < "$OUT_FILE")"
echo ""
echo "Next step: paste $OUT_FILE back to Claude (full file or just the"
echo "relevant sections) to decide A / B / DROP categorization per table."
echo "============================================================"
