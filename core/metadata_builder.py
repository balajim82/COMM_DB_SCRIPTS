"""Build a Metadata-compatible dict from a Pydantic model class.

Mirrors the logic of seed_preconfigured_entities_for_org (preconfigured_entities_seeder.py)
and Metadata.from_pydantic_model (snowtiger metadata_model.py):

  1. Introspect model fields → map Python types to FieldDataType string values.
  2. Apply model_config primary_keys to mark primary_key=True per field.
  3. Override entity_name from model_config["entity_name"].
  4. Post-process required_fields, date_fields, partition_fields exactly as the
     seeder does (field-by-field mutations after the initial build).

The resulting dict matches the JSON structure stored in catalog.MetaDataDictionary.
"""

import typing
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Type, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Type introspection helpers
# ---------------------------------------------------------------------------

def _unwrap_optional(annotation):
    """Strip Optional[X] / Union[X, None] → X (recurse once)."""
    origin = get_origin(annotation)
    if origin is typing.Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _infer_data_type_and_kind(annotation) -> tuple[str, str]:
    """Map a Python/Pydantic annotation to (field_data_type, field_kind).

    Returns string values matching FieldDataType and FieldKind enums in snowtiger.
    Mirrors the if-elif chain in Metadata.from_pydantic_model.
    """
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)

    # list[X]
    if origin is list or (isinstance(origin, type) and issubclass(origin, list)):
        inner = args[0] if args else Any
        inner_origin = get_origin(inner)
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            return "list_object", "Dimension"
        if inner_origin is dict or inner is dict:
            return "list_object", "Dimension"
        _list_map = {str: "list_string", int: "list_integer", float: "list_float"}
        return _list_map.get(inner, "list_string"), "Dimension"

    # dict / Dict[K, V]
    if origin is dict or annotation is dict:
        return "object", "Dimension"

    # Nested BaseModel subclass
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return "object", "Dimension"

    # Enum subclass → stored as string
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "string", "Dimension"

    # Scalar types — order matters (bool before int)
    if annotation is bool:
        return "boolean", "Dimension"
    if annotation is int:
        return "integer", "Measure"
    if annotation is float:
        return "float", "Measure"
    if annotation is str:
        return "string", "Dimension"
    if annotation is datetime:
        return "datetime", "Datetime"
    if annotation is date:
        return "date", "Datetime"
    if annotation is Decimal:
        return "float", "Measure"
    if annotation is UUID:
        return "string", "Dimension"
    if annotation is Any:
        return "Any", "Dimension"

    # Unknown / complex annotation — fall back to string
    return "string", "Dimension"


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_metadata_dict(model_cls: Type[BaseModel], org_code: str) -> dict:
    """Return a dict matching the Metadata model JSON stored in MetaDataDictionary.

    Steps mirror seed_preconfigured_entities_for_org exactly:
      1. Build fields via from_pydantic_model equivalent (primary_keys only).
      2. Set entity_name from model_config["entity_name"].
      3. Apply required_fields  → required = True.
      4. Apply date_fields      → kind = "datetime"  (lowercase, per seeder).
      5. Apply partition_fields → partition = True, partition_order = <order>.
    """
    from pydantic_core import PydanticUndefinedType

    cfg = dict(getattr(model_cls, "model_config", {}))

    meta_lake_code: str = cfg["meta_lake_code"]
    entity_type: str = cfg["entity_type"]
    kind: str = cfg["kind"]
    entity_name: str = cfg["entity_name"]
    workspaces: list = cfg.get("workspaces", [])
    primary_keys: list = cfg.get("primary_keys", [])
    required_fields: list = cfg.get("required_fields", [])
    date_fields: list = cfg.get("date_fields", [])
    partition_fields: list = cfg.get("partition_fields", [])
    partition_order_cfg = cfg.get("partition_order")  # dict | int | None

    # ── Step 1: build base field dicts (equivalent to from_pydantic_model) ──
    fields_by_name: dict[str, dict] = {}
    for name, pydantic_field in model_cls.model_fields.items():
        data_type, field_kind = _infer_data_type_and_kind(pydantic_field.annotation)
        is_pk = name in primary_keys
        description = pydantic_field.description or f"Field for {name}"

        # A field is Pydantic-required when it has no default and no default_factory
        has_no_default = isinstance(pydantic_field.default, PydanticUndefinedType)
        has_no_factory = pydantic_field.default_factory is None
        is_required = has_no_default and has_no_factory

        fields_by_name[name] = {
            "field_name": name,
            "data_type": data_type,
            "data_spec": None,
            "kind": field_kind,
            "description": description,
            "unit": None,
            "default_x_axis": False,
            "default_y_axis": False,
            "secondary_filter": False,
            "group_by": False,
            "show_data_by": False,
            "default_for_date_range_filters": False,
            "mandatory_for_ai_agent": False,
            "primary_key": is_pk,
            "partition": False,
            "partition_order": None,
            "partition_by": None,
            "forecast": False,
            "required": is_required,
            "master_data_entity_name": None,
            "master_data_field_name": None,
        }

    # ── Step 2: apply required_fields ────────────────────────────────────────
    for fname in required_fields:
        if fname in fields_by_name:
            fields_by_name[fname]["required"] = True

    # ── Step 3: apply date_fields (sets kind to lowercase "datetime") ────────
    for fname in date_fields:
        if fname in fields_by_name:
            fields_by_name[fname]["kind"] = "datetime"

    # ── Step 4: apply partition_fields ───────────────────────────────────────
    for fname in partition_fields:
        if fname in fields_by_name:
            if isinstance(partition_order_cfg, dict):
                order = partition_order_cfg.get(fname)
            elif isinstance(partition_order_cfg, int):
                order = partition_order_cfg
            else:
                order = None
            fields_by_name[fname]["partition"] = True
            fields_by_name[fname]["partition_order"] = order

    entity_description = (model_cls.__doc__ or f"Metadata for {entity_name}").strip()

    return {
        "meta_lake_code": meta_lake_code,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "kind": kind,
        "org_code": org_code,
        "workspaces": workspaces,
        "guidelines": None,
        "entity_description": entity_description,
        "widget_size": None,
        "tag_groups": [],
        "widget_type": None,
        "plot_type": None,
        "default_show_data_by": None,
        "default_show_by_values": [],
        "source_system": None,
        "fields": list(fields_by_name.values()),
        "vega_template": [],
        "last_updated_at": None,
        "processed_at": None,
    }
