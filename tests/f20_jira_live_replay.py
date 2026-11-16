"""Read-back and replay existing real sandbox effects; never create a new live intent."""

import asyncio
import hashlib
import json
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text

from opspilot.api.main import create_app
from opspilot.auth.context import Principal, auth_scope
from opspilot.auth.service_context import action_scope
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.actions import payload_hash
from opspilot.runtime.fencing import execution_lease
from opspilot.runtime.run_service import RunService
from opspilot.tenancy.context import DEMO_TENANT
from tests.auth_helpers import session_client


async def main():
    settings = Settings()
    assert settings.app_env == "test" and settings.llm_mode == "scripted"
    engine = create_engine(settings.database_url("migration"))
    app = create_app(settings)
    service = RunService(settings)
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        stack.push_async_callback(service.close)
        await stack.enter_async_context(app.router.lifespan_context(app))
        c = await stack.enter_async_context(
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=settings.app_origin)
        )
        _, user = await session_client(c, settings, "operator", DEMO_TENANT)
        async with engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text("""
                SELECT a.id,a.run_id,a.arguments,a.tool_name,o.external_id,
                       a.expires_at>clock_timestamp() AS unexpired
                FROM workflow.actions a JOIN integrations.jira_operations o ON o.action_id=a.id
                WHERE o.outcome='verified' AND
                  (a.arguments->>'title' LIKE 'F20 acceptance deadline-fix-r2:%'
                   OR a.arguments->>'body' LIKE
                       'F20 distinct standalone-comment acceptance: object-marker-r1%')
            """)
                    )
                )
                .mappings()
                .all()
            )
        assert len(rows) == 2
        results = []
        for row in rows:
            r = await c.post(f"/api/v2/jira/operations/{row['id']}/reconcile")
            assert r.status_code == 200 and r.json()["outcome"] == "verified", (
                "readback",
                r.status_code,
                r.json().get("outcome"),
            )
            principal = Principal(
                user, DEMO_TENANT, frozenset({"operator"}), uuid4(), datetime.now(UTC)
            )
            with auth_scope(principal):
                async with execution_lease(service.engine, row["run_id"], settings):
                    with action_scope(
                        str(row["run_id"]),
                        str(row["id"]),
                        payload_hash(row["arguments"]),
                        tool=row["tool_name"],
                    ):
                        async with MCPClient(settings).session() as (session, _):
                            replay = await MCPClient.call(
                                session,
                                row["tool_name"],
                                {
                                    "run_id": str(row["run_id"]),
                                    "action_id": str(row["id"]),
                                    "arguments": row["arguments"],
                                },
                            )
            if row["unexpired"]:
                assert replay.ok and replay.data["replayed"]
            else:
                assert not replay.ok
            # Re-enumeration must remain exactly one matching marker after replay.
            r = await c.post(f"/api/v2/jira/operations/{row['id']}/reconcile")
            assert r.status_code == 200 and r.json()["outcome"] == "verified"
            results.append(
                {
                    "tool": row["tool_name"],
                    "independent_readback": "verified",
                    "replay": "saved_receipt" if replay.ok else "denied_expired",
                    "external_id_sha256": hashlib.sha256(row["external_id"].encode()).hexdigest(),
                }
            )
        report = {"passed": True, "new_posts": 0, "duplicate_markers": 0, "operations": results}
        await asyncio.to_thread(
            Path("/reports/live-existing-replay.json").write_text,
            json.dumps(report, indent=2) + "\n",
        )
        print(json.dumps(report))


if __name__ == "__main__":
    asyncio.run(main())
