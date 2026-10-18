"""Worker killed by its parent or after a real committed MCP write."""

import asyncio
import json
import os
import sys
from uuid import UUID, uuid4

from opspilot.config import Settings
from opspilot.contracts.api import CreateRun, Decision
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.run_service import RunService


async def main():
    service = RunService(Settings())
    mode = sys.argv[1]
    if mode == "pause":
        result = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        run_id = UUID(result["run_id"])
        while True:
            if (await service.snapshot(run_id))["status"] == "waiting_for_approval":
                break
            await asyncio.sleep(0.02)
        print(json.dumps(await service.snapshot(run_id)), flush=True)
        await asyncio.Event().wait()
    else:
        run_id = UUID(sys.argv[2])
        snapshot = await service.snapshot(run_id)
        if mode == "decision":
            service.spawn = lambda coroutine: coroutine.close()
        if mode == "write":
            original = MCPClient.call

            async def call(session, name, arguments):
                result = await original(session, name, arguments)
                if name == "create_ticket" and result.ok:
                    os._exit(73)
                return result

            MCPClient.call = staticmethod(call)
        await service.decide(
            run_id, Decision(action_id=snapshot["action"]["action_id"], decision="approve")
        )
        if mode == "decision":
            print("committed", flush=True)
            await asyncio.Event().wait()
        await asyncio.Event().wait()


asyncio.run(main())
