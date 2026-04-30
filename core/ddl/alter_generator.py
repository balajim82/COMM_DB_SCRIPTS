"""Generate ALTER TABLE SQL scripts by diffing DB schema vs updated Pydantic model."""

from pathlib import Path
from typing import Optional

from config import settings
from core.db.connection import fetch_constraints, fetch_table_schema
from core.model_inspector import ColumnInfo, ModelInfo

# Maps PostgreSQL information_schema data_type values → canonical type tokens
# used to compare against our resolved PG types.
_NORMALIZE: dict[str, str] = {
    "bigint": "BIGINT",
    "integer": "BIGINT",
    "smallint": "BIGINT",
    "text": "TEXT",
    "character varying": "TEXT",
    "character": "TEXT",
    "boolean": "BOOLEAN",
    "jsonb": "JSONB",
    "json": "JSONB",
    "timestamp with time zone": "TIMESTAMP WITH TIME ZONE",
    "timestamp without time zone": "TIMESTAMP WITH TIME ZONE",
    "date": "DATE",
    "double precision": "DOUBLE PRECISION",
    "real": "DOUBLE PRECISION",
    "numeric": "NUMERIC",
    "uuid": "UUID",
    "bytea": "BYTEA",
}

_SYSTEM_COLS = {"data", "created_at", "updated_at"}


def _normalize(data_type: str) -> str:
    return _NORMALIZE.get(data_type.lower(), data_type.upper())


def _col_def_inline(col: ColumnInfo) -> str:
    null_str = " NOT NULL" if not col.is_nullable else ""
    return f"{col.pg_type}{null_str}"


def generate_alter_script(table_name: str, new_model: ModelInfo) -> str:
    """
    Fetch current schema from the DB, diff against *new_model*, and produce
    an ALTER TABLE script covering:

    - ADD COLUMN  – structural columns present in model but absent in DB
    - DROP COLUMN – structural columns present in DB but removed from model
    - ALTER COLUMN TYPE – type changes on existing structural columns
    - DROP + ADD data JSONB – unconditional rebuild so any model-level doc/
      default changes are captured; safe because data is schema-less
    """
    existing_rows = fetch_table_schema(table_name)
    if not existing_rows:
        return (
            f"-- ERROR: table '{table_name}' not found in information_schema.\n"
            f"-- Run generate-table first, or check the table name.\n"
        )

    existing: dict[str, dict] = {r["column_name"]: r for r in existing_rows}
    new_structural: dict[str, ColumnInfo] = {
        c.name: c for c in new_model.structural_columns
    }

    lines: list[str] = [
        "-- ============================================================",
        f"-- ALTER TABLE : {table_name}",
        f"-- Model       : {new_model.model_name}",
        "-- ============================================================",
        "",
    ]

    changes: list[str] = []

    # ── ADD new structural columns ───────────────────────────────────────
    for col_name, col in new_structural.items():
        if col_name not in existing:
            null_str = " NOT NULL" if not col.is_nullable else ""
            default_str = " DEFAULT NULL" if col.is_nullable else ""
            changes.append(
                f"ALTER TABLE {table_name}\n"
                f"    ADD COLUMN IF NOT EXISTS {col_name} {col.pg_type}{null_str}{default_str};"
            )

    # ── DROP removed structural columns ─────────────────────────────────
    for col_name in existing:
        if col_name in _SYSTEM_COLS:
            continue
        if col_name not in new_structural:
            changes.append(
                f"ALTER TABLE {table_name}\n"
                f"    DROP COLUMN IF EXISTS {col_name} CASCADE;"
            )

    # ── TYPE changes on existing structural columns ──────────────────────
    for col_name, col in new_structural.items():
        if col_name in existing:
            db_type = _normalize(existing[col_name]["data_type"])
            if db_type != col.pg_type:
                changes.append(
                    f"ALTER TABLE {table_name}\n"
                    f"    ALTER COLUMN {col_name}"
                    f" TYPE {col.pg_type}"
                    f" USING {col_name}::{col.pg_type};"
                )

    if changes:
        lines += changes
    else:
        lines.append("-- No structural column changes detected.")

    # ── Rebuild data JSONB column ────────────────────────────────────────
    # The data column is schemaless; we drop & recreate to reset its default
    # and clear any stale rows if needed (data migration handled separately).
    lines += [
        "",
        "-- ── Rebuild data JSONB column ──────────────────────────────────",
        "-- NOTE: This drops all existing JSONB data. Run DML migration",
        "--       scripts BEFORE executing this block if you need to",
        "--       preserve or reshape existing row data.",
        f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS data;",
        f"ALTER TABLE {table_name} ADD COLUMN data JSONB NOT NULL DEFAULT '{{}}';",
    ]

    # ── Nullability changes (nullable → NOT NULL requires backfill) ──────
    for col_name, col in new_structural.items():
        if col_name in existing:
            was_nullable = existing[col_name]["is_nullable"].upper() == "YES"
            if was_nullable and not col.is_nullable:
                lines += [
                    "",
                    f"-- WARNING: {col_name} changed from NULL → NOT NULL.",
                    f"-- Backfill nulls BEFORE applying the constraint:",
                    f"-- UPDATE {table_name} SET {col_name} = <value> WHERE {col_name} IS NULL;",
                    f"ALTER TABLE {table_name} ALTER COLUMN {col_name} SET NOT NULL;",
                ]

    return "\n".join(lines) + "\n"


def write_alter_script(table_name: str, new_model: ModelInfo) -> Path:
    """Generate and persist ALTER TABLE script; returns the file path."""
    sql = generate_alter_script(table_name, new_model)
    out_dir = Path(settings.SQL_OUTPUT_PATH) / "ddl"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"alter_{table_name.lower()}.sql"
    out_path.write_text(sql, encoding="utf-8")
    return out_path
