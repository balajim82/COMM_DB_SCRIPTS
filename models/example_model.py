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
from enum import Enum

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


class ClaimType(str, Enum):
    """Whether a role is granted or explicitly denied an action / data access."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class PermRoleActionClaimModel(BaseModel):
    """
    Sub-entity: ALLOW / DENY claims per role + resource + operation.
    SnowTiger table: PermRoleActionClaims.
    claim = ClaimType.ALLOW grants; ClaimType.DENY blocks (DENY wins).
    """

    org_code: str = Field(..., description="[PK, Partition] Tenant organisation code")
    role_code: str = Field(
        ..., description="[PK, Partition] Role this claim belongs to"
    )
    resource_code: str = Field(
        ..., description="[PK, Required]  Resource the claim applies to"
    )
    operation_code: str = Field(
        ..., description="[PK, Required]  Operation the claim applies to"
    )
    claim: ClaimType = Field(..., description="[Required]      ALLOW or DENY")
    is_active: bool = Field(
        True, description="[Optional]      Whether this claim is currently enforced"
    )
    is_deleted: bool = Field(False, description="[Optional]     Soft-delete flag")

    model_config = {
        "meta_lake_code": "COGITO",
        "entity_type": "SystemData",
        "kind": "System",
        "entity_name": "PermRoleActionClaims",
        "workspaces": [],
        "primary_keys": ["org_code", "role_code", "resource_code", "operation_code"],
        "required_fields": [
            "org_code",
            "role_code",
            "resource_code",
            "operation_code",
            "claim",
        ],
        "partition_fields": ["org_code", "role_code"],
        "partition_order": {"org_code": 1, "role_code": 2},
        "date_fields": [],
    }
