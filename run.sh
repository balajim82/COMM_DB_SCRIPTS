#!/usr/bin/env bash
# run.sh — Local runner for CommVerse DB Migration Framework
#
# ── QUICK MODE (no config file, everything on the command line) ───────────────
#
#   ./run.sh \
#     --db-host  localhost    \
#     --db-port  5432         \
#     --db-name  mydb         \
#     --db-user  admin        \
#     --db-password secret    \
#     --git-repo https://github.com/your-org/db-scripts.git \
#     [--scripts-path migrations]  [--git-branch main] \
#     [--git-token ghp_xxxx]       [--env dev]         [--dry-run]
#
# ── CONFIG MODE (reads .env + config/databases.yml) ───────────────────────────
#
#   ./run.sh --env dev [--dry-run]
#
#   .env must contain DEV_DB_HOST, DEV_DB_PORT, DEV_DB_NAME,
#   DEV_DB_USER, DEV_DB_PASSWORD  (prefix matches --env value)
#
# ── VALIDATE ONLY ─────────────────────────────────────────────────────────────
#
#   ./run.sh [--env dev] [same flags] --validate-only

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
ENVIRONMENT="dev"
DRY_RUN_ARG=""
VALIDATE_ONLY=false

# Quick-mode vars
Q_HOST="" Q_PORT="" Q_NAME="" Q_USER="" Q_PASS=""
Q_GIT_REPO="" Q_SCRIPTS_PATH="migrations" Q_GIT_BRANCH="main" Q_GIT_TOKEN=""

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env|-e)         ENVIRONMENT="${2:?}";        shift 2 ;;
        --dry-run)        DRY_RUN_ARG="--dry-run";     shift   ;;
        --validate-only)  VALIDATE_ONLY=true;          shift   ;;
        --db-host)        Q_HOST="${2:?}";             shift 2 ;;
        --db-port)        Q_PORT="${2:?}";             shift 2 ;;
        --db-name)        Q_NAME="${2:?}";             shift 2 ;;
        --db-user)        Q_USER="${2:?}";             shift 2 ;;
        --db-password)    Q_PASS="${2:?}";             shift 2 ;;
        --git-repo)       Q_GIT_REPO="${2:?}";         shift 2 ;;
        --scripts-path)   Q_SCRIPTS_PATH="${2:?}";     shift 2 ;;
        --git-branch)     Q_GIT_BRANCH="${2:?}";       shift 2 ;;
        --git-token)      Q_GIT_TOKEN="${2:?}";        shift 2 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \?//' | head -30
            exit 0 ;;
        *) echo "Unknown option: $1  (use --help)"; exit 1 ;;
    esac
done

echo "=============================================="
echo " CommVerse DB Migration — Local Runner"
echo " Environment : $ENVIRONMENT"
echo "=============================================="

# Resolve Python command — checks actual output to skip Windows Store alias stubs
if command -v python3 &>/dev/null && python3 --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="python3"
elif command -v py &>/dev/null && py --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="py"
elif command -v python &>/dev/null && python --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="python"
else
    echo "[error] Python 3 is required. Install from https://www.python.org/downloads/"; exit 1
fi

# Resolve pip command
if command -v pip3 &>/dev/null; then
    PIP_CMD="pip3"
elif command -v pip &>/dev/null; then
    PIP_CMD="pip"
else
    PIP_CMD="$PYTHON_CMD -m pip"
fi

export PYTHON_CMD PIP_CMD

# Install PyYAML if missing
$PYTHON_CMD -c "import yaml" &>/dev/null || { echo "[info] Installing dependencies..."; $PIP_CMD install -r "${ROOT_DIR}/requirements.txt" --quiet; }

chmod +x "${ROOT_DIR}/scripts/"*.sh

# ══════════════════════════════════════════════════════════════════════════════
# QUICK MODE — DB details and git repo passed as CLI flags
# ══════════════════════════════════════════════════════════════════════════════
if [[ -n "$Q_GIT_REPO" ]]; then
    missing=()
    [[ -z "$Q_HOST" ]] && missing+=("--db-host")
    [[ -z "$Q_PORT" ]] && missing+=("--db-port")
    [[ -z "$Q_NAME" ]] && missing+=("--db-name")
    [[ -z "$Q_USER" ]] && missing+=("--db-user")
    [[ -z "$Q_PASS" ]] && missing+=("--db-password")
    [[ ${#missing[@]} -gt 0 ]] && { echo "[error] Missing: ${missing[*]}"; exit 1; }

    echo "[info] Quick mode"
    echo "[info] Git repo : $Q_GIT_REPO  (branch: $Q_GIT_BRANCH, path: $Q_SCRIPTS_PATH)"
    echo "[info] Database : ${Q_HOST}:${Q_PORT}/${Q_NAME}"

    # Write a minimal temp config so migrate.sh / validate.sh can read git details
    TEMP_CONFIG=$(mktemp "${TMPDIR:-/tmp}/commverse_config_XXXXXX.yml")
    trap 'rm -f "$TEMP_CONFIG"' EXIT
    cat > "$TEMP_CONFIG" <<YAML
database:
  id: quick_run
  description: "CLI quick mode"
  git_repo: "${Q_GIT_REPO}"
  scripts_path: "${Q_SCRIPTS_PATH}"
  git_branch: "${Q_GIT_BRANCH}"
  history_schema: "flyway_history"
  history_table: "schema_version"
YAML

    export CONFIG_FILE="$TEMP_CONFIG"
    export DB_HOST="$Q_HOST"
    export DB_PORT="$Q_PORT"
    export DB_NAME="$Q_NAME"
    export DB_USER="$Q_USER"
    export DB_PASSWORD="$Q_PASS"
    [[ -n "$Q_GIT_TOKEN" ]] && export GIT_TOKEN="$Q_GIT_TOKEN"

    if [[ "$VALIDATE_ONLY" == "true" ]]; then
        exec "${ROOT_DIR}/scripts/validate.sh" --env "$ENVIRONMENT"
    fi
    exec "${ROOT_DIR}/scripts/migrate.sh" --env "$ENVIRONMENT" $DRY_RUN_ARG
fi

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG MODE — read credentials from .env, git config from databases.yml
# ══════════════════════════════════════════════════════════════════════════════
ENV_FILE="${ROOT_DIR}/.env"
if [[ -f "$ENV_FILE" ]]; then
    echo "[info] Loading credentials from .env"
    set -o allexport
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +o allexport
else
    echo "[warn] .env not found at ${ENV_FILE}"
    echo "       Fill in the placeholder values in .env before running config mode."
    echo "       Or use quick mode: ./run.sh --git-repo <url> --db-host <host> ..."
fi

# Map {ENV}_DB_HOST → DB_HOST so migrate.sh always reads the same var names
ENV_UPPER="${ENVIRONMENT^^}"
for field in HOST PORT NAME USER PASSWORD SSL_MODE; do
    src="${ENV_UPPER}_DB_${field}"
    [[ -n "${!src:-}" ]] && export "DB_${field}=${!src}"
done
[[ -n "${GIT_TOKEN:-}" ]] && export GIT_TOKEN

if [[ "$VALIDATE_ONLY" == "true" ]]; then
    exec "${ROOT_DIR}/scripts/validate.sh" --env "$ENVIRONMENT"
fi

exec "${ROOT_DIR}/scripts/migrate.sh" --env "$ENVIRONMENT" $DRY_RUN_ARG
