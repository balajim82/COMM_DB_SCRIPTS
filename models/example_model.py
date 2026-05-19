"""Example Pydantic models demonstrating the supported field annotations.

Field metadata keys (passed via json_schema_extra)
---------------------------------------------------
primary_key     : bool  – column is (part of) the primary key
foreign_key     : str   – "REFERENCED_TABLE.column" reference
partition_column: bool  – column used for table partitioning
"""

from datetime import datetime,date
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field
from enum import Enum

class ClaimType(str, Enum):
    """Whether a role is granted or explicitly denied an action / data access."""
    ALLOW = "ALLOW"
    DENY  = "DENY"


class PermRoleDataClaimModel(BaseModel):
    """
    Sub-entity: data-visibility policies per role + master-data entity.
    SnowTiger table: PermRoleDataClaims.
    claim = ClaimType.ALLOW = show matching rows; ClaimType.DENY = hide matching rows.
    """
    org_code:          str           = Field(...,  description="[PK, Partition] Tenant organisation code")
    role_code:         str           = Field(...,  description="[PK, Partition] Role this claim belongs to")
    entity_name:       str           = Field(...,  description="[PK, Required]  Master-data catalog the policy applies to")
    entity_type:       Optional[str] = Field(None, description="[Optional]      Entity type, e.g. OrgData or MarketData")
    policy_expression: Optional[str] = Field(None, description="[Optional]      JSON-serialised list of filter dicts")
    claim:             ClaimType     = Field(...,  description="[Required]      ALLOW or DENY")
    is_active:         bool          = Field(True, description="[Optional]      Whether this claim is currently enforced")
    is_deleted:        bool          = Field(False, description="[Optional]     Soft-delete flag")
    deleted_at:        Optional[str] = Field(None,  description="[Optional]      UTC timestamp when row was soft-deleted")

    model_config = {
        "meta_lake_code":   "COGITO",
        "entity_type":      "SystemData",
        "kind":             "System",
        "entity_name":      "PermRoleDataClaims",
        "workspaces":       [],
        "primary_keys":     ["org_code", "role_code", "entity_name"],
        "required_fields":  ["org_code", "role_code", "entity_name", "claim"],
        "partition_fields": ["org_code", "role_code"],
        "partition_order":  {"org_code": 1, "role_code": 2},
        "date_fields":      ["deleted_at"],
    }
