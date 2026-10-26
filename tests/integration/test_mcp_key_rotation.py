import asyncio
import socket

import httpx
import uvicorn

from opspilot.auth.service_context import mint
from opspilot.cli.service_keys import initialize, main
from opspilot.mcp_server.main import create_app


async def test_actual_mcp_accepts_next_key_and_rejects_retired_key(
    integration_settings, tmp_path, monkeypatch
):
    initialize(tmp_path)
    settings = integration_settings.model_copy(
        update={
            "service_private_dir": str(tmp_path / "private"),
            "service_public_keys": str(tmp_path / "public" / "keys.json"),
        }
    )
    old = mint(settings)
    new = mint(settings.model_copy(update={"service_active_kid": "next"}))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}/mcp"
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "key-rotation", "version": "1"},
            },
        }
        async with httpx.AsyncClient() as client:

            async def probe(token):
                return await client.post(
                    url,
                    headers={
                        "Authorization": "Bearer " + settings.mcp_service_token.get_secret_value(),
                        "X-OpsPilot-Context": token,
                        "Accept": "application/json,text/event-stream",
                    },
                    json=body,
                )

            assert (await probe(old)).status_code == 200
            assert (await probe(new)).status_code == 200
            monkeypatch.setattr(
                "sys.argv",
                ["service_keys", str(tmp_path), "--retire", "current", "--active", "next"],
            )
            main()
            assert (await probe(old)).status_code == 401
            assert (await probe(new)).status_code == 200
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()
