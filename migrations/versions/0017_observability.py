"""Durable command trace links and narrowly scoped operator projections."""
from alembic import op
revision="0017_observability"
down_revision="0016_governance"
branch_labels=None
depends_on=None

def upgrade() -> None:
    op.execute("""
ALTER TABLE workflow.command_jobs ADD COLUMN traceparent text
 CHECK(traceparent IS NULL OR traceparent ~ '^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$');
ALTER TABLE workflow.command_jobs ADD COLUMN first_claimed_at timestamptz;
ALTER TABLE workflow.command_jobs ADD COLUMN claimed_at timestamptz;
CREATE FUNCTION workflow.operator_diagnostics(target uuid) RETURNS jsonb
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE tenant uuid=identity.current_tenant(); actor uuid=identity.current_actor();
 staff boolean; result jsonb; selected workflow.agent_runs%ROWTYPE;
BEGIN
 IF tenant IS NULL OR actor IS NULL THEN RETURN NULL; END IF;
 staff=identity.lock_role(actor,tenant,'admin') OR identity.lock_role(actor,tenant,'auditor');
 IF NOT staff AND NOT identity.lock_role(actor,tenant,'operator') THEN RETURN NULL; END IF;
 IF target IS NOT NULL THEN
  SELECT * INTO selected FROM workflow.agent_runs WHERE tenant_id=tenant AND id=target
   AND (staff OR actor_id=actor);
  IF NOT FOUND THEN RETURN NULL; END IF;
 END IF;
 WITH scoped AS (SELECT * FROM workflow.agent_runs WHERE tenant_id=tenant
    AND (staff OR actor_id=actor) AND (target IS NULL OR id=target)),
 jobs AS (SELECT j.* FROM workflow.command_jobs j JOIN scoped r ON r.id=j.run_id AND r.tenant_id=j.tenant_id)
 SELECT jsonb_build_object(
  'observed_at',clock_timestamp(),
  'scope_actor_id',CASE WHEN staff THEN NULL ELSE actor END,
  'queued_runs',(SELECT count(*) FROM scoped WHERE status='queued'),
  'active_runs',(SELECT count(*) FROM scoped WHERE status='running'),
  'waiting_runs',(SELECT count(*) FROM scoped WHERE status IN ('waiting_for_approval','waiting_for_input')),
  'queue_age_seconds',COALESCE((SELECT EXTRACT(epoch FROM clock_timestamp()-min(created_at)) FROM jobs WHERE status='pending' AND available_at<=clock_timestamp()),0),
  'waiting_age_seconds',COALESCE((SELECT EXTRACT(epoch FROM clock_timestamp()-min(updated_at)) FROM scoped WHERE status IN ('waiting_for_approval','waiting_for_input')),0),
  'active_seconds',(SELECT COALESCE(sum(u.active_seconds),0) FROM workflow.usage_reservations u JOIN scoped r ON r.id=u.run_id AND r.tenant_id=u.tenant_id),
  'queue_latency_seconds',COALESCE((SELECT avg(EXTRACT(epoch FROM first_claimed_at-created_at)) FROM jobs WHERE first_claimed_at IS NOT NULL),0),
  'dead_jobs',(SELECT count(*) FROM jobs WHERE status='dead'),
  'expired_leases',(SELECT count(*) FROM workflow.run_execution_leases l JOIN scoped r ON r.id=l.run_id AND r.tenant_id=l.tenant_id WHERE l.owner IS NOT NULL AND l.lease_until<=clock_timestamp()),
  'lease_churn',(SELECT COALESCE(sum(GREATEST(l.epoch-1,0)),0) FROM workflow.run_execution_leases l JOIN scoped r ON r.id=l.run_id AND r.tenant_id=l.tenant_id),
  'unknown_operations',(SELECT count(*) FROM workflow.actions a JOIN scoped r ON r.id=a.run_id AND r.tenant_id=a.tenant_id WHERE a.execution_status='unknown'),
  'auth_denials_60s',(SELECT count(*) FROM identity.security_events e WHERE e.tenant_id=tenant AND e.created_at>clock_timestamp()-interval '60 seconds' AND (staff OR e.actor_id=actor) AND e.kind LIKE '%denied%'),
  'exhausted_budgets',(SELECT count(*) FROM workflow.usage_reservations u JOIN scoped r ON r.id=u.run_id AND r.tenant_id=u.tenant_id WHERE r.status IN ('queued','running') AND (u.reads>=(u.limits->>'reads')::integer OR u.llm>=(u.limits->>'llm_attempts')::integer OR u.active_seconds>=(u.limits->>'active_seconds')::numeric)),
  'jobs',COALESCE((SELECT jsonb_agg(x) FROM (SELECT id,run_id,kind,status,attempts,claim_epoch,error_code,created_at,available_at,finished_at,traceparent,first_claimed_at,claimed_at FROM jobs ORDER BY created_at DESC LIMIT 40) x),'[]'::jsonb),
  'run',CASE WHEN target IS NULL THEN NULL ELSE jsonb_build_object('run_id',selected.id,'status',selected.status,'error_code',selected.error->>'code','usage',(SELECT workflow.usage_snapshot(target))) END)
 INTO result;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION workflow.operator_diagnostics(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION workflow.operator_diagnostics(uuid) TO ops_workflow;
""")

def downgrade() -> None:
    raise RuntimeError("Preserve command trace lineage; use an isolated backup")
