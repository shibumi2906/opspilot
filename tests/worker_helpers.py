"""Explicit in-process worker harness for fault injection; API uses production RunService."""

import asyncio
from uuid import UUID

from opspilot.runtime.run_service import RunService as BaseRunService
from opspilot.runtime.worker import process_one


class RunService(BaseRunService):
    def __init__(self, settings):
        super().__init__(settings)
        self.tasks = set()

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def close(self):
        if self.tasks:
            await asyncio.gather(*self.tasks)
        await super().close()

    async def create(self, body):
        result = await super().create(body)
        self.spawn(process_one(self, UUID(result["run_id"])))
        return result

    async def decide(self, run_id, body):
        result = await super().decide(run_id, body)
        self.spawn(process_one(self, run_id))
        return result
