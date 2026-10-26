"""Destructive ONLY in a dedicated isolated Full fixture-test PostgreSQL instance."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from langgraph.checkpoint.postgres.base import MIGRATIONS
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

from opspilot.config import Settings
from opspilot.fixtures.loader import load_fixtures
from opspilot.tenancy.context import DEMO_TENANT

pytestmark = pytest.mark.skipif(
    os.getenv("F02_MIGRATION_TEST") != "1", reason="Dedicated destructive Full fixture project only"
)
TABLES = [
    "domain.customers",
    "domain.customer_integrations",
    "domain.incidents",
    "domain.knowledge_articles",
    "workflow.agent_runs",
    "workflow.actions",
    "workflow.approvals",
    "domain.tickets",
    "checkpoints.checkpoints",
]
RUN = UUID("22222222-2222-4222-8222-222222222222")
ACTION = UUID("33333333-3333-4333-8333-333333333333")


def connect():
    settings = Settings()
    url = make_url(settings.database_url("migration"))
    assert settings.app_env == "test" and url.database == "opspilot_full_test"
    assert os.getenv("F02_MIGRATION_PROJECT") == "opspilot-full-f02-migrations"
    conn = psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False), autocommit=True
    )
    assert conn.execute("SELECT current_database()").fetchone()[0] == "opspilot_full_test"
    return conn


def reset():
    with connect() as conn:
        for schema in ["domain", "workflow", "checkpoints", "identity"]:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        conn.execute(
            "CREATE SCHEMA domain; CREATE SCHEMA workflow; CREATE SCHEMA checkpoints "
            "AUTHORIZATION ops_checkpoint"
        )
        conn.execute(
            "GRANT USAGE ON SCHEMA workflow TO ops_workflow,ops_domain; GRANT USAGE ON "
            "SCHEMA domain TO ops_domain"
        )


def insert(conn, table, row):
    values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in row.values()]
    conn.execute(
        sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.SQL(table),
            sql.SQL(",").join(map(sql.Identifier, row)),
            sql.SQL(",").join(sql.Placeholder() for _ in row),
        ),
        values,
    )


def legacy_fixture():
    fixture = load_fixtures()
    clock = datetime(2026, 10, 18, 9, tzinfo=UTC)
    with connect() as conn:
        for c in fixture.customers:
            insert(
                conn,
                "domain.customers",
                dict(
                    id=c.id,
                    name=c.name,
                    normalized_name=c.name.casefold(),
                    metadata={"synthetic": True},
                ),
            )
        for i in fixture.integrations:
            insert(conn, "domain.customer_integrations", i.model_dump())
        for i in fixture.incidents:
            row = i.model_dump(exclude={"days_before_clock"})
            row["occurred_at"] = clock - timedelta(days=i.days_before_clock)
            insert(conn, "domain.incidents", row)
        for i in fixture.articles:
            insert(conn, "domain.knowledge_articles", i.model_dump())
        insert(
            conn,
            "workflow.agent_runs",
            dict(
                id=RUN,
                client_request_id=RUN,
                request="Synthetic upgrade",
                request_hash="0" * 64,
                language="en",
                status="waiting_for_approval",
                mode="scripted",
                scenario_id="greenshop_expired",
                scenario_clock=clock,
                thread_id=str(RUN),
                state_schema_version=1,
                public_snapshot={"pending": True},
                tool_results={},
                usage={},
            ),
        )
        insert(
            conn,
            "workflow.actions",
            dict(
                id=ACTION,
                run_id=RUN,
                tool_name="create_ticket",
                arguments={},
                arguments_hash="0" * 64,
            ),
        )
        insert(
            conn,
            "workflow.approvals",
            dict(id=UUID(int=700), action_id=ACTION, decision="approved"),
        )
        insert(
            conn,
            "domain.tickets",
            dict(
                id=UUID(int=701),
                customer_id=fixture.customers[0].id,
                originating_action_id=ACTION,
                title="Existing fixture",
                description="Preserve me",
                priority="low",
                evidence_ids=[],
            ),
        )
        conn.execute("SET search_path TO checkpoints,public")
        for v, ddl in enumerate(MIGRATIONS):
            conn.execute(ddl.replace("CONCURRENTLY ", ""))
            conn.execute(
                "INSERT INTO checkpoint_migrations VALUES (%s) ON CONFLICT DO NOTHING", (v,)
            )
        insert(
            conn,
            "checkpoints.checkpoints",
            dict(
                thread_id=str(RUN),
                checkpoint_id="legacy",
                checkpoint={"id": "legacy", "channel_values": {"saved": True}},
                metadata={},
            ),
        )


def snapshot():
    with connect() as conn:
        return {
            table: conn.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::jsonb - 'tenant_id' - 'actor_id' FROM {} t ORDER BY 1"
                ).format(sql.SQL(table))
            ).fetchall()
            for table in TABLES
        }


def test_fresh_database_has_tenant_schema_and_rls():
    reset()
    command.upgrade(Config("alembic.ini"), "0003_tenant_rls")
    with connect() as conn:
        assert (
            conn.execute("SELECT version_num FROM workflow.alembic_version").fetchone()[0]
            == "0003_tenant_rls"
        )
        assert conn.execute("SELECT count(*) FROM identity.tenants").fetchone()[0] == 2
    url = make_url(Settings().database_url("checkpoint")).set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False)) as runtime:
        assert runtime.execute("SELECT current_schema()").fetchone()[0] == "checkpoints"
        assert runtime.execute("SELECT count(*) FROM checkpoints").fetchone()[0] == 0
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM pg_class WHERE relnamespace IN "
                "('domain'::regnamespace,'workflow'::regnamespace,'checkpoints'::regnamespace) "
                "AND relrowsecurity AND relforcerowsecurity"
            ).fetchone()[0]
            == 11
        )


def test_fixture_mvp_upgrade_preserves_rows_pending_interrupt_and_ticket():
    reset()
    command.upgrade(Config("alembic.ini"), "0002_search_indexes")
    legacy_fixture()
    before = snapshot()
    command.upgrade(Config("alembic.ini"), "0003_tenant_rls")
    assert snapshot() == before
    with connect() as conn:
        for table in TABLES:
            assert (
                conn.execute(
                    sql.SQL("SELECT count(*) FROM {} WHERE tenant_id IS DISTINCT FROM %s").format(
                        sql.SQL(table)
                    ),
                    (DEMO_TENANT,),
                ).fetchone()[0]
                == 0
            )


@pytest.mark.parametrize("unknown", ["customer", "checkpoint"])
def test_unknown_ownership_blocks_and_rolls_back(unknown):
    reset()
    command.upgrade(Config("alembic.ini"), "0002_search_indexes")
    legacy_fixture()
    with connect() as conn:
        if unknown == "customer":
            insert(
                conn,
                "domain.customers",
                dict(id=UUID(int=999), name="Unmapped", normalized_name="unmapped", metadata={}),
            )
        else:
            insert(
                conn,
                "checkpoints.checkpoints",
                dict(thread_id="unknown-orphan", checkpoint_id="orphan", checkpoint={}),
            )
    with pytest.raises(RuntimeError, match="explicit mapping"):
        command.upgrade(Config("alembic.ini"), "0003_tenant_rls")
    with connect() as conn:
        assert (
            conn.execute("SELECT version_num FROM workflow.alembic_version").fetchone()[0]
            == "0002_search_indexes"
        )
        assert conn.execute("SELECT to_regnamespace('identity')").fetchone()[0] is None
