import re
import typing
from dataclasses import dataclass, field
from typing import Any, List, Optional, Type

from pydantic import BaseModel

from core.type_map import resolve_pg_type


@dataclass
class ColumnInfo:
    name: str
    python_type: Any
    pg_type: str
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    fk_reference: Optional[str]   # e.g. "ORGANIZATION.id"
    is_partition_column: bool
    has_default: bool
    default: Any


@dataclass
class ModelInfo:
    model_name: str
    table_name: str
    all_fields: List[ColumnInfo]
    structural_columns: List[ColumnInfo]  # columns that become real DB columns
    pk_fields: List[ColumnInfo]
    fk_fields: List[ColumnInfo]
    partition_fields: List[ColumnInfo]
    meta: dict  # raw model_config extras (entity_type, kind, etc.)


def to_table_name(raw: str) -> str:
    """Convert a PascalCase name to UPPER_SNAKE_CASE, stripping a trailing 'Model' suffix.

    Examples:
        PermRoleModel  -> PERM_ROLE
        UserProfile    -> USER_PROFILE
        HTTPSRequest   -> HTTPS_REQUEST
    """
    # Strip common suffix so 'PermRoleModel' becomes 'PermRole'
    name = re.sub(r"Model$", "", raw)
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    s = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", s)
    return s.upper()


def _resolve_table_name(model_cls: Type[BaseModel]) -> str:
    """Prefer model_config['entity_name'] when present, else derive from class name."""
    cfg = _raw_config(model_cls)
    entity_name = cfg.get("entity_name")
    if entity_name:
        return to_table_name(entity_name)
    return to_table_name(model_cls.__name__)


def _raw_config(model_cls: Type[BaseModel]) -> dict:
    """Return the model_config as a plain dict, handling both ConfigDict and plain dict."""
    cfg = getattr(model_cls, "model_config", {})
    # ConfigDict is dict-like; plain dicts also work
    return dict(cfg) if cfg else {}


def _is_nullable(annotation, pydantic_field) -> bool:
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        if type(None) in typing.get_args(annotation):
            return True
    from pydantic_core import PydanticUndefinedType
    if not isinstance(pydantic_field.default, PydanticUndefinedType) and pydantic_field.default is None:
        return True
    return False


def inspect_model(model_cls: Type[BaseModel]) -> ModelInfo:
    """Inspect a Pydantic model and return structured column metadata.

    Supports two annotation styles (can be mixed):

    Style A – per-field json_schema_extra:
        field: type = Field(..., json_schema_extra={"primary_key": True})

    Style B – model_config dict (preferred for shared-schema models):
        model_config = {
            "primary_keys":      ["field1", "field2"],
            "partition_fields":  ["field1"],
            "foreign_keys":      {"field3": "OTHER_TABLE.id"},
            "entity_name":       "TableName",   # overrides class-name derivation
        }
    """
    from pydantic_core import PydanticUndefinedType

    cfg = _raw_config(model_cls)

    # Style B: bulk declarations in model_config
    cfg_pk_set: set[str] = set(cfg.get("primary_keys", []))
    cfg_part_set: set[str] = set(cfg.get("partition_fields", []))
    cfg_fk_map: dict[str, str] = cfg.get("foreign_keys", {})  # {field: "TABLE.col"}

    table_name = _resolve_table_name(model_cls)
    all_fields: List[ColumnInfo] = []

    for name, pf in model_cls.model_fields.items():
        annotation = pf.annotation
        extra = pf.json_schema_extra or {}

        has_default = not isinstance(pf.default, PydanticUndefinedType)
        default_val = pf.default if has_default else None
        if not has_default and pf.default_factory is not None:
            has_default = True

        # Merge Style A and Style B — either wins
        is_pk = bool(extra.get("primary_key", False)) or (name in cfg_pk_set)
        is_fk = ("foreign_key" in extra) or (name in cfg_fk_map)
        fk_ref = extra.get("foreign_key") or cfg_fk_map.get(name)
        is_part = bool(extra.get("partition_column", False)) or (name in cfg_part_set)

        col = ColumnInfo(
            name=name,
            python_type=annotation,
            pg_type=resolve_pg_type(annotation),
            is_nullable=_is_nullable(annotation, pf),
            is_primary_key=is_pk,
            is_foreign_key=is_fk,
            fk_reference=fk_ref,
            is_partition_column=is_part,
            has_default=has_default,
            default=default_val,
        )
        all_fields.append(col)

    pk_fields = [c for c in all_fields if c.is_primary_key]
    fk_fields = [c for c in all_fields if c.is_foreign_key]
    partition_fields = [c for c in all_fields if c.is_partition_column]

    # Deduplicate structural columns preserving declaration order
    seen: set = set()
    structural_columns: List[ColumnInfo] = []
    for col in pk_fields + fk_fields + partition_fields:
        if col.name not in seen:
            seen.add(col.name)
            structural_columns.append(col)

    # Collect non-standard config keys as metadata
    _known = {"primary_keys", "partition_fields", "foreign_keys", "entity_name",
               "arbitrary_types_allowed", "populate_by_name", "str_strip_whitespace"}
    meta = {k: v for k, v in cfg.items() if k not in _known}

    return ModelInfo(
        model_name=model_cls.__name__,
        table_name=table_name,
        all_fields=all_fields,
        structural_columns=structural_columns,
        pk_fields=pk_fields,
        fk_fields=fk_fields,
        partition_fields=partition_fields,
        meta=meta,
    )
