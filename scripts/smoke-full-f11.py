"""Local Full-only live read/queue smoke; no external provider or write request."""

import asyncio
import json
from uuid import UUID, uuid4

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.contracts.api import CreateRun
from opspilot.mcp_client.client import MCPClient
from opspilot.mcp_client.registry import ALL_TOOLS
from opspilot.runtime.run_service import RunService
from opspilot.tenancy.context import tenant_scope


async def main():
    settings = Settings()
    assert settings.llm_mode == "scripted"
    service = RunService(settings)
    try:
        with tenant_scope(settings.local_demo_tenant):
            async with service.engine.connect() as conn:
                database = await conn.scalar(text("SELECT current_database()"))
                schema = await conn.scalar(text("SELECT version_num FROM workflow.alembic_version"))
                assert database == "opspilot_full" and schema == "0013_mixed_plans"
                for table in ("ticket_comments", "notifications"):
                    flags = (
                        await conn.execute(
                            text(
                                "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
                                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                                "WHERE n.nspname='domain' AND c.relname=:t"
                            ),
                            {"t": table},
                        )
                    ).one()
                    assert all(flags)
            client = MCPClient(settings)
            async with client.session() as (session, protocol):
                tools = await client.discover(session)
            assert {t.name for t in tools} == set(ALL_TOOLS)
            created = await service.create(
                CreateRun(request="GreenShop status", client_request_id=uuid4())
            )
            run = UUID(created["run_id"])
            async with asyncio.timeout(90):
                while True:
                    result = await service.snapshot(run)
                    if result["status"] not in {"running", "queued"}:
                        break
                    await asyncio.sleep(0.2)
            assert result["status"] == "completed" and result["outcome"] == "diagnosis_only", (
                result["status"]
            )
            async with service.engine.connect() as conn:
                receipts = await conn.scalar(
                    text("SELECT count(*) FROM workflow.actions WHERE run_id=:r"), {"r": run}
                )
                events = await conn.scalar(
                    text("SELECT count(*) FROM workflow.run_events WHERE run_id=:r"), {"r": run}
                )
                audit = await conn.scalar(
                    text("SELECT count(*) FROM workflow.run_audit WHERE run_id=:r"), {"r": run}
                )
            assert receipts == 0 and events == audit and events > 0
            read_only = {
                "run_id": str(run),
                "outcome": result["outcome"],
                "events": events,
                "audit": audit,
            }
            body = CreateRun(
                request="Investigate GreenShop and notify manager and add a ticket comment",
                client_request_id=uuid4(),
            )
            mixed = await service.create(body)
            mixed_id = UUID(mixed["run_id"])

            async def wait_for(states):
                async with asyncio.timeout(90):
                    while True:
                        value = await service.snapshot(mixed_id)
                        if value["status"] in states:
                            return value
                        assert value["status"] not in {"failed", "needs_attention"}, value["status"]
                        await asyncio.sleep(0.2)

            pending = await wait_for({"waiting_for_approval"})
            assert len(pending["actions"]) == 2 and pending["plan"]["wave"] == 1
            from opspilot.contracts.api import Decision

            for card in pending["actions"]:
                await service.decide(
                    mixed_id,
                    Decision(
                        action_id=card["action_id"],
                        decision="approve",
                        expected_version=card["expected_version"],
                    ),
                )
            async with asyncio.timeout(90):
                while True:
                    pending = await service.snapshot(mixed_id)
                    if pending["status"] == "waiting_for_approval" and pending["plan"]["wave"] == 2:
                        break
                    assert pending["status"] not in {"failed", "needs_attention", "completed"}, (
                        pending["status"]
                    )
                    await asyncio.sleep(0.2)
            ticket = next(a for a in pending["actions"] if a["key"] == "ticket")
            comment = next(a for a in pending["actions"] if a["key"] == "comment")
            assert (
                comment["arguments"]["ticket_id"] == ticket["result"]["ticket_id"]
                and comment["approval_status"] == "pending"
            )
            await service.decide(
                mixed_id,
                Decision(
                    action_id=comment["action_id"],
                    decision="approve",
                    expected_version=comment["expected_version"],
                ),
            )
            final = await wait_for({"completed"})
            assert final["outcome"] == "actions_verified" and all(
                n["status"] == "verified" for n in final["plan"]["nodes"]
            )
            replay = await service.create(body)
            assert replay["run_id"] == str(mixed_id)
            async with service.engine.connect() as conn:
                receipts = await conn.scalar(
                    text(
                        "SELECT count(*) FROM workflow.actions WHERE run_id=:r "
                        "AND execution_status='succeeded'"
                    ),
                    {"r": mixed_id},
                )
                assert receipts == 3
                version = await conn.scalar(
                    text("SELECT workflow_version FROM workflow.agent_runs WHERE id=:r"),
                    {"r": mixed_id},
                )
            assert version == "full-graph-v2"
            print(
                json.dumps(
                    {
                        "database": database,
                        "schema": schema,
                        "mcp_protocol": protocol,
                        "mcp_tools": len(tools),
                        "v1_read_only": read_only,
                        "mixed_run_id": str(mixed_id),
                        "workflow_version": version,
                        "approval_waves": 2,
                        "outcome": final["outcome"],
                        "receipts": receipts,
                        "plan_nodes": final["plan"]["nodes"],
                        "replay_same_run": True,
                        "paid_calls": 0,
                    }
                )
            )
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())
