#!/usr/bin/env bash
# validate.sh — Pre-flight checks before running a migration.
#
# Verifies:
#   1. Required tools are available (psql, python3, git, curl)
#   2. Required env vars are set (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
#   3. The configured Git scripts repo is reachable and scripts_path exists
#
# Usage:
#   validate.sh --env <dev|uat|prod>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${CONFIG_FILE:-${ROOT_DIR}/config/databases.yml}"
ERRORS=0
TEMP_DIR=""

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

cleanup() { [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]] && rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

ENVIRONMENT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env|-e)  ENVIRONMENT="${2:?}"; shift 2 ;;
        -h|--help) echo "Usage: $0 --env <dev|uat|prod>"; exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

[[ -z "$ENVIRONMENT" ]] && { echo "ERROR: --env is required"; exit 1; }
[[ "$ENVIRONMENT" =~ ^(dev|uat|prod)$ ]] || { echo "ERROR: env must be dev, uat, or prod"; exit 1; }

fail()    { echo "  [FAIL] $*"; (( ERRORS++ )) || true; }
pass()    { echo "  [PASS] $*"; }
section() { echo; echo "=== $* ==="; }

# ── 1. Tools ──────────────────────────────────────────────────────────────────
section "Tool availability"
for tool in psql git curl; do
    command -v "$tool" &>/dev/null \
        && pass "$tool  →  $(command -v "$tool")" \
        || fail "$tool not found"
done
pass "python  →  $(command -v "$PYTHON_CMD")  ($($PYTHON_CMD --version 2>&1))"
if command -v flyway &>/dev/null; then
    pass "flyway  →  $(command -v flyway)"
elif [[ -x "${ROOT_DIR}/.flyway/flyway" ]]; then
    pass "flyway  →  ${ROOT_DIR}/.flyway/flyway (cached)"
else
    echo "  [WARN] flyway not in PATH — migrate.sh will download it automatically"
fi

# ── 2. Config + PyYAML ────────────────────────────────────────────────────────
section "Configuration"
[[ -f "$CONFIG_FILE" ]] \
    && pass "config/databases.yml found" \
    || { fail "config/databases.yml not found"; exit 1; }

$PYTHON_CMD -c "import yaml" &>/dev/null \
    && pass "PyYAML available" \
    || fail "PyYAML missing — run: pip install -r requirements.txt"

# ── 3. DB connection env vars ─────────────────────────────────────────────────
section "Database connection env vars"
echo "  (Expected: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)"
for var in DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD; do
    [[ -n "${!var:-}" ]] \
        && pass "${var} is set" \
        || fail "${var} is NOT set"
done

# ── 4. Git repo reachability ──────────────────────────────────────────────────
section "Git scripts repo"
git_repo=$($PYTHON_CMD   "${SCRIPT_DIR}/helpers.py" git-repo    "$CONFIG_FILE")
git_branch=$($PYTHON_CMD "${SCRIPT_DIR}/helpers.py" git-branch  "$CONFIG_FILE")
mapfile -t schema_list < <($PYTHON_CMD "${SCRIPT_DIR}/helpers.py" scripts-list "$CONFIG_FILE" | tr -d '\r')

if [[ -z "$git_repo" ]]; then
    fail "git_repo is not configured in databases.yml"
else
    echo "  repo    : $git_repo"
    echo "  branch  : $git_branch"
    echo "  schemas : ${schema_list[*]}"

    clone_url="$git_repo"
    [[ -n "${GIT_TOKEN:-}" ]] && clone_url="${git_repo/https:\/\//https://x-access-token:${GIT_TOKEN}@}"

    TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/commverse_validate_XXXXXX")

    if git clone --depth=1 --branch "$git_branch" --quiet "$clone_url" "$TEMP_DIR" 2>/dev/null; then
        pass "Repo cloned successfully"
        for schema in "${schema_list[@]}"; do
            schema_dir="${TEMP_DIR}/${schema}"
            if [[ -d "$schema_dir" ]]; then
                count=$(find "$schema_dir" -name "V*.sql" | wc -l)
                pass "schema folder '${schema}' found — ${count} V*.sql file(s) total"
            else
                fail "schema folder '${schema}' NOT found in repo"
            fi
        done
        echo "  Repo root contains: $(ls "$TEMP_DIR" | tr '\n' '  ')"
    else
        fail "Could not clone repo: ${git_repo}  (branch: ${git_branch})"
        echo "       → Check URL and branch name"
        echo "       → For private repos, set GIT_TOKEN"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo
echo "=================================================="
if [[ "$ERRORS" -eq 0 ]]; then
    echo "Validation PASSED — ready to run migrations."
    exit 0
else
    echo "Validation FAILED — ${ERRORS} error(s) found."
    exit 1
fi
