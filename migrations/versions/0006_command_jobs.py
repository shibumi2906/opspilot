"""Durable single-worker commands, tenant RLS and atomic enqueue."""
from alembic import op

revision = "0006_command_jobs"
down_revision = "0005_authorization_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE workflow.command_jobs (
        id uuid PRIMARY KEY, tenant_id uuid NOT NULL DEFAULT identity.current_tenant(),
        run_id uuid NOT NULL, kind text NOT NULL CHECK(kind IN ('start','resume')),
        action_id uuid, status text NOT NULL DEFAULT 'pending'
          CHECK(status IN ('pending','running','done','dead')),
        attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
        available_at timestamptz NOT NULL DEFAULT now(),
        created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        error_code text, UNIQUE(tenant_id,run_id,kind),
        FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id),
        FOREIGN KEY(tenant_id,action_id) REFERENCES workflow.actions(tenant_id,id),
        CHECK ((kind='start' AND action_id IS NULL) OR (kind='resume' AND action_id IS NOT NULL))
    )""")
    op.execute("CREATE INDEX command_jobs_ready ON workflow.command_jobs(tenant_id,available_at) WHERE status='pending'")
    op.execute("ALTER TABLE workflow.command_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workflow.command_jobs FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_scope ON workflow.command_jobs
        USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant())""")
    op.execute("GRANT SELECT,INSERT,UPDATE ON workflow.command_jobs TO ops_workflow")
    # Upgrade only the isolated Full database; preserve pending pre-F05 work.
    op.execute("""INSERT INTO workflow.command_jobs(id,tenant_id,run_id,kind,action_id)
        SELECT r.id,r.tenant_id,r.id,CASE WHEN a.id IS NULL THEN 'start' ELSE 'resume' END,a.id
        FROM workflow.agent_runs r LEFT JOIN workflow.actions a ON a.run_id=r.id
        LEFT JOIN workflow.approvals v ON v.action_id=a.id
        WHERE r.status IN ('queued','running') AND (a.id IS NULL OR v.decision<>'pending')""")


def downgrade() -> None:
    raise RuntimeError("Restore an isolated Full instance instead of destructive downgrade")
