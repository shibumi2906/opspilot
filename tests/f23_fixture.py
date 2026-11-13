"""Create one real pending interrupt and one committed synthetic operation for F23."""

import asyncio
import json
import os
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy.engine import make_url

from opspilot.api.main import create_app
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.evals.runner import count_tickets, database_checks, source
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.tenancy.context import DEMO_TENANT, tenant_scope
from tests.auth_helpers import session_client


async def main():
    settings = Settings()
    assert settings.app_env == "test" and settings.llm_mode == "scripted"
    assert not settings.prometheus_registry_file
    for role in ("migration", "workflow", "domain", "checkpoint", "identity"):
        url = make_url(settings.database_url(role))
        assert (url.host, url.database) == ("postgres", "opspilot_full_test")
    engine = create_engine(settings.database_url("migration"))
    try:
        async with source(settings) as configured, AsyncExitStack() as stack:
            app = create_app(configured)
            await stack.enter_async_context(app.router.lifespan_context(app))
            clients = {}
            for who in ("operator", "approver"):
                client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url=configured.app_origin
                    )
                )
                await session_client(client, configured, who, DEMO_TENANT)
                clients[who] = client
            service = RunService(configured)
            stack.push_async_callback(service.close)
            before = await count_tickets(engine)
            run_ids = {}
            for approve in (False, True):
                owner = clients["operator"]
                response = await owner.post(
                    "/api/v2/runs",
                    json={"request": "Investigate GreenShop", "client_request_id": str(uuid4())},
                )
                assert response.status_code == 202
                run_id = UUID(response.json()["run_id"])
                run_ids["committed" if approve else "pending"] = str(run_id)
                path = f"/api/v2/runs/{run_id}"
                with tenant_scope(DEMO_TENANT):
                    assert await process_one(service, run_id)
                pending = (await owner.get(path)).json()
                assert pending["status"] == "waiting_for_approval"
                if not approve:
                    continue
                action = pending["action"]
                decision = {
                    "action_id": action["action_id"],
                    "expected_version": action["expected_version"],
                    "decision": "approve",
                }
                approver = clients["approver"]
                assert (await approver.post(path + "/decision", json=decision)).status_code in {
                    200,
                    202,
                }
                with tenant_scope(DEMO_TENANT):
                    assert await process_one(service, run_id)
                final = (await owner.get(path)).json()
                assert final["outcome"] == "actions_verified"
                assert (await approver.post(path + "/decision", json=decision)).status_code == 200
                checks = await database_checks(engine, run_id, before, before)
                assert checks["exact_verified_ticket"] and checks["ticket_delta"] == 1
                assert checks["duplicates"] == checks["unauthorized_writes"] == 0
            project = os.environ["F23_PROJECT"]
            (Path("/reports") / project / "fixture.json").write_text(json.dumps(run_ids))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
