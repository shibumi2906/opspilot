"""Bounded private workspace views; raw domain/configuration state never exported."""

import base64
import hmac
import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import text

from opspilot.api.routes_authorized import cursor_mac
from opspilot.api.routes_runs import get_run
from opspilot.auth.context import AuthError, principal, require_role
from opspilot.auth.session_routes import require_recent
from opspilot.runtime.actions import Conflict

router = APIRouter(prefix="/api/v2")


def encode(request: Request, scope: str, after: list[str]) -> str:
    user = principal()
    raw = base64.urlsafe_b64encode(
        json.dumps(
            [1, str(user.session_id), str(user.user_id), str(user.tenant_id), scope, after],
            separators=(",", ":"),
        ).encode()
    ).decode()
    return raw + "." + cursor_mac(request, "workspace:" + raw)


def decode(request: Request, scope: str, value: str) -> tuple[datetime, UUID]:
    try:
        if len(value) > 1500:
            raise ValueError()
        raw, mac = value.split(".")
        if not hmac.compare_digest(mac, cursor_mac(request, "workspace:" + raw)):
            raise ValueError()
        data = json.loads(base64.b64decode(raw, altchars=b"-_", validate=True))
        if encode(request, scope, data[5]) != value:
            raise ValueError()
        stamp = datetime.fromisoformat(data[5][0])
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp, UUID(data[5][1])
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise AuthError("INVALID_CURSOR", 400) from exc


@router.get("/inbox")
async def inbox(
    request: Request, limit: int = Query(20, ge=1, le=50), cursor: str | None = None
) -> dict[str, Any]:
    user = principal()
    if user.tenant_id is None or not user.roles:
        raise AuthError()
    after = decode(request, "inbox", cursor) if cursor else (None, None)
    async with request.app.state.engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text("SELECT * FROM workflow.workspace_inbox(:time,:id,:n)"),
                    {"time": after[0], "id": after[1], "n": limit + 1},
                )
            )
            .mappings()
            .all()
        )
    items = [dict(r) for r in rows[:limit]]
    return {
        "items": items,
        "next_cursor": encode(
            request, "inbox", [items[-1]["created_at"].isoformat(), str(items[-1]["id"])]
        )
        if len(rows) > limit
        else None,
    }


class ReadCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID


class ConnectorChange(ReadCommand):
    expected_version: int = Field(ge=0, le=2147483646, strict=True)
    enabled: StrictBool


async def command(request: Request, kind: str, target: UUID, body: ReadCommand) -> dict[str, Any]:
    async with request.app.state.engine.begin() as conn:
        value = await conn.scalar(
            text("SELECT workflow.workspace_command(:kind,:id,:v,:enabled,:cmd)"),
            {
                "kind": kind,
                "id": target,
                "v": body.expected_version if isinstance(body, ConnectorChange) else None,
                "enabled": body.enabled if isinstance(body, ConnectorChange) else None,
                "cmd": body.command_id,
            },
        )
    if value is None:
        raise AuthError("NOT_FOUND", 404)
    if value.get("conflict"):
        raise Conflict("Stale or conflicting command")
    return dict(value)


@router.post("/inbox/{notification_id}/read")
async def read_notification(
    notification_id: UUID, body: ReadCommand, request: Request
) -> dict[str, Any]:
    return await command(request, "read", notification_id, body)


@router.get("/admin/connectors")
async def connectors(request: Request) -> dict[str, Any]:
    require_role("admin")
    async with request.app.state.engine.connect() as conn:
        rows = (
            (await conn.execute(text("SELECT * FROM workflow.workspace_connectors()")))
            .mappings()
            .all()
        )
    if len(rows) > 500:
        raise AuthError("REFINE_SCOPE", 413)
    return {"items": [dict(row) for row in rows], "source": "synthetic"}


@router.put("/admin/connectors/{integration_id}")
async def change_connector(
    integration_id: UUID, body: ConnectorChange, request: Request
) -> dict[str, Any]:
    require_role("admin")
    require_recent(request.app.state.identity.settings)
    return await command(request, "connector", integration_id, body)


@router.get("/audit")
async def audit_page(
    request: Request, limit: int = Query(30, ge=1, le=100), cursor: str | None = None
) -> dict[str, Any]:
    user = require_role("auditor")
    after = decode(request, "audit", cursor) if cursor else (None, None)
    async with request.app.state.engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT * FROM (SELECT e.event_id,e.timestamp,e.run_id,e.sequence,"
                        "e.type,a.actor_id,a.reason_code "
                        "FROM workflow.run_events e JOIN workflow.run_audit a "
                        "USING(tenant_id,run_id,sequence) "
                        "WHERE e.tenant_id=:t AND (CAST(:time AS timestamptz) IS NULL OR "
                        "(e.timestamp,e.event_id)<(:time,:id)) UNION ALL "
                        "SELECT * FROM workflow.workspace_security_events(:time,:id,:n)) events "
                        "ORDER BY timestamp DESC,event_id DESC LIMIT :n"
                    ),
                    {"t": user.tenant_id, "time": after[0], "id": after[1], "n": limit + 1},
                )
            )
            .mappings()
            .all()
        )
    items = [dict(r) for r in rows[:limit]]
    return {
        "items": items,
        "next_cursor": encode(
            request, "audit", [items[-1]["timestamp"].isoformat(), str(items[-1]["event_id"])]
        )
        if len(rows) > limit
        else None,
    }


async def export_response(request: Request, value: dict[str, Any], scope: str) -> Response:
    body = json.dumps(jsonable_encoder(value), ensure_ascii=True, separators=(",", ":"))
    if len(body.encode()) > 65536:
        raise AuthError("EXPORT_TOO_LARGE", 413)
    async with request.app.state.identity.engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO identity.security_events(id,actor_id,tenant_id,kind,details) "
                "VALUES(:id,:a,:t,'workspace_export',jsonb_build_object('scope',CAST(:s AS text)))"
            ),
            {"id": uuid4(), "a": principal().user_id, "t": principal().tenant_id, "s": scope},
        )
    return Response(
        body,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="opspilot-export.json"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/audit/export")
async def export_audit(request: Request, cursor: str | None = None) -> Response:
    value = await audit_page(request, 100, cursor)
    return await export_response(request, value, "audit")


@router.get("/runs/{run_id}/export")
async def export_run(run_id: UUID, request: Request) -> Response:
    snap = await get_run(run_id, request)
    fields = [
        "run_id",
        "actor_id",
        "status",
        "outcome",
        "created_at",
        "updated_at",
        "snapshot_version",
    ]
    value = {k: snap[k] for k in fields if k in snap}
    value["actions"] = [
        {
            k: a[k]
            for k in [
                "action_id",
                "logical_action_id",
                "expected_version",
                "tool_name",
                "approval_status",
                "execution_status",
            ]
            if k in a
        }
        for a in snap.get("actions") or ([snap["action"]] if snap.get("action") else [])
    ]
    return await export_response(request, value, "run")
