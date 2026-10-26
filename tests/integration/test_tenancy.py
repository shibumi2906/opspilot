from uuid import uuid4, uuid5

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.db.engine import create_engine
from opspilot.db.models_domain import Customer
from opspilot.mcp_server.services.customers import get_customer
from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT, TenantContextError, tenant_scope
from opspilot.tenancy.session import TenantSession
from tests.tenant_helpers import register_probe

A = DEMO_TENANT
B = SECOND_TENANT
CUSTOMER_A = "00000000-0000-0000-0000-000000000001"
CUSTOMER_B = uuid5(B, CUSTOMER_A)


@pytest.mark.parametrize(
    "role,table",
    [
        ("domain", "domain.customers"),
        ("domain", "domain.customer_integrations"),
        ("domain", "domain.incidents"),
        ("domain", "domain.knowledge_articles"),
        ("domain", "domain.tickets"),
        ("workflow", "workflow.agent_runs"),
        ("workflow", "workflow.actions"),
        ("workflow", "workflow.approvals"),
        ("checkpoint", "checkpoints.checkpoints"),
        ("checkpoint", "checkpoints.checkpoint_blobs"),
        ("checkpoint", "checkpoints.checkpoint_writes"),
    ],
)
async def test_no_context_is_default_deny(integration_settings, role, table):
    engine = create_engine(integration_settings.database_url(role))
    try:
        with tenant_scope(None):
            async with engine.connect() as conn:
                assert await conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0
    finally:
        await engine.dispose()


async def test_pool_context_resets_and_duplicate_names_are_scoped(integration_settings):
    engine = create_engine(integration_settings.database_url("domain"))
    try:
        pids = []
        for tenant, expected in [
            (A, CUSTOMER_A),
            (None, None),
            (B, str(CUSTOMER_B)),
            (A, CUSTOMER_A),
        ]:
            with tenant_scope(tenant):
                async with engine.begin() as conn:
                    pids.append(await conn.scalar(text("SELECT pg_backend_pid()")))
                    ids = list(
                        await conn.scalars(
                            text("SELECT id::text FROM domain.customers WHERE name='GreenShop'")
                        )
                    )
                    assert ids == ([] if expected is None else [expected])
        assert len(set(pids)) == 1  # exercise the same physical pooled connection
    finally:
        await engine.dispose()


@pytest.mark.parametrize("role", ["workflow", "domain", "checkpoint"])
async def test_runtime_roles_cannot_bypass_or_disable_rls(integration_settings, role):
    engine = create_engine(integration_settings.database_url(role))
    table = {
        "workflow": "workflow.agent_runs",
        "domain": "domain.customers",
        "checkpoint": "checkpoints.checkpoints",
    }[role]
    try:
        async with engine.connect() as conn:
            flags = (
                await conn.execute(
                    text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
                )
            ).one()
            assert flags == (False, False)
            attrs = (
                await conn.execute(
                    text(
                        "SELECT "
                        "relrowsecurity,relforcerowsecurity,pg_get_userbyid(relowner)=current_user "
                        "FROM pg_class WHERE oid=CAST(:table AS regclass)"
                    ),
                    {"table": table},
                )
            ).one()
            assert attrs == (True, True, False)
            with pytest.raises(DBAPIError):
                await conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    finally:
        await engine.dispose()


@pytest.mark.parametrize("tenant", [None, B])
async def test_insert_cannot_claim_another_tenant(integration_settings, tenant):
    engine = create_engine(integration_settings.database_url("workflow"))
    try:
        with tenant_scope(tenant):
            async with engine.begin() as conn:
                with pytest.raises(DBAPIError):
                    await conn.execute(
                        text(
                            "INSERT INTO workflow.approvals(id,tenant_id,action_id) VALUES "
                            "(:id,:tenant,:action)"
                        ),
                        {"id": uuid4(), "tenant": A, "action": uuid5(A, "seed-action")},
                    )
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "statement,params",
    [
        (
            "UPDATE workflow.actions SET run_id=:foreign WHERE id=:id",
            {"foreign": uuid5(B, "seed-run"), "id": uuid5(A, "seed-action")},
        ),
        (
            "UPDATE workflow.agent_runs SET tenant_id=:foreign WHERE id=:id",
            {"foreign": B, "id": uuid5(A, "seed-run")},
        ),
        (
            "INSERT INTO workflow.approvals(id,tenant_id,action_id) VALUES (:id,:tenant,:foreign)",
            {"id": uuid4(), "tenant": A, "foreign": uuid5(B, "seed-action")},
        ),
    ],
)
async def test_cross_tenant_update_or_composite_fk_is_rejected(
    integration_settings, statement, params
):
    engine = create_engine(integration_settings.database_url("workflow"))
    try:
        async with engine.begin() as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(text(statement), params)
    finally:
        await engine.dispose()


async def test_ticket_customer_and_action_must_share_tenant(integration_settings):
    engine = create_engine(integration_settings.database_url("domain"))
    try:
        async with engine.begin() as conn:
            with pytest.raises(DBAPIError) as error:
                await conn.execute(
                    text(
                        "INSERT INTO "
                        "domain.tickets(id,tenant_id,customer_id,originating_action_id, "
                        "title,description,priority, "
                        "evidence_ids) "
                        "VALUES (:id,:tenant,:customer,:action,'x','x','low','[]')"
                    ),
                    {
                        "id": uuid4(),
                        "tenant": A,
                        "customer": CUSTOMER_B,
                        "action": uuid5(A, "seed-action"),
                    },
                )
            # FK or the existing action uniqueness both deny this malformed row.
            assert error.value.orig.sqlstate in {"23503", "23505"}
    finally:
        await engine.dispose()


async def test_repository_and_identity_map_never_cross_scope(integration_settings):
    engine = create_engine(integration_settings.database_url("domain"))
    try:
        with tenant_scope(A):
            assert (await get_customer(engine, CUSTOMER_B)) is None
            async with TenantSession(engine) as session:
                customer = await session.get(Customer, CUSTOMER_A)
                assert customer.name == "GreenShop"
                with tenant_scope(B), pytest.raises(TenantContextError):
                    await session.get(Customer, CUSTOMER_A)
        with tenant_scope(B):
            assert (await get_customer(engine, CUSTOMER_B)).name == "GreenShop"
            async with TenantSession(engine) as session:
                assert all(c.tenant_id == B for c in await session.scalars(select(Customer)))
        with tenant_scope(None), pytest.raises(TenantContextError):
            await get_customer(engine, CUSTOMER_A)
    finally:
        await engine.dispose()


async def test_checkpoint_thread_is_hidden_from_other_tenant(integration_settings):
    from langgraph.graph import END, START, StateGraph

    thread = "tenant-probe-" + str(uuid4())
    config = {"configurable": {"thread_id": thread}}
    registration = create_engine(integration_settings.database_url("workflow"))
    try:
        await register_probe(registration, integration_settings.scenario_clock, thread)
    finally:
        await registration.dispose()
    with tenant_scope(A):
        async with postgres_checkpointer(integration_settings) as saver:
            builder = StateGraph(dict)
            builder.add_node("probe", lambda state: {"value": 1})
            builder.add_edge(START, "probe")
            builder.add_edge("probe", END)
            graph = builder.compile(checkpointer=saver)
            await graph.ainvoke({}, config)
            assert await saver.aget_tuple(config) is not None
    with tenant_scope(B):
        async with postgres_checkpointer(integration_settings) as saver:
            assert await saver.aget_tuple(config) is None
            assert [row async for row in saver.alist(config)] == []


@pytest.mark.parametrize("mutation", ["insert", "update"])
async def test_customer_composite_fk_even_with_privileged_role(admin_engine, mutation):
    async with admin_engine.begin() as conn:
        with pytest.raises(DBAPIError) as error:
            if mutation == "insert":
                await conn.execute(
                    text(
                        "INSERT INTO domain.customer_integrations "
                        "(id,tenant_id,customer_id,integration_type,external_ref) "
                        "VALUES (:id,:tenant,:customer,'shopify','cross-sentinel')"
                    ),
                    {"id": uuid4(), "tenant": A, "customer": CUSTOMER_B},
                )
            else:
                await conn.execute(
                    text(
                        "UPDATE domain.customer_integrations SET customer_id=:customer, "
                        "external_ref='cross-sentinel' WHERE id=:id"
                    ),
                    {"customer": CUSTOMER_B, "id": "00000000-0000-0000-0000-000000000101"},
                )
        assert error.value.orig.sqlstate == "23503"


async def test_checkpoint_cannot_reference_foreign_run_even_as_admin(admin_engine):
    async with admin_engine.begin() as conn:
        with pytest.raises(DBAPIError) as error:
            await conn.execute(
                text(
                    "INSERT INTO checkpoints.checkpoints "
                    "(tenant_id,thread_id,checkpoint_id,checkpoint) "
                    "VALUES (:a,:thread,'cross','{}')"
                ),
                {"a": A, "thread": str(uuid5(B, "seed-run"))},
            )
        assert error.value.orig.sqlstate == "23503"


async def test_client_command_keys_are_scoped_to_tenant(admin_engine):
    key = uuid4()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE workflow.agent_runs SET client_request_id=:key WHERE id IN (:a,:b)"),
            {"key": key, "a": uuid5(A, "seed-run"), "b": uuid5(B, "seed-run")},
        )
        assert (
            await conn.scalar(
                text("SELECT count(*) FROM workflow.agent_runs WHERE client_request_id=:key"),
                {"key": key},
            )
            == 2
        )
        await conn.rollback()
