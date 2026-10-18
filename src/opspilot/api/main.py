from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from opspilot.api.routes_health import router
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.logging import configure_logging
from opspilot.mcp_client.client import MCPClient


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(settings.database_url("workflow"))
        app.state.mcp = MCPClient(settings)
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="OpsPilot", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app


if __name__ == "__main__":
    configure_logging()
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, access_log=False, log_level="warning")
