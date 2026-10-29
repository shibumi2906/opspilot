"""V2 object-level authorization and bounded, scope-bound pagination."""

import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text, tuple_

from opspilot.api.routes_runs import get_run
from opspilot.auth.context import AuthError, principal, require_role
from opspilot.db.models_workflow import AgentRun
from opspilot.runtime.run_service import RunService
from opspilot.tenancy.session import TenantSession

router = APIRouter(prefix="/api/v2")


def cursor_mac(request: Request, value: str) -> str:
    key = request.app.state.identity.settings.session_signing_key.get_secret_value()
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def cursor_encode(request: Request, after: list[str], status: str | None) -> str:
    user = principal()
    raw = json.dumps(
        {
            "v": 1,
            "actor": str(user.user_id),
            "tenant": str(user.tenant_id),
            "status": status,
            "after": after,
        },
        sort_keys=True,
    ).encode()
    value = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return value + "." + cursor_mac(request, value)


def cursor_decode(request: Request, value: str, status: str | None) -> tuple[datetime, UUID]:
    try:
        if len(value) > 1500:
            raise ValueError()
        raw, signature = value.split(".")
        if not hmac.compare_digest(signature, cursor_mac(request, raw)):
            raise ValueError()
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * ((-len(raw)) % 4)))
        user = principal()
        if (
            body.get("v") != 1
            or body.get("actor") != str(user.user_id)
            or body.get("tenant") != str(user.tenant_id)
            or body.get("status") != status
        ):
            raise ValueError()
        return datetime.fromisoformat(body["after"][0]), UUID(body["after"][1])
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise AuthError("INVALID_CURSOR", 400) from exc


@router.get("/tenants")
async def tenants(request: Request) -> dict[str, Any]:
    return {"memberships": await request.app.state.identity.memberships(principal().user_id)}


@router.get("/runs")
async def history(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = None,
    status: str | None = Query(None, max_length=40),
) -> dict[str, Any]:
    user = principal()
    if user.tenant_id is None or not user.roles & {"operator", "approver", "auditor"}:
        raise AuthError()
    filters = [AgentRun.tenant_id == user.tenant_id]
    if not user.roles & {"approver", "auditor"}:
        filters.append(AgentRun.actor_id == user.user_id)
    if status is not None:
        filters.append(AgentRun.status == status)
    service = cast(RunService, request.app.state.runs)
    async with TenantSession(service.engine) as session:
        count = await session.scalar(select(func.count()).select_from(AgentRun).where(*filters))
        if cursor:
            after = cursor_decode(request, cursor, status)
            filters.append(tuple_(AgentRun.created_at, AgentRun.id) < after)
        rows = list(
            await session.scalars(
                select(AgentRun)
                .where(*filters)
                .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
                .limit(limit + 1)
            )
        )
    items = [
        {
            "run_id": str(r.id),
            "status": r.status,
            "outcome": r.outcome,
            "actor_id": str(r.actor_id),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows[:limit]
    ]
    next_cursor = (
        cursor_encode(
            request, [rows[limit - 1].created_at.isoformat(), str(rows[limit - 1].id)], status
        )
        if len(rows) > limit
        else None
    )
    return {"items": items, "total": count, "next_cursor": next_cursor}


@router.get("/runs/{run_id}/actions")
async def actions(run_id: UUID, request: Request) -> dict[str, Any]:
    snapshot = await get_run(run_id, request)
    return {"items": [snapshot["action"]] if snapshot.get("action") else []}


@router.get("/runs/{run_id}/evidence/{evidence_id}")
async def evidence(run_id: UUID, evidence_id: str, request: Request) -> dict[str, Any]:
    snapshot = await get_run(run_id, request)
    if len(evidence_id) > 100:
        raise AuthError("NOT_FOUND", 404)
    item = next(
        (e for e in snapshot.get("evidence", []) if e.get("evidence_id") == evidence_id), None
    )
    if item is None:
        raise AuthError("NOT_FOUND", 404)
    return dict(item)


class MembershipChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[Literal["operator", "approver", "auditor", "admin"]] = Field(max_length=4)


@router.get("/admin/memberships")
async def list_memberships(request: Request) -> dict[str, Any]:
    user = require_role("admin")
    async with request.app.state.identity.engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT user_id, role FROM identity.tenant_memberships WHERE "
                    "tenant_id=:t ORDER BY user_id, role LIMIT 100"
                ),
                {"t": user.tenant_id},
            )
        ).mappings()
        return {"items": [{"user_id": str(r["user_id"]), "role": r["role"]} for r in rows]}


@router.put("/admin/memberships/{user_id}")
async def update_membership(
    user_id: UUID, body: MembershipChange, request: Request
) -> dict[str, Any]:
    actor = require_role("admin")
    from opspilot.auth.session_routes import require_recent

    require_recent(request.app.state.identity.settings)
    roles = set(body.roles)
    if user_id == actor.user_id and not roles <= actor.roles:
        raise AuthError("SELF_ESCALATION_FORBIDDEN")
    store = request.app.state.identity
    async with store.engine.begin() as conn:
        live = await conn.scalar(
            text("SELECT identity.lock_role(:u,:t,'admin')"),
            {"t": actor.tenant_id, "u": actor.user_id},
        )
        if not live:
            raise AuthError()
        if not await conn.scalar(
            text("SELECT EXISTS(SELECT 1 FROM identity.users WHERE id=:u)"), {"u": user_id}
        ):
            raise AuthError("NOT_FOUND", 404)
        await conn.execute(
            text("DELETE FROM identity.tenant_memberships WHERE tenant_id=:t AND user_id=:u"),
            {"t": actor.tenant_id, "u": user_id},
        )
        for role in sorted(roles):
            await conn.execute(
                text("INSERT INTO identity.tenant_memberships VALUES (:t,:u,:r)"),
                {"t": actor.tenant_id, "u": user_id, "r": role},
            )
        await conn.execute(
            text(
                "INSERT INTO identity.security_events(id,actor_id,tenant_id,k"
                "ind) VALUES(:id,:u,:t,'membership_changed')"
            ),
            {"id": uuid4(), "u": actor.user_id, "t": actor.tenant_id},
        )
    return {"user_id": str(user_id), "roles": sorted(roles)}


def stream_cursor(request: Request, run_id: UUID, stream: str, sequence: int) -> str:
    user = principal()
    raw = json.dumps(
        {
            "v": 1,
            "actor": str(user.user_id),
            "tenant": str(user.tenant_id),
            "run": str(run_id),
            "stream": stream,
            "sequence": sequence,
        },
        sort_keys=True,
    ).encode()
    value = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return value + "." + cursor_mac(request, value)


def stream_after(request: Request, run_id: UUID, stream: str, cursor: str) -> int:
    try:
        if len(cursor) > 1500:
            raise ValueError()
        raw, signature = cursor.split(".")
        if not hmac.compare_digest(signature, cursor_mac(request, raw)):
            raise ValueError()
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * ((-len(raw)) % 4)))
        user = principal()
        if any(
            body.get(k) != v
            for k, v in {
                "v": 1,
                "actor": str(user.user_id),
                "tenant": str(user.tenant_id),
                "run": str(run_id),
                "stream": stream,
            }.items()
        ):
            raise ValueError()
        sequence = body["sequence"]
        if type(sequence) is not int or sequence < 0:
            raise ValueError()
        return sequence
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise AuthError("INVALID_CURSOR", 400) from exc


async def replay(
    run_id: UUID, request: Request, stream: str, limit: int, cursor: str | None
) -> dict[str, Any]:
    # Authorization precedes cursor validation, bounds and every export query.
    await get_run(run_id, request)
    after = stream_after(request, run_id, stream, cursor) if cursor else 0
    service = cast(RunService, request.app.state.runs)
    async with TenantSession(
        service.engine.execution_options(isolation_level="REPEATABLE READ")
    ) as session:
        latest = await session.scalar(
            text("SELECT sequence FROM workflow.run_streams WHERE run_id=:r"), {"r": run_id}
        )
        earliest = max(1, latest - 999)
        reset = after < earliest - 1 or after > latest
        after = earliest - 1 if reset else after
        # Both variants are static SQL; stream is never interpolated into a query.
        query = (
            "SELECT e.* FROM workflow.run_events e WHERE e.run_id=:r AND "
            "e.sequence>:s ORDER BY e.sequence LIMIT :n"
            if stream == "events"
            else "SELECT e.event_id,e.timestamp,e.type,e.schema_version,e.snapshot_version,a.* "
            "FROM workflow.run_audit a JOIN workflow.run_events e "
            "USING(tenant_id,run_id,sequence) WHERE a.run_id=:r"
            " AND a.sequence>:s ORDER BY a.sequence LIMIT :n"
        )
        rows = (
            (await session.execute(text(query), {"r": run_id, "s": after, "n": limit + 1}))
            .mappings()
            .all()
        )
    items = [dict(row) for row in rows[:limit]]
    return {
        "schema_version": 1,
        "items": items,
        "snapshot_version": latest,
        "earliest_sequence": earliest,
        "reset_required": reset,
        "next_cursor": stream_cursor(request, run_id, stream, items[-1]["sequence"])
        if len(rows) > limit
        else None,
    }


@router.get("/runs/{run_id}/events")
async def events(
    run_id: UUID, request: Request, limit: int = Query(50, ge=1, le=100), cursor: str | None = None
) -> Any:
    if any(
        item.split(";", 1)[0].strip().lower() == "text/event-stream"
        for item in request.headers.get("accept", "").split(",")
    ):
        from opspilot.api.routes_events import events as stream_events

        return await stream_events(run_id, request)
    return await replay(run_id, request, "events", limit, cursor)


@router.get("/runs/{run_id}/audit")
async def audit(
    run_id: UUID, request: Request, limit: int = Query(50, ge=1, le=100), cursor: str | None = None
) -> dict[str, Any]:
    return await replay(run_id, request, "audit", limit, cursor)
