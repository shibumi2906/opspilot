"""Run separately with the Compose API stopped, to exercise the real singleton lifespan."""

import asyncio
import os
import socket
import sys
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_RECOVERY_API") != "1", reason="Dedicated API process check"
)


@pytest.mark.parametrize("fault", ["pause", "decision", "write"])
async def test_api_hard_restart(fault):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    async def start(inject=False):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "uvicorn",
            "tests.api_fault_server:app" if inject else "opspilot.api.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
            "--log-level",
            "error",
            env={**os.environ, "TEST_API_FAULT": fault},
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        async with asyncio.timeout(30):
            while True:
                try:
                    if (await client.get("/health")).status_code == 200:
                        return process
                except httpx.TransportError:
                    pass
                assert process.returncode is None
                await asyncio.sleep(0.05)

    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
        process = await start(inject=True)
        try:
            response = await client.post(
                "/api/v1/runs",
                json={"request": "Investigate GreenShop", "client_request_id": str(uuid4())},
            )
            assert response.status_code == 202
            path = "/api/v1/runs/" + response.json()["run_id"]
            async with asyncio.timeout(30):
                while True:
                    pending = (await client.get(path)).json()
                    if pending["status"] == "waiting_for_approval":
                        break
                    await asyncio.sleep(0.05)
            if fault == "pause":
                process.kill()
                await process.wait()
            else:
                try:
                    await client.post(
                        path + "/decision",
                        json={"action_id": pending["action"]["action_id"], "decision": "approve"},
                    )
                except httpx.TransportError:
                    pass
                assert await asyncio.wait_for(process.wait(), 30) == 73
            process = await start()
            restored = (await client.get(path)).json()
            assert restored["action"]["arguments_hash"] == pending["action"]["arguments_hash"]
            if fault == "pause":
                assert restored["status"] == "waiting_for_approval"
                assert (
                    await client.post(
                        path + "/decision",
                        json={"action_id": restored["action"]["action_id"], "decision": "approve"},
                    )
                ).status_code == 202
            async with asyncio.timeout(30):
                while True:
                    final = (await client.get(path)).json()
                    if final["status"] == "completed":
                        break
                    await asyncio.sleep(0.05)
            assert final["outcome"] == "actions_verified", final
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
