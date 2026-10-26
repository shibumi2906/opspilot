"""Exit strictly after durable commit and before HTTP response, only in tests."""

import os

from opspilot.api.main import create_app
from opspilot.runtime.run_service import RunService


def app():
    name = os.environ["QUEUE_FAULT"]
    original = getattr(RunService, name)

    async def committed(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        os._exit(73)

    setattr(RunService, name, committed)
    return create_app()
