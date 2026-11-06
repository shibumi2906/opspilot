"""Administrative lifecycle ledger; runtime cannot erase tombstones or restore compacted runs."""

from alembic import op
from sqlalchemy import text

revision = "0018_lifecycle"
down_revision = "0017_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE workflow.retention_jobs (
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
 actor_id uuid NOT NULL REFERENCES identity.users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 kind text NOT NULL CHECK(kind IN ('preview','compact','export')), policy_hash text NOT NULL,
 affected integer NOT NULL CHECK(affected BETWEEN 0 AND 100));
CREATE TABLE workflow.deletion_tombstones (
 tenant_id uuid NOT NULL, run_id uuid NOT NULL, action_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('evidence','history','operation','audit')),
 identity_hash text NOT NULL CHECK(length(identity_hash)=64),
 result_ref uuid, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,run_id,action_id,kind),
 FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id));
ALTER TABLE workflow.retention_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow.retention_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON workflow.retention_jobs USING(tenant_id=identity.current_tenant());
ALTER TABLE workflow.deletion_tombstones ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow.deletion_tombstones FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON workflow.deletion_tombstones USING(tenant_id=identity.current_tenant());
GRANT SELECT ON workflow.deletion_tombstones TO ops_workflow,ops_domain,ops_checkpoint;
CREATE FUNCTION workflow.guard_compacted_run() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE rid uuid; tid uuid;
BEGIN
 IF session_user='ops_migration' THEN RETURN COALESCE(NEW,OLD); END IF;
 IF TG_TABLE_NAME='agent_runs' THEN rid=NEW.id;
 ELSIF TG_TABLE_NAME='approvals' THEN
   SELECT run_id INTO rid FROM workflow.actions WHERE tenant_id=NEW.tenant_id AND id=NEW.action_id;
 ELSE rid=NEW.run_id; END IF;
 tid=NEW.tenant_id;
 IF EXISTS(SELECT 1 FROM workflow.deletion_tombstones
  WHERE tenant_id=tid AND run_id=rid AND kind IN ('evidence','history')) THEN
  RAISE EXCEPTION 'RUN_COMPACTED';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION workflow.guard_compacted_run() FROM PUBLIC;
CREATE TRIGGER aaa_compacted_run BEFORE UPDATE ON workflow.agent_runs
 FOR EACH ROW EXECUTE FUNCTION workflow.guard_compacted_run();
CREATE TRIGGER compacted_job BEFORE INSERT OR UPDATE ON workflow.command_jobs
 FOR EACH ROW EXECUTE FUNCTION workflow.guard_compacted_run();
CREATE TRIGGER compacted_action BEFORE INSERT OR UPDATE ON workflow.actions
 FOR EACH ROW EXECUTE FUNCTION workflow.guard_compacted_run();
CREATE TRIGGER compacted_grant BEFORE INSERT ON workflow.execution_grants
 FOR EACH ROW EXECUTE FUNCTION workflow.guard_compacted_run();
CREATE TRIGGER compacted_lease BEFORE INSERT OR UPDATE ON workflow.run_execution_leases
 FOR EACH ROW EXECUTE FUNCTION workflow.guard_compacted_run();
CREATE TRIGGER compacted_approval BEFORE INSERT OR UPDATE ON workflow.approvals
 FOR EACH ROW EXECUTE FUNCTION workflow.guard_compacted_run();
CREATE TRIGGER compacted_human_command BEFORE INSERT ON workflow.human_commands
 FOR EACH ROW EXECUTE FUNCTION workflow.guard_compacted_run();
""")
    # Keep the existing immutability rules. Only the migration login may erase exactly
    # the content fields after writing the anti-replay ledger in the same transaction.
    conn = op.get_bind()
    definition = conn.scalar(text("SELECT pg_get_functiondef('workflow.immutable_revision()'::regprocedure)"))
    assert isinstance(definition, str)
    exception = """
        IF TG_OP='UPDATE' AND session_user='ops_migration'
          AND NEW.arguments='{}'::jsonb AND NEW.revision_document='{}'::jsonb
          AND NEW.plan_binding IS NULL AND NEW.execution_result IS NULL
          AND (to_jsonb(NEW)-'arguments'-'revision_document'-'plan_binding'-'execution_result')
            =(to_jsonb(OLD)-'arguments'-'revision_document'-'plan_binding'-'execution_result')
          AND EXISTS(SELECT 1 FROM workflow.deletion_tombstones
            WHERE tenant_id=OLD.tenant_id AND run_id=OLD.run_id AND action_id=OLD.id AND kind='operation')
        THEN RETURN NEW; END IF;
"""
    op.execute(definition.replace("BEGIN", "BEGIN" + exception, 1))
    definition = conn.scalar(text("SELECT pg_get_functiondef('workflow.guard_plan()'::regprocedure)"))
    assert isinstance(definition, str)
    exception = """
      IF TG_OP='UPDATE' AND session_user='ops_migration' AND EXISTS(
        SELECT 1 FROM workflow.deletion_tombstones WHERE tenant_id=OLD.tenant_id
        AND run_id=OLD.run_id AND kind='history') THEN
        IF TG_TABLE_NAME='plan_slots' AND NEW.template='{}'::jsonb
          AND NEW.verification='{}'::jsonb
          AND (to_jsonb(NEW)-'template'-'verification')=(to_jsonb(OLD)-'template'-'verification')
        THEN RETURN NEW; END IF;
        IF TG_TABLE_NAME='run_plans' AND NEW.document='{"actions":[{}]}'::jsonb
          AND (to_jsonb(NEW)-'document')=(to_jsonb(OLD)-'document')
        THEN RETURN NEW; END IF;
      END IF;
"""
    op.execute(definition.replace("BEGIN", "BEGIN" + exception, 1))


def downgrade() -> None:
    raise RuntimeError("Retain anti-replay identities; restore an isolated backup")
