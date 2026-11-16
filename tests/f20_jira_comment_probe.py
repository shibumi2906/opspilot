"""One newly approved diagnostic comment, never a retry of an unknown operation."""

import asyncio
import json
import os
import re
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import text

from opspilot.api.main import create_app
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.tenancy.context import DEMO_TENANT, tenant_scope
from tests.auth_helpers import session_client
from tests.f20_jira_live import claim_report


async def main():
    settings = Settings()
    assert settings.app_env == "test" and settings.llm_mode == "scripted"
    label = os.environ["F20_COMMENT_ATTEMPT"]
    assert re.fullmatch(r"[a-z0-9-]{1,60}", label)
    report = Path(f"/reports/comment-{label}.json")
    await asyncio.to_thread(claim_report, report, label)
    engine = create_engine(settings.database_url("migration"))
    service = RunService(settings)
    app = create_app(settings)
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        stack.push_async_callback(service.close)
        await stack.enter_async_context(app.router.lifespan_context(app))
        clients = {}
        for who in ("operator", "approver"):
            c = await stack.enter_async_context(
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url=settings.app_origin
                )
            )
            await session_client(c, settings, who, DEMO_TENANT)
            clients[who] = c
        async with engine.connect() as conn:
            issue = await conn.scalar(
                text(
                    "SELECT external_id FROM integrations.jira_operations "
                    "WHERE outcome='verified' AND issue_id=external_id "
                    "ORDER BY created_at DESC LIMIT 1"
                )
            )
        assert issue and issue.isdigit()
        c = clients["operator"]
        r = await c.post(
            "/api/v2/runs",
            json={
                "request": f"Investigate GreenShop; Jira comment issue {issue}",
                "client_request_id": str(uuid4()),
            },
        )
        assert r.status_code == 202
        run = UUID(r.json()["run_id"])

        async def step():
            with tenant_scope(DEMO_TENANT):
                assert await process_one(service, run)
            r = await c.get(f"/api/v2/runs/{run}")
            assert r.status_code == 200
            return r.json()

        v = await step()
        assert v["status"] == "waiting_for_approval", (v["status"], v.get("outcome"))
        a = v["action"]
        assert a["tool_name"] == "create_jira_comment"
        arguments = {
            **a["arguments"],
            "body": f"F20 distinct standalone-comment acceptance: {label}.",
        }
        r = await c.post(
            f"/api/v2/actions/{a['logical_action_id']}/revisions",
            json={"expected_version": a["expected_version"], "arguments": arguments},
        )
        assert r.status_code == 201, ("revision", r.status_code, r.json().get("detail"))
        # Revision response carries the current action; no worker is queued for an edit.
        a = r.json()["action"]
        r = await clients["approver"].post(
            f"/api/v2/runs/{run}/decision",
            json={
                "action_id": a["action_id"],
                "expected_version": a["expected_version"],
                "decision": "approve",
            },
        )
        assert r.status_code in (200, 202)
        v = await step()
        print(json.dumps({"run": str(run), "status": v["status"], "outcome": v.get("outcome")}))
        await asyncio.to_thread(
            report.write_text,
            json.dumps(
                {
                    "run_id": str(run),
                    "passed": v["outcome"] == "actions_verified",
                    "outcome": v.get("outcome"),
                },
                indent=2,
            ),
        )
        assert v["outcome"] == "actions_verified"


if __name__ == "__main__":
    asyncio.run(main())
