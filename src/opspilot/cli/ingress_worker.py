"""Independent transactionally claimed observation processor; no business write credentials."""

import argparse
import asyncio
import signal

from opspilot.db.engine import create_engine
from opspilot.integrations.service import process_one
from opspilot.integrations.worker_settings import IngressWorkerSettings
from opspilot.tenancy.context import tenant_scope


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = IngressWorkerSettings()
    engine = create_engine(settings.database_url())
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, stop.set)
    try:
        while not stop.is_set():
            worked = False
            for tenant in settings.recovery_tenants:
                with tenant_scope(tenant):
                    worked = await process_one(engine) or worked
            if args.once:
                return
            if not worked:
                try:
                    await asyncio.wait_for(stop.wait(), 0.25)
                except TimeoutError:
                    pass
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
