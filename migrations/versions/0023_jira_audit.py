"""Append Jira receipt transitions to the protected transactional audit stream."""

from alembic import op

revision = "0023_jira_audit"
down_revision = "0022_jira_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE FUNCTION integrations.capture_jira_receipt() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE n bigint; body jsonb;
BEGIN
 IF TG_OP='UPDATE' AND NEW.outcome=OLD.outcome
    AND NEW.external_id IS NOT DISTINCT FROM OLD.external_id THEN RETURN NEW; END IF;
 body=jsonb_build_object('action_id',NEW.action_id,'outcome',NEW.outcome,
                         'external_id_present',NEW.external_id IS NOT NULL);
 INSERT INTO workflow.run_streams(tenant_id,run_id)
 VALUES(NEW.tenant_id,NEW.run_id) ON CONFLICT DO NOTHING;
 UPDATE workflow.run_streams SET sequence=sequence+1
 WHERE tenant_id=NEW.tenant_id AND run_id=NEW.run_id RETURNING sequence INTO n;
 INSERT INTO workflow.run_events(tenant_id,run_id,sequence,type,snapshot_version,payload)
 VALUES(NEW.tenant_id,NEW.run_id,n,'operation.receipt_recorded',n,body);
 INSERT INTO workflow.run_audit(tenant_id,run_id,sequence,actor_id,service,action_id,
                               reason_code,execution_epoch,diff)
 VALUES(NEW.tenant_id,NEW.run_id,n,identity.current_actor(),session_user,NEW.action_id,
        'jira.'||NEW.outcome,
        NULLIF(current_setting('app.execution_epoch',true),'')::bigint,body);
 INSERT INTO workflow.event_outbox(tenant_id,run_id,sequence)
 VALUES(NEW.tenant_id,NEW.run_id,n);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION integrations.capture_jira_receipt() FROM PUBLIC;
CREATE TRIGGER jira_receipt_audit AFTER INSERT OR UPDATE ON integrations.jira_operations
 FOR EACH ROW EXECUTE FUNCTION integrations.capture_jira_receipt();
""")


def downgrade() -> None:
    raise RuntimeError("Preserve Jira audit evidence; restore an isolated Full instance")
