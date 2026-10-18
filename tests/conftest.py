import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.config import Settings
from opspilot.db.engine import create_engine


@pytest.fixture
def integration_settings() -> Settings:
    if os.environ.get("APP_ENV") != "test":
        pytest.skip("Use the isolated Compose test stack (APP_ENV=test)")
    settings = Settings()
    for role in ("migration", "workflow", "domain", "checkpoint"):
        if make_url(settings.database_url(role)).database != "opspilot_test":
            pytest.fail("Integration tests require the isolated opspilot_test database")
    return settings


@pytest.fixture
async def admin_engine(integration_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(integration_settings.database_url("migration"))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def overlay_settings(integration_settings, request):
    import asyncio
    import socket

    import uvicorn

    from opspilot.mcp_server.main import create_app

    settings = integration_settings.model_copy(update={"scenario_id": request.param})
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield settings.model_copy(update={"mcp_url": f"http://127.0.0.1:{port}/mcp"})
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()
