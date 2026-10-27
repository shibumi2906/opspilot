"""F08 real PostgreSQL/checkpointer/MCP gates, without vendor calls."""

import asyncio
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from opspilot.contracts.api import CancelRun, ClarificationAnswer, CreateRun, Decision
from opspilot.runtime.actions import Conflict
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one


def choice(form, index=0):
    return ClarificationAnswer(
        clarification_id=form["id"],
        expected_version=form["version"],
        kind=form["kind"],
        choice=form["options"][index]["id"],
        command_id=uuid4(),
    )


async def create(service, request="Investigate Green"):
    value = await service.create(CreateRun(request=request, client_request_id=uuid4()))
    run = UUID(value["run_id"])
    await process_one(service, run)
    return run, await service.snapshot(run)


@pytest.mark.parametrize("user_text", ["Investigate Green", "Расследуй Green"])
async def test_restart_pending_answer_replay(integration_settings, user_text):
    service = RunService(integration_settings)
    try:
        run, pending = await create(service, user_text)
        assert pending["status"] == "waiting_for_input", pending
        form = pending["clarification"]
        assert form["kind"] == "customer" and len(form["options"]) >= 2
        # New OS process reads/reconciles the persisted interrupt, without an answer.
        code = """import asyncio,sys
from uuid import UUID
from opspilot.config import Settings
from opspilot.runtime.run_service import RunService
from opspilot.runtime.recovery import recover
from opspilot.tenancy.context import tenant_scope
async def main():
 s=Settings()
 with tenant_scope(s.local_demo_tenant):
  service=RunService(s)
  await recover(service,UUID(sys.argv[1]))
  assert (await service.snapshot(UUID(sys.argv[1])))["status"]=="waiting_for_input"
  await service.close()
asyncio.run(main())
"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            str(run),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await asyncio.wait_for(proc.communicate(), 30)
        assert proc.returncode == 0, err.decode()[-1000:]
        assert (await service.snapshot(run))["clarification"] == form
        answer = choice(form)
        with pytest.raises(Conflict):
            await service.clarify(run, answer.model_copy(update={"choice": str(uuid4())}))
        with pytest.raises(Conflict):
            await service.clarify(run, answer.model_copy(update={"expected_version": 2}))
        await asyncio.gather(service.clarify(run, answer), service.clarify(run, answer))
        with pytest.raises(Conflict):
            await service.clarify(run, choice(form, 1))
        # Close/reopen service after answer commit before worker resumes.
        await service.close()
        service = RunService(integration_settings)
        await process_one(service, run)
        final = await service.snapshot(run)
        assert final["status"] == "waiting_for_approval", final
        assert final["action"]["arguments"]["customer_id"] == answer.choice
        await service.clarify(run, answer)  # lost-response replay remains harmless
    finally:
        await service.close()


async def test_answer_transaction_rollback(integration_settings, admin_engine, monkeypatch):
    import opspilot.runtime.human_commands as commands

    service = RunService(integration_settings)
    try:
        run, pending = await create(service)

        async def fail(*args):
            raise RuntimeError("injected before queue commit")

        monkeypatch.setattr(commands, "enqueue", fail)
        with pytest.raises(RuntimeError):
            await service.clarify(run, choice(pending["clarification"]))
        after = await service.snapshot(run)
        assert after["status"] == "waiting_for_input"
        assert not after["clarification"].get("answer")
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM workflow.command_jobs "
                        "WHERE run_id=:r AND kind LIKE 'clarify%'"
                    ),
                    {"r": run},
                )
                == 0
            )
    finally:
        await service.close()


async def test_expired_interrupt(integration_settings):
    service = RunService(integration_settings.model_copy(update={"clarification_ttl_seconds": 1}))
    try:
        run, pending = await create(service)
        await asyncio.sleep(1.05)
        with pytest.raises(Conflict):
            await service.clarify(run, choice(pending["clarification"]))
        await process_one(service, run)
        final = await service.snapshot(run)
        assert final["status"] == "completed" and final["outcome"] == "insufficient_context", final
    finally:
        await service.close()


@pytest.mark.parametrize(
    "user_text,clock,offset",
    [
        ("Check GreenShop status today timezone", "2026-10-24T09:00:00+00:00", 3),
        ("Проверь статус GreenShop сегодня часовой пояс", "2026-10-26T09:00:00+00:00", 2),
    ],
)
async def test_timezone_ru_en_dst(integration_settings, user_text, clock, offset):
    from opspilot.agent.checkpoints import postgres_checkpointer

    settings = integration_settings.model_copy(
        update={"scenario_clock": datetime.fromisoformat(clock)}
    )
    service = RunService(settings)
    try:
        run, pending = await create(service, user_text)
        assert pending["clarification"]["kind"] == "timezone"
        await service.clarify(run, choice(pending["clarification"]))
        await process_one(service, run)
        final = await service.snapshot(run)
        assert final["outcome"] == "diagnosis_only", final
        async with postgres_checkpointer(settings) as saver:
            saved = await saver.aget_tuple({"configurable": {"thread_id": str(run)}})
        window = saved.checkpoint["channel_values"]["time_window"]
        assert datetime.fromisoformat(window["from"]).astimezone(UTC).hour == 24 - offset
    finally:
        await service.close()


@pytest.mark.parametrize("waiting", ["queued", "clarification", "approval"])
async def test_cancel_queued_waiting(integration_settings, waiting):
    service = RunService(integration_settings)
    try:
        request = "Investigate GreenShop" if waiting == "approval" else "Investigate Green"
        value = await service.create(CreateRun(request=request, client_request_id=uuid4()))
        run = UUID(value["run_id"])
        if waiting != "queued":
            await process_one(service, run)
        pending = await service.snapshot(run)
        body = CancelRun(command_id=uuid4())
        await service.cancel(run, body)
        await service.cancel(run, body)
        if waiting == "clarification":
            with pytest.raises(Conflict):
                await service.clarify(run, choice(pending["clarification"]))
        if waiting == "approval":
            with pytest.raises(Conflict):
                await service.decide(
                    run, Decision(action_id=pending["action"]["action_id"], decision="approve")
                )
        await process_one(service, run)
        final = await service.snapshot(run)
        assert final["status"] == "cancelled" and final["report"]["ticket_id"] is None, final
        assert final["report"]["outcome"] == "cancelled"
    finally:
        await service.close()


async def test_cancel_running_stops_next_dispatch(integration_settings, monkeypatch):
    from opspilot.llm.scripted import ScriptedProvider

    entered, release = asyncio.Event(), asyncio.Event()
    original = ScriptedProvider.complete
    calls = []

    async def blocked(self, operation, context):
        calls.append(operation)
        entered.set()
        await release.wait()
        return await original(self, operation, context)

    monkeypatch.setattr(ScriptedProvider, "complete", blocked)
    service = RunService(integration_settings)
    try:
        created = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        run = UUID(created["run_id"])
        task = asyncio.create_task(process_one(service, run))
        await asyncio.wait_for(entered.wait(), 15)
        await service.cancel(run, CancelRun(command_id=uuid4()))
        release.set()
        await asyncio.wait_for(task, 20)
        assert (await service.snapshot(run))["status"] == "cancelled"
        assert calls == ["classify"]
    finally:
        release.set()
        await service.close()


@pytest.mark.parametrize("committed", [False, True])
async def test_cancel_racing_local_write(
    integration_settings, monkeypatch, admin_engine, committed
):
    from opspilot.mcp_client.client import MCPClient

    original = MCPClient.call
    entered, release = asyncio.Event(), asyncio.Event()

    async def call(session, name, arguments):
        if name == "create_ticket" and not committed:
            entered.set()
            await release.wait()
        result = await original(session, name, arguments)
        if name == "create_ticket" and committed:
            assert result.ok
            entered.set()
            await release.wait()  # committed receipt, response not yet delivered
        return result

    monkeypatch.setattr(MCPClient, "call", staticmethod(call))
    service = RunService(integration_settings)
    try:
        run, pending = await create(service, "Investigate GreenShop")
        await service.decide(
            run, Decision(action_id=pending["action"]["action_id"], decision="approve")
        )
        task = asyncio.create_task(process_one(service, run))
        await asyncio.wait_for(entered.wait(), 15)
        await service.cancel(run, CancelRun(command_id=uuid4()))
        release.set()
        await asyncio.wait_for(task, 30)
        final = await service.snapshot(run)
        assert final["status"] == "cancelled", final
        assert bool(final["report"]["ticket_id"]) is committed
        async with admin_engine.connect() as conn:
            assert await conn.scalar(
                text("SELECT count(*) FROM domain.tickets WHERE originating_action_id=:a"),
                {"a": UUID(pending["action"]["action_id"])},
            ) == int(committed)
    finally:
        release.set()
        await service.close()


async def test_two_rounds_integration_and_command_replay(integration_settings, admin_engine):
    from opspilot.fixtures.loader import GREENSHOP_ID

    extra = uuid4()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO domain.customer_integrations"
                "(tenant_id,id,customer_id,integration_type,external_ref) "
                "VALUES(:t,:i,:c,'fixture-extra',:ref)"
            ),
            {
                "t": integration_settings.local_demo_tenant,
                "i": extra,
                "c": UUID(GREENSHOP_ID),
                "ref": str(extra),
            },
        )
    service = RunService(integration_settings)
    try:
        run, pending = await create(service)
        form = pending["clarification"]
        answer = choice(form)
        answer = answer.model_copy(update={"choice": GREENSHOP_ID})
        await service.clarify(run, answer)
        await process_one(service, run)
        second = (await service.snapshot(run))["clarification"]
        assert second["kind"] == "integration" and second["version"] == 2
        await service.clarify(run, answer)  # old round command response was lost
        with pytest.raises(Conflict):
            await service.clarify(run, answer.model_copy(update={"command_id": uuid4()}))
        selected = choice(second)
        selected = selected.model_copy(
            update={"choice": next(o["id"] for o in second["options"] if o["id"] != str(extra))}
        )
        await service.clarify(run, selected)
        await process_one(service, run)
        assert (await service.snapshot(run))["status"] == "waiting_for_approval"
    finally:
        await service.close()
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM domain.customer_integrations WHERE id=:i"), {"i": extra}
            )


async def test_round_limit_and_accepted_answer_outlives_ttl(integration_settings):
    from opspilot.agent.budgets import Budget, BudgetLimits
    from opspilot.agent.nodes.clarify import prepare
    from opspilot.agent.runtime import Runtime
    from opspilot.llm.scripted import ScriptedProvider

    state = {"run_id": str(uuid4()), "clarification_round": 2}
    prepare(
        state,
        Runtime(integration_settings, ScriptedProvider(), Budget(BudgetLimits())),
        "timezone",
        [{"id": "UTC", "label": "UTC"}],
    )
    assert state["outcome"] == "insufficient_context" and state["clarification"] is None
    service = RunService(integration_settings.model_copy(update={"clarification_ttl_seconds": 2}))
    try:
        run, pending = await create(service)
        await service.clarify(run, choice(pending["clarification"]))
        await asyncio.sleep(2.05)
        await process_one(service, run)
        assert (await service.snapshot(run))["status"] == "waiting_for_approval"
    finally:
        await service.close()


async def test_http_owner_role_tenant_csrf_and_command_conflict(integration_settings):
    import httpx

    from opspilot.tenancy.context import SECOND_TENANT
    from tests.auth_helpers import session_client
    from tests.integration.test_authorization import ready

    async with (
        httpx.AsyncClient(base_url="http://api:8000") as owner,
        httpx.AsyncClient(base_url="http://api:8000") as other,
    ):
        await session_client(owner, integration_settings, "operator")
        created = await owner.post(
            "/api/v2/runs", json={"request": "Investigate Green", "client_request_id": str(uuid4())}
        )
        run = created.json()["run_id"]
        pending = await ready(owner, f"/api/v2/runs/{run}")
        assert pending["status"] == "waiting_for_input"
        form = pending["clarification"]
        body = choice(form).model_dump(mode="json")
        path = f"/api/v2/runs/{run}"
        await session_client(other, integration_settings, "approver")
        assert (await other.post(path + "/clarifications", json=body)).status_code == 403
        await session_client(other, integration_settings, "demo")
        assert (await other.post(path + "/clarifications", json=body)).status_code == 404
        assert (
            await other.post(path + "/cancel", json={"command_id": str(uuid4())})
        ).status_code == 404
        await session_client(other, integration_settings, "operator", SECOND_TENANT)
        assert (
            await other.post(path + "/cancel", json={"command_id": str(uuid4())})
        ).status_code == 404
        forged = {**body, "choice": str(uuid4())}
        assert (await owner.post(path + "/clarifications", json=forged)).status_code == 409
        assert (await owner.post(path + "/clarifications", json=body)).status_code == 202
        assert (
            await owner.post(
                path + "/clarifications", json={**body, "choice": form["options"][1]["id"]}
            )
        ).status_code == 409


async def test_cancel_rollback_and_opposite_answer_race(
    integration_settings, admin_engine, monkeypatch
):
    import opspilot.runtime.human_commands as commands

    service = RunService(integration_settings)
    original = commands.enqueue
    try:
        run, pending = await create(service)
        body = CancelRun(command_id=uuid4())

        async def fail(*args):
            raise RuntimeError("cancel enqueue rollback")

        monkeypatch.setattr(commands, "enqueue", fail)
        with pytest.raises(RuntimeError):
            await service.cancel(run, body)
        assert (await service.snapshot(run))["cancellation"] is None
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM workflow.human_commands WHERE run_id=:r"), {"r": run}
                )
                == 0
            )
        monkeypatch.setattr(commands, "enqueue", original)
        results = await asyncio.gather(
            service.clarify(run, choice(pending["clarification"])),
            service.cancel(run, body),
            return_exceptions=True,
        )
        assert not isinstance(results[1], Exception)
        assert not isinstance(results[0], Exception) or isinstance(results[0], Conflict)
        while await process_one(service, run):
            pass
        final = await service.snapshot(run)
        assert final["status"] == "cancelled" and final["report"]["ticket_id"] is None
    finally:
        await service.close()


async def test_cancel_serializes_with_inflight_local_transaction(
    integration_settings, admin_engine
):
    from opspilot.auth.execution import execution_scope
    from opspilot.contracts.tools import CreateTicketArgs
    from opspilot.db.engine import create_engine
    from opspilot.mcp_server.services.tickets import create_ticket
    from opspilot.runtime.fencing import execution_lease

    entered, release = asyncio.Event(), asyncio.Event()
    service = RunService(integration_settings)
    domain = create_engine(integration_settings.database_url("domain"))
    try:
        run, pending = await create(service, "Investigate GreenShop")
        card = pending["action"]
        await service.decide(run, Decision(action_id=card["action_id"], decision="approve"))

        async def after_insert():
            entered.set()
            await release.wait()

        async def write():
            async with (
                execution_scope(service.engine, run),
                execution_lease(service.engine, run, integration_settings),
            ):
                return await create_ticket(
                    domain,
                    CreateTicketArgs(
                        run_id=run, action_id=card["action_id"], arguments=card["arguments"]
                    ),
                    settings=integration_settings,
                    after_insert=after_insert,
                )

        writing = asyncio.create_task(write())
        await asyncio.wait_for(entered.wait(), 10)
        cancelling = asyncio.create_task(service.cancel(run, CancelRun(command_id=uuid4())))
        await asyncio.sleep(0.1)
        assert not cancelling.done()  # accepted write owns the serialization lock
        release.set()
        receipt = await asyncio.wait_for(writing, 10)
        await asyncio.wait_for(cancelling, 10)
        await process_one(service, run)
        final = await service.snapshot(run)
        assert final["status"] == "cancelled"
        assert final["report"]["ticket_id"] == receipt["ticket_id"]
        assert final["action"]["execution_status"] == "succeeded"
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM domain.tickets WHERE originating_action_id=:a"),
                    {"a": UUID(card["action_id"])},
                )
                == 1
            )
    finally:
        release.set()
        await domain.dispose()
        await service.close()


async def test_cancel_between_node_entry_and_write_dispatch(integration_settings, monkeypatch):
    import opspilot.agent.nodes.execute as node
    from opspilot.mcp_client.client import MCPClient

    entered, release = asyncio.Event(), asyncio.Event()
    original_saved, original_call = node.saved_action, MCPClient.call
    writes = []

    async def saved(state, runtime):
        result = await original_saved(state, runtime)
        entered.set()
        await release.wait()
        return result

    async def call(session, name, arguments):
        if name == "create_ticket":
            writes.append(arguments)
        return await original_call(session, name, arguments)

    service = RunService(integration_settings)
    try:
        run, pending = await create(service, "Investigate GreenShop")
        monkeypatch.setattr(node, "saved_action", saved)
        monkeypatch.setattr(MCPClient, "call", staticmethod(call))
        await service.decide(
            run, Decision(action_id=pending["action"]["action_id"], decision="approve")
        )
        task = asyncio.create_task(process_one(service, run))
        await asyncio.wait_for(entered.wait(), 10)
        await service.cancel(run, CancelRun(command_id=uuid4()))
        release.set()
        await asyncio.wait_for(task, 20)
        final = await service.snapshot(run)
        assert final["status"] == "cancelled" and not writes
        assert final["action"]["execution_status"] == "not_started"
    finally:
        release.set()
        await service.close()
