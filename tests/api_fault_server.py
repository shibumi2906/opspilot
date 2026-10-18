"""Private process-level faults; never imported by application code."""

import os

from opspilot.api.main import create_app
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.run_service import RunService


def app():
    fault = os.environ.get("TEST_API_FAULT")
    if fault == "decision":

        async def stop(*args, **kwargs):
            os._exit(73)

        RunService.resume = stop
    if fault == "write":
        original = MCPClient.call

        async def call(session, name, arguments):
            result = await original(session, name, arguments)
            if name == "create_ticket" and result.ok:
                os._exit(73)
            return result

        MCPClient.call = staticmethod(call)
    return create_app()
