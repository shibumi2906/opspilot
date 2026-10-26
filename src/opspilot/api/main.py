from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from sqlalchemy import text

from opspilot.api.errors import install_errors
from opspilot.api.routes_health import router
from opspilot.api.routes_runs import router as runs_router
from opspilot.auth.http import SessionMiddleware
from opspilot.auth.http import router as auth_router
from opspilot.auth.store import IdentityStore
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.logging import configure_logging
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.recovery import recover
from opspilot.runtime.run_service import RunService
from opspilot.telemetry import TraceMiddleware, configure
from opspilot.tenancy.context import tenant_scope


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure(settings, "opspilot-api")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.identity = IdentityStore(settings)
        app.state.engine = create_engine(settings.database_url("workflow"))
        app.state.mcp = MCPClient(settings)
        guard = await app.state.engine.connect()
        try:
            acquired = await guard.scalar(text("SELECT pg_try_advisory_lock(1801202604)"))
            if not acquired:
                raise RuntimeError("Only one API process is supported")
            app.state.runs = RunService(settings)
            for tenant in settings.recovery_tenants:
                with tenant_scope(tenant):
                    await recover(app.state.runs)
            yield
        finally:
            if hasattr(app.state, "runs"):
                await app.state.runs.close()
            await guard.execute(text("SELECT pg_advisory_unlock(1801202604)"))
            await guard.close()
            await app.state.engine.dispose()
            await app.state.identity.engine.dispose()

    app = FastAPI(title="OpsPilot", version="0.1.0", lifespan=lifespan)

    @app.get("/api/v2/config")
    async def public_config() -> dict[str, object]:
        return {
            "mode": settings.llm_mode,
            "model_id": settings.openai_model if settings.llm_mode == "real" else None,
            "synthetic": True,
            "scenario_clock": settings.scenario_clock.isoformat(),
            "timezone": "Asia/Jerusalem",
        }

    app.add_middleware(TraceMiddleware, name="http.api")
    app.add_middleware(SessionMiddleware, settings=settings)
    install_errors(app)
    app.include_router(auth_router)
    app.include_router(runs_router)
    app.include_router(router)

    @app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
    async def retired_v1(path: str) -> object:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {
                "error": {
                    "code": "API_VERSION_RETIRED",
                    "schema_version": 1,
                    "message": "Use authenticated V2",
                    "retryable": False,
                }
            },
            status_code=410,
        )

    from opspilot.api.routes_authorized import router as authorized_router

    app.include_router(authorized_router)
    return app


if __name__ == "__main__":
    configure_logging()
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, access_log=False, log_level="warning")
