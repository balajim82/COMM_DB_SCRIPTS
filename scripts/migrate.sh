#!/usr/bin/env bash
# migrate.sh — CommVerse multi-schema migration runner
#
# For each schema listed in scripts_path (databases.yml):
#   For each subfolder in subfolder_order (databases.yml):
#     Run flyway migrate/info against that subfolder.
#     History tracked per schema+subfolder in the central history_schema.
#
# Required env vars (set by run.sh or GitHub Actions):
#   DB_HOST  DB_PORT  DB_NAME  DB_USER  DB_PASSWORD
#
# Optional:
#   GIT_TOKEN       — personal access token for private script repos
#   FLYWAY_VERSION  — override Flyway CLI version (default: 10.20.1)
#   GITHUB_ACTOR    — recorded as execution user in the log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${CONFIG_FILE:-${ROOT_DIR}/config/databases.yml}"

# Resolve Python command — checks actual output to skip Windows Store alias stubs
if [[ -n "${PYTHON_CMD:-}" ]]; then
    : # already exported by run.sh
elif command -v python3 &>/dev/null && python3 --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="python3"
elif command -v py &>/dev/null && py --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="py"
elif command -v python &>/dev/null && python --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python 3 is required."; exit 1
fi

LOG_DIR="${ROOT_DIR}/logs"
FLYWAY_VERSION="${FLYWAY_VERSION:-10.20.1}"
FLYWAY_CACHE="${ROOT_DIR}/.flyway"
FLYWAY_CMD=""
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
EXEC_USER="${GITHUB_ACTOR:-${USER:-local}}"
TEMP_DIR=""
REPO_DIR=""

cleanup() { [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]] && rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

# Git Bash on Windows uses /d/... paths; native Windows tools (Flyway) need D:\...
to_native_path() {
    if command -v cygpath &>/dev/null; then
        cygpath -w "$1"
    else
        echo "$1"
    fi
}

# ── Arguments ─────────────────────────────────────────────────────────────────

ENVIRONMENT=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env|-e)  ENVIRONMENT="${2:?'--env requires a value'}"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help)
            echo "Usage: $(basename "$0") --env <dev|uat|prod> [--dry-run]"
            echo "  --env      Target environment: dev, uat, or prod  [required]"
            echo "  --dry-run  Show pending migrations without applying them"
            exit 0 ;;
        *) echo "Unknown option: $1  (use --help)"; exit 1 ;;
    esac
done

[[ -z "$ENVIRONMENT" ]] && { echo "ERROR: --env is required."; exit 1; }
[[ "$ENVIRONMENT" =~ ^(dev|uat|prod)$ ]] || { echo "ERROR: --env must be dev, uat, or prod"; exit 1; }

# ── Logging ───────────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/migration_${ENVIRONMENT}_${TIMESTAMP}.log"

log() {
    local level="$1"; shift
    printf '[%s] [%-5s] [user:%s] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$EXEC_USER" "$*" \
        | tee -a "$LOG_FILE"
}

log INFO "========================================================"
log INFO "CommVerse DB Migration"
log INFO "  Environment : $ENVIRONMENT"
log INFO "  Dry Run     : $DRY_RUN"
log INFO "  Exec User   : $EXEC_USER"
log INFO "  Log File    : $LOG_FILE"
log INFO "========================================================"

# ── Validate required env vars ────────────────────────────────────────────────

for var in DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD; do
    [[ -z "${!var:-}" ]] && { log ERROR "$var is not set"; exit 1; }
done

log INFO "Target DB: ${DB_HOST}:${DB_PORT}/${DB_NAME}"

# ── Flyway binary ─────────────────────────────────────────────────────────────

resolve_flyway() {
    if command -v flyway &>/dev/null; then
        FLYWAY_CMD="flyway"
        log INFO "Flyway: $(flyway -v 2>/dev/null | grep -i 'flyway' | tail -1 || echo 'found in PATH')"
        return
    fi
    FLYWAY_CMD="${FLYWAY_CACHE}/flyway"
    if [[ -x "$FLYWAY_CMD" ]]; then
        log INFO "Flyway: cached at ${FLYWAY_CACHE}"
        return
    fi
    log INFO "Downloading Flyway ${FLYWAY_VERSION}..."
    local url="https://download.red-gate.com/maven/release/com/redgate/flyway/flyway-commandline/${FLYWAY_VERSION}/flyway-commandline-${FLYWAY_VERSION}-linux-x64.tar.gz"
    mkdir -p "$FLYWAY_CACHE"
    curl -sSfL "$url" | tar -xz -C "$FLYWAY_CACHE" --strip-components=1
    chmod +x "$FLYWAY_CMD"
    log INFO "Flyway ${FLYWAY_VERSION} installed at ${FLYWAY_CACHE}"
}

# ── Clone scripts repo ────────────────────────────────────────────────────────

clone_repo() {
    local git_repo="$1"
    local git_branch="$2"

    local clone_url="$git_repo"
    if [[ -n "${GIT_TOKEN:-}" ]]; then
        clone_url="${git_repo/https:\/\//https://x-access-token:${GIT_TOKEN}@}"
    fi

    TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/commverse_migration_XXXXXX")

    log INFO "Cloning scripts repo: ${git_repo}  branch=${git_branch}"
    if ! git clone --depth=1 --branch "$git_branch" --quiet "$clone_url" "$TEMP_DIR" 2>&1 | tee -a "$LOG_FILE"; then
        log ERROR "Failed to clone: ${git_repo}"
        exit 1
    fi

    REPO_DIR="$TEMP_DIR"
    log INFO "Repo cloned to: ${REPO_DIR}"
}

# ── Run Flyway for one subfolder ──────────────────────────────────────────────

run_flyway() {
    local schema="$1"
    local subfolder="$2"
    local subfolder_dir="$3"
    local history_schema="$4"
    local flyway_action="$5"

    local count
    count=$(find "$subfolder_dir" -maxdepth 1 -name "V*.sql" | wc -l)
    log INFO "  [run ] ${schema}/${subfolder} — ${count} V*.sql script(s)"

    local history_table="${schema}__${subfolder}"

    # ── Root cause of all previous failures ─────────────────────────────────
    # Flyway OSS 12.x sets "SET search_path = {defaultSchema}" on the connection
    # during its own setup.  Every mechanism that tried to override this:
    #
    #   initSql              → runs BEFORE Flyway's doChangeCurrentSchemaOrSearchPathTo();
    #                          Flyway's setup call then overwrites it.
    #   SQL callbacks        → beforeMigrate.sql / beforeEachMigrate.sql are a
    #   (beforeMigrate etc.)   Teams/Enterprise feature in Flyway 10.x+.
    #                          Flyway OSS silently ignores these files.
    #   beforeMigrate__*.sql → double-underscore is the migration separator;
    #                          not recognised as a callback name, silently skipped.
    #
    # ── The only working approach in Flyway OSS ──────────────────────────────
    # Prepend "SET search_path TO {schema}, {history_schema};" as the FIRST SQL
    # statement of every migration file.  This is plain SQL that executes on the
    # already-established connection, after Flyway has done all its setup.
    # PostgreSQL session-level SET persists for every subsequent statement in the
    # same file, so all unqualified object names resolve to {schema}.
    #
    # Files are written to a temp dir inside TEMP_DIR so cleanup() removes them.
    # Checksums are stable: (same prefix) + (immutable versioned file) = same
    # checksum every run → flyway.validateOnMigrate=true never fails.
    local processed_dir="${TEMP_DIR}/processed_${schema}_${subfolder}"
    mkdir -p "$processed_dir"

    local has_files=false
    for sql_file in "$subfolder_dir"/V*.sql "$subfolder_dir"/R*.sql; do
        [[ -f "$sql_file" ]] || continue
        has_files=true
        local fname
        fname=$(basename "$sql_file")
        printf 'SET search_path TO "%s", "%s";\n' "$schema" "$history_schema" | \
            cat - "$sql_file" > "${processed_dir}/${fname}"
    done

    if [[ "$has_files" == "false" ]]; then
        log INFO "  [skip] ${schema}/${subfolder} — no SQL files found"
        return 0
    fi

    # defaultSchema = history_schema  →  Flyway stores the history table there.
    # FLYWAY_LOCATIONS points to processed_dir (search_path already injected).
    export FLYWAY_DEFAULT_SCHEMA="$history_schema"
    export FLYWAY_SCHEMAS="${history_schema},${schema}"
    export FLYWAY_TABLE="$history_table"
    export FLYWAY_LOCATIONS="filesystem:$(to_native_path "$processed_dir")"

    local exit_code=0
    "$FLYWAY_CMD" \
        -configFiles="$(to_native_path "${ROOT_DIR}/flyway/conf/flyway-base.conf"),$(to_native_path "${ROOT_DIR}/flyway/conf/flyway-${ENVIRONMENT}.conf")" \
        "$flyway_action" 2>&1 | tee -a "$LOG_FILE" || exit_code=$?

    unset FLYWAY_DEFAULT_SCHEMA FLYWAY_SCHEMAS FLYWAY_TABLE FLYWAY_LOCATIONS

    if [[ $exit_code -ne 0 ]]; then
        log ERROR "  FAILED: ${schema}/${subfolder} (exit code: ${exit_code})"
        return $exit_code
    fi

    log INFO "  [done] ${schema}/${subfolder}"
}

# ── Main ──────────────────────────────────────────────────────────────────────

resolve_flyway

# Read git config
git_repo=$($PYTHON_CMD    "${SCRIPT_DIR}/helpers.py" git-repo       "$CONFIG_FILE")
git_branch=$($PYTHON_CMD  "${SCRIPT_DIR}/helpers.py" git-branch     "$CONFIG_FILE")
history_schema=$($PYTHON_CMD "${SCRIPT_DIR}/helpers.py" history-schema "$CONFIG_FILE")
db_label=$($PYTHON_CMD    "${SCRIPT_DIR}/helpers.py" db-id          "$CONFIG_FILE")

# Read schema list and subfolder order into arrays
mapfile -t schema_list     < <($PYTHON_CMD "${SCRIPT_DIR}/helpers.py" scripts-list    "$CONFIG_FILE" | tr -d '\r')
mapfile -t subfolder_order < <($PYTHON_CMD "${SCRIPT_DIR}/helpers.py" subfolder-order "$CONFIG_FILE" | tr -d '\r')

log INFO "Schemas       : ${schema_list[*]}"
log INFO "Subfolder order: ${subfolder_order[*]}"

# Clone repo once — all schemas live inside it
clone_repo "$git_repo" "$git_branch"

# Check DB connectivity
log INFO "Checking database connectivity..."
db_state=$(bash "${SCRIPT_DIR}/detect-state.sh" \
    "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "$DB_PASSWORD" \
    "$history_schema" "schema_version")

if [[ "$db_state" == "unreachable" ]]; then
    log ERROR "Cannot connect to ${DB_NAME}@${DB_HOST}:${DB_PORT}"
    exit 1
fi
log INFO "Database reachable (state: ${db_state})"

# Common Flyway JDBC connection vars (credentials unset after all runs complete)
export FLYWAY_URL="jdbc:postgresql://${DB_HOST}:${DB_PORT}/${DB_NAME}?sslmode=${DB_SSL_MODE:-require}"
export FLYWAY_USER="$DB_USER"
export FLYWAY_PASSWORD="$DB_PASSWORD"

flyway_action="migrate"
[[ "$DRY_RUN" == "true" ]] && flyway_action="info"

log INFO "Running: flyway ${flyway_action}  db=${db_label}"
log INFO "========================================================"

overall_exit=0

for schema in "${schema_list[@]}"; do
    schema_dir="${REPO_DIR}/${schema}"

    if [[ ! -d "$schema_dir" ]]; then
        log WARN "Schema folder '${schema}' not found in repo — skipping"
        continue
    fi

    log INFO "-------- Schema: ${schema} --------"

    for subfolder in "${subfolder_order[@]}"; do
        subfolder_dir="${schema_dir}/${subfolder}"

        if [[ ! -d "$subfolder_dir" ]]; then
            log INFO "  [skip] ${schema}/${subfolder} — folder not found"
            continue
        fi

        if ! run_flyway "$schema" "$subfolder" "$subfolder_dir" \
                        "$history_schema" "$flyway_action"; then
            overall_exit=$?
            break 2   # stop all processing on first failure
        fi
    done
done

unset FLYWAY_URL FLYWAY_USER FLYWAY_PASSWORD

log INFO "========================================================"
if [[ $overall_exit -eq 0 ]]; then
    log INFO "All migrations ${flyway_action} completed SUCCESSFULLY"
else
    log ERROR "Migration ${flyway_action} FAILED (exit code: ${overall_exit})"
fi
log INFO "========================================================"

exit $overall_exit
