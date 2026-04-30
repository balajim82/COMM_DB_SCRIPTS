"""Generate INSERT DML scripts for catalog.MetaDataDictionary.

One INSERT per (model × org_code) pair, using ON CONFLICT … DO UPDATE so the
script is safely re-runnable (idempotent upsert).

Mirrors the upload path in seed_preconfigured_entities_for_org:
  - db_name   = org_code  (each org has its own logical database in CogitoPg)
  - metadata  = full Metadata JSON built by metadata_builder.build_metadata_dict()
"""

import json
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from config import settings
from core.metadata_builder import build_metadata_dict


def _esc(s: str) -> str:
    """Escape single quotes for a PostgreSQL string literal."""
    return s.replace("'", "''")


def generate_metadata_inserts(model_cls: Type[BaseModel], org_codes: list[str]) -> str:
    """Return a SQL string of upsert statements for catalog.MetaDataDictionary.

    One statement per org_code; wraps the whole script in BEGIN / COMMIT.
    """
    cfg = dict(getattr(model_cls, "model_config", {}))
    entity_name = cfg["entity_name"]
    meta_lake_code = cfg["meta_lake_code"]
    entity_type = cfg["entity_type"]

    lines: list[str] = [
        "-- ============================================================",
        f"-- MetaDataDictionary upserts : {entity_name}",
        f"-- Source model               : {model_cls.__name__}",
        f"-- Organisations              : {len(org_codes)}",
        "-- ============================================================",
        "",
        "BEGIN;",
        "",
    ]

    for org_code in org_codes:
        metadata_dict = build_metadata_dict(model_cls, org_code)
        metadata_json = json.dumps(metadata_dict, ensure_ascii=False)
        entity_desc = _esc(metadata_dict["entity_description"])

        lines.append(f"-- org_code: {org_code}")
        lines.append(
            f"INSERT INTO catalog.\"MetaDataDictionary\"\n"
            f"    (db_name, org_code, meta_lake_code, entity_name,\n"
            f"     entity_type, entity_description, metadata, updated_at)\n"
            f"VALUES\n"
            f"    ('{_esc(org_code)}',\n"
            f"     '{_esc(org_code)}',\n"
            f"     '{_esc(meta_lake_code)}',\n"
            f"     '{_esc(entity_name)}',\n"
            f"     '{_esc(entity_type)}',\n"
            f"     '{entity_desc}',\n"
            f"     '{_esc(metadata_json)}'::JSONB,\n"
            f"     NOW())\n"
            f"ON CONFLICT (db_name, entity_name) DO UPDATE SET\n"
            f"    metadata           = EXCLUDED.metadata,\n"
            f"    org_code           = EXCLUDED.org_code,\n"
            f"    meta_lake_code     = EXCLUDED.meta_lake_code,\n"
            f"    entity_type        = EXCLUDED.entity_type,\n"
            f"    entity_description = EXCLUDED.entity_description,\n"
            f"    updated_at         = NOW();"
        )
        lines.append("")

    lines.extend(["COMMIT;", ""])
    return "\n".join(lines)


def write_metadata_insert_script(
    model_cls: Type[BaseModel], org_codes: list[str]
) -> Path:
    """Generate and persist the MetaDataDictionary INSERT script; returns file path."""
    cfg = dict(getattr(model_cls, "model_config", {}))
    entity_name = cfg.get("entity_name", model_cls.__name__).lower()

    sql = generate_metadata_inserts(model_cls, org_codes)
    out_dir = Path(settings.SQL_OUTPUT_PATH) / "dml"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"metadata_insert_{entity_name}.sql"
    out_path.write_text(sql, encoding="utf-8")
    return out_path
