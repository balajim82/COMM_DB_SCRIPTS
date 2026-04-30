#!/usr/bin/env python3
"""commverse-db DDL runner.

Scans the models/ directory, discovers every Pydantic BaseModel subclass,
and generates CREATE TABLE (or ALTER TABLE) SQL scripts automatically.
DB credentials are read from .env — no arguments needed.

    python main.py            # generate CREATE TABLE scripts for all models
    python main.py --apply    # generate + execute against the DB
    python main.py --alter    # generate ALTER TABLE scripts (diff vs live DB)
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
                and obj.__module__ == module_name  # defined here, not re-imported
                and obj.model_fields  # has at least one field
            ):
                found.append((f"{module_name}.{name}", obj))

    return found


# ── DDL runner ────────────────────────────────────────────────────────────────


def run(apply: bool = False, alter: bool = False) -> None:
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
            if alter:
                out_path = write_alter_script(table, model_info)
            else:
                out_path = write_create_table_script(model_info)
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


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="commverse-db",
        description="Auto-generate PostgreSQL DDL from Pydantic models (reads .env)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the generated SQL against the database configured in .env",
    )
    parser.add_argument(
        "--alter",
        action="store_true",
        help="Generate ALTER TABLE scripts (diff live DB schema vs model)",
    )
    args = parser.parse_args()
    run(apply=args.apply, alter=args.alter)


if __name__ == "__main__":
    main()
