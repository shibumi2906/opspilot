"""Resolve worker identity from persisted run, not the approver's request context."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.auth.context import AuthError, Principal, auth_scope
from opspilot.auth.service_context import run_scope
from opspilot.runtime.fencing import execution_lease
from opspilot.tenancy.context import require_tenant


@asynccontextmanager
async def execution_scope(engine: AsyncEngine, run: UUID) -> AsyncIterator[None]:
    tenant = require_tenant()
    async with engine.connect() as conn:
        actor = await conn.scalar(
            text("SELECT actor_id FROM workflow.agent_runs WHERE id=:r AND tenant_id=:t"),
            {"r": run, "t": tenant},
        )
        if actor is None:
            raise AuthError("NOT_FOUND", 404)
        roles = frozenset(
            await conn.scalars(
                text(
                    "SELECT role FROM identity.tenant_memberships WHERE tenant_id=:t AND user_id=:u"
                ),
                {"t": tenant, "u": actor},
            )
        )
    if "operator" not in roles:
        raise AuthError("ACTOR_REVOKED")
    with auth_scope(Principal(actor, tenant, roles, UUID(int=0))), run_scope(str(run)):
        yield


def persisted_worker(method: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(method)
    async def wrapped(self: Any, run: UUID, *args: Any, **kwargs: Any) -> Any:
        try:
            async with (
                execution_scope(self.engine, run),
                execution_lease(self.engine, run, self.settings),
            ):
                return await method(self, run, *args, **kwargs)
        except AuthError:
            await self.fail(run, "AUTHORIZATION_REVOKED")

    return wrapped
