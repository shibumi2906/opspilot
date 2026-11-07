"""Read-only registered Prometheus mapping; no synthetic preconditions for configured sources."""

from alembic import op

revision = "0020_prometheus"
down_revision = "0019_adapters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE integrations.connector_configs DROP CONSTRAINT connector_configs_kind_check;
ALTER TABLE integrations.connector_configs ADD CONSTRAINT connector_configs_kind_check
 CHECK(kind IN ('simulator','prometheus'));
ALTER TABLE integrations.connector_configs ADD COLUMN adapter_mapping jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE integrations.connector_configs ADD CONSTRAINT prometheus_read_only
 CHECK(kind<>'prometheus' OR NOT ingress_enabled);
ALTER TABLE integrations.connector_configs ADD CONSTRAINT bounded_adapter_mapping
 CHECK(jsonb_typeof(adapter_mapping)='object' AND octet_length(adapter_mapping::text)<=2048);
CREATE FUNCTION integrations.has_binding(i uuid) RETURNS boolean
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM integrations.connector_configs x
 WHERE x.tenant_id=identity.current_tenant() AND x.integration_id=i) $$;
REVOKE ALL ON FUNCTION integrations.has_binding(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION integrations.has_binding(uuid) TO ops_workflow,ops_domain;
""")


def downgrade() -> None:
    raise RuntimeError("Preserve registered source and replay identities; explicit recovery required")
