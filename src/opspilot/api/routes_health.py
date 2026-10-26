import asyncio

from fastapi import APIRouter, Request
from sqlalchemy import text
from starlette.responses import JSONResponse

from opspilot.tenancy.context import tenant_scope

router = APIRouter()


@router.get("/health/ready")
@router.get("/health")
async def health(request: Request) -> JSONResponse:
    checks = {"database": "unavailable", "migrations": "unavailable", "mcp": "unavailable"}
    try:
        async with asyncio.timeout(5), request.app.state.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            checks["database"] = "ready"
            revision = await connection.scalar(
                text("SELECT version_num FROM workflow.alembic_version")
            )
            if revision == "0005_authorization_context":
                checks["migrations"] = "ready"
    except Exception:
        pass
    try:
        with tenant_scope(request.app.state.mcp.settings.local_demo_tenant):
            async with asyncio.timeout(6), request.app.state.mcp.session() as (session, _):
                await request.app.state.mcp.discover(session)
                checks["mcp"] = "ready"
    except Exception:
        pass
    ready = all(value == "ready" for value in checks.values())
    return JSONResponse(
        {"status": "ready" if ready else "unavailable"},
        status_code=200 if ready else 503,
    )


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}
