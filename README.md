# CommVerse DB Migration Framework

A lightweight, multi-schema database migration framework built with **Flyway**, **PostgreSQL**, and **GitHub Actions**. Supports sequential schema migrations with centralized history tracking.

## Overview

CommVerse DB Migration automates database version control and deployment across multiple schemas. It validates environment setup, clones migration scripts from Git, detects database state, and orchestrates Flyway migrations with comprehensive audit logging.

**Key Features:**
- ✅ Multi-schema support with configurable execution order
- ✅ Automatic Flyway installation and management
- ✅ Environment-based configuration (dev, uat, prod)
- ✅ Pre-flight validation before migrations
- ✅ Centralized history tracking across schemas
- ✅ Comprehensive audit logging
- ✅ Dry-run mode for testing
- ✅ GitHub Actions integration for CI/CD
- ✅ Cross-platform support (Linux, macOS, Windows WSL)

---

## How It Works

```
Input                                 Framework Processing
─────────────────────────────────────────────────────────────
DB credentials (.env)        ──►      1. Validate prerequisites
Git repo + branch            ──►      2. Clone scripts repository
database.yml config          ──►      3. Detect database state (fresh/existing)
                            ──►      4. Execute Flyway for each schema+subfolder
                            ──►      5. Generate audit log with execution details
```

---

## Project Structure

```
COMM_DB_MIGRATION_PRJ/
├── .github/workflows/            # GitHub Actions CI/CD
│   ├── migrate-dev.yml           # Triggered on develop/* push
│   ├── migrate-uat.yml           # Manual + code review approval
│   └── migrate-prod.yml          # Manual + main branch + approval
│
├── config/
│   └── databases.yml             # Target database + Git repo configuration
│
├── flyway/conf/
│   ├── flyway-base.conf          # Shared Flyway settings
│   ├── flyway-dev.conf           # DEV environment overrides
│   ├── flyway-uat.conf           # UAT environment overrides
│   └── flyway-prod.conf          # PROD environment overrides
│
├── scripts/
│   ├── migrate.sh                # Main migration orchestrator
│   ├── detect-state.sh           # Fresh vs existing DB detection
│   ├── validate.sh               # Pre-flight environment checks
│   ├── helpers.py                # Configuration parser (YAML reader)
│   └── README.md                 # Script documentation
│
├── logs/                         # Audit logs (auto-generated, git-ignored)
├── run.sh                        # Local entry point (main runner)
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variables template
└── README.md                     # This file
```

---

## Prerequisites

### System Requirements

| Component | Minimum | Purpose |
|-----------|---------|---------|
| **Bash** | 4.0+ | Shell scripting |
| **Python** | 3.7+ | Configuration parsing (YAML) |
| **Git** | 2.0+ | Cloning migration scripts repository |
| **PostgreSQL Client** | psql | Database connectivity checks |
| **cURL** | 7.0+ | HTTP requests (Flyway download) |

### Python Dependencies

```
PyYAML==6.0.2    # For parsing databases.yml configuration
```

### Optional

- **Flyway CLI** — Auto-downloaded if not present (v10.20.1 by default)
- **GIT_TOKEN** — Required only for private repositories

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone <this-repository>
cd COMM_DB_MIGRATION_PRJ
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
# or
python3 -m pip install -r requirements.txt
```

### 3. Create Environment File

Copy the template and fill in your database credentials:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
# For DEV environment
DEV_DB_HOST=localhost
DEV_DB_PORT=5432
DEV_DB_NAME=commverse_dev
DEV_DB_USER=postgres
DEV_DB_PASSWORD=your_password
# DEV_DB_SSL_MODE=require  # Optional: use for production

# For UAT environment
UAT_DB_HOST=uat-db-server.example.com
UAT_DB_PORT=5432
UAT_DB_NAME=commverse_uat
UAT_DB_USER=migration_user
UAT_DB_PASSWORD=your_password

# For PROD environment
PROD_DB_HOST=prod-db-server.example.com
PROD_DB_PORT=5432
PROD_DB_NAME=commverse_prod
PROD_DB_USER=migration_user
PROD_DB_PASSWORD=your_password
```

### 4. Configure Target Database

Edit [config/databases.yml](config/databases.yml):

```yaml
database:
  id: commverse_db                              # Identifier for logging
  description: "CommVerse Production Database"
  git_repo: "https://github.com/balajim82/COMM_DB_SCRIPTS"
  git_branch: "DB_SCRIPTS"                      # Migration scripts branch
  
  scripts_path:                                 # Schemas to migrate (in order)
    - catalog
    - SystemData
    - OrgData
    - MasterData
    - MarketData
  
  subfolder_order:                              # Execution order within each schema
    - tables_scripts
    - master_scripts
    - objects_scripts
  
  history_schema: "flyway_history_schema"       # Centralized history schema
```

**Configuration Details:**
- `scripts_path`: List of schema folders in the Git repo (processed sequentially)
- `subfolder_order`: Execution order for subfolders within each schema
- `history_schema`: Central metadata schema for Flyway history (auto-created)
- Each schema+subfolder combination gets its own history table: `{schema}__{subfolder}`

### 5. Scripts Repository Layout

Your Git repository (specified in `git_repo`) must follow this structure:

```
COMM_DB_SCRIPTS/
└── DB_SCRIPTS/ (branch)
    ├── SystemData/
    │   ├── tables_scripts/
    │   │   ├── V1__create_system_tables.sql
    │   │   └── V2__add_system_indexes.sql
    │   ├── master_scripts/
    │   │   └── V3__insert_system_data.sql
    │   └── objects_scripts/
    │       └── V4__create_system_functions.sql
    ├── OrgData/
    │   ├── tables_scripts/
    │   │   └── V1__create_org_tables.sql
    │   ├── master_scripts/
    │   │   └── V2__insert_org_data.sql
    │   └── objects_scripts/ (empty if not needed)
    └── MasterData/
        ├── tables_scripts/
        │   └── V1__create_master_tables.sql
        └── master_scripts/
            └── V2__populate_master_data.sql
```

**Naming Convention:** `V{version}__{description}.sql`
- Version format: `1`, `2`, `3.1`, `10` (auto-sorted)
- Double underscore `__` separates version from description
- Descriptions should use underscores for spaces: `V1__create_user_table.sql`

---

## How to Run the Program

### Quick Start (Interactive)

#### Step 1: Basic Migration (DEV Environment)

```bash
./run.sh --env dev
```

This will:
1. Load credentials from `.env` (DEV_DB_* variables)
2. Validate all prerequisites
3. Clone the migration scripts repository
4. Run Flyway migrations for each schema in order
5. Generate audit logs

#### Step 2: Validate Before Running

```bash
./run.sh --env dev --validate-only
```

Checks all prerequisites without executing migrations.

---

### Running Migrations

#### 1. **Config Mode** (Recommended for Local Development)

Uses `.env` + `config/databases.yml`:

```bash
# DEV environment
./run.sh --env dev

# UAT environment
./run.sh --env uat

# PROD environment (requires extra caution)
./run.sh --env prod
```

#### 2. **Quick Mode** (All Details on Command Line)

Useful for CI/CD or testing:

```bash
./run.sh \
  --db-host localhost \
  --db-port 5432 \
  --db-name commverse_dev \
  --db-user postgres \
  --db-password secret123 \
  --git-repo https://github.com/balajim82/COMM_DB_SCRIPTS \
  --git-branch DB_SCRIPTS \
  --scripts-path SystemData \
  --env dev
```

#### 3. **Dry Run Mode** (Test Without Executing)

```bash
./run.sh --env dev --dry-run
```

Flyway will report what *would* run without making changes.

#### 4. **Validate Only** (Pre-flight Checks)

```bash
./run.sh --env dev --validate-only
```

Verifies:
- All required tools are available (psql, git, python3, etc.)
- Environment variables are set correctly
- Database connectivity
- Git repository accessibility
- Scripts path exists

---

### Command-Line Options

```
USAGE:
  ./run.sh [--env {dev|uat|prod}] [OPTIONS]

GENERAL OPTIONS:
  --env ENV              Environment: dev, uat, or prod (default: dev)
  --dry-run              Preview migrations without execution
  --validate-only        Run pre-flight checks only (exit before migration)
  -h, --help             Show full help message

CONFIG MODE (reads .env + databases.yml):
  ./run.sh --env dev

  Requires .env with variables: {ENV}_DB_HOST, {ENV}_DB_PORT, etc.

QUICK MODE (all details on CLI):
  ./run.sh \
    --db-host HOST \
    --db-port PORT \
    --db-name DB_NAME \
    --db-user USER \
    --db-password PASSWORD \
    --git-repo REPO_URL \
    [--scripts-path PATH]    (default: migrations)
    [--git-branch BRANCH]    (default: main)
    [--git-token TOKEN]      (for private repos)
    [--env ENV]              (default: dev)

EXAMPLES:

  # 1. Standard DEV migration with .env
  ./run.sh --env dev

  # 2. Validate before running
  ./run.sh --env dev --validate-only

  # 3. Dry run (preview without changes)
  ./run.sh --env dev --dry-run

  # 4. Quick mode with all params
  ./run.sh \
    --db-host localhost \
    --db-port 5432 \
    --db-name commverse_dev \
    --db-user postgres \
    --db-password mysecret \
    --git-repo https://github.com/org/db-scripts \
    --git-branch main \
    --env dev

  # 5. Private repo with token
  ./run.sh --env prod --git-token ghp_xxxxxxxxxxxx
```

---

## Environment Variables

### Format

Environment variables follow the pattern: `{ENVIRONMENT}_DB_{FIELD}`

Example: For `--env dev`, the framework looks for:
- `DEV_DB_HOST`
- `DEV_DB_PORT`
- `DEV_DB_NAME`
- `DEV_DB_USER`
- `DEV_DB_PASSWORD`
- `DEV_DB_SSL_MODE` (optional)

### Sample .env File

```bash
# ========== DEV ==========
DEV_DB_HOST=localhost
DEV_DB_PORT=5432
DEV_DB_NAME=commverse_dev
DEV_DB_USER=postgres
DEV_DB_PASSWORD=dev_password
# DEV_DB_SSL_MODE=disable

# ========== UAT ==========
UAT_DB_HOST=uat-db.internal
UAT_DB_PORT=5432
UAT_DB_NAME=commverse_uat
UAT_DB_USER=db_migration
UAT_DB_PASSWORD=uat_password
UAT_DB_SSL_MODE=require

# ========== PROD ==========
PROD_DB_HOST=prod-db.internal
PROD_DB_PORT=5432
PROD_DB_NAME=commverse_prod
PROD_DB_USER=db_migration
PROD_DB_PASSWORD=prod_password
PROD_DB_SSL_MODE=require

# ========== GIT (optional, for private repos) ==========
GIT_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Optional Variables

- **GIT_TOKEN** — Personal access token for private Git repositories
- **FLYWAY_VERSION** — Override Flyway CLI version (default: 10.20.1)
- **GITHUB_ACTOR** — Recorded execution user in audit logs (auto-set in GitHub Actions)

---

## Output & Logs

### Console Output

The runner provides real-time feedback:

```
==============================================
 CommVerse DB Migration — Local Runner
 Environment : dev
==============================================

[info] Loading credentials from .env
[info] Validating prerequisites...
[info] Cloning scripts repository...
[info] Detecting database state...
[info] Running Flyway migration for SystemData/tables_scripts...
[info] Migration successful!
```

### Audit Logs

After each run, detailed logs are saved to `logs/` directory:

```
logs/
├── migration_20250424_143022_dev.log
├── migration_20250424_150015_prod.log
└── validation_20250424_152048_uat.log
```

Log contains:
- Start/end timestamps
- Environment details
- Database connection info
- Migrated schemas and scripts
- Execution status (success/failure)
- Execution user
- Any errors or warnings

---

## Updated Changes & New Features

### Version 2.0 Updates

- ✨ **Multi-Schema Support**: Execute migrations sequentially across multiple schemas with independent history tracking
- ✨ **Subfolder Ordering**: Configurable execution order for script subfolders (e.g., tables → functions → procedures)
- 🔧 **Flexible Configuration**: YAML-based multi-schema configuration in `databases.yml`
- ✅ **Enhanced Validation**: Pre-flight checks for all dependencies and configurations
- 📋 **Comprehensive Logging**: Detailed audit trails for compliance and troubleshooting
- 🚀 **Auto Flyway Download**: Automatic Flyway CLI installation if not present
- 🔒 **Secure Credentials**: Credentials stored in `.env` (git-ignored), never in code
- 🐧 **Cross-Platform**: Works on Linux, macOS, Windows WSL, and Git Bash
- 🔄 **Dry-Run Mode**: Test migrations without applying changes
- 🎯 **Environment Isolation**: Separate configs for dev, uat, prod with independent credentials

### Recent Improvements

- Python 3.7+ support for broader compatibility
- Enhanced error messages for troubleshooting
- Support for SSL/TLS database connections
- Automatic handling of Git Bash paths on Windows
- Support for private GitHub repositories with token authentication
- Improved dependency resolution (handles multiple Python command variants)

---

## Troubleshooting

### Common Issues

#### 1. "Python 3 is required"

```bash
# Install Python 3.7+
# macOS:
brew install python3

# Ubuntu/Debian:
sudo apt-get install python3 python3-pip

# Windows:
# Download from https://www.python.org/downloads/
```

#### 2. "PyYAML not found"

```bash
pip install -r requirements.txt
```

#### 3. Database Connection Fails

```bash
# Check connection manually
psql -h $DEV_DB_HOST -p $DEV_DB_PORT -U $DEV_DB_USER -d $DEV_DB_NAME

# Check .env is loaded
cat .env
```

#### 4. Git Repository Not Found

```bash
# Verify git_repo in databases.yml
# Check branch exists
git ls-remote https://github.com/balajim82/COMM_DB_SCRIPTS | grep DB_SCRIPTS

# For private repos, ensure GIT_TOKEN is set
export GIT_TOKEN=ghp_xxxx
```

#### 5. Flyway Download Fails

```bash
# Check internet connectivity
curl -I https://repo1.maven.org/maven2/

# Manually download Flyway
# or specify version: export FLYWAY_VERSION=10.20.1
```

#### 6. "Validation Failed"

```bash
# Run validation to see what's missing
./run.sh --env dev --validate-only

# This will check:
# ✓ bash 4.0+
# ✓ python3
# ✓ psql (PostgreSQL client)
# ✓ git
# ✓ curl
# ✓ Environment variables
# ✓ Database connectivity
```

---

## Contributing

When adding new migrations:

1. **Follow Naming Convention**: `V{version}__{description}.sql`
   - ✅ `V1__create_users_table.sql`
   - ✅ `V2__add_email_column.sql`
   - ❌ `V1_create_users_table.sql` (single underscore)
   - ❌ `create_users.sql` (no version)

2. **Place in Correct Folder**: 
   ```
   SystemData/
   ├── tables_scripts/          # DDL: CREATE TABLE, ALTER TABLE, etc.
   ├── master_scripts/          # DML: INSERT, UPDATE, DELETE (master data)
   └── objects_scripts/         # Functions, procedures, views, triggers
   ```

3. **Test Locally**:
   ```bash
   ./run.sh --env dev --validate-only
   ./run.sh --env dev --dry-run
   ./run.sh --env dev
   ```

4. **Verify Migrations**:
   ```bash
   # Check migration history in the database
   SELECT * FROM flyway_history_schema.schema_version;
   ```

---

## Database Migration Naming & Structure

### Flyway Versioning

Migrations are automatically sorted by version number:

```
V1__initial_schema.sql          → 1
V2__add_users_table.sql         → 2
V2.1__alter_users.sql           → 2.1
V10__create_indexes.sql         → 10 (runs after V2.1!)
```

### Schema & Subfolder Separation

The framework processes each schema independently with its own history:

```
Schema: SystemData
├── tables_scripts/
│   └── History table: flyway_history_schema.SystemData__tables_scripts
├── master_scripts/
│   └── History table: flyway_history_schema.SystemData__master_scripts
└── objects_scripts/
    └── History table: flyway_history_schema.SystemData__objects_scripts

Schema: OrgData
├── tables_scripts/
│   └── History table: flyway_history_schema.OrgData__tables_scripts
... (and so on)
```

This ensures:
- Parallel folder migrations don't interfere
- Failed migrations can be rolled back by schema/subfolder
- Clear history tracking per component

---

## Support & Documentation

- 📖 [Flyway Documentation](https://flywaydb.org/documentation/)
- 🔗 [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- 📂 [GitHub Repository](https://github.com/balajim82/COMM_DB_SCRIPTS)
- 📝 [Script Documentation](scripts/README.md)

---

## License

This project is part of CommVerse. See LICENSE file for details.

### Quick mode — everything on the command line

```bash
./run.sh \
  --db-host  localhost     \
  --db-port  5432          \
  --db-name  mydb          \
  --db-user  admin         \
  --db-password secret     \
  --git-repo https://github.com/your-org/db-scripts.git
```

Private repo:

```bash
./run.sh ... --git-token ghp_xxxxxxxxxxxx
```

Dry run (see what would apply, no changes):

```bash
./run.sh ... --dry-run
```

Validate only (check connectivity + repo, no migration):

```bash
./run.sh ... --validate-only
```

---

### Config mode — use .env file

```bash
cp .env.example .env
# fill in DEV_DB_HOST, DEV_DB_PORT, DEV_DB_NAME, DEV_DB_USER, DEV_DB_PASSWORD

./run.sh --env dev
./run.sh --env dev --dry-run
./run.sh --env dev --validate-only
```

The `.env` file uses an environment prefix (`DEV_`, `UAT_`, `PROD_`). `run.sh` automatically maps `DEV_DB_HOST` → `DB_HOST` when you pass `--env dev`.

---

## Environment Variables

| Variable | Used by | Purpose |
|----------|---------|---------|
| `DB_HOST` | migrate.sh / validate.sh | DB hostname |
| `DB_PORT` | migrate.sh / validate.sh | DB port |
| `DB_NAME` | migrate.sh / validate.sh | Database name |
| `DB_USER` | migrate.sh / validate.sh | DB username |
| `DB_PASSWORD` | migrate.sh / validate.sh | DB password |
| `GIT_TOKEN` | migrate.sh / validate.sh | PAT for private script repos |
| `FLYWAY_VERSION` | migrate.sh | Override Flyway CLI version (default: 10.20.1) |

In **GitHub Actions**, each Environment (dev / uat / production) has its own secret values for these variables — no prefix needed.

Locally, `.env` uses `DEV_DB_HOST` / `UAT_DB_HOST` / `PROD_DB_HOST` etc., and `run.sh` selects the right set based on `--env`.

---

## GitHub Actions

### DEV — Auto Trigger

Runs automatically on push to `develop`, `feature/**`, or `fix/**`.
Can also be triggered manually via **Actions → Migrate — DEV → Run workflow**.

**GitHub Secrets to add** (under the `dev` Environment):
```
DB_HOST  DB_PORT  DB_NAME  DB_USER  DB_PASSWORD  GIT_TOKEN
```

---

### UAT — Manual Approval

1. **Actions → Migrate — UAT → Run workflow**
2. Type `CONFIRM` in the confirmation field
3. Optionally check dry run first
4. The `migrate` job **pauses** until a reviewer approves

**GitHub Secrets** (under the `uat` Environment):
```
DB_HOST  DB_PORT  DB_NAME  DB_USER  DB_PASSWORD  GIT_TOKEN
```

---

### PROD — Manual + Restricted

1. Must trigger **from the `main` branch**
2. **Actions → Migrate — PROD → Run workflow**
3. Type exactly `CONFIRM-PROD`
4. Dry run defaults to `true` — run it first, then re-run with it unchecked
5. The `migrate` job **pauses** until a reviewer approves

**GitHub Secrets** (under the `production` Environment):
```
DB_HOST  DB_PORT  DB_NAME  DB_USER  DB_PASSWORD  GIT_TOKEN
```

---

### GitHub Environment Protection Setup

**UAT:**
1. **Settings → Environments → New environment** → name: `uat`
2. Add **Required reviewers**

**PROD:**
1. **Settings → Environments → New environment** → name: `production`
2. Add **Required reviewers** (DBAs / tech leads)
3. **Deployment branches** → select `main` only

Because each GitHub Environment stores its own secret values for `DB_HOST` etc., the same workflow file works for all environments without any name changes.

---

## Flyway History Schema

Every database gets a `flyway_history` schema with a `schema_version` table. It is:
- Created automatically on first run
- Isolated from your application schemas
- Protected from `clean` in UAT and PROD configs

To inspect it:

```sql
SELECT version, description, installed_on, execution_time, success
FROM flyway_history.schema_version
ORDER BY installed_rank;
```

---

## Troubleshooting

**`DB_HOST is not set`**
→ Set env vars before calling migrate.sh, or use `run.sh` which handles this.

**`Failed to clone scripts repo`**
→ Check `git_repo` URL and `git_branch` in databases.yml. For private repos set `GIT_TOKEN`.

**`scripts_path 'migrations' not found in repo`**
→ The folder name doesn't match. The error output lists what folders do exist.

**`Migration checksum mismatch`**
→ A previously applied script was edited. Never modify applied scripts — add a new `V{n+1}__*.sql` instead.

**PROD blocked: "branch restriction"**
→ PROD can only run from `main`. Switch to `main` and re-trigger.

**UAT/PROD job stuck**
→ Waiting for reviewer approval. Go to **Actions → the running workflow → Review deployments → Approve**.

To run Manually, we should use the below commands
===============================================
# Make the scripts executable (first time only)
chmod +x run.sh scripts/*.sh

# Validate first — checks DB connectivity + repo access before touching anything
./run.sh --env dev --validate-only

# Dry run — shows what migrations WOULD apply, makes zero changes
./run.sh --env dev --dry-run

# Apply migrations
./run.sh --env dev
