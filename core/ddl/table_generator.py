"""Generate CREATE TABLE SQL scripts from Pydantic ModelInfo."""

import json
from pathlib import Path

from config import settings
from core.model_inspector import ModelInfo


_COL_WIDTH = 36   # column-name alignment width


def _col_def(name: str, pg_type: str, nullable: bool, default: str = "") -> str:
    null_str = "" if not nullable else " NULL"
    not_null_str = " NOT NULL" if not nullable else ""
    default_str = f" DEFAULT {default}" if default else ""
    return f"    {name:<{_COL_WIDTH}} {pg_type}{not_null_str}{null_str}{default_str}"


def generate_create_table(model_info: ModelInfo) -> str:
    table = model_info.table_name
    tl = table.lower()

    parts: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────────
    parts.append(f"-- ============================================================")
    parts.append(f"-- Table       : {table}")
    parts.append(f"-- Model       : {model_info.model_name}")
    parts.append(f"-- PK          : {', '.join(c.name for c in model_info.pk_fields) or '(none)'}")
    parts.append(f"-- Partition   : {', '.join(c.name for c in model_info.partition_fields) or '(none)'}")
    if model_info.fk_fields:
        parts.append(f"-- FK          : {', '.join(c.name for c in model_info.fk_fields)}")
    for k, v in model_info.meta.items():
        parts.append(f"-- {k:<12}: {v}")
    parts.append(f"-- Fields      : {', '.join(f.name for f in model_info.all_fields)}")
    parts.append(f"-- ============================================================")
    parts.append(f"CREATE TABLE IF NOT EXISTS {table}")
    parts.append("(")

    col_defs: list[str] = []

    # ── Structural columns (PK / FK / Partition) ─────────────────────────
    for col in model_info.structural_columns:
        col_defs.append(_col_def(col.name, col.pg_type, col.is_nullable))

    # ── data JSONB (stores all model fields) ─────────────────────────────
    col_defs.append(_col_def("data", "JSONB", False, "'{}'"))

    # ── Audit columns ────────────────────────────────────────────────────
    col_defs.append(_col_def("created_at", "TIMESTAMP WITH TIME ZONE", False, "NOW()"))
    col_defs.append(_col_def("updated_at", "TIMESTAMP WITH TIME ZONE", False, "NOW()"))

    # ── Primary key constraint ───────────────────────────────────────────
    if model_info.pk_fields:
        pk_cols = ", ".join(c.name for c in model_info.pk_fields)
        col_defs.append(f"    CONSTRAINT pk_{tl} PRIMARY KEY ({pk_cols})")

    # ── Foreign key constraints ──────────────────────────────────────────
    for fk in model_info.fk_fields:
        ref = fk.fk_reference or ""
        ref_parts = ref.rsplit(".", 1)
        ref_table = ref_parts[0] if ref_parts else ref
        ref_col = ref_parts[1] if len(ref_parts) == 2 else "id"
        col_defs.append(
            f"    CONSTRAINT fk_{tl}_{fk.name}"
            f" FOREIGN KEY ({fk.name})"
            f" REFERENCES {ref_table}({ref_col})"
        )

    parts.append(",\n".join(col_defs))

    # ── Partition clause ─────────────────────────────────────────────────
    if model_info.partition_fields:
        pf = model_info.partition_fields[0]
        ptype = (
            "RANGE"
            if ("TIMESTAMP" in pf.pg_type or "DATE" in pf.pg_type)
            else "HASH"
        )
        parts.append(f") PARTITION BY {ptype} ({pf.name});")
    else:
        parts.append(");")

    # ── Inline comment: full model schema ────────────────────────────────
    schema_comment = json.dumps(
        {c.name: c.pg_type for c in model_info.all_fields}, indent=4
    )
    parts.append(
        "\n-- All model fields stored in data (JSONB):\n"
        + "\n".join(f"--   {ln}" for ln in schema_comment.splitlines())
    )

    return "\n".join(parts)


def write_create_table_script(model_info: ModelInfo) -> Path:
    """Generate and persist CREATE TABLE script; returns the file path."""
    sql = generate_create_table(model_info)
    out_dir = Path(settings.SQL_OUTPUT_PATH) / "ddl"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"create_{model_info.table_name.lower()}.sql"
    out_path.write_text(sql, encoding="utf-8")
    return out_path
