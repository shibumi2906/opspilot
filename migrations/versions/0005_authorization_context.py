"""Scoped role checks and actor-bound checkpoint access; no worker jobs yet."""

from alembic import op

revision = "0005_authorization_context"
down_revision = "0004_identity_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE FUNCTION identity.current_actor() RETURNS uuid LANGUAGE sql STABLE AS $$
        SELECT NULLIF(current_setting('app.actor_id',true),'')::uuid $$""")
    op.execute("REVOKE ALL ON FUNCTION identity.current_actor() FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION identity.current_actor() TO ops_workflow, "
        "ops_domain, ops_checkpoint"
    )
    op.execute("GRANT SELECT ON identity.tenant_memberships TO ops_workflow,ops_domain")
    op.execute("GRANT USAGE ON SCHEMA workflow TO ops_checkpoint")
    op.execute("GRANT SELECT ON workflow.agent_runs TO ops_checkpoint")
    op.execute("""CREATE POLICY checkpoint_actor ON workflow.agent_runs AS RESTRICTIVE
        TO ops_checkpoint USING(actor_id=identity.current_actor())""")
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        op.execute(f"""CREATE POLICY checkpoint_actor ON checkpoints.{table} AS RESTRICTIVE
            TO ops_checkpoint USING(EXISTS (SELECT 1 FROM workflow.agent_runs r
              WHERE r.tenant_id={table}.tenant_id AND r.thread_id={table}.thread_id
                AND r.actor_id=identity.current_actor()))
            WITH CHECK(EXISTS (SELECT 1 FROM workflow.agent_runs r
              WHERE r.tenant_id={table}.tenant_id AND r.thread_id={table}.thread_id
                AND r.actor_id=identity.current_actor()))""")
    # FOR KEY SHARE requires UPDATE privilege. Expose only a scope-checked read/lock function,
    # never UPDATE grants on memberships to the workflow/domain roles.
    op.execute("""CREATE FUNCTION identity.lock_role(subject_id uuid, tenant uuid, wanted_role text)
        RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        BEGIN
            IF tenant IS DISTINCT FROM identity.current_tenant() THEN RETURN false; END IF;
            PERFORM 1 FROM identity.tenant_memberships m
              WHERE m.tenant_id=tenant AND m.user_id=subject_id AND m.role=wanted_role
              FOR KEY SHARE;
            RETURN FOUND;
        END $$""")
    op.execute("REVOKE ALL ON FUNCTION identity.lock_role(uuid,uuid,text) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION identity.lock_role(uuid,uuid,text) "
        "TO ops_workflow,ops_domain,ops_identity"
    )
    # Identity gateway performs authorized admin mutations; domain roles remain read-only here.
    op.execute("GRANT INSERT,DELETE ON identity.tenant_memberships TO ops_identity")


def downgrade() -> None:
    raise RuntimeError("Restore a new isolated Full instance instead of destructive downgrade")
