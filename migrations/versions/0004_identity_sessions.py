"""OIDC BFF identity gateway, one-time login state and server sessions."""

from alembic import op

revision = "0004_identity_sessions"
down_revision = "0003_tenant_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ops_identity') THEN
            CREATE ROLE ops_identity NOLOGIN NOSUPERUSER NOBYPASSRLS;
        END IF;
    END $$""")
    op.execute("GRANT USAGE ON SCHEMA identity TO ops_identity")
    op.execute("GRANT EXECUTE ON FUNCTION identity.current_tenant() TO ops_identity")
    op.execute(
        "ALTER TABLE identity.sessions ADD COLUMN tenant_id uuid REFERENCES identity.tenants(id)"
    )
    op.execute("""CREATE TABLE identity.login_attempts (
        state_hash text PRIMARY KEY, binding_hash text NOT NULL, nonce_hash text NOT NULL,
        verifier text NOT NULL, expires_at timestamptz NOT NULL)""")
    op.execute("""CREATE TABLE identity.security_events (
        id uuid PRIMARY KEY, actor_id uuid, tenant_id uuid,
        kind text NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""")
    for table in (
        "tenants",
        "users",
        "tenant_memberships",
        "sessions",
        "login_attempts",
        "security_events",
    ):
        op.execute(f"ALTER TABLE identity.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE identity.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY identity_gateway ON identity.{table} TO ops_identity "
            "USING (true) WITH CHECK (true)"
        )
    op.execute("GRANT SELECT ON identity.tenants,identity.tenant_memberships TO ops_identity")
    op.execute("GRANT SELECT,INSERT,UPDATE ON identity.users,identity.sessions TO ops_identity")
    op.execute("GRANT SELECT,INSERT,DELETE ON identity.login_attempts TO ops_identity")
    op.execute("GRANT INSERT ON identity.security_events TO ops_identity")
    op.execute(
        "ALTER TABLE workflow.approvals ADD COLUMN decided_by uuid REFERENCES identity.users(id)"
    )
    op.execute(
        "ALTER TABLE workflow.approvals ADD COLUMN self_approval_exception boolean NOT "
        "NULL DEFAULT false"
    )


def downgrade() -> None:
    raise RuntimeError("Restore into a new isolated Full database instead of destructive downgrade")
