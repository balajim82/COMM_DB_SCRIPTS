"""Generate INSERT DML scripts for entity data tables from seed JSON files.

Seed file convention (mirrors preconfigured_actualdata in the reference project):
    <SEED_DATA_PATH>/<entity_name>.json

Expected JSON format:
    {
        "data": [
            {"field1": "value1", "field2": "value2", ...},
            ...
        ],
        "schema_name": "SystemData",
        "table_name":  "PermResources"
    }

For each org_code from admin.Organizations:
  - org_code is injected into every seed row (matching upload_actual_data behaviour).
  - Structural PK/partition column values are extracted from the row.
  - The full row (all fields) is stored in the data JSONB column.
  - One idempotent upsert is emitted per (org_code x seed row).

Mirrors the upload path in seed_preconfigured_entities_for_org / upload_actual_data /
CogitoPgBackend.upload_data.
"""

import json
from pathlib import Path
from typing import Optional, Type

from pydantic import BaseModel

from config import settings
from core.model_inspector import ModelInfo, inspect_model


def _esc(s: str) -> str:
    """Escape single quotes for a PostgreSQL string literal."""
    return s.replace("'", "''")


def _load_seed_rows(entity_name: str, seed_data_path: Path) -> Optional[list[dict]]:
    """Load the data array from <seed_data_path>/<entity_name>.json.

    Returns the list of row dicts, or None when the file does not exist.
    Matches the file-loading logic in upload_actual_data:
      - Top-level key "data" holds a list or a single dict.
    """
    seed_file = seed_data_path / f"{entity_name}.json"
    if not seed_file.exists():
        return None

    with seed_file.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    data = payload.get("data", [])
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def generate_seed_data_inserts(
    model_cls: Type[BaseModel],
    org_codes: list[str],
    seed_data_path: Path,
) -> Optional[str]:
    """Return a SQL string of upsert statements built from the seed JSON file.

    Returns None when no seed file exists for the model's entity_name, so the
    caller can log a skip rather than write an empty file.

    Logic mirrors upload_actual_data + CogitoPgBackend.upload_data:
      1. Load seed rows from <seed_data_path>/<entity_name>.json.
      2. For each org_code, inject it into every row (row["org_code"] = org_code).
      3. Extract structural (PK/partition) column values from the row.
      4. Store the full row as the data JSONB payload.
      5. Emit one idempotent upsert per (org_code x row).
    """
    model_info: ModelInfo = inspect_model(model_cls)
    cfg = dict(getattr(model_cls, "model_config", {}))
    schema: str = cfg.get("entity_type", "public")
    entity_name: str = cfg.get("entity_name", model_info.table_name)

    seed_rows = _load_seed_rows(entity_name, seed_data_path)
    if seed_rows is None:
        return None  # No seed file — caller decides how to report this

    structural_cols = model_info.structural_columns
    pk_cols = model_info.pk_fields

    insert_col_list = (
        ", ".join(f'"{c.name}"' for c in structural_cols)
        + ', "data", "updated_at"'
    )
    conflict_col_list = ", ".join(f'"{c.name}"' for c in pk_cols)

    lines: list[str] = [
        "-- ============================================================",
        f"-- Seed data INSERTs for  : \"{schema}\".\"{entity_name}\"",
        f"-- Source model           : {model_cls.__name__}",
        f"-- Seed file              : {entity_name}.json  ({len(seed_rows)} rows)",
        f"-- Structural columns     : {', '.join(c.name for c in structural_cols)}",
        f"-- Organisations          : {len(org_codes)}",
        f"-- Total statements       : {len(org_codes) * len(seed_rows)}",
        "-- ============================================================",
        "",
        "BEGIN;",
        "",
    ]

    for org_code in org_codes:
        lines.append(f"-- org_code: {org_code} " + "-" * 40)
        lines.append("")

        for row in seed_rows:
            # Step 2: inject org_code into the row (mirrors upload_actual_data)
            full_row: dict = {**row, "org_code": org_code}

            # Step 3: extract structural column values from the row
            struct_values: list[str] = []
            for col in structural_cols:
                val = full_row.get(col.name)
                if val is None:
                    struct_values.append("NULL")
                else:
                    struct_values.append(f"'{_esc(str(val))}'")

            # Step 4: full row → data JSONB
            data_json = json.dumps(full_row, ensure_ascii=False)
            data_literal = f"'{_esc(data_json)}'::JSONB"

            all_values = struct_values + [data_literal, "NOW()"]
            values_str = ",\n     ".join(all_values)

            insert = (
                f"INSERT INTO \"{_esc(schema)}\".\"{_esc(entity_name)}\""
                f" ({insert_col_list})\n"
                f"VALUES\n"
                f"    ({values_str})"
            )
            if conflict_col_list:
                insert += (
                    f"\nON CONFLICT ({conflict_col_list}) DO UPDATE SET\n"
                    f'    "data"       = EXCLUDED."data",\n'
                    f'    "updated_at" = NOW();'
                )
            else:
                insert += ";"

            lines.append(insert)
            lines.append("")

    lines.extend(["COMMIT;", ""])
    return "\n".join(lines)


def write_seed_data_insert_script(
    model_cls: Type[BaseModel],
    org_codes: list[str],
) -> Optional[Path]:
    """Generate and persist the seed data INSERT script; returns the file path.

    Returns None when no seed file exists for the model (caller logs a skip).
    The seed data folder is read from settings.SEED_DATA_PATH.
    """
    seed_data_path = Path(settings.SEED_DATA_PATH)
    cfg = dict(getattr(model_cls, "model_config", {}))
    entity_name = cfg.get("entity_name", model_cls.__name__).lower()

    sql = generate_seed_data_inserts(model_cls, org_codes, seed_data_path)
    if sql is None:
        return None

    out_dir = Path(settings.SQL_OUTPUT_PATH) / "dml"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"seed_insert_{entity_name}.sql"
    out_path.write_text(sql, encoding="utf-8")
    return out_path
