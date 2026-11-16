"""Jira trusted bindings and immutable one-attempt operation receipts."""

from alembic import op

revision = "0022_jira_operations"
down_revision = "0021_worker_admission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE workflow.actions DROP CONSTRAINT ck_actions_tool;
ALTER TABLE workflow.actions ADD CONSTRAINT ck_actions_tool CHECK (
 tool_name IN ('create_ticket','add_ticket_comment','notify_manager',
               'create_jira_issue','create_jira_comment'));

ALTER TABLE workflow.plan_slots DROP CONSTRAINT plan_slots_tool_check;
ALTER TABLE workflow.plan_slots ADD CONSTRAINT plan_slots_tool_check CHECK (
 tool IN ('create_ticket','add_ticket_comment','notify_manager',
          'create_jira_issue','create_jira_comment'));
CREATE TABLE integrations.jira_bindings (
 tenant_id uuid NOT NULL, connector_id uuid NOT NULL, customer_id uuid NOT NULL,
 version integer NOT NULL CHECK(version>0), site text NOT NULL,
 project_id text NOT NULL CHECK(project_id ~ '^[1-9][0-9]{0,19}$'),
 issue_type_id text NOT NULL CHECK(issue_type_id ~ '^[1-9][0-9]{0,19}$'),
 addresses jsonb NOT NULL CHECK(jsonb_typeof(addresses)='array'),
 cloud_id uuid, enabled boolean NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,connector_id),
 FOREIGN KEY(tenant_id,customer_id) REFERENCES domain.customers(tenant_id,id),
 CHECK(site ~ '^https://[a-z0-9][a-z0-9-]*[.]atlassian[.]net$')
);
ALTER TABLE integrations.jira_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE integrations.jira_bindings FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON integrations.jira_bindings
 USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant());
GRANT SELECT ON integrations.jira_bindings TO ops_workflow,ops_domain;

CREATE TABLE integrations.jira_operations (
 tenant_id uuid NOT NULL DEFAULT identity.current_tenant(), action_id uuid NOT NULL,
 run_id uuid NOT NULL, connector_id uuid NOT NULL,
 payload bytea NOT NULL CHECK(octet_length(payload)<=65536),
 payload_hash text NOT NULL CHECK(length(payload_hash)=64),
 outcome text NOT NULL DEFAULT 'unknown' CHECK(outcome IN ('unknown','verified','needs_attention')),
 external_id text CHECK(external_id ~ '^[1-9][0-9]{0,19}$'),
 issue_id text CHECK(issue_id ~ '^[1-9][0-9]{0,19}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 checked_at timestamptz,
 PRIMARY KEY(tenant_id,action_id),
 FOREIGN KEY(tenant_id,action_id) REFERENCES workflow.actions(tenant_id,id),
 FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id),
 FOREIGN KEY(tenant_id,connector_id) REFERENCES integrations.jira_bindings(tenant_id,connector_id)
);
ALTER TABLE integrations.jira_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE integrations.jira_operations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON integrations.jira_operations
 USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant());
GRANT SELECT ON integrations.jira_operations TO ops_workflow;
GRANT SELECT,INSERT,UPDATE ON integrations.jira_operations TO ops_domain;

CREATE FUNCTION integrations.guard_jira_operation() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $guard$
 DECLARE a record; r record;
 BEGIN
 SELECT * INTO STRICT a FROM workflow.actions
 WHERE tenant_id=identity.current_tenant() AND id=NEW.action_id;
 SELECT * INTO STRICT r FROM workflow.agent_runs
 WHERE tenant_id=a.tenant_id AND id=a.run_id;
 IF NEW.tenant_id<>a.tenant_id OR NEW.run_id<>a.run_id
    OR a.tool_name NOT IN ('create_jira_issue','create_jira_comment')
    OR r.actor_id IS DISTINCT FROM identity.current_actor()
 THEN RAISE EXCEPTION 'JIRA_OPERATION_SCOPE'; END IF;
 PERFORM workflow.check_fence(a.run_id);
 IF TG_OP='UPDATE' THEN
   IF (to_jsonb(NEW)-'outcome'-'external_id'-'issue_id'-'checked_at') <>
      (to_jsonb(OLD)-'outcome'-'external_id'-'issue_id'-'checked_at')
      OR (OLD.external_id IS NOT NULL AND NEW.external_id IS DISTINCT FROM OLD.external_id)
      OR (OLD.issue_id IS NOT NULL AND NEW.issue_id IS DISTINCT FROM OLD.issue_id)
      OR (OLD.outcome='needs_attention' AND NEW.outcome<>'needs_attention')
      OR (OLD.outcome='verified' AND NEW.outcome='unknown')
   THEN RAISE EXCEPTION 'JIRA_RECEIPT_IMMUTABLE'; END IF;
 ELSE
   PERFORM workflow.check_not_cancelled(a.run_id);
   IF NOT workflow.lock_approval(a.id) OR NOT EXISTS (
      SELECT 1 FROM workflow.execution_grants g
      WHERE g.tenant_id=a.tenant_id AND g.revision_id=a.id
        AND g.revision_hash=a.revision_hash AND g.consumed_at IS NOT NULL
        AND g.revoked_at IS NULL AND g.expires_at>clock_timestamp()
        AND g.epoch=NULLIF(current_setting('app.execution_epoch',true),'')::bigint
   ) THEN RAISE EXCEPTION 'JIRA_GRANT_REQUIRED'; END IF;
 END IF;
 RETURN NEW;
 END $guard$;
REVOKE ALL ON FUNCTION integrations.guard_jira_operation() FROM PUBLIC;
CREATE TRIGGER jira_operation_guard BEFORE INSERT OR UPDATE ON integrations.jira_operations
 FOR EACH ROW EXECUTE FUNCTION integrations.guard_jira_operation();
""")


def downgrade() -> None:
    raise RuntimeError("Preserve dispatch receipts; restore an isolated Full instance")
