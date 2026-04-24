#!/usr/bin/env bash
# detect-state.sh — Probe a PostgreSQL database and determine migration state.
#
# Usage:
#   detect-state.sh <host> <port> <dbname> <user> <password> [history_schema] [history_table]
#
# Outputs one of:
#   fresh       — database has no Flyway history (initial migration needed)
#   existing    — database has prior successful migrations
#   unreachable — cannot connect

set -euo pipefail

DB_HOST="${1:?DB_HOST is required}"
DB_PORT="${2:?DB_PORT is required}"
DB_NAME="${3:?DB_NAME is required}"
DB_USER="${4:?DB_USER is required}"
DB_PASSWORD="${5:?DB_PASSWORD is required}"
HISTORY_SCHEMA="${6:-flyway_history}"
HISTORY_TABLE="${7:-schema_version}"

export PGPASSWORD="$DB_PASSWORD"
export PGSSLMODE="${DB_SSL_MODE:-require}"

psql_query() {
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -tAc "$1" 2>/dev/null
}

# 1 — Check connectivity
if ! psql_query "SELECT 1" > /dev/null 2>&1; then
    echo "unreachable"
    exit 1
fi

# 2 — Check if Flyway history schema exists
schema_count=$(psql_query \
    "SELECT COUNT(*) FROM information_schema.schemata
     WHERE schema_name = '${HISTORY_SCHEMA}';" 2>/dev/null || echo "0")

if [[ "${schema_count:-0}" -eq 0 ]]; then
    echo "fresh"
    exit 0
fi

# 3 — Check if the schema_version table exists
table_count=$(psql_query \
    "SELECT COUNT(*) FROM information_schema.tables
     WHERE table_schema = '${HISTORY_SCHEMA}'
       AND table_name   = '${HISTORY_TABLE}';" 2>/dev/null || echo "0")

if [[ "${table_count:-0}" -eq 0 ]]; then
    echo "fresh"
    exit 0
fi

# 4 — Check for at least one successful migration record
migration_count=$(psql_query \
    "SELECT COUNT(*) FROM ${HISTORY_SCHEMA}.${HISTORY_TABLE}
     WHERE success = true;" 2>/dev/null || echo "0")

if [[ "${migration_count:-0}" -gt 0 ]]; then
    echo "existing"
else
    echo "fresh"
fi
