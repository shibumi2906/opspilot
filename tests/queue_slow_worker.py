"""Delay one claimed run to prove kill recovery and active graceful drain."""

import asyncio
import os

from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import main

for name in ("execute", "resume"):

    def delayed(original):
        async def call(self, run, *args, **kwargs):
            if str(run) == os.environ["SLOW_RUN"]:
                print("claimed", flush=True)
                await asyncio.sleep(60 if original.__name__ == "execute" else 2)
            return await original(self, run, *args, **kwargs)

        return call

    setattr(RunService, name, delayed(getattr(RunService, name)))

asyncio.run(main())
