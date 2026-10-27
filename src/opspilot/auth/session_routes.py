"""User/admin session lifecycle; membership administration never grants access to run data."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from opspilot.auth.context import AuthError, Principal, principal, require_role
from opspilot.config import Settings

router = APIRouter()


def require_recent(settings: Settings) -> None:
    user = principal()
    if settings.security_profile == "hardened" and (
        user.auth_time is None
        or (datetime.now(UTC) - user.auth_time).total_seconds() > settings.recent_auth_seconds
    ):
        raise AuthError("REAUTHENTICATION_REQUIRED", 401)


@router.get("/auth/sessions")
async def own_sessions(request: Request) -> dict[str, Any]:
    user = principal()
    return {
        "items": await request.app.state.identity.sessions(user.user_id),
        "current": str(user.session_id),
    }


@router.delete("/auth/sessions/{session_id}")
async def revoke_own(session_id: UUID, request: Request) -> dict[str, bool]:
    require_recent(request.app.state.identity.settings)
    await request.app.state.identity.revoke_sessions(
        principal().user_id, session=session_id, reason="user_revoked"
    )
    return {"ok": True}


@router.post("/auth/sessions/revoke-all")
async def revoke_own_all(request: Request) -> dict[str, bool]:
    require_recent(request.app.state.identity.settings)
    await request.app.state.identity.revoke_sessions(principal().user_id, reason="user_revoked_all")
    return {"ok": True}


class AccountStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@asynccontextmanager
async def managed_transaction(
    request: Request, user_id: UUID
) -> AsyncIterator[tuple[AsyncConnection, Principal]]:
    actor = require_role("admin")
    require_recent(request.app.state.identity.settings)
    async with request.app.state.identity.engine.begin() as conn:
        # Global account operations require exclusive identity scope. Lock identities first;
        # membership inserts take FK locks, preventing a new foreign scope during this decision.
        await conn.execute(
            text("SELECT id FROM identity.users WHERE id IN (:a,:u) ORDER BY id FOR UPDATE"),
            {"a": actor.user_id, "u": user_id},
        )
        if not await conn.scalar(
            text("SELECT identity.lock_role(:a,:t,'admin')"),
            {"a": actor.user_id, "t": actor.tenant_id},
        ):
            raise AuthError()
        managed = await conn.scalar(
            text("""SELECT EXISTS(SELECT 1 FROM identity.tenant_memberships
            WHERE user_id=:u AND tenant_id=:t) AND NOT EXISTS(SELECT 1 FROM
identity.tenant_memberships
            WHERE user_id=:u AND tenant_id<>:t)"""),
            {"u": user_id, "t": actor.tenant_id},
        )
        if not managed:
            raise AuthError("NOT_FOUND", 404)
        yield conn, actor


@router.post("/api/v2/admin/users/{user_id}/sessions/revoke-all")
async def admin_revoke(user_id: UUID, request: Request) -> dict[str, bool]:
    async with managed_transaction(request, user_id) as (conn, actor):
        await conn.execute(
            text(
                "UPDATE identity.sessions SET "
                "revoked_at=clock_timestamp(),revocation_reason='administrator_revoked'"
                " WHERE user_id=:u AND revoked_at IS NULL"
            ),
            {"u": user_id},
        )
        await conn.execute(
            text(
                "INSERT INTO identity.security_events(id,actor_id,tenant_id,kind) "
                "VALUES(gen_random_uuid(),:a,:t,'administrator_revoked_sessions')"
            ),
            {"a": actor.user_id, "t": actor.tenant_id},
        )
    return {"ok": True}


@router.put("/api/v2/admin/users/{user_id}/status")
async def account_status(user_id: UUID, body: AccountStatus, request: Request) -> dict[str, bool]:
    async with managed_transaction(request, user_id) as (conn, actor):
        if not await conn.scalar(
            text("SELECT identity.lock_role(:u,:t,'admin')"),
            {"u": actor.user_id, "t": actor.tenant_id},
        ):
            raise AuthError()
        await conn.execute(
            text(
                "UPDATE identity.users SET disabled_at=CASE WHEN :enable THEN NULL ELSE"
                " clock_timestamp() END WHERE id=:u"
            ),
            {"enable": body.enabled, "u": user_id},
        )
        if not body.enabled:
            await conn.execute(
                text(
                    "UPDATE identity.sessions SET "
                    "revoked_at=clock_timestamp(),revocation_reason='account_disabled' "
                    "WHERE user_id=:u AND revoked_at IS NULL"
                ),
                {"u": user_id},
            )
        await conn.execute(
            text(
                "INSERT INTO "
                "identity.security_events(id,actor_id,tenant_id,kind,details) VALUES(ge"
                "n_random_uuid(),:a,:t,'account_status_changed',jsonb_build_object('use"
                "r_id',CAST(:u AS text),'enabled',CAST(:enable AS boolean)))"
            ),
            {"a": actor.user_id, "t": actor.tenant_id, "u": user_id, "enable": body.enabled},
        )
    return {"ok": True}
