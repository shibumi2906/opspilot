"""Separate synthetic worker: pause a real claimed job after grant issuance, before MCP."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from opspilot.auth.service_context import action_scope, run_scope
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.actions import payload_hash
from opspilot.runtime.fencing import Fence, fence_scope, pulse, release
from opspilot.runtime.jobs import claim, enqueue, finish
from opspilot.tenancy.context import tenant_scope
from opspilot.tenancy.session import TenantSession
from tests.integration.test_local_operations import count, setup_action


async def main() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "test" and settings.secret_manager_url
    tenant = UUID(sys.argv[1])
    root = Path("/drill")
    engine = create_engine(settings.database_url("workflow"))
    admin = create_engine(settings.database_url("migration"))
    try:
        with tenant_scope(tenant):
            args = await setup_action(settings, admin, engine, "create_ticket")
            async with TenantSession(engine) as session, session.begin():
                await enqueue(session, args.run_id, "resume", args.action_id)
            job = await claim(engine, args.run_id)
            assert job is not None
            fence = Fence(args.run_id, job["claim_owner"], job["claim_epoch"])
            with fence_scope(fence):
                task = asyncio.current_task()
                assert task is not None
                heartbeat = asyncio.create_task(pulse(engine, fence, settings, task))
                try:
                    with action_scope(
                        str(args.run_id),
                        str(args.action_id),
                        payload_hash(args.arguments.model_dump(mode="json")),
                    ):
                        async with MCPClient(settings).session() as (session, _):
                            # Only a ready flag leaves memory; the JWT and key do not.
                            (root / "ready").write_text("issued")
                            async with asyncio.timeout(30):
                                for _ in range(1500):
                                    if (root / "release").exists():
                                        break
                                    await asyncio.sleep(0.02)
                                else:
                                    raise TimeoutError("Operator rotation boundary timed out")
                            result = await MCPClient.call(
                                session, "create_ticket", args.model_dump(mode="json")
                            )
                            assert result.ok
                    with run_scope(str(args.run_id)):
                        async with MCPClient(settings).session() as (session, _):
                            actual = await MCPClient.call(
                                session, "get_ticket", {"ticket_id": result.data["ticket_id"]}
                            )
                            assert actual.ok and actual.data["title"] == args.arguments.title
                    await finish(engine, job)
                    assert await count(admin, "create_ticket", args) == 1
                    (root / "result.json").write_text(
                        json.dumps(
                            {
                                "tenant": str(tenant),
                                "job_claimed": True,
                                "grant_issued_before_rotation": True,
                                "effect_after_rotation": True,
                                "exact_read_verified": True,
                                "writes": 1,
                            }
                        )
                    )
                finally:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
                    await release(engine, fence)
    finally:
        await engine.dispose()
        await admin.dispose()


if __name__ == "__main__":
    asyncio.run(main())
