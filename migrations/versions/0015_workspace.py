"""Recipient inbox, bounded workspace reads and versioned local connector controls."""
from alembic import op

revision = "0015_workspace"
down_revision = "0014_freshness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE domain.connector_controls (
      tenant_id uuid NOT NULL DEFAULT identity.current_tenant(), integration_id uuid NOT NULL,
      enabled boolean NOT NULL, version integer NOT NULL CHECK(version>0),
      PRIMARY KEY(tenant_id,integration_id),
      FOREIGN KEY(tenant_id,integration_id) REFERENCES domain.customer_integrations(tenant_id,id));
    ALTER TABLE domain.connector_controls ENABLE ROW LEVEL SECURITY;
    ALTER TABLE domain.connector_controls FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_scope ON domain.connector_controls USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant());
    CREATE TABLE workflow.notification_reads (
      tenant_id uuid NOT NULL DEFAULT identity.current_tenant(), user_id uuid NOT NULL REFERENCES identity.users(id),
      notification_id uuid NOT NULL, read_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      PRIMARY KEY(tenant_id,user_id,notification_id),
      FOREIGN KEY(tenant_id,notification_id) REFERENCES domain.notifications(tenant_id,id));
    CREATE TABLE workflow.ui_commands (
      tenant_id uuid NOT NULL, actor_id uuid NOT NULL REFERENCES identity.users(id),command_id uuid NOT NULL,
      payload jsonb NOT NULL CHECK(octet_length(payload::text)<1024),result jsonb NOT NULL CHECK(octet_length(result::text)<2048),
      PRIMARY KEY(tenant_id,actor_id,command_id));
    ALTER TABLE workflow.notification_reads ENABLE ROW LEVEL SECURITY;
    ALTER TABLE workflow.notification_reads FORCE ROW LEVEL SECURITY;
    ALTER TABLE workflow.ui_commands ENABLE ROW LEVEL SECURITY;
    ALTER TABLE workflow.ui_commands FORCE ROW LEVEL SECURITY;
    CREATE POLICY recipient_scope ON workflow.notification_reads USING(tenant_id=identity.current_tenant() AND user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid);
    CREATE POLICY actor_scope ON workflow.ui_commands USING(tenant_id=identity.current_tenant() AND actor_id=NULLIF(current_setting('app.actor_id',true),'')::uuid);
    CREATE FUNCTION workflow.workspace_connectors() RETURNS TABLE(id uuid,customer_id uuid,type text,enabled boolean,version integer)
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    BEGIN
      IF NOT identity.lock_role(NULLIF(current_setting('app.actor_id',true),'')::uuid,identity.current_tenant(),'admin') THEN RETURN; END IF;
      RETURN QUERY SELECT i.id,i.customer_id,i.integration_type::text,COALESCE(c.enabled,true),COALESCE(c.version,0)
        FROM domain.customer_integrations i LEFT JOIN domain.connector_controls c ON c.tenant_id=i.tenant_id AND c.integration_id=i.id
        WHERE i.tenant_id=identity.current_tenant() ORDER BY i.id LIMIT 501;
    END $$;
    CREATE FUNCTION workflow.workspace_inbox(before_time timestamptz,before_id uuid,n integer)
    RETURNS TABLE(id uuid,customer_id uuid,body text,created_at timestamptz,read_at timestamptz,run_id uuid)
    LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
      SELECT x.id,x.customer_id,x.body,x.created_at,r.read_at,
        CASE WHEN (ar.actor_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND identity.lock_role(ar.actor_id,x.tenant_id,'operator')) OR EXISTS(SELECT 1 FROM identity.tenant_memberships m WHERE m.tenant_id=x.tenant_id AND m.user_id=x.recipient_id AND m.role IN ('auditor','approver')) THEN a.run_id ELSE NULL END
      FROM domain.notifications x JOIN workflow.actions a ON a.tenant_id=x.tenant_id AND a.id=x.originating_action_id
      JOIN workflow.agent_runs ar ON ar.tenant_id=a.tenant_id AND ar.id=a.run_id
      LEFT JOIN workflow.notification_reads r ON r.tenant_id=x.tenant_id AND r.notification_id=x.id AND r.user_id=x.recipient_id
      WHERE x.tenant_id=identity.current_tenant() AND x.recipient_id=NULLIF(current_setting('app.actor_id',true),'')::uuid
      AND EXISTS(SELECT 1 FROM identity.tenant_memberships m JOIN identity.users u ON u.id=m.user_id WHERE m.tenant_id=x.tenant_id AND m.user_id=x.recipient_id AND u.disabled_at IS NULL)
      AND (before_time IS NULL OR (x.created_at,x.id)<(before_time,before_id))
      ORDER BY x.created_at DESC,x.id DESC LIMIT LEAST(GREATEST(n,1),51)
    $$;
    CREATE FUNCTION workflow.workspace_command(kind text,target uuid,expected integer,desired boolean,cmd uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE t uuid=identity.current_tenant(); u uuid=NULLIF(current_setting('app.actor_id',true),'')::uuid;
      payload jsonb=jsonb_build_object('kind',kind,'target',target,'expected',expected,'desired',desired);
      prior record; control record; output jsonb; stamp timestamptz;
    BEGIN
      IF kind NOT IN ('read','connector') OR t IS NULL OR u IS NULL THEN RETURN NULL; END IF;
      PERFORM pg_advisory_xact_lock(hashtextextended(t::text||u::text||cmd::text,0));
      IF kind='read' THEN
        IF NOT EXISTS(SELECT 1 FROM domain.notifications x JOIN identity.users a ON a.id=x.recipient_id
          WHERE x.tenant_id=t AND x.id=target AND x.recipient_id=u AND a.disabled_at IS NULL
          AND EXISTS(SELECT 1 FROM identity.tenant_memberships m WHERE m.tenant_id=t AND m.user_id=u)) THEN RETURN NULL; END IF;
      ELSE
        IF NOT identity.lock_role(u,t,'admin') THEN RETURN NULL; END IF;
        PERFORM 1 FROM domain.customer_integrations WHERE tenant_id=t AND id=target FOR UPDATE;
        IF NOT FOUND THEN RETURN NULL; END IF;
      END IF;
      SELECT * INTO prior FROM workflow.ui_commands WHERE tenant_id=t AND actor_id=u AND command_id=cmd;
      IF FOUND THEN
        IF prior.payload<>payload THEN RETURN jsonb_build_object('conflict',true); END IF;
        RETURN prior.result;
      END IF;
      IF kind='read' THEN
        INSERT INTO workflow.notification_reads(tenant_id,user_id,notification_id) VALUES(t,u,target) ON CONFLICT DO NOTHING;
        SELECT read_at INTO stamp FROM workflow.notification_reads WHERE tenant_id=t AND user_id=u AND notification_id=target;
        output=jsonb_build_object('ok',true,'read_at',stamp);
      ELSE
        SELECT * INTO control FROM domain.connector_controls WHERE tenant_id=t AND integration_id=target FOR UPDATE;
        IF COALESCE(control.version,0)<>expected THEN RETURN jsonb_build_object('conflict',true); END IF;
        INSERT INTO domain.connector_controls VALUES(t,target,desired,1) ON CONFLICT(tenant_id,integration_id)
          DO UPDATE SET enabled=EXCLUDED.enabled,version=connector_controls.version+1 RETURNING * INTO control;
        output=jsonb_build_object('id',target,'enabled',control.enabled,'version',control.version);
      END IF;
      INSERT INTO workflow.ui_commands VALUES(t,u,cmd,payload,output);
      INSERT INTO identity.security_events(id,actor_id,tenant_id,kind,details) VALUES(gen_random_uuid(),u,t,
        CASE WHEN kind='read' THEN 'notification_read' ELSE 'connector_config_changed' END,jsonb_build_object('target_id',target,'command_id',cmd));
      RETURN output;
    END $$;
    CREATE INDEX security_events_workspace ON identity.security_events(tenant_id,created_at DESC,id DESC);
    CREATE FUNCTION workflow.workspace_security_events(before_time timestamptz,before_id uuid,n integer)
    RETURNS TABLE(event_id uuid,"timestamp" timestamptz,run_id uuid,sequence bigint,type text,actor_id uuid,reason_code text)
    LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
      SELECT s.id,s.created_at,NULL::uuid,NULL::bigint,'security.'||s.kind,s.actor_id,s.kind
      FROM identity.security_events s WHERE s.tenant_id=identity.current_tenant()
      AND identity.lock_role(NULLIF(current_setting('app.actor_id',true),'')::uuid,identity.current_tenant(),'auditor')
      AND (before_time IS NULL OR (s.created_at,s.id)<(before_time,before_id))
      ORDER BY s.created_at DESC,s.id DESC LIMIT LEAST(GREATEST(n,1),101)
    $$;
    REVOKE ALL ON FUNCTION workflow.workspace_security_events(timestamptz,uuid,integer) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION workflow.workspace_security_events(timestamptz,uuid,integer) TO ops_workflow;
    REVOKE ALL ON FUNCTION workflow.workspace_connectors(),workflow.workspace_inbox(timestamptz,uuid,integer),workflow.workspace_command(text,uuid,integer,boolean,uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION workflow.workspace_connectors(),workflow.workspace_inbox(timestamptz,uuid,integer),workflow.workspace_command(text,uuid,integer,boolean,uuid) TO ops_workflow;
    """)
    op.execute("""    CREATE OR REPLACE FUNCTION workflow.precondition_snapshot(r uuid,args jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE c record;i record;t record;owner_id uuid;requester uuid;result jsonb;items jsonb='[]';n integer=0; roles jsonb; control record;
    BEGIN
      IF NOT EXISTS(SELECT 1 FROM workflow.agent_runs WHERE tenant_id=identity.current_tenant() AND id=r)
      THEN RETURN NULL; END IF;
      SELECT * INTO c FROM domain.customers WHERE tenant_id=identity.current_tenant() AND id=(args->>'customer_id')::uuid FOR SHARE;
      IF NOT FOUND THEN RETURN NULL; END IF;
      FOR i IN SELECT * FROM domain.customer_integrations WHERE tenant_id=c.tenant_id AND customer_id=c.id ORDER BY id LIMIT 11 FOR SHARE LOOP
        SELECT * INTO control FROM domain.connector_controls WHERE tenant_id=c.tenant_id AND integration_id=i.id FOR SHARE;
        IF FOUND AND NOT control.enabled THEN RETURN NULL; END IF;
        n=n+1;
        items=items||jsonb_build_array(jsonb_build_object('id',i.id,'type',i.integration_type,'project_fingerprint',encode(sha256(convert_to(i.external_ref,'UTF8')),'hex')) || CASE WHEN control.version>0 THEN jsonb_build_object('control_version',control.version) ELSE '{}'::jsonb END);
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
""")


def downgrade() -> None:
    raise RuntimeError("Preserve inbox markers and admin command history; restore isolated Full")
