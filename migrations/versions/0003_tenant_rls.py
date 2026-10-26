"""Tenant foundation, explicit synthetic legacy mapping and FORCE RLS.

Frozen checkpoint DDL from locked langgraph-checkpoint-postgres 3.2.0.
No import from runtime models/fixtures/SDK: future upgrades cannot mutate this revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_tenant_rls"
down_revision = "0002_search_indexes"
branch_labels = None
depends_on = None

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ACTOR = "11111111-1111-4111-8111-111111111111"
TABLES = (
    "domain.customers",
    "domain.customer_integrations",
    "domain.incidents",
    "domain.knowledge_articles",
    "workflow.agent_runs",
    "workflow.actions",
    "workflow.approvals",
    "domain.tickets",
)
LEGACY_IDS = {
    "customers": [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000003",
    ],
    "integrations": [
        "00000000-0000-0000-0000-000000000101",
        "00000000-0000-0000-0000-000000000102",
        "00000000-0000-0000-0000-000000000103",
    ],
    "incidents": [
        "00000000-0000-0000-0000-000000000201",
        "00000000-0000-0000-0000-000000000202",
        "00000000-0000-0000-0000-000000000203",
        "00000000-0000-0000-0000-000000000204",
        "00000000-0000-0000-0000-000000000205",
        "00000000-0000-0000-0000-000000000206",
        "00000000-0000-0000-0000-000000000207",
        "00000000-0000-0000-0000-000000000208",
        "00000000-0000-0000-0000-000000000209",
        "00000000-0000-0000-0000-000000000210",
    ],
    "articles": [
        "00000000-0000-0000-0000-000000000301",
        "00000000-0000-0000-0000-000000000302",
        "00000000-0000-0000-0000-000000000303",
        "00000000-0000-0000-0000-000000000304",
        "00000000-0000-0000-0000-000000000305",
    ],
}
CHECKPOINT_DDL = [
    """CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);""",
    """CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);""",
    """CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);""",
    """CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);""",
    """ALTER TABLE checkpoint_blobs ALTER COLUMN blob DROP not null;""",
    """SELECT 1;""",
    """CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id);""",
    """CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id);""",
    """CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx
    ON checkpoint_writes(thread_id);""",
    """ALTER TABLE checkpoint_writes
    ADD COLUMN IF NOT EXISTS task_path TEXT NOT NULL DEFAULT '';""",
]


def upgrade() -> None:
    bind = op.get_bind()
    # Reject unknown ownership BEFORE changing any schema; Alembic rolls back atomically.
    for table, key in (
        ("customers", "customers"),
        ("customer_integrations", "integrations"),
        ("incidents", "incidents"),
        ("knowledge_articles", "articles"),
    ):
        known = ",".join("'" + value + "'::uuid" for value in LEGACY_IDS[key])
        if bind.scalar(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM domain.{table} WHERE id NOT IN ({known}))")
        ):
            raise RuntimeError("Legacy tenant ownership requires an explicit mapping")
    if bind.scalar(
        sa.text("""SELECT EXISTS (SELECT 1 FROM workflow.agent_runs
        WHERE scenario_id NOT IN
        ('greenshop_expired','healthy','unknown','timeout','contradictory'))""")
    ):
        raise RuntimeError("Legacy run ownership requires an explicit mapping")
    op.execute("CREATE SCHEMA identity")
    op.execute("""CREATE FUNCTION identity.current_tenant() RETURNS uuid
        LANGUAGE sql STABLE AS $$
        SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$""")
    op.execute("REVOKE ALL ON FUNCTION identity.current_tenant() FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA identity TO ops_workflow, ops_domain, ops_checkpoint")
    op.execute(
        "GRANT EXECUTE ON FUNCTION identity.current_tenant() TO ops_workflow, ops_domain, "
        "ops_checkpoint"
    )
    op.execute("""CREATE TABLE identity.tenants (
        id uuid PRIMARY KEY, name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE identity.users (
        id uuid PRIMARY KEY, issuer text NOT NULL, subject text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(issuer, subject))""")
    op.execute("""CREATE TABLE identity.tenant_memberships (
        tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
        user_id uuid NOT NULL REFERENCES identity.users(id), role text NOT NULL
        CHECK (role IN ('operator','approver','auditor','admin')),
        PRIMARY KEY(tenant_id, user_id, role))""")
    op.execute("""CREATE TABLE identity.sessions (
        id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES identity.users(id),
        token_hash text NOT NULL UNIQUE, expires_at timestamptz NOT NULL,
        revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now())""")
    bind.execute(
        sa.text(
            "INSERT INTO identity.tenants(id,name) VALUES (:a,'Synthetic A'),(:b,'Synthetic B')"
        ),
        {"a": A, "b": B},
    )
    bind.execute(
        sa.text(
            "INSERT INTO identity.users(id,issuer,subject) VALUES "
            "(:actor,'urn:opspilot:synthetic','local-demo')"
        ),
        {"actor": ACTOR},
    )
    for tenant in (A, B):
        bind.execute(
            sa.text("INSERT INTO identity.tenant_memberships VALUES (:t,:actor,'operator')"),
            {"t": tenant, "actor": ACTOR},
        )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id uuid")
        bind.execute(sa.text(f"UPDATE {table} SET tenant_id=:a"), {"a": A})
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN tenant_id SET DEFAULT identity.current_tenant()"
        )
        op.execute(
            f"ALTER TABLE {table} ADD FOREIGN KEY (tenant_id) REFERENCES identity.tenants(id)"
        )
        op.execute(f"ALTER TABLE {table} ADD UNIQUE (tenant_id,id)")
        op.execute(f"CREATE INDEX ON {table}(tenant_id)")
    op.execute(
        "ALTER TABLE workflow.agent_runs ADD COLUMN actor_id uuid REFERENCES identity.users(id)"
    )
    bind.execute(sa.text("UPDATE workflow.agent_runs SET actor_id=:actor"), {"actor": ACTOR})
    op.execute("ALTER TABLE workflow.agent_runs ALTER COLUMN actor_id SET NOT NULL")
    op.execute("ALTER TABLE workflow.agent_runs DROP CONSTRAINT agent_runs_client_request_id_key")
    op.execute("ALTER TABLE workflow.agent_runs ADD UNIQUE(tenant_id,client_request_id)")
    op.execute("ALTER TABLE workflow.agent_runs ADD UNIQUE(tenant_id,thread_id)")
    for table, col, parent in (
        ("domain.customer_integrations", "customer_id", "domain.customers"),
        ("domain.incidents", "customer_id", "domain.customers"),
        ("domain.tickets", "customer_id", "domain.customers"),
        ("domain.tickets", "originating_action_id", "workflow.actions"),
        ("workflow.actions", "run_id", "workflow.agent_runs"),
        ("workflow.approvals", "action_id", "workflow.actions"),
    ):
        # Retaining old single FK as well is harmless; composite FK is authoritative for tenancy.
        op.execute(
            f"ALTER TABLE {table} ADD FOREIGN KEY(tenant_id,{col}) REFERENCES "
            f"{parent}(tenant_id,id)"
        )
    # Checkpoint schema is provisioned administratively; runtime no longer owns tables or runs DDL.
    op.execute("SET LOCAL search_path TO checkpoints,public")
    for version, ddl in enumerate(CHECKPOINT_DDL):
        op.execute(ddl)
        bind.execute(
            sa.text("INSERT INTO checkpoint_migrations(v) VALUES (:v) ON CONFLICT DO NOTHING"),
            {"v": version},
        )
    # Map only the historical, explicitly named SDK compatibility fixture, only in test DB.
    # Every persisted thread now references its tenant-owned run, including SDK probes.
    if bind.scalar(sa.text("SELECT current_database()")) == "opspilot_full_test":
        bind.execute(
            sa.text("""
            INSERT INTO workflow.agent_runs
            (id,client_request_id,request,request_hash,language,status,mode,scenario_id,
             scenario_clock,thread_id,state_schema_version,public_snapshot,tool_results,usage,
             tenant_id,actor_id)
            SELECT md5(c.thread_id)::uuid,md5(c.thread_id)::uuid,'Synthetic SDK fixture',
                   repeat('0',64),'en','completed','scripted','healthy',
                   '2026-10-18T09:00:00Z'::timestamptz,c.thread_id,1,'{}','{}','{}',
                   CAST(:a AS uuid),CAST(:actor AS uuid)
            FROM checkpoints.checkpoints c
            WHERE c.thread_id ~ '^compatibility-[0-9a-f-]{36}$'
              AND NOT EXISTS (SELECT 1 FROM workflow.agent_runs r WHERE r.thread_id=c.thread_id)
            GROUP BY c.thread_id
            ON CONFLICT DO NOTHING
        """),
            {"a": A, "actor": ACTOR},
        )
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        # Historical F01 compatibility-* probes are explicitly synthetic test fixtures.
        if bind.scalar(
            sa.text(f"""SELECT EXISTS (SELECT 1 FROM checkpoints.{table} c
            WHERE NOT EXISTS (SELECT 1 FROM workflow.agent_runs r
                              WHERE r.thread_id=c.thread_id))""")
        ):
            raise RuntimeError("Legacy checkpoint ownership requires an explicit mapping")
        op.execute(f"ALTER TABLE checkpoints.{table} OWNER TO ops_migration")
        op.execute(f"ALTER TABLE checkpoints.{table} ADD COLUMN tenant_id uuid")
        bind.execute(sa.text(f"UPDATE checkpoints.{table} SET tenant_id=:a"), {"a": A})
        op.execute(f"ALTER TABLE checkpoints.{table} ALTER COLUMN tenant_id SET NOT NULL")
        op.execute(
            f"ALTER TABLE checkpoints.{table} ALTER COLUMN tenant_id SET DEFAULT "
            f"identity.current_tenant()"
        )
        op.execute(
            f"ALTER TABLE checkpoints.{table} ADD FOREIGN KEY (tenant_id) REFERENCES "
            f"identity.tenants(id)"
        )
        op.execute(
            f"ALTER TABLE checkpoints.{table} ADD FOREIGN KEY(tenant_id,thread_id) "
            "REFERENCES workflow.agent_runs(tenant_id,thread_id)"
        )
        op.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON checkpoints.{table} TO ops_checkpoint")
    op.execute("ALTER TABLE checkpoints.checkpoint_migrations OWNER TO ops_migration")
    op.execute("GRANT SELECT ON checkpoints.checkpoint_migrations TO ops_checkpoint")
    op.execute("ALTER SCHEMA checkpoints OWNER TO ops_migration")
    op.execute("REVOKE CREATE ON SCHEMA checkpoints FROM ops_checkpoint")
    op.execute("GRANT USAGE ON SCHEMA checkpoints TO ops_checkpoint")
    for table in (
        *TABLES,
        "identity.tenant_memberships",
        "checkpoints.checkpoints",
        "checkpoints.checkpoint_blobs",
        "checkpoints.checkpoint_writes",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING "
            f"(tenant_id=identity.current_tenant()) WITH CHECK "
            f"(tenant_id=identity.current_tenant())"
        )
    op.execute("ALTER TABLE identity.tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity.tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON identity.tenants "
        "USING(id=identity.current_tenant()) WITH CHECK(id=identity.current_tenant())"
    )
    # Global identity rows are migration-only in F02; F03 grants narrowly scoped BFF access.
    for table in ("identity.users", "identity.sessions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("SET LOCAL search_path TO public")


def downgrade() -> None:
    raise RuntimeError(
        "Tenant migration requires a new isolated restore; destructive downgrade is disabled"
    )
