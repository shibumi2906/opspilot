"""Local comment and internal inbox operations."""

from alembic import op

revision = "0012_local_operations"
down_revision = "0011_action_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workflow.actions DROP CONSTRAINT ck_actions_tool")
    op.execute(
        "ALTER TABLE workflow.actions ADD CONSTRAINT ck_actions_tool CHECK(tool_name IN ('create_ticket','add_ticket_comment','notify_manager'))"
    )
    op.execute("""CREATE FUNCTION workflow.guard_local_effect() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE a record; t record; recipient_role text; allowed boolean := false;
      BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'IMMUTABLE_LOCAL_EFFECT'; END IF;
        SELECT * INTO a FROM workflow.actions WHERE tenant_id=identity.current_tenant() AND id=NEW.originating_action_id;
        IF NOT FOUND OR NEW.tenant_id <> identity.current_tenant() THEN RAISE EXCEPTION 'LOCAL_EFFECT_SCOPE'; END IF;
        PERFORM workflow.check_fence(a.run_id);
        IF (TG_TABLE_NAME='ticket_comments' AND a.tool_name<>'add_ticket_comment') OR
           (TG_TABLE_NAME='notifications' AND a.tool_name<>'notify_manager') OR
           (to_jsonb(NEW)-'tenant_id'-'id'-'originating_action_id'-'created_at') <> a.arguments THEN
          RAISE EXCEPTION 'LOCAL_EFFECT_PAYLOAD'; END IF;
        IF TG_TABLE_NAME='ticket_comments' THEN
          SELECT * INTO t FROM domain.tickets WHERE tenant_id=NEW.tenant_id AND id=NEW.ticket_id FOR SHARE;
          IF NOT FOUND OR t.customer_id<>NEW.customer_id THEN RAISE EXCEPTION 'LOCAL_TARGET_SCOPE'; END IF;
        ELSE
          FOR recipient_role IN SELECT role FROM identity.tenant_memberships WHERE tenant_id=NEW.tenant_id AND user_id=NEW.recipient_id LOOP
            IF identity.lock_role(NEW.recipient_id,NEW.tenant_id,recipient_role) THEN allowed := true; EXIT; END IF;
          END LOOP;
          IF NOT allowed THEN RAISE EXCEPTION 'LOCAL_RECIPIENT_SCOPE'; END IF;
        END IF;
        RETURN NEW;
      END $$;
      REVOKE ALL ON FUNCTION workflow.guard_local_effect() FROM PUBLIC;""")
    for table, target in [
        (
            "ticket_comments",
            "ticket_id uuid NOT NULL, FOREIGN KEY(tenant_id,ticket_id) REFERENCES domain.tickets(tenant_id,id),",
        ),
        ("notifications", "recipient_id uuid NOT NULL REFERENCES identity.users(id),"),
    ]:
        op.execute(f"""CREATE TABLE domain.{table} (
          tenant_id uuid NOT NULL DEFAULT identity.current_tenant(), id uuid PRIMARY KEY,
          customer_id uuid NOT NULL, {target}
          body text NOT NULL CHECK(length(body) BETWEEN 1 AND 6000), evidence_ids jsonb NOT NULL,
          originating_action_id uuid NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
          UNIQUE(tenant_id,id), FOREIGN KEY(tenant_id,customer_id) REFERENCES domain.customers(tenant_id,id),
          FOREIGN KEY(tenant_id,originating_action_id) REFERENCES workflow.actions(tenant_id,id));
          ALTER TABLE domain.{table} ENABLE ROW LEVEL SECURITY;
          ALTER TABLE domain.{table} FORCE ROW LEVEL SECURITY;
          CREATE POLICY tenant_isolation ON domain.{table} USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant());
          GRANT SELECT,INSERT ON domain.{table} TO ops_domain;
          CREATE TRIGGER local_effect_guard BEFORE INSERT OR UPDATE OR DELETE ON domain.{table} FOR EACH ROW EXECUTE FUNCTION workflow.guard_local_effect();""")


def downgrade() -> None:
    raise RuntimeError("Local receipts must not be destroyed by automatic downgrade")
