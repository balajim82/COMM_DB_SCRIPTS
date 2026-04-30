-- ============================================================
-- Table       : PERM_RESOURCES
-- Model       : PermResourceModel
-- PK          : org_code, resource_code
-- Partition   : org_code
-- meta_lake_code: COGITO
-- entity_type : SystemData
-- kind        : System
-- workspaces  : []
-- required_fields: ['org_code', 'resource_code', 'resource_name']
-- partition_order: {'org_code': 1}
-- date_fields : []
-- Fields      : org_code, resource_code, resource_name
-- ============================================================
CREATE TABLE IF NOT EXISTS PERM_RESOURCES
(
    org_code                             TEXT NOT NULL,
    resource_code                        TEXT NOT NULL,
    data                                 JSONB NOT NULL DEFAULT '{}',
    created_at                           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at                           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_perm_resources PRIMARY KEY (org_code, resource_code)
) PARTITION BY HASH (org_code);

-- All model fields stored in data (JSONB):
--   {
--       "org_code": "TEXT",
--       "resource_code": "TEXT",
--       "resource_name": "TEXT"
--   }