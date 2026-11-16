"""Fenced operator reconciliation reads Jira and records the result without redispatch."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import text

from opspilot.auth.context import AuthError, require_role
from opspilot.auth.service_context import run_scope
from opspilot.auth.session_routes import require_recent
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.fencing import execution_lease
from opspilot.tenancy.session import TenantSession

router = APIRouter(prefix="/api/v2/jira")


@router.post("/operations/{operation}/reconcile")
async def reconcile(operation: UUID, request: Request) -> dict[str, Any]:
    principal = require_role("operator")
    service = request.app.state.runs
    require_recent(service.settings)
    async with TenantSession(service.engine) as session:
        row = (
            (
                await session.execute(
                    text("""
            SELECT r.id,r.actor_id FROM workflow.agent_runs r
            JOIN workflow.actions a ON a.run_id=r.id AND a.tenant_id=r.tenant_id
            WHERE a.tenant_id=identity.current_tenant() AND a.id=:operation
              AND a.tool_name IN ('create_jira_issue','create_jira_comment')
        """),
                    {"operation": operation},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["actor_id"] != principal.user_id:
            raise AuthError("NOT_FOUND", 404)
        run = row["id"]
    async with execution_lease(service.engine, run, service.settings):
        with run_scope(str(run)):
            client = MCPClient(service.settings)
            async with client.session() as (session, _):
                result = await client.call(
                    session, "get_jira_operation", {"operation_id": str(operation)}
                )
            if not result.ok or result.data is None:
                raise AuthError("JIRA_RECONCILIATION_UNAVAILABLE", 503)
            return result.data
