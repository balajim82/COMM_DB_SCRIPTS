#!/usr/bin/env python3
"""commverse-db DML runner — util_deep_merge_jsonb wrapper.

Generates and optionally executes DO $$ ... END $$ blocks that call
the util_deep_merge_jsonb stored function.

Usage
-----
    python dml.py --update              # generate SQL for all update operations
    python dml.py --update --apply      # generate + execute against the DB
    python dml.py --insert              # (coming soon)
    python dml.py --delete              # (coming soon)

Each entry in OPERATIONS must have:

    {
        "op"             : "update",           # operation type
        "schema_name"    : "SystemData",       # PostgreSQL schema
        "table_name"     : "SchedulerDiary",   # table name
        "p_column_name"  : "data",             # JSONB column (default: "data")
        "p_new_json"     : { ... } or "...",   # dict or raw JSON string
        "p_append_keys"  : { ... } or "...",   # keys to append (default: {})
        "p_where_columns": [],                 # filter column names
        "p_where_values" : [],                 # filter column values
    }
"""

import argparse
import json
from pathlib import Path

from config import settings

# =============================================================================
#  CONFIGURE OPERATIONS HERE
# =============================================================================

OPERATIONS: list[dict] = [
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
]

# =============================================================================


# ── SQL builder ───────────────────────────────────────────────────────────────


def _to_json_str(value) -> str:
    """Pretty-print a value as JSON, accepting both dict and raw JSON string."""
    if isinstance(value, str):
        return json.dumps(json.loads(value), indent=2)
    return json.dumps(value, indent=2)


def _sql_escape(s: str) -> str:
    """Escape single quotes for embedding inside a SQL string literal."""
    return s.replace("'", "''")


def _format_json_param(value, param_indent: int = 8) -> str:
    """Return a SQL string literal for a JSON value with correct line alignment.

    Single-line JSON  ->  '{"key": "val"}'
    Multi-line JSON   ->  '{
                              "key": "val"
                          }'
    Every line after the first is prefixed with *param_indent* spaces so the
    content aligns visually with the opening quote in the SQL block.
    """
    raw = _sql_escape(_to_json_str(value))
    lines = raw.splitlines()

    if len(lines) <= 1:
        return f"'{raw}'"

    pad = " " * param_indent
    aligned = [lines[0]]  # opening '{' stays flush
    for line in lines[1:-1]:
        aligned.append(pad + line)  # inner lines indented
    aligned.append(pad + lines[-1])  # closing '}' indented

    return "'" + "\n".join(aligned) + "'"


def _pg_text_array(values: list) -> str:
    """Render a Python list as a PostgreSQL text[] literal.

    []          -> ARRAY[]::text[]
    ['a', 'b']  -> ARRAY['a', 'b']::text[]
    """
    if not values:
        return "ARRAY[]::text[]"
    items = ", ".join(f"'{_sql_escape(str(v))}'" for v in values)
    return f"ARRAY[{items}]::text[]"


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


def _run_insert() -> None:
    """Placeholder — insert support coming soon."""
    print("commverse-db DML  |  op=insert")
    print("Insert operations are not yet implemented.")


def _run_delete() -> None:
    """Placeholder — delete support coming soon."""
    print("commverse-db DML  |  op=delete")
    print("Delete operations are not yet implemented.")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="commverse-db-dml",
        description="Generate util_deep_merge_jsonb SQL blocks (reads .env)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python dml.py --update              generate SQL for all update ops\n"
            "  python dml.py --update --apply      generate + execute against the DB\n"
            "  python dml.py --insert              (coming soon)\n"
            "  python dml.py --delete              (coming soon)\n"
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
        help="Run all 'delete' operations (coming soon)",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the generated SQL against the database configured in .env",
    )

    args = parser.parse_args()

    if args.update:
        _run_update(apply=args.apply)
    elif args.insert:
        _run_insert()
    elif args.delete:
        _run_delete()


if __name__ == "__main__":
    main()
