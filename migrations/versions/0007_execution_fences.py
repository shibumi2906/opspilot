"""Per-run ownership and transactional fencing at every persisted worker boundary."""
from alembic import op

revision = "0007_execution_fences"
down_revision = "0006_command_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE workflow.run_execution_leases (
      tenant_id uuid NOT NULL DEFAULT identity.current_tenant(), run_id uuid NOT NULL,
      owner uuid, epoch bigint NOT NULL DEFAULT 0 CHECK(epoch>=0), lease_until timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(tenant_id,run_id),
      FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id))""")
    op.execute("ALTER TABLE workflow.run_execution_leases ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workflow.run_execution_leases FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_scope ON workflow.run_execution_leases
      USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant())""")
    op.execute("GRANT SELECT,INSERT,UPDATE ON workflow.run_execution_leases TO ops_workflow")
    op.execute("GRANT SELECT ON workflow.run_execution_leases TO ops_checkpoint,ops_domain")
    op.execute("ALTER TABLE workflow.agent_runs ADD COLUMN workflow_version text NOT NULL DEFAULT 'full-graph-v1'")
    op.execute("ALTER TABLE workflow.command_jobs ADD COLUMN claim_owner uuid")
    op.execute("ALTER TABLE workflow.command_jobs ADD COLUMN claim_epoch bigint")
    op.execute("""CREATE FUNCTION workflow.check_fence(target uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE ownership record;
      BEGIN
        SELECT * INTO ownership FROM workflow.run_execution_leases
          WHERE tenant_id=identity.current_tenant() AND run_id=target FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'EXECUTION_OWNERSHIP_REQUIRED' USING ERRCODE='40001'; END IF;
        IF ownership.owner IS NULL OR ownership.lease_until<=clock_timestamp()
          OR NULLIF(current_setting('app.execution_run',true),'')::uuid IS DISTINCT FROM target
          OR NULLIF(current_setting('app.execution_owner',true),'')::uuid IS DISTINCT FROM ownership.owner
          OR NULLIF(current_setting('app.execution_epoch',true),'')::bigint IS DISTINCT FROM ownership.epoch
        THEN RAISE EXCEPTION 'STALE_EXECUTION_FENCE' USING ERRCODE='40001'; END IF;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION workflow.check_fence(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION workflow.check_fence(uuid) TO ops_workflow,ops_checkpoint,ops_domain")
    op.execute("""CREATE FUNCTION workflow.fence_worker_write() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE r uuid; rowdata jsonb;
      BEGIN
        IF session_user='ops_migration' THEN RETURN COALESCE(NEW,OLD); END IF;
        IF TG_TABLE_NAME='approvals' AND TG_OP='UPDATE'
          AND NULLIF(current_setting('app.execution_owner',true),'') IS NULL
        THEN RETURN NEW; END IF;
        rowdata=CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
        IF TG_TABLE_SCHEMA='checkpoints' THEN
          SELECT id INTO r FROM workflow.agent_runs WHERE tenant_id=identity.current_tenant()
            AND thread_id=rowdata->>'thread_id';
          IF r IS NULL THEN RAISE EXCEPTION 'FENCE_RUN_MISSING'; END IF;
        ELSIF TG_TABLE_NAME='agent_runs' THEN
          r=NEW.id;
          -- The API may commit a human decision's status transition, never a projection.
          IF NULLIF(current_setting('app.execution_owner',true),'') IS NULL
            AND OLD.status='waiting_for_approval' AND NEW.status='running'
            AND (to_jsonb(OLD)-'status'-'updated_at')=(to_jsonb(NEW)-'status'-'updated_at')
          THEN RETURN NEW; END IF;
        ELSIF TG_TABLE_NAME IN ('approvals','tickets') THEN
          SELECT run_id INTO r FROM workflow.actions WHERE id=(rowdata->>'action_id')::uuid
            AND tenant_id=identity.current_tenant();
          IF TG_TABLE_NAME='tickets' THEN
            SELECT run_id INTO r FROM workflow.actions WHERE id=(rowdata->>'originating_action_id')::uuid
              AND tenant_id=identity.current_tenant();
          END IF;
        ELSE r=(rowdata->>'run_id')::uuid; END IF;
        IF rowdata->>'tenant_id' IS DISTINCT FROM identity.current_tenant()::text
          THEN RAISE EXCEPTION 'FENCE_TENANT_MISMATCH'; END IF;
        PERFORM workflow.check_fence(r);
        RETURN COALESCE(NEW,OLD);
      END $$""")
    for table, events in [("workflow.agent_runs","UPDATE"),("workflow.actions","INSERT OR UPDATE OR DELETE"),
                          ("workflow.approvals","INSERT OR UPDATE OR DELETE"),("domain.tickets","INSERT OR UPDATE OR DELETE"),
                          ("checkpoints.checkpoints","INSERT OR UPDATE OR DELETE"),
                          ("checkpoints.checkpoint_blobs","INSERT OR UPDATE OR DELETE"),
                          ("checkpoints.checkpoint_writes","INSERT OR UPDATE OR DELETE")]:
        op.execute(f"CREATE TRIGGER execution_fence BEFORE {events} ON {table} FOR EACH ROW EXECUTE FUNCTION workflow.fence_worker_write()")


def downgrade() -> None:
    raise RuntimeError("Restore an isolated Full instance instead of destructive downgrade")
