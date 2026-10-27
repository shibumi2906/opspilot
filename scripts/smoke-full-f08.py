import asyncio, json
from uuid import UUID, uuid4
from sqlalchemy import text
from opspilot.config import Settings
from opspilot.contracts.api import CreateRun, ClarificationAnswer, CancelRun
from opspilot.contracts.public import public_snapshot
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.run_service import RunService
from opspilot.tenancy.context import tenant_scope


async def wait(service, run, states):
    async with asyncio.timeout(90):
        while True:
            value = await service.snapshot(run)
            if value["status"] in states:
                return value
            assert value["status"] not in {"failed", "needs_attention"}, value["status"]
            await asyncio.sleep(0.2)


async def main():
    settings = Settings()
    assert settings.llm_mode == "scripted"
    service = RunService(settings)
    try:
        with tenant_scope(settings.local_demo_tenant):
            async with service.engine.connect() as conn:
                database = await conn.scalar(text("SELECT current_database()"))
                schema = await conn.scalar(text("SELECT version_num FROM workflow.alembic_version"))
                assert database == "opspilot_full" and schema == "0009_human_commands"
                rls = await conn.scalar(
                    text(
                        "SELECT relforcerowsecurity FROM pg_class JOIN pg_namespace n ON n.oid=relnamespace WHERE n.nspname='workflow' AND relname='human_commands'"
                    )
                )
                assert rls and not await conn.scalar(
                    text(
                        "SELECT has_table_privilege(current_user,'workflow.human_commands','UPDATE')"
                    )
                )
            client = MCPClient(settings)
            async with client.session() as (session, protocol):
                tools = await client.discover(session)
            created = await service.create(
                CreateRun(request="Investigate Green", client_request_id=uuid4())
            )
            run = UUID(created["run_id"])
            pending = await wait(service, run, {"waiting_for_input"})
            form = pending["clarification"]
            assert form["kind"] == "customer" and len(form["options"]) > 1
            await service.close()
            service = RunService(settings)
            assert (await service.snapshot(run))["clarification"] == form
            answer = ClarificationAnswer(
                clarification_id=form["id"],
                expected_version=form["version"],
                kind="customer",
                choice=next(o["id"] for o in form["options"] if o["label"] == "GreenShop"),
                command_id=uuid4(),
            )
            answered = await service.clarify(run, answer)
            await service.clarify(run, answer)
            approval = await wait(service, run, {"waiting_for_approval"})
            cancelling = await service.cancel(run, CancelRun(command_id=uuid4()))
            final = await wait(service, run, {"cancelled"})
            public = public_snapshot(final)
            assert (
                not public["report"]["ticket_id"]
                and len(public["report"]["cancelled_actions"]) == 1
            )
            async with asyncio.timeout(30):
                while True:
                    async with service.engine.connect() as conn:
                        pending_outbox = await conn.scalar(
                            text(
                                "SELECT count(*) FROM workflow.event_outbox WHERE run_id=:r AND published_at IS NULL"
                            ),
                            {"r": run},
                        )
                    if not pending_outbox:
                        break
                    await asyncio.sleep(0.2)
            async with service.engine.connect() as conn:
                events = (
                    (
                        await conn.execute(
                            text(
                                "SELECT type FROM workflow.run_events WHERE run_id=:r ORDER BY sequence"
                            ),
                            {"r": run},
                        )
                    )
                    .scalars()
                    .all()
                )
                commands = await conn.scalar(
                    text("SELECT count(*) FROM workflow.human_commands WHERE run_id=:r"), {"r": run}
                )
                audit = await conn.scalar(
                    text("SELECT count(*) FROM workflow.run_audit WHERE run_id=:r"), {"r": run}
                )
            assert "clarification.changed" in events and "run.cancel_requested" in events
            assert commands == 2 and len(events) == audit
            print(
                json.dumps(
                    dict(
                        database=database,
                        schema=schema,
                        run_id=str(run),
                        states=[
                            created["status"],
                            pending["status"],
                            answered["status"],
                            approval["status"],
                            cancelling["status"],
                            final["status"],
                        ],
                        reopened_pending_form_unchanged=True,
                        duplicate_answer_replayed=True,
                        human_commands=commands,
                        event_count=len(events),
                        audit_count=audit,
                        pending_outbox=pending_outbox,
                        rls=True,
                        ledger_update_denied=True,
                        mcp_protocol=protocol,
                        mcp_tools=len(tools),
                        report=public["report"],
                        paid_calls=0,
                    )
                )
            )
    finally:
        await service.close()


asyncio.run(main())
