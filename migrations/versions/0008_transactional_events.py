"""Atomic public events, append-only audit and durable projection sources."""
from alembic import op

revision = "0008_transactional_events"
down_revision = "0007_execution_fences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE workflow.run_streams (
      tenant_id uuid NOT NULL, run_id uuid NOT NULL, sequence bigint NOT NULL DEFAULT 0,
      projection jsonb NOT NULL DEFAULT '{}', PRIMARY KEY(tenant_id,run_id),
      FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id));
    CREATE TABLE workflow.run_events (
      tenant_id uuid NOT NULL, run_id uuid NOT NULL, sequence bigint NOT NULL,
      event_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(), type text NOT NULL,
      schema_version integer NOT NULL DEFAULT 1 CHECK(schema_version=1),
      snapshot_version bigint NOT NULL, timestamp timestamptz NOT NULL DEFAULT clock_timestamp(),
      payload jsonb NOT NULL CHECK(octet_length(payload::text)<=4096),
      PRIMARY KEY(tenant_id,run_id,sequence),
      FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id));
    CREATE TABLE workflow.run_audit (
      tenant_id uuid NOT NULL, run_id uuid NOT NULL, sequence bigint NOT NULL,
      actor_id uuid, service text NOT NULL, action_id uuid, reason_code text NOT NULL,
      execution_epoch bigint, diff jsonb NOT NULL CHECK(octet_length(diff::text)<=4096),
      PRIMARY KEY(tenant_id,run_id,sequence),
      FOREIGN KEY(tenant_id,run_id,sequence) REFERENCES workflow.run_events(tenant_id,run_id,sequence));
    CREATE TABLE workflow.event_outbox (
      tenant_id uuid NOT NULL, run_id uuid NOT NULL, sequence bigint NOT NULL,
      published_at timestamptz, PRIMARY KEY(tenant_id,run_id,sequence),
      FOREIGN KEY(tenant_id,run_id,sequence) REFERENCES workflow.run_events(tenant_id,run_id,sequence));
    CREATE INDEX event_outbox_pending ON workflow.event_outbox(tenant_id,run_id,sequence)
      WHERE published_at IS NULL;
    CREATE TABLE workflow.event_delivery (
      tenant_id uuid NOT NULL, run_id uuid NOT NULL, sequence bigint NOT NULL,
      PRIMARY KEY(tenant_id,run_id),
      FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id));""")
    for table in ("run_streams", "run_events", "run_audit", "event_outbox", "event_delivery"):
        op.execute(f"ALTER TABLE workflow.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workflow.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY tenant_scope ON workflow.{table}
          USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant())""")
        op.execute(f"GRANT SELECT ON workflow.{table} TO ops_workflow")
    # Only fixed-search-path trigger functions can append or update these tables.
    op.execute("""CREATE FUNCTION workflow.capture_run_event() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE t uuid; r uuid; a uuid; n bigint; kind text; body jsonb; delta jsonb;
      BEGIN
        t=NEW.tenant_id;
        IF TG_TABLE_NAME='agent_runs' THEN
          r=NEW.id;
          IF TG_OP='UPDATE' AND (to_jsonb(NEW)-'updated_at')=(to_jsonb(OLD)-'updated_at')
            THEN RETURN NEW; END IF;
          kind=CASE WHEN TG_OP='INSERT' THEN 'run.created'
            WHEN NEW.status IS DISTINCT FROM OLD.status THEN 'run.status_changed'
            ELSE 'run.progress' END;
          body=jsonb_build_object('status',NEW.status,'outcome',NEW.outcome);
          -- Error messages, request, private state and credentials never enter the event log.
          IF NEW.error IS NOT NULL THEN body=body || jsonb_build_object('reason_code',
            CASE WHEN NEW.error->>'code' IN ('RUN_FAILED','RESTART_INTERRUPTED',
              'UNSUPPORTED_WORKFLOW_VERSION','CHECKPOINT_UNSUPPORTED','AUTHORIZATION_REVOKED')
            THEN NEW.error->>'code' ELSE 'RUN_FAILED' END); END IF;
          delta=jsonb_build_object('status',NEW.status);
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
      END $$;
      REVOKE ALL ON FUNCTION workflow.capture_run_event() FROM PUBLIC;""")
    for table in ("agent_runs", "actions", "approvals"):
        op.execute(f"CREATE TRIGGER transactional_event AFTER INSERT OR UPDATE ON workflow.{table} FOR EACH ROW EXECUTE FUNCTION workflow.capture_run_event()")
    # Existing runs gain an explicit baseline, never invented historical transitions.
    op.execute("""INSERT INTO workflow.run_streams(tenant_id,run_id,sequence,projection)
      SELECT tenant_id,id,1,public_snapshot FROM workflow.agent_runs;
      INSERT INTO workflow.run_events(tenant_id,run_id,sequence,type,snapshot_version,payload)
      SELECT tenant_id,id,1,'run.baseline',1,jsonb_build_object('status',status,'outcome',outcome)
      FROM workflow.agent_runs;
      INSERT INTO workflow.run_audit(tenant_id,run_id,sequence,service,reason_code,diff)
      SELECT tenant_id,id,1,'ops_migration','run.baseline','{}' FROM workflow.agent_runs;
      INSERT INTO workflow.event_outbox(tenant_id,run_id,sequence)
      SELECT tenant_id,id,1 FROM workflow.agent_runs;""")
    op.execute("""CREATE FUNCTION workflow.publish_event(target uuid, item bigint) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE t uuid=identity.current_tenant();
      BEGIN
        UPDATE workflow.event_outbox SET published_at=COALESCE(published_at,clock_timestamp())
          WHERE tenant_id=t AND run_id=target AND sequence=item;
        IF NOT FOUND THEN RETURN; END IF;
        INSERT INTO workflow.event_delivery(tenant_id,run_id,sequence) VALUES(t,target,item)
          ON CONFLICT(tenant_id,run_id) DO UPDATE
          SET sequence=GREATEST(workflow.event_delivery.sequence,EXCLUDED.sequence);
        -- Wakeups contain only identifiers; consumers always replay authorized DB state.
        PERFORM pg_notify('opspilot_events',json_build_object('run_id',target,'sequence',item)::text);
      END $$;
      REVOKE ALL ON FUNCTION workflow.publish_event(uuid,bigint) FROM PUBLIC;
      GRANT EXECUTE ON FUNCTION workflow.publish_event(uuid,bigint) TO ops_workflow;""")

    op.execute("""CREATE FUNCTION workflow.record_recovery(target uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE t uuid=identity.current_tenant(); n bigint;
      BEGIN
        PERFORM workflow.check_fence(target);
        UPDATE workflow.run_streams SET sequence=sequence+1 WHERE tenant_id=t AND run_id=target
          RETURNING sequence INTO n;
        IF NOT FOUND THEN RAISE EXCEPTION 'RUN_MISSING'; END IF;
        INSERT INTO workflow.run_events(tenant_id,run_id,sequence,type,snapshot_version,payload)
          VALUES(t,target,n,'recovery.started',n,'{}');
        INSERT INTO workflow.run_audit(tenant_id,run_id,sequence,actor_id,service,reason_code,execution_epoch,diff)
          VALUES(t,target,n,NULLIF(current_setting('app.actor_id',true),'')::uuid,session_user,
          'recovery.started',NULLIF(current_setting('app.execution_epoch',true),'')::bigint,'{}');
        INSERT INTO workflow.event_outbox(tenant_id,run_id,sequence) VALUES(t,target,n);
      END $$;
      REVOKE ALL ON FUNCTION workflow.record_recovery(uuid) FROM PUBLIC;
      GRANT EXECUTE ON FUNCTION workflow.record_recovery(uuid) TO ops_workflow;""")


def downgrade() -> None:
    raise RuntimeError("Restore an isolated Full instance instead of destructive downgrade")
