#!/usr/bin/env python3
"""commverse-db DDL / DML runner.

Scans the models/ directory, discovers every Pydantic BaseModel subclass,
and generates SQL scripts automatically.  DB credentials are read from .env.

Commands
--------
    python main.py --table_generate      # CREATE TABLE scripts  -> generated_sql/ddl/
    python main.py --metadata_generate   # MetaDataDictionary INSERT scripts -> generated_sql/dml/
    python main.py --seed_data_insert    # Seed data INSERT scripts -> generated_sql/dml/

Legacy flags (still supported)
-------------------------------
    python main.py --apply   # generate + execute CREATE TABLE scripts
    python main.py --alter   # generate ALTER TABLE scripts (diff vs live DB)
"""

import argparse
import importlib
import inspect
import sys
from pathlib import Path
from typing import Type

from pydantic import BaseModel

MODELS_DIR = Path(__file__).parent / "models"


# ── Model discovery ───────────────────────────────────────────────────────────


def discover_models() -> list[tuple[str, Type[BaseModel]]]:
    """Return (dotted_path, class) for every BaseModel subclass in models/."""
    found: list[tuple[str, Type[BaseModel]]] = []

    for py_file in sorted(MODELS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"models.{py_file.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            print(f"  [WARN] Could not import {module_name}: {exc}")
            continue

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                obj is not BaseModel
                and issubclass(obj, BaseModel)
                and obj.__module__ == module_name
                and obj.model_fields
            ):
                found.append((f"{module_name}.{name}", obj))

    return found


# ── --table_generate ──────────────────────────────────────────────────────────


def run_table_generate(apply: bool = False, alter: bool = False) -> None:
    """Generate CREATE TABLE (or ALTER TABLE) DDL scripts for all discovered models.

    Writes files to generated_sql/ddl/.
    Optionally executes them against the database when apply=True.
    """
    from core.model_inspector import inspect_model
    from core.ddl.table_generator import write_create_table_script
    from core.ddl.alter_generator import write_alter_script

    models = discover_models()
    if not models:
        print("No Pydantic models found in models/")
        return

    mode = "ALTER" if alter else "CREATE"
    print(f"commverse-db  |  mode={mode}  apply={apply}")
    print(f"Found {len(models)} model(s)\n")
    print("-" * 60)

    for dotted, model_cls in models:
        model_info = inspect_model(model_cls)
        table = model_info.table_name

        try:
            out_path = (
                write_alter_script(table, model_info)
                if alter
                else write_create_table_script(model_info)
            )
        except Exception as exc:
            print(f"[ERROR] {model_cls.__name__}: script generation failed — {exc}")
            continue

        print(f"[{mode}] {model_cls.__name__:<30} => {table}")
        print(f"        file : {out_path}")

        if apply:
            from core.db.connection import execute_sql

            sql = out_path.read_text(encoding="utf-8")
            try:
                execute_sql(sql)
                print(f"        apply: OK")
            except Exception as exc:
                print(f"        apply: FAILED — {exc}")

        print()

    print("-" * 60)
    print(f"Scripts written to: {Path('generated_sql').resolve()}")


# ── --metadata_generate ───────────────────────────────────────────────────────


def run_metadata_generate() -> None:
    """Generate INSERT DML scripts for catalog.MetaDataDictionary.

    For every discovered model × every organisation code fetched from
    admin."Organizations":
      - Builds the Metadata JSON using build_metadata_dict() (mirrors
        seed_preconfigured_entities_for_org / Metadata.from_pydantic_model).
      - Writes one SQL file per model to generated_sql/dml/metadata_insert_<entity>.sql.

    Requires a database connection configured in .env.
    """
    from core.org_fetcher import fetch_org_codes
    from core.dml.metadata_generator import write_metadata_insert_script

    models = discover_models()
    if not models:
        print("No Pydantic models found in models/")
        return

    print("commverse-db  |  mode=METADATA_GENERATE")
    print(f"Found {len(models)} model(s)")

    print('Fetching organisation codes from admin."Organizations" …')
    try:
        org_codes = ["PT03"]  # fetch_org_codes()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    if not org_codes:
        print("[WARN] No organisation codes found — scripts will be empty.")

    print(f"Organisations : {org_codes}\n")
    print("-" * 60)

    for dotted, model_cls in models:
        try:
            out_path = write_metadata_insert_script(model_cls, org_codes)
        except Exception as exc:
            print(
                f"[ERROR] {model_cls.__name__}: metadata script generation failed — {exc}"
            )
            continue

        cfg = dict(getattr(model_cls, "model_config", {}))
        entity_name = cfg.get("entity_name", model_cls.__name__)
        print(f"[METADATA] {model_cls.__name__:<30} => {entity_name}")
        print(f"           file : {out_path}")
        print()

    print("-" * 60)
    print(f"Scripts written to: {Path('generated_sql/dml').resolve()}")


# ── --seed_data_insert ────────────────────────────────────────────────────────


def run_seed_data_insert() -> None:
    """Generate INSERT DML scripts for entity data tables from seed JSON files.

    For every discovered model × every organisation code:
      - Looks for a seed file at SEED_DATA_PATH/<entity_name>.json.
      - If found, injects org_code into every seed row and generates real
        upsert statements targeting the entity table
        (schema = entity_type, table = entity_name from model_config).
      - Skips models with no matching seed file (prints a warning).
      - Writes one SQL file per model to generated_sql/dml/seed_insert_<entity>.sql.

    Seed file format:
        {"data": [...rows], "schema_name": "SystemData", "table_name": "PermResources"}

    Mirrors the upload_actual_data / CogitoPgBackend.upload_data pattern from
    seed_preconfigured_entities_for_org.
    """
    from core.org_fetcher import fetch_org_codes
    from core.dml.table_insert_generator import write_seed_data_insert_script
    from config import settings

    models = discover_models()
    if not models:
        print("No Pydantic models found in models/")
        return

    print("commverse-db  |  mode=SEED_DATA_INSERT")
    print(f"Found {len(models)} model(s)")
    print(f"Seed data path : {settings.SEED_DATA_PATH}")

    print('Fetching organisation codes from admin."Organizations" ...')
    try:
        org_codes = ["PT03"]  # fetch_org_codes()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    if not org_codes:
        print("[WARN] No organisation codes found — scripts will be empty.")

    print(f"Organisations : {org_codes}\n")
    print("-" * 60)

    for dotted, model_cls in models:
        cfg = dict(getattr(model_cls, "model_config", {}))
        entity_name = cfg.get("entity_name", model_cls.__name__)
        entity_type = cfg.get("entity_type", "public")

        try:
            out_path = write_seed_data_insert_script(model_cls, org_codes)
        except Exception as exc:
            print(
                f"[ERROR] {model_cls.__name__}: seed-insert script generation failed — {exc}"
            )
            continue

        if out_path is None:
            print(
                f"[SKIP]   {model_cls.__name__:<30}  "
                f"no seed file found: {settings.SEED_DATA_PATH}/{entity_name}.json"
            )
        else:
            print(f'[SEED]   {model_cls.__name__:<30} => "{entity_type}"."{entity_name}"')
            print(f"         file : {out_path}")
        print()

    print("-" * 60)
    print(f"Scripts written to: {Path('generated_sql/dml').resolve()}")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="commverse-db",
        description="Auto-generate PostgreSQL DDL/DML from Pydantic models (reads .env)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --table_generate      Generate CREATE TABLE scripts\n"
            "  python main.py --metadata_generate   Generate MetaDataDictionary INSERT scripts\n"
            "  python main.py --seed_data_insert    Generate INSERT scripts from seed JSON files\n"
            "  python main.py --apply               Generate + execute CREATE TABLE scripts\n"
            "  python main.py --alter               Generate ALTER TABLE diff scripts\n"
        ),
    )

    # ── New commands ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--table_generate",
        action="store_true",
        help="Generate CREATE TABLE DDL scripts -> generated_sql/ddl/",
    )
    parser.add_argument(
        "--metadata_generate",
        action="store_true",
        help=(
            "Generate INSERT scripts for catalog.MetaDataDictionary "
            "(fetches org codes from admin.Organizations) -> generated_sql/dml/"
        ),
    )
    parser.add_argument(
        "--seed_data_insert",
        action="store_true",
        help=(
            "Generate INSERT scripts from seed JSON files for entity data tables "
            "(fetches org codes from admin.Organizations) -> generated_sql/dml/"
        ),
    )

    # ── Legacy flags ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Generate CREATE TABLE scripts and execute them against the DB in .env",
    )
    parser.add_argument(
        "--alter",
        action="store_true",
        help="Generate ALTER TABLE scripts (diff live DB schema vs model)",
    )

    args = parser.parse_args()

    if args.metadata_generate:
        run_metadata_generate()
    elif args.seed_data_insert:
        run_seed_data_insert()
    else:
        # --table_generate (explicit), --apply, --alter, or no args -> DDL generation
        run_table_generate(apply=args.apply, alter=args.alter)


if __name__ == "__main__":
    main()
