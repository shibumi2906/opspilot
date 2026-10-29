"""Uncached preconditions, run-wide replan bound and durable verification reserve."""

from alembic import op

revision = "0014_freshness"
down_revision = "0013_mixed_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE workflow.actions ADD CONSTRAINT bounded_revisions CHECK(revision_number<=2) NOT VALID;
    ALTER TABLE workflow.agent_runs ADD COLUMN replan_count integer NOT NULL DEFAULT 0 CHECK(replan_count BETWEEN 0 AND 1);
    CREATE FUNCTION workflow.guard_replan_count() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.replan_count IS DISTINCT FROM OLD.replan_count THEN
        PERFORM workflow.check_fence(NEW.id);
        IF NEW.replan_count<>OLD.replan_count+1 THEN RAISE EXCEPTION 'REPLAN_LIMIT'; END IF;
      END IF; RETURN NEW;
    END $$;
    CREATE TRIGGER replan_count_guard BEFORE UPDATE ON workflow.agent_runs FOR EACH ROW EXECUTE FUNCTION workflow.guard_replan_count();
    CREATE TABLE workflow.action_read_budgets (
      tenant_id uuid NOT NULL DEFAULT identity.current_tenant(),action_id uuid PRIMARY KEY,run_id uuid NOT NULL,
      attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
      FOREIGN KEY(tenant_id,action_id) REFERENCES workflow.actions(tenant_id,id),
      FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id));
    ALTER TABLE workflow.action_read_budgets ENABLE ROW LEVEL SECURITY;
    ALTER TABLE workflow.action_read_budgets FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_scope ON workflow.action_read_budgets USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant());
    GRANT SELECT,INSERT,UPDATE ON workflow.action_read_budgets TO ops_workflow;
    CREATE FUNCTION workflow.guard_read_budget() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM workflow.check_fence(NEW.run_id);
      IF TG_OP='UPDATE' AND (NEW.attempts<>OLD.attempts+1 OR NEW.tenant_id<>OLD.tenant_id OR NEW.action_id<>OLD.action_id OR NEW.run_id<>OLD.run_id)
      THEN RAISE EXCEPTION 'INVALID_VERIFICATION_RESERVATION'; END IF;
      IF NOT EXISTS(SELECT 1 FROM workflow.actions WHERE tenant_id=NEW.tenant_id AND id=NEW.action_id AND run_id=NEW.run_id)
      THEN RAISE EXCEPTION 'INVALID_VERIFICATION_ACTION'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER read_budget_guard BEFORE INSERT OR UPDATE ON workflow.action_read_budgets FOR EACH ROW EXECUTE FUNCTION workflow.guard_read_budget();
    CREATE FUNCTION workflow.precondition_snapshot(r uuid,args jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE c record;i record;t record;owner_id uuid;requester uuid;result jsonb;items jsonb='[]';n integer=0; roles jsonb;
    BEGIN
      IF NOT EXISTS(SELECT 1 FROM workflow.agent_runs WHERE tenant_id=identity.current_tenant() AND id=r)
      THEN RETURN NULL; END IF;
      SELECT * INTO c FROM domain.customers WHERE tenant_id=identity.current_tenant() AND id=(args->>'customer_id')::uuid FOR SHARE;
      IF NOT FOUND THEN RETURN NULL; END IF;
      FOR i IN SELECT * FROM domain.customer_integrations WHERE tenant_id=c.tenant_id AND customer_id=c.id ORDER BY id LIMIT 11 FOR SHARE LOOP
        n=n+1;
        items=items||jsonb_build_array(jsonb_build_object('id',i.id,'type',i.integration_type,'project_fingerprint',encode(sha256(convert_to(i.external_ref,'UTF8')),'hex')));
      END LOOP;
      IF n=0 OR n>10 THEN RETURN NULL; END IF;
      result=jsonb_build_object('customer',c.id,'configuration',encode(sha256(convert_to(c.metadata::text,'UTF8')),'hex'),'integrations',items);
      IF args ? 'ticket_id' THEN
        SELECT * INTO t FROM domain.tickets WHERE tenant_id=c.tenant_id AND id=(args->>'ticket_id')::uuid AND customer_id=c.id FOR SHARE;
        IF NOT FOUND THEN RETURN NULL; END IF;
        SELECT ar.actor_id INTO owner_id FROM workflow.actions a JOIN workflow.agent_runs ar
          ON ar.tenant_id=a.tenant_id AND ar.id=a.run_id
          WHERE a.tenant_id=c.tenant_id AND a.id=t.originating_action_id;
        SELECT actor_id INTO requester FROM workflow.agent_runs WHERE tenant_id=c.tenant_id AND id=r;
        IF owner_id IS DISTINCT FROM requester AND NOT identity.lock_role(requester,c.tenant_id,'approver')
          AND NOT identity.lock_role(requester,c.tenant_id,'auditor') THEN RETURN NULL; END IF;
        result=result||jsonb_build_object('ticket',t.id,'ticket_status',t.status);
      END IF;
      IF args ? 'recipient_id' THEN
        SELECT jsonb_agg(role ORDER BY role) INTO roles FROM identity.tenant_memberships
          WHERE tenant_id=c.tenant_id AND user_id=(args->>'recipient_id')::uuid;
        IF roles IS NULL THEN RETURN NULL; END IF;
        result=result||jsonb_build_object('recipient',args->>'recipient_id','recipient_roles',roles);
      END IF;
      RETURN result;
    END $$;
    REVOKE ALL ON FUNCTION workflow.precondition_snapshot(uuid,jsonb) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION workflow.precondition_snapshot(uuid,jsonb) TO ops_workflow,ops_domain;
    REVOKE ALL ON FUNCTION workflow.guard_replan_count(),workflow.guard_read_budget() FROM PUBLIC;
    """)
    # The only permitted slot pointer change is a new unexecuted revision of this exact intent.
    op.execute(
        """      CREATE OR REPLACE FUNCTION workflow.guard_plan() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'IMMUTABLE_PLAN'; END IF;
        PERFORM workflow.check_fence(NEW.run_id);
        IF TG_OP='UPDATE' THEN
          IF TG_TABLE_NAME='run_plans' OR (to_jsonb(NEW)-'status'-'verification'-'verify_attempts'-'action_id') IS DISTINCT FROM (to_jsonb(OLD)-'status'-'verification'-'verify_attempts'-'action_id')
            OR (OLD.action_id IS NOT NULL AND NEW.action_id IS DISTINCT FROM OLD.action_id AND NOT (
       OLD.status='prepared' AND NEW.status='prepared' AND EXISTS(
       SELECT 1 FROM workflow.actions a JOIN workflow.actions b ON b.tenant_id=a.tenant_id AND b.logical_action_id=a.logical_action_id
       JOIN workflow.agent_runs r ON r.tenant_id=a.tenant_id AND r.id=a.run_id
       WHERE a.tenant_id=OLD.tenant_id AND a.id=OLD.action_id AND b.id=NEW.action_id
       AND a.logical_action_id=OLD.id AND a.execution_status='not_started' AND a.superseded_at IS NOT NULL
       AND b.execution_status='not_started' AND b.revision_number=a.revision_number+1
       AND b.plan_binding=a.plan_binding AND r.replan_count=1
       AND NOT EXISTS(SELECT 1 FROM workflow.plan_slots w WHERE w.tenant_id=OLD.tenant_id AND w.run_id=OLD.run_id AND w.wave>1))))
            OR NEW.verify_attempts<OLD.verify_attempts OR
            (OLD.status<>'prepared' AND (NEW.status<>OLD.status OR NEW.verification IS DISTINCT FROM OLD.verification))
          THEN RAISE EXCEPTION 'IMMUTABLE_PLAN_INTENT'; END IF;
        END IF;
        RETURN NEW;
      END $$;
"""
    )


def downgrade() -> None:
    raise RuntimeError("Preserve approved revisions and receipts; restore isolated Full")
