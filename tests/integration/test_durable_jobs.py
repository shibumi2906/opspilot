import asyncio
import os
import socket
import sys
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from opspilot.contracts.api import CreateRun, Decision
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one


async def test_enqueue_rollback_and_replay(integration_settings, monkeypatch, admin_engine):
    import opspilot.agent.service as creator
    import opspilot.runtime.run_service as decisions

    service = RunService(integration_settings)
    original = creator.enqueue

    async def fail(*args):
        raise RuntimeError("injected enqueue rollback")

    body = CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
    try:
        monkeypatch.setattr(creator, "enqueue", fail)
        with pytest.raises(RuntimeError):
            await service.create(body)
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM workflow.agent_runs WHERE client_request_id=:id"),
                    {"id": body.client_request_id},
                )
                == 0
            )
        monkeypatch.setattr(creator, "enqueue", original)
        result = await service.create(body)
        run = UUID(result["run_id"])
        assert (await service.create(body))["run_id"] == str(run)
        assert (await service.snapshot(run))["status"] == "queued"
        await process_one(service, run)
        pending = await service.snapshot(run)
        choice = Decision(action_id=pending["action"]["action_id"], decision="approve")
        monkeypatch.setattr(decisions, "enqueue", fail)
        with pytest.raises(RuntimeError):
            await service.decide(run, choice)
        pending = await service.snapshot(run)
        assert pending["status"] == "waiting_for_approval"
        assert pending["action"]["approval_status"] == "pending"
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM workflow.command_jobs "
                        "WHERE run_id=:id AND kind='resume'"
                    ),
                    {"id": run},
                )
                == 0
            )
        monkeypatch.setattr(decisions, "enqueue", original)
        await service.decide(run, choice)
        await service.decide(run, choice)
        await process_one(service, run)
        assert (await service.snapshot(run))["outcome"] == "actions_verified"
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM workflow.command_jobs WHERE run_id=:id"), {"id": run}
                )
                == 2
            )
    finally:
        await service.close()


async def test_command_tenant_isolation(integration_settings):
    from sqlalchemy.exc import DBAPIError

    from opspilot.runtime.jobs import claim
    from opspilot.tenancy.context import SECOND_TENANT, tenant_scope

    service = RunService(integration_settings)
    try:
        result = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        run = UUID(result["run_id"])
        with tenant_scope(SECOND_TENANT):
            assert await claim(service.engine, run) is None
            async with service.engine.connect() as conn:
                assert (
                    await conn.scalar(
                        text("SELECT count(*) FROM workflow.command_jobs WHERE run_id=:id"),
                        {"id": run},
                    )
                    == 0
                )
            with pytest.raises(DBAPIError):
                async with service.engine.begin() as conn:
                    await conn.execute(
                        text(
                            "INSERT INTO workflow.command_jobs(id,tenant_id,run_id,kind) "
                            "VALUES(:id,:tenant,:run,'start')"
                        ),
                        {
                            "id": uuid4(),
                            "tenant": integration_settings.local_demo_tenant,
                            "run": run,
                        },
                    )
        # Consume the probe so the dedicated process gate sees no unrelated queued run.
        await process_one(service, run)
    finally:
        await service.close()


async def test_queued_start_uses_saved_limits(integration_settings):
    settings = integration_settings.model_copy(update={"agent_max_reads": 8})
    service = RunService(settings)
    try:
        result = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        run = UUID(result["run_id"])
        service.settings = settings.model_copy(update={"agent_max_reads": 15})
        await process_one(service, run)
        pending = await service.snapshot(run)
        assert pending["status"] == "waiting_for_approval", pending
        assert pending["budget"]["limits"]["reads"] == 8
    finally:
        await service.close()


async def test_backoff_dead_letter(integration_settings, monkeypatch, admin_engine):
    import opspilot.runtime.worker as module

    service = RunService(integration_settings)
    created = await service.create(
        CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
    )
    run = UUID(created["run_id"])

    async def fail(*args):
        raise RuntimeError("PRIVATE worker infrastructure details")

    monkeypatch.setattr(service, "execute", fail)
    try:
        for attempt in range(1, 6):
            assert await module.process_one(service, run)
            async with admin_engine.begin() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT status,attempts,error_code,available_at>now() "
                            "FROM workflow.command_jobs WHERE run_id=:id"
                        ),
                        {"id": run},
                    )
                ).one()
                assert row[0] == ("dead" if attempt == 5 else "pending")
                assert row[1] == attempt and row[3]
                assert "PRIVATE" not in str(row)
                await conn.execute(
                    text("UPDATE workflow.command_jobs SET available_at=now() WHERE run_id=:id"),
                    {"id": run},
                )
        assert not await module.process_one(service, run)
        assert (await service.snapshot(run))["error"]["code"] == "COMMAND_DEAD_LETTER"
    finally:
        await service.close()


@pytest.mark.skipif(
    os.environ.get("TEST_QUEUE_PROCESSES") != "1", reason="Dedicated real API/worker process gate"
)
async def test_api_commit_loss_offline_worker_and_singleton(integration_settings, admin_engine):
    from tests.auth_helpers import session_client

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    processes = []

    async def start_api(fault=None):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "uvicorn",
            "tests.queue_fault_server:app" if fault else "opspilot.api.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
            env={**os.environ, "QUEUE_FAULT": fault or ""},
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        processes.append(proc)
        async with asyncio.timeout(30):
            while True:
                try:
                    if (await client.get("/health")).status_code == 200:
                        return proc
                except httpx.TransportError:
                    pass
                assert proc.returncode is None
                await asyncio.sleep(0.05)

    async def worker(slow=False):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "tests.queue_slow_worker" if slow else "tests.queue_ready_worker",
            env={**os.environ, "SLOW_RUN": path.rsplit("/", 1)[1]},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        processes.append(proc)
        if not slow:
            assert await asyncio.wait_for(proc.stdout.readline(), 20) == b"ready\n"
        return proc

    async def ready(path):
        async with asyncio.timeout(40):
            while True:
                value = (await client.get(path)).json()
                if value["status"] not in {"queued", "running"}:
                    return value
                await asyncio.sleep(0.05)

    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            api = await start_api("create")
            await session_client(client, integration_settings)
            body = {"request": "Investigate GreenShop", "client_request_id": str(uuid4())}
            with pytest.raises(httpx.TransportError):
                await client.post("/api/v2/runs", json=body)
            assert await asyncio.wait_for(api.wait(), 10) == 73
            api = await start_api()
            await session_client(client, integration_settings)
            created = await client.post("/api/v2/runs", json=body)
            assert created.status_code == 202
            path = created.json()["snapshot_url"]
            assert (await client.get(path)).json()["status"] == "queued"
            delayed = await worker(slow=True)
            assert await asyncio.wait_for(delayed.stdout.readline(), 20) == b"claimed\n"
            duplicate = await worker()
            await asyncio.sleep(0.3)
            assert duplicate.returncode is None
            duplicate.terminate()
            assert await asyncio.wait_for(duplicate.wait(), 15) == 0
            delayed.kill()
            await delayed.wait()
            active = await worker()
            pending = await ready(path)
            assert pending["status"] == "waiting_for_approval", pending
            # The singleton is enforced by an actual independent worker process.
            duplicate = await worker()
            await asyncio.sleep(0.3)
            assert duplicate.returncode is None
            duplicate.terminate()
            assert await asyncio.wait_for(duplicate.wait(), 15) == 0
            assert active.returncode is None
            active.terminate()
            assert await asyncio.wait_for(active.wait(), 15) == 0
            api.terminate()
            await asyncio.wait_for(api.wait(), 15)
            api = await start_api("decide")
            await session_client(client, integration_settings)
            choice = {"action_id": pending["action"]["action_id"], "decision": "approve"}
            with pytest.raises(httpx.TransportError):
                await client.post(path + "/decision", json=choice)
            assert await asyncio.wait_for(api.wait(), 10) == 73
            api = await start_api()
            await session_client(client, integration_settings)
            replay = await client.post(path + "/decision", json=choice)
            assert replay.status_code == 202
            assert (await client.get(path)).json()["status"] == "running"
            active = await worker(slow=True)
            assert await asyncio.wait_for(active.stdout.readline(), 20) == b"claimed\n"
            active.terminate()
            assert await asyncio.wait_for(active.wait(), 20) == 0
            final = await ready(path)
            assert final["outcome"] == "actions_verified", final
            assert (await client.post(path + "/decision", json=choice)).status_code == 200
            async with admin_engine.connect() as conn:
                assert (
                    await conn.scalar(
                        text("SELECT count(*) FROM domain.tickets WHERE originating_action_id=:id"),
                        {"id": UUID(choice["action_id"])},
                    )
                    == 1
                )
                rows = (
                    await conn.execute(
                        text(
                            "SELECT kind,status,attempts FROM workflow.command_jobs "
                            "WHERE run_id=:id ORDER BY kind"
                        ),
                        {"id": UUID(final["run_id"])},
                    )
                ).all()
                assert rows == [("resume", "done", 1), ("start", "done", 2)]
    finally:
        for proc in processes:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
