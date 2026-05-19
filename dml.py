#!/usr/bin/env python3
"""commverse-db DML runner.

Generates SQL for update, insert, and delete operations against entity tables.

Update operations use the util_deep_merge_jsonb stored function.
Delete operations derive the WHERE clause automatically from the Pydantic
model's primary_keys (model_config["primary_keys"]) so the caller only needs
to supply the PK values — column names are never hardcoded.

Usage
-----
    python dml.py --update              # generate SQL for all update operations
    python dml.py --update --apply      # generate + execute against the DB
    python dml.py --delete              # generate DELETE scripts from model PKs
    python dml.py --delete --apply      # generate + execute DELETE scripts
    python dml.py --insert              # (coming soon)

OPERATIONS format
-----------------
Update:
    {
        "op"             : "update",
        "schema_name"    : "SystemData",
        "table_name"     : "SchedulerDiary",
        "p_column_name"  : "data",
        "p_new_json"     : { ... } or "...",
        "p_append_keys"  : { ... } or "...",
        "p_where_columns": [],
        "p_where_values" : [],
    }

Delete:
    {
        "op"        : "delete",
        "table_name": "PermResources",   # must match model_config["entity_name"]
        "pk_values" : {                  # one entry per primary key field
            "org_code"     : "Admin",
            "resource_code": "DATA_CATALOG",
        },
        "schema_name": "SystemData",     # optional — derived from model if absent
    }
"""

import argparse
import importlib
import inspect
import json
from pathlib import Path
from typing import Optional, Type

from pydantic import BaseModel

from config import settings

# =============================================================================
#  CONFIGURE OPERATIONS HERE
# =============================================================================

OPERATIONS: list[dict] = [
    # ── Update example ────────────────────────────────────────────────────────
    {
        "op": "update",
        "schema_name": "SystemData",
        "table_name": "SchedulerDiary",
        "p_column_name": "data",
        "p_new_json": {"suri_new_trade": "RamaTrade"},
        "p_append_keys": {},
        "p_where_columns": ["diary_record_id"],
        "p_where_values": ["000c2ef5-4d61-4aa6-bc0d-12fbda55678f"],
    },
    # ── Delete example ────────────────────────────────────────────────────────
    # Primary keys (org_code, resource_code, operation_code) are derived
    # automatically from PermResourceOperationModel.model_config["primary_keys"]
    # — only the values need to be supplied here.
    {
        "op": "delete",
        "table_name": "PermResourceOperations",
        "pk_values": {
            "org_code": "Admin",
            "resource_code": "DATA_CATALOG",
            "operation_code": "DELETE",
        },
    },
]

# =============================================================================


# ── Model discovery ───────────────────────────────────────────────────────────

_MODELS_DIR = Path(__file__).parent / "models"


def _find_model_for_entity(entity_name: str) -> Optional[Type[BaseModel]]:
    """Return the first Pydantic model whose model_config["entity_name"] matches.

    Scans every *.py file in models/ (excluding __init__.py and similar).
    Returns None if no matching model is found.
    """
    for py_file in sorted(_MODELS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"models.{py_file.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                obj is not BaseModel
                and issubclass(obj, BaseModel)
                and obj.__module__ == module_name
                and obj.model_fields
            ):
                cfg = dict(getattr(obj, "model_config", {}))
                if cfg.get("entity_name") == entity_name:
                    return obj
    return None


# ── SQL helpers ───────────────────────────────────────────────────────────────


def _to_json_str(value) -> str:
    """Pretty-print a value as JSON, accepting both dict and raw JSON string."""
    if isinstance(value, str):
        return json.dumps(json.loads(value), indent=2)
    return json.dumps(value, indent=2)


def _sql_escape(s: str) -> str:
    """Escape single quotes for embedding inside a SQL string literal."""
    return s.replace("'", "''")


def _format_json_param(value, param_indent: int = 8) -> str:
    """Return a SQL string literal for a JSON value with correct line alignment."""
    raw = _sql_escape(_to_json_str(value))
    lines = raw.splitlines()
    if len(lines) <= 1:
        return f"'{raw}'"
    pad = " " * param_indent
    aligned = [lines[0]]
    for line in lines[1:-1]:
        aligned.append(pad + line)
    aligned.append(pad + lines[-1])
    return "'" + "\n".join(aligned) + "'"


def _pg_text_array(values: list) -> str:
    """Render a Python list as a PostgreSQL text[] literal."""
    if not values:
        return "ARRAY[]::text[]"
    items = ", ".join(f"'{_sql_escape(str(v))}'" for v in values)
    return f"ARRAY[{items}]::text[]"


# ── SQL generators ────────────────────────────────────────────────────────────


def generate_deep_merge_sql(op: dict) -> str:
    """Build the DO $$ PERFORM util_deep_merge_jsonb(...) END $$; block."""
    operation = op["op"]
    schema_name = op["schema_name"]
    table_name = op["table_name"]
    p_column_name = op.get("p_column_name", "data")
    p_new_json = _format_json_param(op["p_new_json"])
    p_append_keys = _format_json_param(op.get("p_append_keys", {}))
    p_where_cols = _pg_text_array(op.get("p_where_columns", []))
    p_where_vals = _pg_text_array(op.get("p_where_values", []))

    return (
        f"DO $$\n"
        f"BEGIN\n"
        f"    PERFORM util_deep_merge_jsonb(\n"
        f"        '{operation}',\n"
        f"        '{schema_name}',\n"
        f"        '{table_name}',\n"
        f"        '{p_column_name}',\n"
        f"        {p_new_json},\n"
        f"        {p_append_keys},\n"
        f"        {p_where_cols},\n"
        f"        {p_where_vals}\n"
        f"    );\n"
        f"END $$;"
    )


def generate_delete_sql(op: dict, model_cls: Type[BaseModel]) -> str:
    """Generate a DELETE statement whose WHERE clause is built from the model's PKs.

    Primary key column names are read from model_config["primary_keys"].
    The caller supplies the corresponding values via op["pk_values"].

    Raises ValueError when:
      - model_config has no primary_keys defined
      - a required PK value is missing from op["pk_values"]
    """
    cfg = dict(getattr(model_cls, "model_config", {}))
    pk_fields: list[str] = cfg.get("primary_keys", [])

    if not pk_fields:
        raise ValueError(
            f"Model '{model_cls.__name__}' has no primary_keys in model_config. "
            "Add primary_keys to generate a DELETE statement."
        )

    schema_name: str = op.get("schema_name") or cfg.get("entity_type", "public")
    table_name: str = op["table_name"]
    pk_values: dict = op.get("pk_values", {})

    # Validate that every PK has a supplied value
    missing = [pk for pk in pk_fields if pk not in pk_values]
    if missing:
        raise ValueError(
            f"pk_values is missing entries for primary key(s): {missing}. "
            f"Required keys: {pk_fields}"
        )

    where_parts = [
        f"\"{pk}\" = '{_sql_escape(str(pk_values[pk]))}'" for pk in pk_fields
    ]
    where_clause = "\n  AND ".join(where_parts)
    pk_names_str = ", ".join(pk_fields)

    return (
        f'-- DELETE from "{schema_name}"."{table_name}"\n'
        f"-- Primary keys (from {model_cls.__name__}): {pk_names_str}\n"
        f'DELETE FROM "{schema_name}"."{table_name}"\n'
        f"WHERE {where_clause};"
    )


# ── File writer ───────────────────────────────────────────────────────────────


def _write_sql_file(op: dict, sql: str) -> Path:
    table = op["table_name"].lower()
    op_tag = op["op"]
    out_dir = Path(settings.SQL_OUTPUT_PATH) / "dml"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"dml_{table}_{op_tag}.sql"
    out_path.write_text(sql, encoding="utf-8")
    return out_path


# ── Runners ───────────────────────────────────────────────────────────────────


def _run_update(apply: bool) -> None:
    """Execute all OPERATIONS where op == 'update'."""
    ops = [o for o in OPERATIONS if o.get("op", "").lower() == "update"]
    if not ops:
        print("No 'update' operations found in OPERATIONS.")
        return

    print(f"commverse-db DML  |  op=update  apply={apply}")
    print(f"{len(ops)} operation(s)")
    print("-" * 60)

    for i, op in enumerate(ops, 1):
        try:
            sql = generate_deep_merge_sql(op)
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            print(f"[{i}] ERROR generating SQL: {exc}\n")
            continue

        out_path = _write_sql_file(op, sql)

        print(
            f"[{i}] UPDATE  {op['schema_name']}.{op['table_name']}.{op.get('p_column_name', 'data')}"
        )
        print(f"     file  : {out_path}")
        print()
        print(sql)
        print()

        if apply:
            from core.db.connection import execute_sql

            try:
                execute_sql(sql)
                print(f"     apply : OK\n")
            except Exception as exc:
                print(f"     apply : FAILED — {exc}\n")

    print("-" * 60)


def _run_delete(apply: bool) -> None:
    """Execute all OPERATIONS where op == 'delete'.

    For each delete operation:
      1. Locates the Pydantic model whose entity_name matches op["table_name"].
      2. Reads primary_keys from model_config — these become the WHERE columns.
      3. Builds a DELETE statement using the values in op["pk_values"].
      4. Writes the SQL file and optionally executes it.
    """
    ops = [o for o in OPERATIONS if o.get("op", "").lower() == "delete"]
    if not ops:
        print("No 'delete' operations found in OPERATIONS.")
        return

    print(f"commverse-db DML  |  op=delete  apply={apply}")
    print(f"{len(ops)} operation(s)")
    print("-" * 60)

    for i, op in enumerate(ops, 1):
        table_name = op.get("table_name", "")

        # Step 1: find the matching model
        model_cls = _find_model_for_entity(table_name)
        if model_cls is None:
            print(
                f"[{i}] ERROR: no model found with entity_name='{table_name}' in models/\n"
                f'     Add or check model_config["entity_name"] in your model file.\n'
            )
            continue

        # Step 2 & 3: generate DELETE SQL from model PKs + supplied values
        try:
            sql = generate_delete_sql(op, model_cls)
        except (KeyError, ValueError) as exc:
            print(f"[{i}] ERROR generating DELETE SQL: {exc}\n")
            continue

        out_path = _write_sql_file(op, sql)

        cfg = dict(getattr(model_cls, "model_config", {}))
        schema_name = op.get("schema_name") or cfg.get("entity_type", "public")
        pk_names_str = ", ".join(cfg.get("primary_keys", []))

        print(f'[{i}] DELETE  "{schema_name}"."{table_name}"')
        print(f"     model  : {model_cls.__name__}")
        print(f"     PKs    : {pk_names_str}")
        print(f"     values : {op.get('pk_values', {})}")
        print(f"     file   : {out_path}")
        print()
        print(sql)
        print()

        if apply:
            from core.db.connection import execute_sql

            try:
                execute_sql(sql)
                print(f"     apply : OK\n")
            except Exception as exc:
                print(f"     apply : FAILED — {exc}\n")

    print("-" * 60)


def _run_insert() -> None:
    """Placeholder — insert support coming soon."""
    print("commverse-db DML  |  op=insert")
    print("Insert operations are not yet implemented.")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="commverse-db-dml",
        description="Generate DML SQL from Pydantic model definitions (reads .env)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python dml.py --update              generate SQL for all update ops\n"
            "  python dml.py --update --apply      generate + execute against the DB\n"
            "  python dml.py --delete              generate DELETE scripts from model PKs\n"
            "  python dml.py --delete --apply      generate + execute DELETE scripts\n"
            "  python dml.py --insert              (coming soon)\n"
        ),
    )

    op_group = parser.add_mutually_exclusive_group(required=True)
    op_group.add_argument(
        "--update",
        action="store_true",
        help="Run all 'update' operations defined in OPERATIONS",
    )
    op_group.add_argument(
        "--insert",
        action="store_true",
        help="Run all 'insert' operations (coming soon)",
    )
    op_group.add_argument(
        "--delete",
        action="store_true",
        help=(
            "Run all 'delete' operations — WHERE clause is derived from "
            "the matching Pydantic model's primary_keys"
        ),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the generated SQL against the database configured in .env",
    )

    args = parser.parse_args()

    if args.update:
        _run_update(apply=args.apply)
    elif args.delete:
        _run_delete(apply=args.apply)
    elif args.insert:
        _run_insert()


if __name__ == "__main__":
    main()
