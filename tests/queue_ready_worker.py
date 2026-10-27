"""Production worker, with a test-only signal-handler readiness marker."""

import asyncio

import opspilot.runtime.worker as worker

original = worker.serve


async def ready(settings, stop):
    # main installs SIGTERM/SIGINT handlers before calling serve.
    print("ready", flush=True)
    await original(settings, stop)


worker.serve = ready
asyncio.run(worker.main())
