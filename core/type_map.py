import typing
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

PG_TYPE_MAP: dict = {
    str: "TEXT",
    int: "BIGINT",
    float: "DOUBLE PRECISION",
    bool: "BOOLEAN",
    datetime: "TIMESTAMP WITH TIME ZONE",
    date: "DATE",
    Decimal: "NUMERIC",
    UUID: "UUID",
    dict: "JSONB",
    list: "JSONB",
    bytes: "BYTEA",
}


def resolve_pg_type(annotation) -> str:
    """Map a Python/Pydantic type annotation to a PostgreSQL column type."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # Optional[X] / Union[X, None]
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return resolve_pg_type(non_none[0])
        return "TEXT"

    # list[X] → store as JSONB
    if origin is list:
        return "JSONB"

    # dict[K, V] → store as JSONB
    if origin is dict:
        return "JSONB"

    return PG_TYPE_MAP.get(annotation, "TEXT")
