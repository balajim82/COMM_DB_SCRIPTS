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

## 3. Configuration (.env)

Copy `.env.example` to `.env`. Two options for the database connection — use **one**:

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

`DATABASE_URL` takes priority. If neither is fully configured the program prints exactly which variables are missing.

**Additional settings:**

```ini
SQL_OUTPUT_PATH=./generated_sql   # where generated SQL files are written (default)
SEED_DATA_PATH=./seed_data        # folder containing entity seed JSON files (default)
```

Generated SQL files land in:
```
generated_sql/
├── ddl/    <- CREATE TABLE and ALTER TABLE scripts
└── dml/    <- INSERT, DELETE, and UPDATE scripts
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
class PermResourceOperationModel(BaseModel):
    """Sub-entity: allowed operations per resource."""

    org_code:       str           = Field(..., description="[PK, Partition] Tenant org code")
    resource_code:  str           = Field(..., description="[PK, Partition] Parent resource code")
    operation_code: str           = Field(..., description="[PK] Operation identifier")
    operation_name: Optional[str] = Field(None, description="Human-readable label")

    model_config = {
        "meta_lake_code":    "COGITO",
        "entity_type":       "SystemData",
        "kind":              "System",
        "entity_name":       "PermResourceOperations",
        "workspaces":        [],
        "primary_keys":      ["org_code", "resource_code", "operation_code"],
        "required_fields":   ["org_code", "resource_code", "operation_code"],
        "partition_fields":  ["org_code", "resource_code"],
        "partition_order":   {"org_code": 1, "resource_code": 2},
        "date_fields":       [],
    }
```

### `model_config` keys reference

| Key | Type | Used by | Purpose |
|---|---|---|---|
| `entity_name` | `str` | all commands | Table / entity name. Trailing `Model` stripped from class name as fallback. |
| `primary_keys` | `list[str]` | DDL, delete | Fields forming the PRIMARY KEY. Also used as the WHERE clause for `--delete`. |
| `partition_fields` | `list[str]` | DDL, metadata | Fields used for PARTITION BY and marked `partition=True` in metadata. |
| `partition_order` | `dict[str,int]` or `int` | DDL, metadata | Partition priority per field. |
| `foreign_keys` | `dict[str, str]` | DDL | `{"field": "TABLE.col"}` FK references. |
| `meta_lake_code` | `str` | metadata | MetaLake code stored in MetaDataDictionary (e.g. `"COGITO"`). |
| `entity_type` | `str` | DDL, metadata | PostgreSQL schema for the entity table (e.g. `"SystemData"`). |
| `kind` | `str` | metadata | MetadataKind value (e.g. `"System"`, `"Standard"`). |
| `workspaces` | `list[str]` | metadata | Workspace tags stored in metadata. |
| `required_fields` | `list[str]` | metadata | Fields flagged `required=True` in MetaDataDictionary. |
| `date_fields` | `list[str]` | metadata | Fields whose `kind` is overridden to `"datetime"` in metadata. |

All unrecognised keys are preserved as `--` comments in the SQL header.

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

`main.py` auto-discovers every `BaseModel` subclass under `models/`. No model path argument is needed.

### Command summary

| Command | Output folder | Description |
|---|---|---|
| `python main.py --table_generate` | `generated_sql/ddl/` | Generate CREATE TABLE scripts |
| `python main.py --metadata_generate` | `generated_sql/dml/` | Generate INSERT scripts for `catalog.MetaDataDictionary` |
| `python main.py --seed_data_insert` | `generated_sql/dml/` | Generate INSERT scripts from seed JSON files |
| `python main.py --apply` | `generated_sql/ddl/` | Generate CREATE TABLE + execute against DB |
| `python main.py --alter` | `generated_sql/ddl/` | Generate ALTER TABLE diff scripts |
| `python main.py --alter --apply` | `generated_sql/ddl/` | Generate ALTER TABLE + execute against DB |

Running `python main.py` with no flags is equivalent to `--table_generate`.

---

### `--table_generate` — CREATE TABLE scripts

```bash
python main.py --table_generate
```

Scans `models/`, generates `generated_sql/ddl/create_<entity>.sql` for each model.

**Table design rules**

- `primary_keys` fields -> real columns + `PRIMARY KEY` constraint.
- `foreign_keys` fields -> real columns + `FOREIGN KEY` constraint.
- `partition_fields` fields -> real columns + `PARTITION BY`.
  - Partition type: `RANGE` for DATE/TIMESTAMP fields, `HASH` for all others.
- **All** model fields are also stored in `data JSONB` at runtime.
- `created_at` and `updated_at` audit columns are added automatically.

**Example output:**

```sql
CREATE TABLE IF NOT EXISTS PERM_RESOURCE_OPERATIONS
(
    org_code        TEXT NOT NULL,
    resource_code   TEXT NOT NULL,
    operation_code  TEXT NOT NULL,
    data            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_perm_resource_operations
        PRIMARY KEY (org_code, resource_code, operation_code)
) PARTITION BY HASH (org_code);
```

---

### `--metadata_generate` — MetaDataDictionary INSERT scripts

```bash
python main.py --metadata_generate
```

For every model × every organisation code fetched from `admin."Organizations"`:

1. Builds a `Metadata`-compatible JSON from the Pydantic model using `model_config`  
   (mirrors `seed_preconfigured_entities_for_org` / `Metadata.from_pydantic_model`).
2. Generates one idempotent `INSERT … ON CONFLICT … DO UPDATE` statement.
3. Writes `generated_sql/dml/metadata_insert_<entity>.sql`.

The JSON stored in `metadata JSONB` includes all field metadata (data_type, kind,
primary_key, partition, required flags) exactly as the SnowTiger runtime expects.

**How org codes are sourced:**

```python
# in run_metadata_generate() — edit as needed:
org_codes = fetch_org_codes()   # reads from admin."Organizations"
```

**Target table schema (`catalog.MetaDataDictionary`):**

| Column | Type | Notes |
|---|---|---|
| `db_name` | TEXT | Set to `org_code` (one logical DB per org) |
| `org_code` | TEXT | Organisation code |
| `meta_lake_code` | TEXT | From `model_config["meta_lake_code"]` |
| `entity_name` | TEXT | From `model_config["entity_name"]` |
| `entity_type` | TEXT | From `model_config["entity_type"]` |
| `entity_description` | TEXT | Model docstring |
| `metadata` | JSONB | Full Metadata JSON (fields, PKs, partitions, …) |
| `updated_at` | TIMESTAMP | Set to `NOW()` |

**Example output:**

```sql
BEGIN;

-- org_code: PT03
INSERT INTO catalog."MetaDataDictionary"
    (db_name, org_code, meta_lake_code, entity_name,
     entity_type, entity_description, metadata, updated_at)
VALUES
    ('PT03', 'PT03', 'COGITO', 'PermResourceOperations',
     'SystemData', 'Sub-entity: allowed operations per resource.',
     '{"meta_lake_code": "COGITO", "entity_name": "PermResourceOperations", ...}'::JSONB,
     NOW())
ON CONFLICT (db_name, entity_name) DO UPDATE SET
    metadata           = EXCLUDED.metadata,
    org_code           = EXCLUDED.org_code,
    meta_lake_code     = EXCLUDED.meta_lake_code,
    entity_type        = EXCLUDED.entity_type,
    entity_description = EXCLUDED.entity_description,
    updated_at         = NOW();

COMMIT;
```

---

### `--seed_data_insert` — Seed data INSERT scripts

```bash
python main.py --seed_data_insert
```

For every model × every organisation code, reads the matching seed JSON file and
generates real `INSERT … ON CONFLICT … DO UPDATE` statements.

**Seed file location:**

```
<SEED_DATA_PATH>/<entity_name>.json
```

Default `SEED_DATA_PATH` is `./seed_data`. Override in `.env`:

```ini
SEED_DATA_PATH=./seed_data
```

**Seed file format** (one file per entity):

```json
{
    "data": [
        {
            "resource_code": "DATA_CATALOG",
            "resource_name": "Data Catalog",
            "description":   "Data catalog management"
        },
        {
            "resource_code": "AGENTIC_WORKFLOW",
            "resource_name": "Agentic Workflows",
            "description":   "Agentic workflow and agent management"
        }
    ],
    "schema_name": "SystemData",
    "table_name":  "PermResources"
}
```

**Behaviour:**

- `org_code` is **injected automatically** into every row  
  (mirrors `upload_actual_data` from `seed_preconfigured_entities_for_org`).
- Structural PK/partition column values are extracted from the row.
- The full row (all fields, including `org_code`) is stored in `data JSONB`.
- Models with no matching seed file are skipped with a `[SKIP]` message.
- Output written to `generated_sql/dml/seed_insert_<entity>.sql`.

**Example output** (2 orgs × 2 rows = 4 statements):

```sql
BEGIN;

-- org_code: PT03 ----------------------------------------

INSERT INTO "SystemData"."PermResources" ("org_code", "resource_code", "data", "updated_at")
VALUES
    ('PT03',
     'DATA_CATALOG',
     '{"resource_code": "DATA_CATALOG", "resource_name": "Data Catalog",
       "description": "Data catalog management", "org_code": "PT03"}'::JSONB,
     NOW())
ON CONFLICT ("org_code", "resource_code") DO UPDATE SET
    "data"       = EXCLUDED."data",
    "updated_at" = NOW();

COMMIT;
```

---

## 6. DML – `dml.py`

`dml.py` generates SQL for update and delete operations against entity tables.  
Configure the `OPERATIONS` list inside the file, then run.

### Command summary

| Command | Description |
|---|---|
| `python dml.py --update` | Generate `util_deep_merge_jsonb` SQL for all `update` entries |
| `python dml.py --update --apply` | Generate + execute update SQL against the DB |
| `python dml.py --delete` | Generate DELETE scripts — WHERE clause derived from model PKs |
| `python dml.py --delete --apply` | Generate + execute DELETE SQL against the DB |
| `python dml.py --insert` | Coming soon |

An operation type flag is **required**. `--apply` is optional on any command.

---

### Update operations

Configure in the `OPERATIONS` list:

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
        "p_where_values" : ["PT03"],            # filter values
    },
]
```

**Generated SQL:**

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
        ARRAY['PT03']::text[]
    );
END $$;
```

**`OPERATIONS` field reference — update:**

| Field | Required | Default | Description |
|---|---|---|---|
| `op` | yes | — | `"update"` |
| `schema_name` | yes | — | PostgreSQL schema |
| `table_name` | yes | — | Table name |
| `p_column_name` | no | `"data"` | JSONB column to merge into |
| `p_new_json` | yes | — | `dict` or raw JSON string |
| `p_append_keys` | no | `{}` | Keys to append rather than overwrite |
| `p_where_columns` | no | `[]` | Filter column names (`[]` = all rows) |
| `p_where_values` | no | `[]` | Filter column values |

---

### Delete operations

The delete generator **automatically derives the WHERE clause** from the model's
`model_config["primary_keys"]`. You only supply the values — column names are never
hardcoded in `OPERATIONS`.

```python
OPERATIONS: list[dict] = [
    {
        "op"        : "delete",
        "table_name": "PermResourceOperations",  # must match model_config["entity_name"]
        "pk_values" : {                          # one entry per primary key field
            "org_code"      : "PT03",
            "resource_code" : "DATA_CATALOG",
            "operation_code": "DELETE",
        },
        # "schema_name": "SystemData",           # optional — derived from model_config["entity_type"]
    },
]
```

**How it works:**

1. `table_name` is used to locate the matching Pydantic model in `models/`  
   (matched against `model_config["entity_name"]`).
2. `primary_keys` are read from that model's `model_config`.
3. Each PK column is matched to the corresponding value in `pk_values`.
4. A `DELETE … WHERE pk1 = 'v1' AND pk2 = 'v2' …` statement is generated.

**Generated SQL:**

```sql
-- DELETE from "SystemData"."PermResourceOperations"
-- Primary keys (from PermResourceOperationModel): org_code, resource_code, operation_code
DELETE FROM "SystemData"."PermResourceOperations"
WHERE "org_code" = 'PT03'
  AND "resource_code" = 'DATA_CATALOG'
  AND "operation_code" = 'DELETE';
```

Output written to `generated_sql/dml/dml_<entity>_delete.sql`.

**`OPERATIONS` field reference — delete:**

| Field | Required | Default | Description |
|---|---|---|---|
| `op` | yes | — | `"delete"` |
| `table_name` | yes | — | Must match `model_config["entity_name"]` of a model in `models/` |
| `pk_values` | yes | — | `dict` mapping every primary key field to its value |
| `schema_name` | no | from model | PostgreSQL schema; derived from `model_config["entity_type"]` if absent |

**Error cases:**

| Situation | Error message |
|---|---|
| No model found with matching `entity_name` | `no model found with entity_name='…'` |
| Model has no `primary_keys` in `model_config` | `Model '…' has no primary_keys in model_config` |
| A required PK value is missing from `pk_values` | `pk_values is missing entries for primary key(s): […]` |

---

## 7. Full workflow example

```bash
# 1. Define your model in models/example_model.py

# 2. Generate CREATE TABLE DDL
python main.py --table_generate

# 3. Apply DDL to database
python main.py --apply

# 4. Seed MetaDataDictionary for all organisations
python main.py --metadata_generate

# 5. Insert preconfigured entity data for all organisations
#    (requires seed_data/PermResourceOperations.json)
python main.py --seed_data_insert

# 6. Update model (add/change fields), then diff and apply
python main.py --alter
python main.py --alter --apply

# 7. Update JSONB data using DML
#    Edit OPERATIONS in dml.py, then:
python dml.py --update              # preview SQL
python dml.py --update --apply      # execute

# 8. Delete specific rows by primary key
#    Edit the delete entry in OPERATIONS, then:
python dml.py --delete              # preview SQL
python dml.py --delete --apply      # execute
```

---

## 8. Project structure

```
COMM_PYDANTIC_TABLE_PRJ/
├── .env                           <- credentials + SEED_DATA_PATH (not committed)
├── .env.example                   <- template with Option 1 / Option 2
├── requirements.txt
├── config.py                      <- pydantic-settings reads .env
│                                     (DATABASE_URL, DB_*, SQL_OUTPUT_PATH, SEED_DATA_PATH)
├── main.py                        <- DDL + metadata/seed DML runner
│                                     --table_generate  --metadata_generate
│                                     --seed_data_insert  --apply  --alter
├── dml.py                         <- DML runner (update / delete)
│                                     --update  --delete  --apply
│
├── models/
│   └── example_model.py           <- Pydantic model definitions
│
├── seed_data/                     <- seed JSON files (one per entity)
│   └── <EntityName>.json          <- {"data": [...], "schema_name": "...", "table_name": "..."}
│
├── core/
│   ├── type_map.py                <- Python -> PostgreSQL type resolution
│   ├── model_inspector.py         <- parses pk/fk/partition metadata (Style A + B)
│   ├── org_fetcher.py             <- fetch_org_codes() from admin."Organizations"
│   ├── metadata_builder.py        <- build_metadata_dict() — mirrors Metadata.from_pydantic_model
│   ├── db/
│   │   └── connection.py          <- psycopg2 + information_schema helpers
│   ├── ddl/
│   │   ├── table_generator.py     <- CREATE TABLE script generator
│   │   └── alter_generator.py     <- ALTER TABLE diff engine
│   └── dml/
│       ├── jsonb_ops.py           <- low-level JSONB SQL helpers
│       ├── metadata_generator.py  <- MetaDataDictionary INSERT script generator
│       └── table_insert_generator.py <- seed data INSERT script generator
│
└── generated_sql/
    ├── ddl/                       <- create_*.sql, alter_*.sql
    └── dml/                       <- metadata_insert_*.sql, seed_insert_*.sql,
                                      dml_*_update.sql, dml_*_delete.sql
```

---

## 9. Seed data file conventions

Seed files are matched to models by `entity_name` (case-sensitive):

| Model `entity_name` | Expected file |
|---|---|
| `PermResources` | `seed_data/PermResources.json` |
| `PermResourceOperations` | `seed_data/PermResourceOperations.json` |
| `SchedulerDiary` | `seed_data/SchedulerDiary.json` |

**Rules:**
- The `"data"` key holds a list of row dicts or a single dict.
- `org_code` is **not** required in the seed file — it is injected at generation time.
- Extra fields (e.g. `"description"`) beyond the model's declared fields are preserved in the `data JSONB` column.
- `"schema_name"` and `"table_name"` in the file are informational; the generator derives schema and table from `model_config`.
