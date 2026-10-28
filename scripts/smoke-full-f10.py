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
                assert database == "opspilot_full" and schema == "0012_local_operations"
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
            print(
                json.dumps(
                    {
                        "database": database,
                        "schema": schema,
                        "mcp_protocol": protocol,
                        "mcp_tools": len(tools),
                        "run_id": str(run),
                        "outcome": result["outcome"],
                        "read_only_run_actions": receipts,
                        "event_count": events,
                        "audit_count": audit,
                        "force_rls": True,
                        "paid_calls": 0,
                    }
                )
            )
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())
