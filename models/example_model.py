"""Example Pydantic models demonstrating the supported field annotations.

Field metadata keys (passed via json_schema_extra)
---------------------------------------------------
primary_key     : bool  – column is (part of) the primary key
foreign_key     : str   – "REFERENCED_TABLE.column" reference
partition_column: bool  – column used for table partitioning
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

# class UserProfile(BaseModel):
#     """One row per user; partitioned by created_date (RANGE)."""

#     user_id: UUID = Field(
#         ...,
#         json_schema_extra={"primary_key": True},
#     )
#     org_id: int = Field(
#         ...,
#         json_schema_extra={"foreign_key": "ORGANIZATION.id"},
#     )
#     created_date: datetime = Field(
#         ...,
#         json_schema_extra={"partition_column": True},
#     )

#     # ── Data fields (stored in data JSONB) ────────────────────────────────
#     username: str
#     email: str
#     display_name: Optional[str] = None
#     age: Optional[int] = None
#     balance: Decimal = Decimal("0.00")
#     preferences: dict = Field(default_factory=dict)
#     tags: List[str] = Field(default_factory=list)
#     is_active: bool = True


# class OrderItem(BaseModel):
#     """Composite PK (order_id + item_id); partitioned by order_date (RANGE)."""

#     order_id: int = Field(..., json_schema_extra={"primary_key": True})
#     item_id: int = Field(..., json_schema_extra={"primary_key": True})
#     user_id: UUID = Field(
#         ...,
#         json_schema_extra={"foreign_key": "USER_PROFILE.user_id"},
#     )
#     order_date: datetime = Field(
#         ...,
#         json_schema_extra={"partition_column": True},
#     )

#     # ── Data fields ───────────────────────────────────────────────────────
#     product_name: str
#     quantity: int
#     unit_price: Decimal
#     discount: Optional[Decimal] = None
#     metadata: Optional[dict] = None
#     tags: List[str] = Field(default_factory=list)


# class Organization(BaseModel):
#     """No partitioning; simple table with a single integer PK."""

#     id: int = Field(..., json_schema_extra={"primary_key": True})
#     name: str
#     domain: Optional[str] = None
#     settings: dict = Field(default_factory=dict)
#     created_at_ts: datetime = Field(default_factory=datetime.utcnow)


class PermResourceModel(BaseModel):
    """Sub-entity: protected resource types. SnowTiger table: PermResources."""

    org_code: str = Field(..., description="[PK, Partition] Tenant organisation code")
    resource_code: str = Field(
        ...,
        description="[PK, Required]  Unique resource identifier, e.g. AGENTIC_WORKFLOW",
    )
    resource_name: str = Field(
        ..., description="[Required]      Human-readable resource label"
    )

    model_config = {
        "meta_lake_code": "COGITO",
        "entity_type": "SystemData",
        "kind": "System",
        "entity_name": "PermResources",
        "workspaces": [],
        "primary_keys": ["org_code", "resource_code"],
        "required_fields": ["org_code", "resource_code", "resource_name"],
        "partition_fields": ["org_code"],
        "partition_order": {"org_code": 1},
        "date_fields": [],
    }
