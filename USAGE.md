# commverse-db – Usage Guide

Pydantic -> PostgreSQL DDL / DML script generator.

---

## 1. Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| PostgreSQL | 14+ (Neon, Supabase, local, or any Postgres-compatible host) |

---

## 2. Installation

```bash
cd COMM_PYDANTIC_TABLE_PRJ

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

---

## 3. Database connection (.env)

Copy `.env.example` to `.env`. Two options — use **one**:

```bash
copy .env.example .env    # Windows
```

**Option 1 – full URL** (credentials embedded):
```ini
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

**Option 2 – individual fields** (recommended for cloud DBs like Neon):
```ini
DB_HOST=ep-xxx.us-east-1.aws.neon.tech
DB_PORT=5432
DB_NAME=mydb
DB_USER=myuser
DB_PASSWORD=mypassword
DB_SSLMODE=require        # use "disable" for local Docker
```

`DATABASE_URL` takes priority. If neither is fully configured, the program prints exactly which variables are missing.

Generated SQL files land in:
```
generated_sql/
├── ddl/    <- CREATE TABLE and ALTER TABLE scripts
└── dml/    <- util_deep_merge_jsonb UPDATE scripts
```

---

## 4. Define a Pydantic model

Place models in `models/`. Two annotation styles are supported and can be mixed.

### Style A – per-field `json_schema_extra`

```python
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class UserProfile(BaseModel):
    user_id: UUID     = Field(..., json_schema_extra={"primary_key": True})
    org_id:  int      = Field(..., json_schema_extra={"foreign_key": "ORGANIZATION.id"})
    created: datetime = Field(..., json_schema_extra={"partition_column": True})
    username: str
    email:    str
```

### Style B – `model_config` dict (preferred for shared-schema models)

```python
class PermRoleModel(BaseModel):
    org_code:  str  = Field(..., description="[PK, Partition] Tenant org code")
    role_code: str  = Field(..., description="[PK] Unique role code")
    role_name: str
    is_active: bool = True

    model_config = {
        "entity_name":      "PermRoles",                   # -> table PERM_ROLES
        "primary_keys":     ["org_code", "role_code"],
        "partition_fields": ["org_code"],
        "foreign_keys":     {"org_code": "ORGANIZATION.code"},  # optional
        "entity_type":      "SystemData",                  # written as SQL comment
    }
```

### `model_config` keys recognised by the inspector

| Key | Type | Purpose |
|---|---|---|
| `entity_name` | `str` | Table name (UPPER_SNAKE_CASE). Trailing `Model` is stripped from class name as fallback. |
| `primary_keys` | `list[str]` | Fields that form the PRIMARY KEY. |
| `partition_fields` | `list[str]` | Fields used for PARTITION BY. |
| `foreign_keys` | `dict[str, str]` | `{"field": "TABLE.col"}` FK references. |

All other keys are preserved as `--` comments in the SQL header.

### Python -> PostgreSQL type mapping

| Python type | PostgreSQL type |
|---|---|
| `str` | `TEXT` |
| `int` | `BIGINT` |
| `float` | `DOUBLE PRECISION` |
| `bool` | `BOOLEAN` |
| `datetime` | `TIMESTAMP WITH TIME ZONE` |
| `date` | `DATE` |
| `Decimal` | `NUMERIC` |
| `UUID` | `UUID` |
| `dict` / `Dict[…]` | `JSONB` |
| `list` / `List[…]` | `JSONB` |
| `bytes` | `BYTEA` |
| `Optional[X]` | same as `X`, column marked nullable |

---

## 5. DDL – `main.py`

`main.py` auto-discovers every `BaseModel` subclass under `models/`. No model path argument needed.

### Generate CREATE TABLE scripts

```bash
python main.py
```

Scans `models/`, generates `generated_sql/ddl/create_<table>.sql` for each model.

### Generate and apply to database

```bash
python main.py --apply
```

Generates scripts then executes them against the DB configured in `.env`.

### Generate ALTER TABLE scripts (diff live DB vs model)

```bash
python main.py --alter
```

Connects to the DB, reads `information_schema`, compares against the current model, and generates `generated_sql/ddl/alter_<table>.sql`.

### Generate ALTER and apply

```bash
python main.py --alter --apply
```

**Table design rules**

- `primary_key` / `primary_keys` fields -> real columns + `PRIMARY KEY` constraint.
- `foreign_key` / `foreign_keys` fields -> real columns + `FOREIGN KEY` constraint.
- `partition_column` / `partition_fields` fields -> real columns + `PARTITION BY`.
- Partition type: `RANGE` for DATE/TIMESTAMP fields, `HASH` for all others.
- **All** model fields are also stored in `data JSONB` at runtime.
- `created_at` and `updated_at` audit columns are added automatically.

**Example output – `PERM_ROLES`:**

```sql
CREATE TABLE IF NOT EXISTS PERM_ROLES
(
    org_code    TEXT NOT NULL,
    role_code   TEXT NOT NULL,
    data        JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_perm_roles PRIMARY KEY (org_code, role_code)
) PARTITION BY HASH (org_code);
```

---

## 6. DML – `dml.py`

`dml.py` generates `DO $$ ... END $$` blocks that call the `util_deep_merge_jsonb`
stored function. Configure `OPERATIONS` inside the file, then run.

### Commands

| Command | Effect |
|---|---|
| `python dml.py --update` | Generate SQL for all `update` entries in `OPERATIONS` |
| `python dml.py --update --apply` | Generate + execute against the DB |
| `python dml.py --insert` | Coming soon |
| `python dml.py --delete` | Coming soon |

An operation type flag (`--update`, `--insert`, or `--delete`) is **required**.
Running `python dml.py` without one shows a usage error.

### Configure OPERATIONS

Edit the `OPERATIONS` list at the top of `dml.py`:

```python
OPERATIONS: list[dict] = [
    {
        "op"             : "update",
        "schema_name"    : "SystemData",
        "table_name"     : "SchedulerDiary",
        "p_column_name"  : "data",              # JSONB column (default: "data")
        "p_new_json"     : {                    # dict or raw JSON string
            "frequency_configuration": {
                "schedule_type"      : "Regular_Frequency",
                "cron_expression"    : "*/30 * * * *",
                "execution_date_times": [],
            }
        },
        "p_append_keys"  : {},                  # keys to deep-merge/append
        "p_where_columns": ["org_code"],        # filter columns ([] = all rows)
        "p_where_values" : ["ACME"],            # filter values
    },
]
```

### Generated SQL output

```sql
DO $$
BEGIN
    PERFORM util_deep_merge_jsonb(
        'update',
        'SystemData',
        'SchedulerDiary',
        'data',
        '{
          "frequency_configuration": {
            "schedule_type": "Regular_Frequency",
            "cron_expression": "*/30 * * * *",
            "execution_date_times": []
          }
        }',
        '{}',
        ARRAY['org_code']::text[],
        ARRAY['ACME']::text[]
    );
END $$;
```

### `p_new_json` alignment rules

- Single-key / flat JSON stays on one line: `'{"key": "value"}'`
- Multi-line JSON: every line after `{` is indented 8 spaces to align with the SQL parameter column.

### `OPERATIONS` field reference

| Field | Required | Default | Description |
|---|---|---|---|
| `op` | yes | — | Operation type: `"update"` |
| `schema_name` | yes | — | PostgreSQL schema |
| `table_name` | yes | — | Table name |
| `p_column_name` | no | `"data"` | JSONB column to merge into |
| `p_new_json` | yes | — | `dict` or raw JSON string |
| `p_append_keys` | no | `{}` | Keys to append rather than overwrite |
| `p_where_columns` | no | `[]` | Filter column names (`[]` = all rows) |
| `p_where_values` | no | `[]` | Filter column values |

---

## 7. Full workflow example

```bash
# 1. Define your model in models/example_model.py

# 2. Generate CREATE TABLE
python main.py

# 3. Apply to database
python main.py --apply

# 4. Update your model (add/change fields)

# 5. Generate ALTER TABLE diff
python main.py --alter

# 6. Apply ALTER
python main.py --alter --apply

# 7. Update JSONB data using DML
#    Edit OPERATIONS in dml.py, then:
python dml.py --update             # preview SQL
python dml.py --update --apply     # execute
```

---

## 8. Project structure

```
COMM_PYDANTIC_TABLE_PRJ/
├── .env                          <- credentials (not committed)
├── .env.example                  <- template with Option 1 / Option 2
├── requirements.txt
├── config.py                     <- pydantic-settings reads .env
├── main.py                       <- DDL runner (auto-discovers models/)
├── dml.py                        <- DML runner (util_deep_merge_jsonb)
│
├── models/
│   └── example_model.py          <- Pydantic model definitions
│
├── core/
│   ├── type_map.py               <- Python -> PostgreSQL type resolution
│   ├── model_inspector.py        <- parses pk/fk/partition metadata (Style A + B)
│   ├── db/
│   │   └── connection.py         <- psycopg2 + information_schema helpers
│   ├── ddl/
│   │   ├── table_generator.py    <- CREATE TABLE script generator
│   │   └── alter_generator.py    <- ALTER TABLE diff engine
│   └── dml/
│       └── jsonb_ops.py          <- low-level JSONB SQL helpers
│
└── generated_sql/
    ├── ddl/                      <- create_*.sql, alter_*.sql
    └── dml/                      <- dml_*_update.sql, ...
```
