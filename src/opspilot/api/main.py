from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from opspilot.api.errors import install_errors
from opspilot.api.routes_actions import router as actions_router
from opspilot.api.routes_health import router
from opspilot.api.routes_runs import router as runs_router
from opspilot.auth.http import SessionMiddleware
from opspilot.auth.http import router as auth_router
from opspilot.auth.session_routes import router as sessions_router
from opspilot.auth.store import IdentityStore
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.logging import configure_logging
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.run_service import RunService
from opspilot.security.http import SecurityMiddleware
from opspilot.telemetry import TraceMiddleware, configure


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure(settings, "opspilot-api")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.identity = IdentityStore(settings)
        app.state.engine = create_engine(settings.database_url("workflow"))
        app.state.streams_engine = create_engine(settings.database_url("workflow"))
        app.state.mcp = MCPClient(settings)
        app.state.runs = RunService(settings)
        try:
            yield
        finally:
            await app.state.runs.close()
            await app.state.streams_engine.dispose()
            await app.state.engine.dispose()
            await app.state.identity.engine.dispose()

    app = FastAPI(
        title="OpsPilot",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/api/v2/config")
    async def public_config() -> dict[str, object]:
        return {
            "mode": settings.llm_mode,
            "model_id": settings.openai_model if settings.llm_mode == "real" else None,
            "synthetic": True,
            "source": "synthetic",
            "account_url": settings.oidc_issuer + "/account/",
            "scenario_clock": settings.scenario_clock.isoformat(),
            "timezone": "Asia/Jerusalem",
        }

    app.add_middleware(TraceMiddleware, name="http.api")
    app.add_middleware(SessionMiddleware, settings=settings)
    app.add_middleware(SecurityMiddleware, settings=settings)
    install_errors(app, settings)
    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(runs_router)
    app.include_router(actions_router)
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
    from opspilot.api.routes_workspace import router as workspace_router

    app.include_router(workspace_router)
    from opspilot.api.routes_diagnostics import router as diagnostics_router

    app.include_router(diagnostics_router)
    return app


if __name__ == "__main__":
    configure_logging()
    settings = Settings()
    if settings.security_profile == "hardened" and not (
        settings.tls_cert_file and settings.tls_key_file
    ):
        raise ValueError("Hardened server requires native TLS certificate and key")
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_config=None,
        log_level="warning",
        ssl_certfile=settings.tls_cert_file,
        ssl_keyfile=settings.tls_key_file,
        proxy_headers=False,
    )
