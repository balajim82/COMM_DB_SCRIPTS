-- ============================================================
-- Table       : PERM_ROLE_ACTION_CLAIMS
-- Model       : PermRoleActionClaimModel
-- PK          : org_code, role_code, resource_code, operation_code
-- Partition   : org_code, role_code
-- meta_lake_code: COGITO
-- entity_type : SystemData
-- kind        : System
-- workspaces  : []
-- required_fields: ['org_code', 'role_code', 'resource_code', 'operation_code', 'claim']
-- partition_order: {'org_code': 1, 'role_code': 2}
-- date_fields : []
-- Fields      : org_code, role_code, resource_code, operation_code, claim, is_active, is_deleted
-- ============================================================
CREATE TABLE IF NOT EXISTS PERM_ROLE_ACTION_CLAIMS
(
    org_code                             TEXT NOT NULL,
    role_code                            TEXT NOT NULL,
    resource_code                        TEXT NOT NULL,
    operation_code                       TEXT NOT NULL,
    data                                 JSONB NOT NULL DEFAULT '{}',
    updated_at                           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_perm_role_action_claims PRIMARY KEY (org_code, role_code, resource_code, operation_code)
) PARTITION BY HASH (org_code);

-- All model fields stored in data (JSONB):
--   {
--       "org_code": "TEXT",
--       "role_code": "TEXT",
--       "resource_code": "TEXT",
--       "operation_code": "TEXT",
--       "claim": "TEXT",
--       "is_active": "BOOLEAN",
--       "is_deleted": "BOOLEAN"
--   }

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_permroleactionclaims_org_code
    ON PERM_ROLE_ACTION_CLAIMS USING BTREE (org_code);
CREATE INDEX IF NOT EXISTS idx_permroleactionclaims_role_code
    ON PERM_ROLE_ACTION_CLAIMS USING BTREE (role_code);
CREATE INDEX IF NOT EXISTS idx_permroleactionclaims_resource_code
    ON PERM_ROLE_ACTION_CLAIMS USING BTREE (resource_code);
CREATE INDEX IF NOT EXISTS idx_permroleactionclaims_operation_code
    ON PERM_ROLE_ACTION_CLAIMS USING BTREE (operation_code);
CREATE INDEX IF NOT EXISTS idx_permroleactionclaims_data_gin
    ON PERM_ROLE_ACTION_CLAIMS USING GIN (data);

-- Unique index pk_perm_role_action_claims on (org_code, role_code, resource_code, operation_code) is created automatically
-- by the PRIMARY KEY constraint defined above.