"""ASVS identity lifecycle, append-only denial audit and shared admission budgets."""

from alembic import op

revision = "0010_security_baseline"
down_revision = "0009_human_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE identity.users ADD COLUMN disabled_at timestamptz;
      ALTER TABLE identity.sessions ADD COLUMN last_seen_at timestamptz NOT NULL
DEFAULT clock_timestamp();
      ALTER TABLE identity.sessions ADD COLUMN auth_time timestamptz NOT NULL
DEFAULT clock_timestamp();
      ALTER TABLE identity.sessions ADD COLUMN auth_strength text NOT NULL DEFAULT
'single-factor';
      ALTER TABLE identity.sessions ADD COLUMN idp_sid text;
      ALTER TABLE identity.sessions ADD COLUMN idp_token_ciphertext text;
      ALTER TABLE identity.sessions ADD COLUMN revocation_reason text;
      ALTER TABLE identity.security_events ADD COLUMN details jsonb NOT NULL
DEFAULT '{}'
        CHECK(octet_length(details::text)<=4096);
      CREATE INDEX sessions_user_active ON identity.sessions(user_id,created_at
DESC) WHERE revoked_at IS NULL;
      CREATE TABLE identity.request_budgets (
        key_hash text NOT NULL, window_start bigint NOT NULL, count integer NOT
NULL CHECK(count>0),
        expires_at timestamptz NOT NULL, PRIMARY KEY(key_hash,window_start));
      ALTER TABLE identity.request_budgets ENABLE ROW LEVEL SECURITY;
      ALTER TABLE identity.request_budgets FORCE ROW LEVEL SECURITY;
      CREATE POLICY identity_gateway ON identity.request_budgets TO ops_identity
USING(true) WITH CHECK(true);
      GRANT SELECT,INSERT,UPDATE,DELETE ON identity.request_budgets TO
ops_identity;
      CREATE TABLE identity.logout_tokens (issuer text NOT NULL,jti_hash text NOT
NULL,
        expires_at timestamptz NOT NULL,PRIMARY KEY(issuer,jti_hash));
      ALTER TABLE identity.logout_tokens ENABLE ROW LEVEL SECURITY;
      ALTER TABLE identity.logout_tokens FORCE ROW LEVEL SECURITY;
      CREATE POLICY identity_gateway ON identity.logout_tokens TO ops_identity
USING(true) WITH CHECK(true);
      GRANT SELECT,INSERT,DELETE ON identity.logout_tokens TO ops_identity;""")
    op.execute("""CREATE OR REPLACE FUNCTION identity.lock_role(
 subject_id uuid, tenant uuid, wanted_role text)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        IF tenant IS DISTINCT FROM identity.current_tenant() THEN RETURN false; END IF;
        PERFORM 1 FROM identity.users WHERE id=subject_id AND disabled_at IS NULL FOR KEY SHARE;
        IF NOT FOUND THEN RETURN false; END IF;
        PERFORM 1 FROM identity.tenant_memberships m
          WHERE m.tenant_id=tenant AND m.user_id=subject_id AND m.role=wanted_role FOR KEY SHARE;
        RETURN FOUND;
      END $$;""")
    # Gate initial run admission in the same INSERT transaction as run/job/event creation.
    op.execute("""CREATE FUNCTION workflow.admit_run() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE actor_active integer; tenant_active integer; all_active integer;
      BEGIN
        PERFORM pg_advisory_xact_lock(1801202610);
        SELECT count(*) INTO actor_active FROM workflow.agent_runs
          WHERE tenant_id=NEW.tenant_id AND actor_id=NEW.actor_id AND status IN
('queued','running','waiting_for_input','waiting_for_approval','cancelling');
        SELECT count(*) INTO tenant_active FROM workflow.agent_runs
          WHERE tenant_id=NEW.tenant_id AND status IN
('queued','running','waiting_for_input','waiting_for_approval','cancelling');
        SELECT count(*) INTO all_active FROM workflow.agent_runs WHERE status IN
('queued','running','waiting_for_input','waiting_for_approval','cancelling');
        IF
actor_active>=COALESCE(NULLIF(current_setting('app.max_actor_runs',true),''),'1000')::integer
          OR
tenant_active>=COALESCE(NULLIF(current_setting('app.max_tenant_runs',true),''),'5000')::integer
          OR
all_active>=COALESCE(NULLIF(current_setting('app.max_global_runs',true),''),'10000')::integer
          THEN RAISE EXCEPTION 'RUN_ADMISSION_LIMIT' USING ERRCODE='P0001'; END
IF;
        RETURN NEW;
      END $$;
      REVOKE ALL ON FUNCTION workflow.admit_run() FROM PUBLIC;
      CREATE TRIGGER admission_budget BEFORE INSERT ON workflow.agent_runs
        FOR EACH ROW EXECUTE FUNCTION workflow.admit_run();""")


def downgrade() -> None:
    raise RuntimeError("Restore an isolated Full instance instead of destructive downgrade")
