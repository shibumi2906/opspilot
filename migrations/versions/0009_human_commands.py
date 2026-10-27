"""Durable typed clarification and cancellation commands (Full only)."""

from alembic import op

revision = "0009_human_commands"
down_revision = "0008_transactional_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE workflow.agent_runs ADD COLUMN clarification jsonb;
      ALTER TABLE workflow.agent_runs ADD COLUMN cancellation jsonb;
      ALTER TABLE workflow.command_jobs DROP CONSTRAINT command_jobs_kind_check;
      ALTER TABLE workflow.command_jobs DROP CONSTRAINT command_jobs_check;
      ALTER TABLE workflow.command_jobs ADD CHECK(kind IN ('start','resume','clarify1','clarify2','cancel'));
      ALTER TABLE workflow.command_jobs ADD CHECK((kind='resume' AND action_id IS NOT NULL)
        OR (kind<>'resume' AND action_id IS NULL));""")
    op.execute("""CREATE OR REPLACE FUNCTION workflow.fence_worker_write() RETURNS trigger
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
          IF NULLIF(current_setting('app.execution_owner',true),'') IS NULL
            AND (to_jsonb(OLD)-'clarification'-'cancellation'-'updated_at'-'status')=
                (to_jsonb(NEW)-'clarification'-'cancellation'-'updated_at'-'status')
            AND (NEW.status=OLD.status OR
              (OLD.status='waiting_for_input' AND NEW.status='queued') OR
              (NEW.status='cancelling' AND NEW.cancellation IS NOT NULL AND OLD.status IN ('queued','running','waiting_for_input','waiting_for_approval')))
            AND (NEW.clarification IS DISTINCT FROM OLD.clarification OR
                 NEW.cancellation IS DISTINCT FROM OLD.cancellation)
          THEN RETURN NEW; END IF;
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
      END $$;""")
    op.execute("""CREATE OR REPLACE FUNCTION workflow.capture_run_event() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE t uuid; r uuid; a uuid; n bigint; kind text; body jsonb; delta jsonb;
      BEGIN
        t=NEW.tenant_id;
        IF TG_TABLE_NAME='agent_runs' THEN
          r=NEW.id;
          IF TG_OP='UPDATE' AND (to_jsonb(NEW)-'updated_at')=(to_jsonb(OLD)-'updated_at')
            THEN RETURN NEW; END IF;
          kind=CASE WHEN TG_OP='INSERT' THEN 'run.created'
            WHEN NEW.cancellation IS DISTINCT FROM OLD.cancellation THEN 'run.cancel_requested'
            WHEN NEW.clarification IS DISTINCT FROM OLD.clarification THEN 'clarification.changed'
            WHEN NEW.status IS DISTINCT FROM OLD.status THEN 'run.status_changed'
            ELSE 'run.progress' END;
          body=jsonb_build_object('status',NEW.status,'outcome',NEW.outcome);
          -- Error messages, request, private state and credentials never enter the event log.
          IF NEW.error IS NOT NULL THEN body=body || jsonb_build_object('reason_code',
            CASE WHEN NEW.error->>'code' IN ('RUN_FAILED','RESTART_INTERRUPTED',
              'UNSUPPORTED_WORKFLOW_VERSION','CHECKPOINT_UNSUPPORTED','AUTHORIZATION_REVOKED')
            THEN NEW.error->>'code' ELSE 'RUN_FAILED' END); END IF;
          body=body || jsonb_build_object('clarification_id',NEW.clarification->>'id', 'version',NEW.clarification->'version');
          delta=body;
        ELSIF TG_TABLE_NAME='actions' THEN
          r=NEW.run_id; a=NEW.id;
          IF TG_OP='UPDATE' AND NEW.execution_status IS NOT DISTINCT FROM OLD.execution_status
            AND NEW.execution_result IS NOT DISTINCT FROM OLD.execution_result THEN RETURN NEW; END IF;
          kind=CASE WHEN TG_OP='INSERT' THEN 'action.proposed' ELSE 'operation.receipt_recorded' END;
          body=jsonb_build_object('action_id',a,'execution_status',NEW.execution_status);
          delta=body;
        ELSE
          a=NEW.action_id;
          SELECT run_id INTO r FROM workflow.actions WHERE tenant_id=t AND id=a;
          IF TG_OP='UPDATE' AND NEW.decision=OLD.decision THEN RETURN NEW; END IF;
          kind=CASE WHEN TG_OP='INSERT' THEN 'approval.requested' ELSE 'approval.decided' END;
          body=jsonb_build_object('action_id',a,'decision',NEW.decision,
            'self_approval_exception',NEW.self_approval_exception);
          delta=body;
        END IF;
        INSERT INTO workflow.run_streams(tenant_id,run_id) VALUES(t,r) ON CONFLICT DO NOTHING;
        UPDATE workflow.run_streams SET sequence=sequence+1 WHERE tenant_id=t AND run_id=r
          RETURNING sequence INTO n;
        IF TG_TABLE_NAME='agent_runs' THEN
          UPDATE workflow.run_streams SET projection=NEW.public_snapshot WHERE tenant_id=t AND run_id=r;
        END IF;
        INSERT INTO workflow.run_events(tenant_id,run_id,sequence,type,snapshot_version,payload)
          VALUES(t,r,n,kind,n,body);
        INSERT INTO workflow.run_audit(tenant_id,run_id,sequence,actor_id,service,action_id,
          reason_code,execution_epoch,diff) VALUES(t,r,n,
          NULLIF(current_setting('app.actor_id',true),'')::uuid,session_user,a,
          COALESCE(body->>'reason_code',kind),
          NULLIF(current_setting('app.execution_epoch',true),'')::bigint,delta);
        INSERT INTO workflow.event_outbox(tenant_id,run_id,sequence) VALUES(t,r,n);
        RETURN NEW;
      END $$;""")
    op.execute("""CREATE TABLE workflow.human_commands (
      tenant_id uuid NOT NULL DEFAULT identity.current_tenant(), run_id uuid NOT NULL,
      command_id uuid NOT NULL, payload jsonb NOT NULL CHECK(octet_length(payload::text)<=2048),
      PRIMARY KEY(tenant_id,run_id,command_id),
      FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id));
      ALTER TABLE workflow.human_commands ENABLE ROW LEVEL SECURITY;
      ALTER TABLE workflow.human_commands FORCE ROW LEVEL SECURITY;
      CREATE POLICY tenant_scope ON workflow.human_commands
        USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant());
      GRANT SELECT,INSERT ON workflow.human_commands TO ops_workflow;""")
    op.execute("""CREATE FUNCTION workflow.preserve_cancel_status() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF OLD.status='cancelling' AND NEW.cancellation IS NOT NULL AND NEW.status<>'cancelled'
          THEN NEW.status='cancelling'; END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER aa_preserve_cancel BEFORE UPDATE ON workflow.agent_runs
        FOR EACH ROW EXECUTE FUNCTION workflow.preserve_cancel_status();""")
    # Both cancel and local write hold the ownership lock before inspecting the run.
    op.execute("""CREATE FUNCTION workflow.check_not_cancelled(target uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        PERFORM workflow.check_fence(target);
        IF EXISTS(SELECT 1 FROM workflow.agent_runs WHERE tenant_id=identity.current_tenant()
          AND id=target AND cancellation IS NOT NULL)
        THEN RAISE EXCEPTION 'RUN_CANCELLED' USING ERRCODE='P0001'; END IF;
      END $$;
      REVOKE ALL ON FUNCTION workflow.check_not_cancelled(uuid) FROM PUBLIC;
      GRANT EXECUTE ON FUNCTION workflow.check_not_cancelled(uuid) TO ops_workflow,ops_domain;""")


def downgrade() -> None:
    raise RuntimeError("Restore an isolated Full instance instead of destructive downgrade")
