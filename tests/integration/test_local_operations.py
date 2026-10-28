"""F10 real PostgreSQL and MCP operations; no mocked domain writes."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from opspilot.agent.nodes.execute import execute
from opspilot.agent.nodes.verify import verify
from opspilot.auth.context import actor_id
from opspilot.auth.service_context import action_scope, run_scope
from opspilot.contracts.common import ToolError, ToolResult
from opspilot.db.engine import create_engine
from opspilot.db.models_domain import Customer
from opspilot.db.models_workflow import AgentRun
from opspilot.mcp_client.client import MCPClient
from opspilot.mcp_client.registry import WRITE_TOOLS
from opspilot.mcp_server.services.tickets import local_write
from opspilot.runtime.actions import payload_hash, prepare
from opspilot.runtime.fencing import execution_lease
from opspilot.security.grants import grant_scope, issue
from opspilot.tenancy.context import SECOND_TENANT, require_tenant, tenant_scope
from opspilot.tenancy.session import TenantSession

KINDS = ["create_ticket", "add_ticket_comment", "notify_manager"]
MAPPING = {
    "create_ticket": ("tickets", "get_ticket", "ticket_id"),
    "add_ticket_comment": ("ticket_comments", "get_ticket_comment", "comment_id"),
    "notify_manager": ("notifications", "get_notification", "notification_id"),
}
BODY = "<img src=x onerror=alert(1)> javascript:alert(1) \u2028 Тест"


async def setup_action(settings, admin, engine, kind, overrides=None):
    async with admin.connect() as conn:
        customer = await conn.scalar(
            select(Customer.id).where(
                Customer.name == "GreenShop", Customer.tenant_id == require_tenant()
            )
        )
        if customer is None:
            customer = await conn.scalar(
                select(Customer.id).where(Customer.tenant_id == require_tenant()).limit(1)
            )
    arguments = {"customer_id": str(customer), "evidence_ids": ["synthetic:evidence"]}
    if kind == "create_ticket":
        arguments.update(title="F10 local test", description=BODY, priority="medium")
    elif kind == "add_ticket_comment":
        ticket_args = await setup_action(settings, admin, engine, "create_ticket")
        async with execution_lease(engine, ticket_args.run_id, settings):
            result = await rpc(settings, "create_ticket", ticket_args)
        assert result.ok, result
        arguments.update(ticket_id=result.data["ticket_id"], body=BODY)
    else:
        arguments.update(recipient_id=str(actor_id()), body=BODY)
    arguments.update(overrides or {})
    run_id = uuid4()
    async with TenantSession(admin) as session, session.begin():
        session.add(
            AgentRun(
                id=run_id,
                client_request_id=uuid4(),
                request="F10 synthetic operation",
                request_hash=payload_hash(arguments),
                language="en",
                status="waiting_for_approval",
                mode="scripted",
                scenario_id=settings.scenario_id,
                scenario_clock=settings.scenario_clock,
                thread_id=str(run_id),
            )
        )
    async with execution_lease(engine, run_id, settings):
        async with TenantSession(engine) as session, session.begin():
            action = await prepare(session, run_id, arguments, settings, tool=kind)
            action_id = action.id
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "UPDATE workflow.approvals SET decision='approved',decided_by=:u,"
                "decided_at=clock_timestamp(),self_approval_exception=true WHERE action_id=:a"
            ),
            {"u": actor_id(), "a": action_id},
        )
    return WRITE_TOOLS[kind].arguments.model_validate(
        {"run_id": run_id, "action_id": action_id, "arguments": arguments}
    )


async def rpc(settings, kind, args):
    with action_scope(
        str(args.run_id),
        str(args.action_id),
        payload_hash(args.arguments.model_dump(mode="json")),
        tool=kind,
    ):
        async with MCPClient(settings).session() as (session, _):
            return await MCPClient.call(session, kind, args.model_dump(mode="json"))


async def count(admin, kind, args):
    table = MAPPING[kind][0]
    async with admin.connect() as conn:
        return await conn.scalar(
            text(f"SELECT count(*) FROM domain.{table} WHERE originating_action_id=:a"),
            {"a": args.action_id},
        )


@pytest.mark.parametrize("kind", KINDS)
async def test_local_concurrent_replay_exact_read(integration_settings, admin_engine, kind):
    settings = integration_settings
    engine = create_engine(settings.database_url("workflow"))
    try:
        args = await setup_action(settings, admin_engine, engine, kind)
        async with execution_lease(engine, args.run_id, settings):
            results = await asyncio.gather(*(rpc(settings, kind, args) for _ in range(4)))
        assert all(r.ok for r in results), results
        _, read, key = MAPPING[kind]
        assert len({r.data[key] for r in results}) == 1
        assert sum(not r.data["replayed"] for r in results) == 1
        with run_scope(str(args.run_id)):
            async with MCPClient(settings).session() as (session, _):
                result = await MCPClient.call(session, read, {key: results[0].data[key]})
        assert result.ok, result
        expected = {
            **args.arguments.model_dump(mode="json"),
            key: results[0].data[key],
            "created_at": results[0].data["created_at"],
            "originating_action_id": str(args.action_id),
        }
        if kind == "create_ticket":
            expected["status"] = "open"
        assert result.data == expected
        assert await count(admin_engine, kind, args) == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize("kind", KINDS)
async def test_no_grant_and_changed_fields_never_write(
    integration_settings, admin_engine, monkeypatch, kind
):
    settings = integration_settings
    engine = create_engine(settings.database_url("workflow"))
    try:
        args = await setup_action(settings, admin_engine, engine, kind)
        async with execution_lease(engine, args.run_id, settings):
            from opspilot.auth.context import AuthError

            async def missing(*a, **kw):
                raise AuthError("GRANT_REQUIRED")

            with monkeypatch.context() as m:
                m.setattr("opspilot.mcp_client.client.issue", missing)
                result = await rpc(settings, kind, args)
            assert not result.ok and result.error.code == "GRANT_REQUIRED"
            data = args.model_dump(mode="json")
            data["arguments"]["title" if kind == "create_ticket" else "body"] = "unapproved"
            changed = WRITE_TOOLS[kind].arguments.model_validate(data)
            result = await rpc(settings, kind, changed)
            assert not result.ok
        assert await count(admin_engine, kind, args) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize("kind", KINDS)
async def test_rollback_keeps_grant_and_receipt_atomic(integration_settings, admin_engine, kind):
    settings = integration_settings
    engine = create_engine(settings.database_url("workflow"))
    domain = create_engine(settings.database_url("domain"))
    try:
        args = await setup_action(settings, admin_engine, engine, kind)
        async with execution_lease(engine, args.run_id, settings):
            token = await issue(
                settings,
                {
                    "run": str(args.run_id),
                    "action": str(args.action_id),
                    "hash": payload_hash(args.arguments.model_dump(mode="json")),
                    "tool": kind,
                },
            )

            async def fail():
                raise RuntimeError("synthetic rollback")

            with grant_scope(token), pytest.raises(RuntimeError, match="synthetic rollback"):
                await local_write(domain, args, settings=settings, tool=kind, after_insert=fail)
            assert await count(admin_engine, kind, args) == 0
            with grant_scope(token):
                result = await local_write(domain, args, settings=settings, tool=kind)
            assert not result["replayed"]
        assert await count(admin_engine, kind, args) == 1
    finally:
        await engine.dispose()
        await domain.dispose()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("fault", ["lost_response", "missing", "mismatch"])
async def test_execution_and_independent_verification(
    integration_settings, admin_engine, kind, fault
):
    settings = integration_settings
    engine = create_engine(settings.database_url("workflow"))
    original = MCPClient.call

    class Client(MCPClient):
        @staticmethod
        async def call(session, name, arguments):
            result = await original(session, name, arguments)
            if name == kind and fault == "lost_response":
                assert result.ok
                raise TimeoutError("private transport sentinel")
            return result

    try:
        args = await setup_action(settings, admin_engine, engine, kind)

        async def read(name, arguments, state, **kw):
            with run_scope(str(args.run_id)):
                async with MCPClient(settings).session() as (session, _):
                    result = await original(session, name, arguments)
            assert result.ok, result
            if fault == "missing":
                return ToolResult(
                    ok=False,
                    observed_at=settings.scenario_clock,
                    error=ToolError(code="NOT_FOUND", message="Not found"),
                )
            if fault == "mismatch":
                return result.model_copy(
                    update={
                        "data": {
                            **result.data,
                            "title" if kind == "create_ticket" else "body": "unexpected",
                        }
                    }
                )
            return result

        runtime = SimpleNamespace(
            settings=settings,
            client=Client(settings),
            budget=SimpleNamespace(check=lambda: None),
            read=read,
        )
        state = {"run_id": str(args.run_id), "action_id": str(args.action_id), "errors": {}}
        async with execution_lease(engine, args.run_id, settings):
            await execute(state, runtime)
            assert state.get("execution_result"), state
            await verify(state, runtime)
        assert (
            state["verification_result"]["status"]
            == {"lost_response": "verified", "missing": "unknown", "mismatch": "mismatch"}[fault]
        )
        assert (
            state["outcome"]
            == {
                "lost_response": "actions_verified",
                "missing": "unknown_outcome",
                "mismatch": "partial",
            }[fault]
        )
        assert "private transport sentinel" not in str(state)
        assert await count(admin_engine, kind, args) == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "kind,field", [("add_ticket_comment", "ticket_id"), ("notify_manager", "recipient_id")]
)
async def test_unknown_targets_never_write(integration_settings, admin_engine, kind, field):
    engine = create_engine(integration_settings.database_url("workflow"))
    try:
        args = await setup_action(
            integration_settings, admin_engine, engine, kind, {field: str(uuid4())}
        )
        async with execution_lease(engine, args.run_id, integration_settings):
            result = await rpc(integration_settings, kind, args)
        assert not result.ok and result.error.code == "NOT_FOUND", result
        assert await count(admin_engine, kind, args) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize("kind", ["add_ticket_comment", "notify_manager"])
async def test_foreign_existing_targets_and_reads(integration_settings, admin_engine, kind):
    settings = integration_settings
    engine = create_engine(settings.database_url("workflow"))
    try:
        if kind == "add_ticket_comment":
            with tenant_scope(SECOND_TENANT):
                foreign = await setup_action(settings, admin_engine, engine, "create_ticket")
                async with execution_lease(engine, foreign.run_id, settings):
                    result = await rpc(settings, "create_ticket", foreign)
                assert result.ok
                target = result.data["ticket_id"]
            field = "ticket_id"
        else:
            from opspilot.db.models_identity import User

            async with TenantSession(admin_engine) as session, session.begin():
                user = User(id=uuid4(), issuer="urn:f10:synthetic", subject=str(uuid4()))
                session.add(user)
                await session.flush()
                target = str(user.id)
                await session.execute(
                    text(
                        "INSERT INTO identity.tenant_memberships(tenant_id,user_id,role) "
                        "VALUES(:t,:u,'operator')"
                    ),
                    {"t": SECOND_TENANT, "u": user.id},
                )
            field = "recipient_id"
        args = await setup_action(settings, admin_engine, engine, kind, {field: target})
        async with execution_lease(engine, args.run_id, settings):
            result = await rpc(settings, kind, args)
        assert not result.ok and result.error.code == "NOT_FOUND", result
        assert await count(admin_engine, kind, args) == 0
        # A real, persisted object in another tenant cannot be read by ID.
        own = await setup_action(settings, admin_engine, engine, kind)
        async with execution_lease(engine, own.run_id, settings):
            result = await rpc(settings, kind, own)
        assert result.ok
        _, read, key = MAPPING[kind]
        with tenant_scope(SECOND_TENANT):
            async with MCPClient(settings).session() as (session, _):
                denied = await MCPClient.call(session, read, {key: result.data[key]})
        assert not denied.ok and denied.error.code == "NOT_FOUND", denied
    finally:
        await engine.dispose()


@pytest.mark.parametrize("kind", ["add_ticket_comment", "notify_manager"])
async def test_other_operator_cannot_read_private_payload(integration_settings, admin_engine, kind):
    from opspilot.auth.context import Principal, auth_scope
    from opspilot.db.models_identity import User

    settings = integration_settings
    engine = create_engine(settings.database_url("workflow"))
    try:
        args = await setup_action(settings, admin_engine, engine, kind)
        async with execution_lease(engine, args.run_id, settings):
            result = await rpc(settings, kind, args)
        assert result.ok
        async with TenantSession(admin_engine) as session, session.begin():
            user = User(id=uuid4(), issuer="urn:f10:operator", subject=str(uuid4()))
            session.add(user)
            await session.flush()
            await session.execute(
                text(
                    "INSERT INTO identity.tenant_memberships(tenant_id,user_id,role) "
                    "VALUES(:t,:u,'operator')"
                ),
                {"t": require_tenant(), "u": user.id},
            )
            user_id = user.id
        _, read, key = MAPPING[kind]
        with auth_scope(Principal(user_id, require_tenant(), frozenset({"operator"}), uuid4())):
            async with MCPClient(settings).session() as (session, _):
                denied = await MCPClient.call(session, read, {key: result.data[key]})
        assert not denied.ok and denied.error.code == "NOT_FOUND", denied
        async with admin_engine.connect() as conn:
            for table, column in [("run_events", "payload"), ("run_audit", "diff")]:
                # Only bounded public event metadata may be copied into audit/event storage.
                rows = await conn.scalars(
                    text(f"SELECT {column}::text FROM workflow.{table} WHERE run_id=:r"),
                    {"r": args.run_id},
                )
                assert all("onerror" not in row and "javascript:" not in row for row in rows)
    finally:
        await engine.dispose()


@pytest.mark.parametrize("change", ["disabled", "removed"])
async def test_live_recipient_revalidation(integration_settings, admin_engine, change):
    from opspilot.db.models_identity import User

    settings = integration_settings
    engine = create_engine(settings.database_url("workflow"))
    try:
        async with TenantSession(admin_engine) as session, session.begin():
            user = User(id=uuid4(), issuer="urn:f10:recipient", subject=str(uuid4()))
            session.add(user)
            await session.flush()
            await session.execute(
                text(
                    "INSERT INTO identity.tenant_memberships(tenant_id,user_id,role) "
                    "VALUES(:t,:u,'operator')"
                ),
                {"t": require_tenant(), "u": user.id},
            )
            user_id = user.id
        args = await setup_action(
            settings, admin_engine, engine, "notify_manager", {"recipient_id": str(user_id)}
        )
        async with admin_engine.begin() as conn:
            if change == "disabled":
                await conn.execute(
                    text("UPDATE identity.users SET disabled_at=clock_timestamp() WHERE id=:u"),
                    {"u": user_id},
                )
            else:
                await conn.execute(
                    text(
                        "DELETE FROM identity.tenant_memberships WHERE tenant_id=:t AND user_id=:u"
                    ),
                    {"t": require_tenant(), "u": user_id},
                )
        async with execution_lease(engine, args.run_id, settings):
            result = await rpc(settings, "notify_manager", args)
        assert not result.ok and result.error.code == "NOT_FOUND", result
        assert await count(admin_engine, "notify_manager", args) == 0
    finally:
        await engine.dispose()
