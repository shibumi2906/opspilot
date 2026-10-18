import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot.agent.service import run_investigation
from opspilot.contracts.tools import CreateTicketArgs
from opspilot.db.engine import create_engine
from opspilot.db.models_domain import Ticket
from opspilot.db.models_workflow import Action, Approval
from opspilot.mcp_client.client import MCPClient
from opspilot.mcp_server.services.tickets import create_ticket


async def pending_action(settings):
    pending = await run_investigation(settings, "Investigate GreenShop", mode="scripted")
    return CreateTicketArgs(
        run_id=pending["run_id"],
        action_id=pending["action_id"],
        arguments=pending["proposed_action"],
    )


async def set_approval(engine, action_id, decision):
    async with engine.begin() as conn:
        await conn.execute(
            update(Approval).where(Approval.action_id == action_id).values(decision=decision)
        )


async def call_write(settings, args):
    client = MCPClient(settings)
    async with client.session() as (session, _):
        return await client.call(session, "create_ticket", args.model_dump(mode="json"))


async def tickets_for(engine, action_id):
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(select(Ticket).where(Ticket.originating_action_id == action_id))
        )


@pytest.mark.parametrize(
    "case,code",
    [
        ("pending", "APPROVAL_REQUIRED"),
        ("rejected", "APPROVAL_REQUIRED"),
        ("missing", "APPROVAL_REQUIRED"),
        ("wrong_run", "STATE_CONFLICT"),
        ("tampered", "PAYLOAD_MISMATCH"),
        ("missing_approval", "APPROVAL_REQUIRED"),
        ("wrong_hash", "PAYLOAD_MISMATCH"),
    ],
)
async def test_direct_mcp_write_barrier(integration_settings, admin_engine, case, code):
    args = await pending_action(integration_settings)
    original_id = args.action_id
    if case not in {"pending", "rejected"}:
        await set_approval(admin_engine, args.action_id, "approved")
    if case == "rejected":
        await set_approval(admin_engine, args.action_id, "rejected")
    elif case == "missing":
        args = args.model_copy(update={"action_id": uuid4()})
    elif case == "wrong_run":
        args = args.model_copy(update={"run_id": uuid4()})
    elif case == "tampered":
        args = args.model_copy(
            update={"arguments": args.arguments.model_copy(update={"title": "tampered"})}
        )
    elif case == "wrong_hash":
        async with admin_engine.begin() as conn:
            await conn.execute(
                update(Action).where(Action.id == args.action_id).values(arguments_hash="0" * 64)
            )
    elif case == "missing_approval":
        from sqlalchemy import delete

        async with admin_engine.begin() as conn:
            await conn.execute(delete(Approval).where(Approval.action_id == args.action_id))
    result = await call_write(integration_settings, args)
    assert not result.ok and result.error.code == code
    assert not await tickets_for(admin_engine, original_id)


async def test_concurrent_writes_replay_and_exact_payload(integration_settings, admin_engine):
    args = await pending_action(integration_settings)
    await set_approval(admin_engine, args.action_id, "approved")
    results = await asyncio.gather(*(call_write(integration_settings, args) for _ in range(3)))
    assert all(result.ok for result in results), results
    assert len({result.data["ticket_id"] for result in results}) == 1
    assert sum(not result.data["replayed"] for result in results) == 1
    tickets = await tickets_for(admin_engine, args.action_id)
    assert len(tickets) == 1
    for key, value in args.arguments.model_dump().items():
        assert getattr(tickets[0], key) == value
    replay = await call_write(integration_settings, args)
    assert replay.ok and replay.data["replayed"]
    tampered = args.model_copy(
        update={
            "arguments": args.arguments.model_copy(update={"description": "changed after commit"})
        }
    )
    denied = await call_write(integration_settings, tampered)
    assert not denied.ok and denied.error.code == "PAYLOAD_MISMATCH"
    assert len(await tickets_for(admin_engine, args.action_id)) == 1


async def test_failure_after_insert_rolls_back_both_records(integration_settings, admin_engine):
    args = await pending_action(integration_settings)
    await set_approval(admin_engine, args.action_id, "approved")
    engine = create_engine(integration_settings.database_url("domain"))

    async def fail():
        raise RuntimeError("test-only fault after insert")

    try:
        with pytest.raises(RuntimeError, match="test-only"):
            await create_ticket(engine, args, after_insert=fail)
    finally:
        await engine.dispose()
    assert not await tickets_for(admin_engine, args.action_id)
    async with AsyncSession(admin_engine) as session:
        action = await session.get(Action, args.action_id)
        assert action.execution_status == "not_started" and action.execution_result is None
    result = await call_write(integration_settings, args)
    assert result.ok and not result.data["replayed"]
    assert len(await tickets_for(admin_engine, args.action_id)) == 1


@pytest.mark.parametrize("extra", [{"approval_status": "approved"}, {"after_insert": "fault"}])
async def test_raw_mcp_write_rejects_extra_grants(integration_settings, admin_engine, extra):
    args = await pending_action(integration_settings)
    async with MCPClient(integration_settings).session() as (session, _):
        response = await session.call_tool(
            "create_ticket", {**args.model_dump(mode="json"), **extra}
        )
    assert response.isError
    assert response.structuredContent["error"]["code"] == "INVALID_ARGUMENTS"
    assert not await tickets_for(admin_engine, args.action_id)
