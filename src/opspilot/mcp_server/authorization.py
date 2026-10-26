from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.auth.context import AuthError, actor_id
from opspilot.auth.service_context import verified_context
from opspilot.mcp_server.services.tickets import WriteDenied
from opspilot.runtime.actions import payload_hash
from opspilot.tenancy.context import require_tenant


async def authorize_tool(name: str, args: Any, engine: AsyncEngine) -> None:
    claims = verified_context()
    if claims is None:
        raise AuthError("SERVICE_CONTEXT_REQUIRED")
    tenant, user = require_tenant(), actor_id()
    async with engine.connect() as conn:
        roles = set(
            await conn.scalars(
                text(
                    "SELECT role FROM identity.tenant_memberships WHERE tenant_id=:t AND user_id=:u"
                ),
                {"t": tenant, "u": user},
            )
        )
        if not roles & {"operator", "approver", "auditor"}:
            raise AuthError()
        if name == "create_ticket":
            if (
                claims["scope"] != "action"
                or claims.get("run") != str(args.run_id)
                or claims.get("action") != str(args.action_id)
                or claims.get("hash") != payload_hash(args.arguments.model_dump(mode="json"))
            ):
                raise WriteDenied("APPROVAL_REQUIRED")
            return
        if claims["scope"] != "read":
            raise AuthError()
        if claims.get("run"):
            owner = await conn.scalar(
                text("SELECT actor_id FROM workflow.agent_runs WHERE tenant_id=:t AND id=:r"),
                {"t": tenant, "r": UUID(claims["run"])},
            )
            if owner is None or owner != user and not roles & {"approver", "auditor"}:
                raise AuthError("NOT_FOUND", 404)
        if name == "get_ticket" and not roles & {"approver", "auditor"}:
            owner = await conn.scalar(
                text(
                    "SELECT r.actor_id FROM domain.tickets t JOIN workflow.actions a ON "
                    "a.tenant_id=t.tenant_id AND a.id=t.originating_action_id JOIN "
                    "workflow.agent_runs r ON r.tenant_id=a.tenant_id AND r.id=a.run_id "
                    "WHERE t.tenant_id=:t AND t.id=:id"
                ),
                {"t": tenant, "id": args.ticket_id},
            )
            if owner is not None and owner != user:
                raise AuthError("NOT_FOUND", 404)
