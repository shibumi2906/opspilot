"""Bounded plans, per-intent ledger, independent dependency authorization and resume successor."""

from alembic import op

revision = "0013_mixed_plans"
down_revision = "0012_local_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE workflow.actions ADD COLUMN plan_binding jsonb;
      ALTER TABLE workflow.actions DROP CONSTRAINT ck_actions_execution_status;
      ALTER TABLE workflow.actions ADD CONSTRAINT ck_actions_execution_status CHECK(execution_status IN ('not_started','succeeded','failed','unknown','skipped_dependency'));
      ALTER TABLE workflow.command_jobs ADD COLUMN next_action_id uuid;
      CREATE TABLE workflow.run_plans (
        tenant_id uuid NOT NULL DEFAULT identity.current_tenant(),id uuid PRIMARY KEY,run_id uuid NOT NULL UNIQUE,
        document jsonb NOT NULL CHECK(octet_length(document::text)<=40000 AND jsonb_array_length(document->'actions') BETWEEN 1 AND 3),document_hash text NOT NULL,
        UNIQUE(tenant_id,id),FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id));
      CREATE TABLE workflow.plan_slots (
        tenant_id uuid NOT NULL DEFAULT identity.current_tenant(),id uuid PRIMARY KEY,run_id uuid NOT NULL,plan_id uuid NOT NULL,
        key varchar(32) NOT NULL, ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 2),wave integer NOT NULL CHECK(wave BETWEEN 1 AND 2),
        tool varchar(40) NOT NULL CHECK(tool IN ('create_ticket','add_ticket_comment','notify_manager')),
        template jsonb NOT NULL,dependencies jsonb NOT NULL CHECK(jsonb_array_length(dependencies)<=2),action_id uuid,
        status varchar(30) NOT NULL DEFAULT 'prepared' CHECK(status IN ('prepared','verified','rejected','skipped_dependency','unknown','mismatch','failed','cancelled')),
        verification jsonb NOT NULL DEFAULT '{"status":"not_started"}',verify_attempts integer NOT NULL DEFAULT 0 CHECK(verify_attempts BETWEEN 0 AND 3),
        UNIQUE(tenant_id,id),UNIQUE(tenant_id,plan_id,key),UNIQUE(tenant_id,plan_id,ordinal),UNIQUE(action_id),
        FOREIGN KEY(tenant_id,plan_id) REFERENCES workflow.run_plans(tenant_id,id),
        FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id),
        FOREIGN KEY(tenant_id,action_id) REFERENCES workflow.actions(tenant_id,id));
      CREATE FUNCTION workflow.guard_plan() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'IMMUTABLE_PLAN'; END IF;
        PERFORM workflow.check_fence(NEW.run_id);
        IF TG_OP='UPDATE' THEN
          IF TG_TABLE_NAME='run_plans' OR (to_jsonb(NEW)-'status'-'verification'-'verify_attempts'-'action_id') IS DISTINCT FROM (to_jsonb(OLD)-'status'-'verification'-'verify_attempts'-'action_id')
            OR (OLD.action_id IS NOT NULL AND NEW.action_id IS DISTINCT FROM OLD.action_id)
            OR NEW.verify_attempts<OLD.verify_attempts OR
            (OLD.status<>'prepared' AND (NEW.status<>OLD.status OR NEW.verification IS DISTINCT FROM OLD.verification))
          THEN RAISE EXCEPTION 'IMMUTABLE_PLAN_INTENT'; END IF;
        END IF;
        RETURN NEW;
      END $$;
      REVOKE ALL ON FUNCTION workflow.guard_plan() FROM PUBLIC;""")
    for table in ("run_plans", "plan_slots"):
        op.execute(f"""ALTER TABLE workflow.{table} ENABLE ROW LEVEL SECURITY;
          ALTER TABLE workflow.{table} FORCE ROW LEVEL SECURITY;
          CREATE POLICY tenant_isolation ON workflow.{table} USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant());
          GRANT SELECT,INSERT,UPDATE ON workflow.{table} TO ops_workflow;
          CREATE TRIGGER plan_guard BEFORE INSERT OR UPDATE OR DELETE ON workflow.{table} FOR EACH ROW EXECUTE FUNCTION workflow.guard_plan();""")
    op.execute("""CREATE FUNCTION workflow.check_plan_action(target uuid) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE a record; s record; p record; d record;
      BEGIN
        SELECT * INTO a FROM workflow.actions WHERE tenant_id=identity.current_tenant() AND id=target;
        SELECT * INTO s FROM workflow.plan_slots WHERE tenant_id=identity.current_tenant() AND action_id=target;
        IF (a.plan_binding IS NULL OR a.plan_binding='null'::jsonb) AND NOT FOUND THEN
          IF EXISTS(SELECT 1 FROM workflow.run_plans WHERE tenant_id=a.tenant_id AND run_id=a.run_id)
          THEN RAISE EXCEPTION 'UNBOUND_PLAN_ACTION' USING ERRCODE='40001'; END IF;
          RETURN; END IF;
        IF s.id IS NULL OR (a.plan_binding IS NULL OR a.plan_binding='null'::jsonb) OR s.status<>'prepared' THEN
          IF s.status='verified' AND a.execution_status='succeeded' AND a.execution_result IS NOT NULL THEN RETURN; END IF;
          RAISE EXCEPTION 'PLAN_ACTION_DENIED' USING ERRCODE='40001'; END IF;
        SELECT * INTO p FROM workflow.run_plans WHERE tenant_id=s.tenant_id AND id=s.plan_id;
        IF p.run_id<>a.run_id OR s.run_id<>a.run_id OR s.tool<>a.tool_name OR
          a.plan_binding IS DISTINCT FROM jsonb_build_object('plan_id',s.plan_id::text,'slot_id',s.id::text,'hash',p.document_hash,'wave',s.wave,'dependencies',s.dependencies,'intent',s.key)
          OR EXISTS(SELECT 1 FROM workflow.plan_slots w JOIN workflow.approvals ap ON ap.tenant_id=w.tenant_id AND ap.action_id=w.action_id
             WHERE w.tenant_id=s.tenant_id AND w.plan_id=s.plan_id AND w.wave=s.wave AND ap.decision='pending')
          THEN RAISE EXCEPTION 'PLAN_BINDING_DENIED' USING ERRCODE='40001'; END IF;
        FOR d IN SELECT value FROM jsonb_array_elements_text(s.dependencies) LOOP
          IF NOT EXISTS(SELECT 1 FROM workflow.plan_slots dep JOIN workflow.actions da ON da.tenant_id=dep.tenant_id AND da.id=dep.action_id
            WHERE dep.tenant_id=s.tenant_id AND dep.plan_id=s.plan_id AND dep.key=d.value AND dep.status='verified'
              AND da.execution_status='succeeded' AND da.execution_result IS NOT NULL)
            THEN RAISE EXCEPTION 'PLAN_DEPENDENCY_DENIED' USING ERRCODE='40001'; END IF;
        END LOOP;
      END $$;
      REVOKE ALL ON FUNCTION workflow.check_plan_action(uuid) FROM PUBLIC;
      GRANT EXECUTE ON FUNCTION workflow.check_plan_action(uuid) TO ops_workflow,ops_domain;""")
    # Bounded, body-free transactional slot events; reuse F07 event/audit/outbox allocation.
    op.execute("""CREATE FUNCTION workflow.capture_plan_event() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE n bigint; body jsonb;
      BEGIN
        IF TG_OP='UPDATE' AND NEW.status=OLD.status AND NEW.action_id IS NOT DISTINCT FROM OLD.action_id THEN RETURN NEW; END IF;
        body=jsonb_build_object('plan_id',NEW.plan_id,'slot_id',NEW.id,'wave',NEW.wave,'status',NEW.status,'action_id',NEW.action_id);
        UPDATE workflow.run_streams SET sequence=sequence+1 WHERE tenant_id=NEW.tenant_id AND run_id=NEW.run_id RETURNING sequence INTO n;
        IF n IS NULL THEN RAISE EXCEPTION 'EVENT_STREAM_REQUIRED'; END IF;
        INSERT INTO workflow.run_events(tenant_id,run_id,sequence,type,snapshot_version,payload) VALUES(NEW.tenant_id,NEW.run_id,n,'plan.slot_changed',n,body);
        INSERT INTO workflow.run_audit(tenant_id,run_id,sequence,actor_id,service,action_id,reason_code,execution_epoch,diff)
          VALUES(NEW.tenant_id,NEW.run_id,n,NULLIF(current_setting('app.actor_id',true),'')::uuid,session_user,NEW.action_id,'plan.slot_changed',NULLIF(current_setting('app.execution_epoch',true),'')::bigint,body);
        INSERT INTO workflow.event_outbox(tenant_id,run_id,sequence) VALUES(NEW.tenant_id,NEW.run_id,n);
        RETURN NEW;
      END $$;
      REVOKE ALL ON FUNCTION workflow.capture_plan_event() FROM PUBLIC;
      CREATE TRIGGER plan_event AFTER INSERT OR UPDATE ON workflow.plan_slots FOR EACH ROW EXECUTE FUNCTION workflow.capture_plan_event();""")


def downgrade() -> None:
    raise RuntimeError("Preserve completed business intents; restore an isolated Full instance")
