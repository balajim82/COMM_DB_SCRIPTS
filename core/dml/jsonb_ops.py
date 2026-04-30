"""Generate PostgreSQL DML statements for JSONB data column operations.

All functions return a SQL string ready to be written to a file or executed.
None of them touch the database directly.

Supported operations
--------------------
add_field        – merge a new key into data (skips rows that already have it)
remove_field     – remove a key from data
update_field     – overwrite a key (supports dot-delimited nested paths)
add_array_element – append an element to a JSONB array key
rename_field     – rename a key inside data
"""

import json
from pathlib import Path
from typing import Any, Optional

from config import settings


# ── Internal helpers ─────────────────────────────────────────────────────────

def _pg_jsonb_literal(value: Any) -> str:
    """Encode a Python value as a PostgreSQL JSONB literal string."""
    return f"'{json.dumps(value)}'::jsonb"


def _jsonb_path_literal(field_path: list[str]) -> str:
    """Encode a list of path segments as a PostgreSQL text-array literal.

    Example: ['address', 'city'] → '{address,city}'
    """
    inner = ",".join(field_path)
    return "'{" + inner + "}'"


def _where(condition: Optional[str]) -> str:
    return f"\nWHERE {condition}" if condition else ""


# ── Public generators ────────────────────────────────────────────────────────

def generate_add_field(
    table_name: str,
    field_name: str,
    default_value: Any = None,
    condition: Optional[str] = None,
) -> str:
    """INSERT a new key into the data JSONB, skipping rows that already have it.

    Uses the || merge operator so existing data is untouched.
    """
    # Build literal: '{"field": <value>}'::jsonb
    literal = f"'{json.dumps({field_name: default_value})}'::jsonb"
    exists_check = f"data ? '{field_name}'"
    where_parts = [f"NOT ({exists_check})"]
    if condition:
        where_parts.append(f"({condition})")

    return (
        f"-- DML: add field '{field_name}' to {table_name}.data\n"
        f"UPDATE {table_name}\n"
        f"SET    data = data || {literal}\n"
        f"WHERE  {' AND '.join(where_parts)};"
    )


def generate_remove_field(
    table_name: str,
    field_name: str,
    condition: Optional[str] = None,
) -> str:
    """Remove a top-level key from the data JSONB using the - operator."""
    return (
        f"-- DML: remove field '{field_name}' from {table_name}.data\n"
        f"UPDATE {table_name}\n"
        f"SET    data = data - '{field_name}'"
        f"{_where(condition)};"
    )


def generate_update_field(
    table_name: str,
    field_path: list[str],
    new_value: Any,
    create_missing: bool = True,
    condition: Optional[str] = None,
) -> str:
    """Overwrite a key (or nested key) in the data JSONB using jsonb_set.

    field_path – e.g. ['status'] or ['address', 'city'] for nested fields.
    create_missing – when True, the path is created if it doesn't exist yet.
    """
    path_lit = _jsonb_path_literal(field_path)
    value_lit = _pg_jsonb_literal(new_value)
    create_flag = "true" if create_missing else "false"
    display = ".".join(field_path)

    return (
        f"-- DML: update field '{display}' in {table_name}.data\n"
        f"UPDATE {table_name}\n"
        f"SET    data = jsonb_set(data, {path_lit}, {value_lit}, {create_flag})"
        f"{_where(condition)};"
    )


def generate_add_array_element(
    table_name: str,
    array_field: str,
    element: Any,
    condition: Optional[str] = None,
) -> str:
    """Append *element* to an existing JSONB array key.

    If the key is absent the array is initialised as [element].
    Uses COALESCE so it is safe whether or not the field exists yet.
    """
    elem_lit = _pg_jsonb_literal(element)
    path_lit = _jsonb_path_literal([array_field])

    return (
        f"-- DML: append element to array '{array_field}' in {table_name}.data\n"
        f"UPDATE {table_name}\n"
        f"SET    data = jsonb_set(\n"
        f"           data,\n"
        f"           {path_lit},\n"
        f"           COALESCE(data->'{array_field}', '[]'::jsonb) || {elem_lit}\n"
        f"       )"
        f"{_where(condition)};"
    )


def generate_rename_field(
    table_name: str,
    old_name: str,
    new_name: str,
    condition: Optional[str] = None,
) -> str:
    """Rename a top-level key: copy value under new_name then remove old_name."""
    where_parts = [f"data ? '{old_name}'"]
    if condition:
        where_parts.append(f"({condition})")

    return (
        f"-- DML: rename field '{old_name}' -> '{new_name}' in {table_name}.data\n"
        f"UPDATE {table_name}\n"
        f"SET    data = (data - '{old_name}') || jsonb_build_object('{new_name}', data->'{old_name}')\n"
        f"WHERE  {' AND '.join(where_parts)};"
    )


def generate_batch(table_name: str, statements: list[str]) -> str:
    """Wrap multiple DML statements in a BEGIN/COMMIT transaction block."""
    body = "\n\n".join(statements)
    return (
        f"-- ── Batch DML for {table_name} ──────────────────────────────────\n"
        f"BEGIN;\n\n"
        f"{body}\n\n"
        f"COMMIT;\n"
    )


# ── File writer ───────────────────────────────────────────────────────────────

def write_dml_script(
    table_name: str,
    statements: list[str],
    operation_tag: str,
    wrap_transaction: bool = True,
) -> Path:
    """Persist *statements* to generated_sql/dml/<table>_<tag>.sql."""
    content = generate_batch(table_name, statements) if wrap_transaction else "\n\n".join(statements)
    out_dir = Path(settings.SQL_OUTPUT_PATH) / "dml"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"dml_{table_name.lower()}_{operation_tag}.sql"
    out_path.write_text(content, encoding="utf-8")
    return out_path
