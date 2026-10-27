"""Immutable revision identities, expiring approvals and independent execution grants."""

import json

from alembic import op
from sqlalchemy import text

from opspilot.security.revisions import canonical_hash, document

revision = "0011_action_grants"
down_revision = "0010_security_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE workflow.logical_actions (
      tenant_id uuid NOT NULL DEFAULT identity.current_tenant(), id uuid PRIMARY KEY,
      run_id uuid NOT NULL, current_revision_id uuid NOT NULL, version integer NOT
NULL CHECK(version>0),
      UNIQUE(tenant_id,id), FOREIGN KEY(tenant_id,run_id) REFERENCES
workflow.agent_runs(tenant_id,id));
      ALTER TABLE workflow.actions ADD COLUMN logical_action_id uuid;
      ALTER TABLE workflow.actions ADD COLUMN revision_number integer NOT NULL
DEFAULT 1;
      ALTER TABLE workflow.actions ADD COLUMN plan_version integer NOT NULL DEFAULT
1;
      ALTER TABLE workflow.actions ADD COLUMN revision_document jsonb;
      ALTER TABLE workflow.actions ADD COLUMN revision_hash text;
      ALTER TABLE workflow.actions ADD COLUMN expires_at timestamptz NOT NULL DEFAULT
clock_timestamp()+interval '15 minutes';
      ALTER TABLE workflow.actions ADD COLUMN superseded_at timestamptz;
      ALTER TABLE workflow.approvals ADD COLUMN version integer NOT NULL DEFAULT 1;
      ALTER TABLE workflow.approvals ADD COLUMN expires_at timestamptz NOT NULL
DEFAULT clock_timestamp()+interval '15 minutes';
      ALTER TABLE workflow.approvals DROP CONSTRAINT ck_approvals_decision;
      ALTER TABLE workflow.approvals ADD CONSTRAINT ck_approvals_decision
CHECK(decision IN
        ('pending','approved','rejected','expired','revoked','superseded'));
      DO $$ DECLARE item record; BEGIN
        FOR item IN SELECT c.conname FROM pg_constraint c JOIN pg_attribute a
          ON a.attrelid=c.conrelid AND a.attnum=c.conkey[1]
          WHERE c.conrelid='workflow.actions'::regclass AND c.contype='u'
          AND array_length(c.conkey,1)=1 AND a.attname='run_id'
        LOOP EXECUTE format('ALTER TABLE workflow.actions DROP CONSTRAINT
%I',item.conname); END LOOP;
      END $$;
      INSERT INTO
workflow.logical_actions(tenant_id,id,run_id,current_revision_id,version)
        SELECT tenant_id,id,run_id,id,1 FROM workflow.actions;
      UPDATE workflow.actions SET logical_action_id=id;
      UPDATE workflow.approvals p SET decision='revoked' FROM workflow.actions a
        WHERE a.id=p.action_id AND p.decision='approved' AND
a.execution_status<>'succeeded';""")
    conn = op.get_bind()
    for row in conn.execute(text("SELECT * FROM workflow.actions")).mappings().all():
        doc = document(
            tenant=str(row["tenant_id"]),
            run=str(row["run_id"]),
            logical=str(row["id"]),
            revision=str(row["id"]),
            version=1,
            arguments=row["arguments"],
            expires=row["expires_at"],
        )
        conn.execute(
            text(
                "UPDATE workflow.actions SET revision_document=CAST(:d AS jsonb),revision_hash=:h WHERE id=:id"
            ),
            {"d": json.dumps(doc), "h": canonical_hash(doc), "id": row["id"]},
        )
    op.execute("""ALTER TABLE workflow.actions ALTER COLUMN logical_action_id SET NOT NULL;
      ALTER TABLE workflow.actions ALTER COLUMN revision_document SET NOT NULL;
      ALTER TABLE workflow.actions ALTER COLUMN revision_hash SET NOT NULL;
      ALTER TABLE workflow.actions ADD
UNIQUE(tenant_id,logical_action_id,revision_number);
      ALTER TABLE workflow.actions ADD FOREIGN KEY(tenant_id,logical_action_id)
REFERENCES workflow.logical_actions(tenant_id,id);
      ALTER TABLE workflow.actions ADD CHECK(revision_number>0 AND plan_version>0 AND
length(revision_hash)=64);
      CREATE TABLE workflow.execution_grants (
        tenant_id uuid NOT NULL DEFAULT identity.current_tenant(), jti uuid PRIMARY
KEY,
        run_id uuid NOT NULL, revision_id uuid NOT NULL, actor_id uuid NOT NULL,
approver_id uuid NOT NULL,
        revision_hash text NOT NULL, kid text NOT NULL, epoch bigint NOT NULL,
        issued_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
        consumed_at timestamptz, revoked_at timestamptz,
        FOREIGN KEY(tenant_id,revision_id) REFERENCES
workflow.actions(tenant_id,id));
      CREATE INDEX approval_expiry ON workflow.approvals(tenant_id,expires_at) WHERE
decision IN ('pending','approved');""")
    for table in ("logical_actions", "execution_grants"):
        op.execute(f"ALTER TABLE workflow.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workflow.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_scope ON workflow.{table} USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant())"
        )
        op.execute(f"GRANT SELECT ON workflow.{table} TO ops_workflow,ops_domain")
    op.execute("""GRANT INSERT,UPDATE ON workflow.logical_actions TO ops_workflow;
      GRANT INSERT ON workflow.execution_grants TO ops_workflow;
      GRANT UPDATE(revoked_at) ON workflow.execution_grants TO ops_workflow;
      GRANT UPDATE(consumed_at) ON workflow.execution_grants TO ops_domain;
      CREATE FUNCTION workflow.immutable_revision() RETURNS trigger LANGUAGE plpgsql
AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'IMMUTABLE_REVISION'; END IF;
        IF
(to_jsonb(NEW)-'execution_status'-'execution_result'-'executed_at'-'superseded_at')
          IS DISTINCT FROM
(to_jsonb(OLD)-'execution_status'-'execution_result'-'executed_at'-'superseded_at')
          THEN RAISE EXCEPTION 'IMMUTABLE_REVISION'; END IF;
        IF OLD.execution_status='succeeded' AND
(NEW.execution_status<>OLD.execution_status
          OR NEW.execution_result IS DISTINCT FROM OLD.execution_result OR
NEW.superseded_at IS DISTINCT FROM OLD.superseded_at)
          THEN RAISE EXCEPTION 'IMMUTABLE_RECEIPT'; END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER immutable_revision BEFORE UPDATE OR DELETE ON workflow.actions
        FOR EACH ROW EXECUTE FUNCTION workflow.immutable_revision();
      CREATE FUNCTION workflow.terminal_approval() RETURNS trigger LANGUAGE plpgsql
AS $$
      BEGIN
        IF NEW.action_id<>OLD.action_id OR NEW.version<>OLD.version OR
NEW.tenant_id<>OLD.tenant_id
          OR NEW.expires_at<>OLD.expires_at THEN RAISE EXCEPTION
'IMMUTABLE_APPROVAL'; END IF;
        IF OLD.decision<>'pending' AND NEW.decision IS DISTINCT FROM OLD.decision
          AND NOT(OLD.decision='approved' AND NEW.decision IN
('expired','revoked','superseded'))
          THEN RAISE EXCEPTION 'TERMINAL_APPROVAL'; END IF;
        IF OLD.decision<>'pending' AND (NEW.decided_by IS DISTINCT FROM
OLD.decided_by
          OR NEW.self_approval_exception IS DISTINCT FROM OLD.self_approval_exception
          OR NEW.decided_at IS DISTINCT FROM OLD.decided_at) THEN RAISE EXCEPTION
'IMMUTABLE_DECISION'; END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER terminal_approval BEFORE UPDATE ON workflow.approvals
        FOR EACH ROW EXECUTE FUNCTION workflow.terminal_approval();""")
    op.execute("""CREATE FUNCTION workflow.lock_approval(target uuid) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        PERFORM 1 FROM workflow.approvals WHERE tenant_id=identity.current_tenant()
          AND action_id=target FOR UPDATE;
        RETURN FOUND;
      END $$;
      REVOKE ALL ON FUNCTION workflow.lock_approval(uuid) FROM PUBLIC;
      GRANT EXECUTE ON FUNCTION workflow.lock_approval(uuid) TO ops_workflow,ops_domain;""")
    for table in ("logical_actions", "execution_grants"):
        op.execute(
            f"CREATE TRIGGER execution_fence BEFORE INSERT OR UPDATE ON workflow.{table} FOR EACH ROW EXECUTE FUNCTION workflow.fence_worker_write()"
        )

    op.execute("""CREATE FUNCTION workflow.capture_grant_event() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE t uuid; r uuid; a uuid; n bigint; kind text; body jsonb;
      BEGIN
        t=NEW.tenant_id; r=NEW.run_id;
        IF TG_TABLE_NAME='logical_actions' THEN
          a=NEW.current_revision_id;
          IF TG_OP='UPDATE' AND NEW.current_revision_id=OLD.current_revision_id THEN RETURN NEW; END IF;
          kind='revision.current_changed';
          body=jsonb_build_object('logical_action_id',NEW.id,'revision_id',a,'version',NEW.version);
        ELSE
          a=NEW.revision_id;
          kind=CASE WHEN TG_OP='INSERT' THEN 'grant.issued'
            WHEN NEW.revoked_at IS DISTINCT FROM OLD.revoked_at THEN 'grant.revoked' ELSE 'grant.consumed' END;
          body=jsonb_build_object('revision_id',a,'jti',NEW.jti,'kid',NEW.kid,'epoch',NEW.epoch);
        END IF;
        UPDATE workflow.run_streams SET sequence=sequence+1 WHERE tenant_id=t AND run_id=r RETURNING sequence INTO n;
        IF n IS NULL THEN RAISE EXCEPTION 'EVENT_STREAM_REQUIRED'; END IF;
        INSERT INTO workflow.run_events(tenant_id,run_id,sequence,type,snapshot_version,payload)
          VALUES(t,r,n,kind,n,body);
        INSERT INTO workflow.run_audit(tenant_id,run_id,sequence,actor_id,service,action_id,reason_code,execution_epoch,diff)
          VALUES(t,r,n,NULLIF(current_setting('app.actor_id',true),'')::uuid,session_user,a,kind,
            NULLIF(current_setting('app.execution_epoch',true),'')::bigint,body);
        INSERT INTO workflow.event_outbox(tenant_id,run_id,sequence) VALUES(t,r,n);
        RETURN NEW;
      END $$;
      REVOKE ALL ON FUNCTION workflow.capture_grant_event() FROM PUBLIC;
      CREATE TRIGGER security_event AFTER INSERT OR UPDATE ON workflow.execution_grants
        FOR EACH ROW EXECUTE FUNCTION workflow.capture_grant_event();
      CREATE TRIGGER security_event AFTER INSERT OR UPDATE ON workflow.logical_actions
        FOR EACH ROW EXECUTE FUNCTION workflow.capture_grant_event();""")


def downgrade() -> None:
    raise RuntimeError("Restore an isolated Full instance instead of destructive downgrade")
