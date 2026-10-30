"""An independent real worker process for F16 trace restart/epoch checks."""

import asyncio
import sys
from uuid import UUID

from opentelemetry import trace

from opspilot.config import Settings
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.telemetry import configure
from opspilot.tenancy.context import tenant_scope


async def main():
    settings = Settings()
    configure(settings, "opspilot-worker")
    service = RunService(settings)
    try:
        with tenant_scope(UUID(sys.argv[1])):
            assert await process_one(service, UUID(sys.argv[2]))
    finally:
        await service.close()
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush(timeout_millis=2000)
        if hasattr(provider, "shutdown"):
            provider.shutdown()


asyncio.run(main())
