import asyncio
import json
import sys
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from opspilot.contracts.api import Decision
from opspilot.runtime.recovery import recover
from opspilot.runtime.run_service import RunService


async def worker(*args):
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "tests/recovery_worker.py",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def line(process):
    return await asyncio.wait_for(process.stdout.readline(), 30)


async def terminal(service, run_id):
    async with asyncio.timeout(30):
        while True:
            result = await service.snapshot(run_id)
            if result["status"] not in {"running", "queued"}:
                return result
            await asyncio.sleep(0.02)


@pytest.mark.parametrize("crash", ["pause", "decision", "write"])
async def test_hard_process_recovery(integration_settings, admin_engine, crash):
    process = await worker("pause")
    try:
        pending = json.loads(await line(process))
    finally:
        process.kill()
        await process.wait()
    run_id = UUID(pending["run_id"])
    if crash != "pause":
        process = await worker(crash, str(run_id))
        if crash == "decision":
            assert await line(process) == b"committed\n"
            process.kill()
        assert await asyncio.wait_for(process.wait(), 30) in {-9, 73}
    service = RunService(integration_settings)
    try:
        await recover(service)
        result = await terminal(service, run_id)
        if crash == "pause":
            assert result["status"] == "waiting_for_approval"
            assert result["action"] == pending["action"]
            await service.decide(
                run_id, Decision(action_id=result["action"]["action_id"], decision="approve")
            )
            result = await terminal(service, run_id)
        assert result["outcome"] == "actions_verified", result
        assert result["action"]["arguments_hash"] == pending["action"]["arguments_hash"]
        await service.decide(
            run_id, Decision(action_id=result["action"]["action_id"], decision="approve")
        )
        async with admin_engine.connect() as conn:
            count = await conn.scalar(
                text("SELECT count(*) FROM domain.tickets WHERE originating_action_id=:id"),
                {"id": UUID(result["action"]["action_id"])},
            )
        assert count == 1
    finally:
        await service.close()


async def test_other_running_run_fails_on_restart(integration_settings, admin_engine):
    from opspilot.agent.service import run_investigation

    result = await run_investigation(
        integration_settings, "Investigate GreenShop", queued_only=True, client_request_id=uuid4()
    )
    service = RunService(integration_settings)
    try:
        await recover(service)
        result = await service.snapshot(UUID(result["run_id"]))
        assert result["status"] == "failed"
        assert result["error"]["code"] == "RESTART_INTERRUPTED"
        assert result["action"] is None
    finally:
        await service.close()
