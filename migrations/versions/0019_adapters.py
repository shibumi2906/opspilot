"""Tenant adapter configuration and durable observation-only signed ingress."""

from alembic import op

revision = "0019_adapters"
down_revision = "0018_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE SCHEMA integrations;
CREATE ROLE ops_ingress NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT USAGE ON SCHEMA integrations,identity TO ops_ingress;
GRANT EXECUTE ON FUNCTION identity.current_tenant() TO ops_ingress;
GRANT USAGE ON SCHEMA integrations TO ops_workflow,ops_domain;
CREATE FUNCTION integrations.set_ingress_password(value text) RETURNS void
 LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF session_user<>'ops_migration' OR length(value)<64 THEN RAISE EXCEPTION 'DENIED'; END IF;
 EXECUTE format('ALTER ROLE ops_ingress LOGIN PASSWORD %L',value);
 END $$;
REVOKE ALL ON FUNCTION integrations.set_ingress_password(text) FROM PUBLIC;
CREATE TABLE integrations.connector_configs (
 tenant_id uuid NOT NULL DEFAULT identity.current_tenant(), id uuid NOT NULL,
 customer_id uuid NOT NULL, integration_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind='simulator'), mapping_version integer NOT NULL CHECK(mapping_version=1),
 origin text NOT NULL CHECK(length(origin)<=300), mapping_hash text NOT NULL CHECK(length(mapping_hash)=64),
 credential_ref text NOT NULL, webhook_ref text NOT NULL,
 read_enabled boolean NOT NULL DEFAULT false, ingress_enabled boolean NOT NULL DEFAULT false,
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,integration_id),
 FOREIGN KEY(tenant_id,customer_id) REFERENCES domain.customers(tenant_id,id),
 FOREIGN KEY(tenant_id,integration_id) REFERENCES domain.customer_integrations(tenant_id,id),
 CHECK(credential_ref='connectors/'||tenant_id::text||'/'||id::text||'/credential'),
 CHECK(webhook_ref='connectors/'||tenant_id::text||'/'||id::text||'/webhook'));
CREATE FUNCTION integrations.guard_config() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM domain.customer_integrations
   WHERE tenant_id=NEW.tenant_id AND id=NEW.integration_id AND customer_id=NEW.customer_id)
 THEN RAISE EXCEPTION 'MAPPING_SCOPE_INVALID'; END IF;
 IF TG_OP='UPDATE' AND (to_jsonb(NEW)-'version'-'read_enabled'-'ingress_enabled'-'updated_at')
  <> (to_jsonb(OLD)-'version'-'read_enabled'-'ingress_enabled'-'updated_at')
 THEN RAISE EXCEPTION 'MAPPING_IMMUTABLE'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER immutable_mapping BEFORE INSERT OR UPDATE ON integrations.connector_configs
 FOR EACH ROW EXECUTE FUNCTION integrations.guard_config();
CREATE TRIGGER invalidate_adapter_cache AFTER INSERT OR UPDATE ON integrations.connector_configs
 FOR EACH ROW EXECUTE FUNCTION workflow.invalidate_cache();
CREATE TABLE integrations.connector_health (
 tenant_id uuid NOT NULL, connector_id uuid NOT NULL, failures integer NOT NULL DEFAULT 0,
 open_until timestamptz, checked_at timestamptz,
 PRIMARY KEY(tenant_id,connector_id),
 FOREIGN KEY(tenant_id,connector_id) REFERENCES integrations.connector_configs(tenant_id,id));
CREATE TABLE integrations.webhook_receipts (
 tenant_id uuid NOT NULL, connector_id uuid NOT NULL, event_id uuid NOT NULL,
 body_hash text NOT NULL CHECK(length(body_hash)=64), kid text NOT NULL CHECK(length(kid)<=40),
 payload jsonb NOT NULL CHECK(octet_length(payload::text)<=2048),
 accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processed','ignored','quarantined')),
 PRIMARY KEY(tenant_id,connector_id,event_id),
 FOREIGN KEY(tenant_id,connector_id) REFERENCES integrations.connector_configs(tenant_id,id));
CREATE TABLE integrations.ingress_jobs (
 tenant_id uuid NOT NULL, connector_id uuid NOT NULL, event_id uuid NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), finished_at timestamptz,
 PRIMARY KEY(tenant_id,connector_id,event_id),
 FOREIGN KEY(tenant_id,connector_id,event_id)
 REFERENCES integrations.webhook_receipts(tenant_id,connector_id,event_id));
CREATE TABLE integrations.observations (
 tenant_id uuid NOT NULL, connector_id uuid NOT NULL, event_id uuid NOT NULL,
 sequence bigint NOT NULL CHECK(sequence>=0), status text NOT NULL
 CHECK(status IN ('healthy','degraded','unavailable','unknown')),
 observed_at timestamptz NOT NULL, source text NOT NULL DEFAULT 'synthetic' CHECK(source='synthetic'),
 mapping_version integer NOT NULL DEFAULT 1 CHECK(mapping_version=1),
 PRIMARY KEY(tenant_id,connector_id,event_id),
 FOREIGN KEY(tenant_id,connector_id,event_id)
 REFERENCES integrations.webhook_receipts(tenant_id,connector_id,event_id));
CREATE TABLE integrations.ingress_cursors (
 tenant_id uuid NOT NULL, connector_id uuid NOT NULL, sequence bigint NOT NULL,
 PRIMARY KEY(tenant_id,connector_id),
 FOREIGN KEY(tenant_id,connector_id) REFERENCES integrations.connector_configs(tenant_id,id));
CREATE TABLE integrations.ingress_budgets (
 tenant_id uuid NOT NULL, connector_id uuid NOT NULL, minute bigint NOT NULL, used integer NOT NULL,
 PRIMARY KEY(tenant_id,connector_id),
 FOREIGN KEY(tenant_id,connector_id) REFERENCES integrations.connector_configs(tenant_id,id));
CREATE TABLE integrations.audit (
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL, connector_id uuid NOT NULL,
 event_id uuid, actor_id uuid, kind text NOT NULL CHECK(kind IN ('configured','accepted','processed','ignored','quarantined')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(tenant_id,connector_id) REFERENCES integrations.connector_configs(tenant_id,id));
CREATE FUNCTION integrations.preserve_receipt() RETURNS trigger
 LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF (to_jsonb(NEW)-'status')<>(to_jsonb(OLD)-'status') OR OLD.status<>'pending'
 THEN RAISE EXCEPTION 'INGRESS_RECEIPT_IMMUTABLE'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER immutable_receipt BEFORE UPDATE ON integrations.webhook_receipts
 FOR EACH ROW EXECUTE FUNCTION integrations.preserve_receipt();
GRANT SELECT ON integrations.connector_configs TO ops_workflow,ops_domain,ops_ingress;
GRANT INSERT,UPDATE ON integrations.connector_configs TO ops_workflow;
GRANT SELECT,INSERT,UPDATE ON integrations.connector_health TO ops_domain;
GRANT SELECT ON integrations.observations TO ops_domain,ops_workflow;
GRANT SELECT ON integrations.audit,integrations.webhook_receipts,integrations.ingress_jobs TO ops_workflow;
GRANT SELECT,INSERT,UPDATE ON integrations.webhook_receipts,integrations.ingress_jobs,
 integrations.ingress_cursors,integrations.ingress_budgets TO ops_ingress;
GRANT SELECT,INSERT ON integrations.observations TO ops_ingress;
GRANT INSERT ON integrations.audit TO ops_workflow,ops_ingress;
""")
    tables = ("connector_configs", "connector_health", "webhook_receipts", "ingress_jobs",
              "observations", "ingress_cursors", "ingress_budgets", "audit")
    for table in tables:
        op.execute(f"""ALTER TABLE integrations.{table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE integrations.{table} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON integrations.{table}
 USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant());""")
    op.execute("""
CREATE POLICY config_admin ON integrations.connector_configs AS RESTRICTIVE
 FOR ALL TO ops_workflow USING(identity.lock_role(
 NULLIF(current_setting('app.actor_id',true),'')::uuid,tenant_id,'admin'))
 WITH CHECK(identity.lock_role(NULLIF(current_setting('app.actor_id',true),'')::uuid,tenant_id,'admin'));
CREATE FUNCTION integrations.admit_ingress() RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
 BEGIN
 RETURN (SELECT count(*)<1000 FROM integrations.ingress_jobs WHERE status='pending')
 AND (SELECT count(*)<100000 FROM integrations.webhook_receipts);
 END $$;
REVOKE ALL ON FUNCTION integrations.admit_ingress() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION integrations.admit_ingress() TO ops_ingress;
CREATE FUNCTION integrations.ingress_config(t uuid,c uuid)
 RETURNS TABLE(customer_id uuid,integration_id uuid,ingress_enabled boolean)
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT x.customer_id,x.integration_id,x.ingress_enabled
 FROM integrations.connector_configs x WHERE x.tenant_id=t AND x.id=c $$;
REVOKE ALL ON FUNCTION integrations.ingress_config(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION integrations.ingress_config(uuid,uuid) TO ops_ingress;
CREATE FUNCTION integrations.lock_config(c uuid)
 RETURNS SETOF integrations.connector_configs
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT x.* FROM integrations.connector_configs x
 WHERE x.tenant_id=identity.current_tenant() AND x.id=c FOR SHARE $$;
REVOKE ALL ON FUNCTION integrations.lock_config(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION integrations.lock_config(uuid) TO ops_domain,ops_ingress;
""")


def downgrade() -> None:
    raise RuntimeError("Retain ingress event identities; use an isolated recovery procedure")
