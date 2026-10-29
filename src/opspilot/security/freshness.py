"""Direct bounded local preconditions. Never accepts checkpoint/cache observations as authority."""

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.tenancy.session import TenantSession


class PreconditionsChanged(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


async def snapshot(
    session: TenantSession, run: UUID, arguments: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    from opspilot.mcp_server.adapters import monitoring

    value = await session.scalar(
        text("SELECT workflow.precondition_snapshot(:r,CAST(:a AS jsonb))"),
        {"r": run, "a": json.dumps(arguments)},
    )
    if not isinstance(value, dict):
        raise PreconditionsChanged("PRECONDITIONS_UNKNOWN")
    now = await session.scalar(text("SELECT clock_timestamp()"))
    assert isinstance(now, datetime)
    observations = []
    try:
        for item in value["integrations"]:
            observed = monitoring.observe(
                settings.model_copy(update={"scenario_clock": now}),
                UUID(arguments["customer_id"]),
                UUID(item["id"]),
            )
            checked = observed.get("checked_at")
            if (
                not isinstance(checked, datetime)
                or not now - timedelta(minutes=5) <= checked <= now
            ):
                raise PreconditionsChanged("PRECONDITIONS_UNKNOWN")
            status, credential = observed["status"], observed["credential_status"]
            if status not in {"degraded", "unavailable", "healthy"} or credential not in {
                "valid",
                "expired",
                "revoked",
            }:
                raise PreconditionsChanged("PRECONDITIONS_UNKNOWN")
            if status == "healthy":
                raise PreconditionsChanged("ACTION_NO_LONGER_REQUIRED")
            observations.append(
                {"integration": item["id"], "status": status, "credential": credential}
            )
    except PreconditionsChanged:
        raise
    except Exception:
        raise PreconditionsChanged("PRECONDITIONS_UNKNOWN") from None
    if "recipient_id" in arguments:
        allowed = False
        for role in value["recipient_roles"]:
            allowed = (
                bool(
                    await session.scalar(
                        text("SELECT identity.lock_role(:u,identity.current_tenant(),:role)"),
                        {"u": UUID(arguments["recipient_id"]), "role": role},
                    )
                )
                or allowed
            )
        if not allowed:
            raise PreconditionsChanged("PRECONDITIONS_UNKNOWN")
    return {**value, "observations": observations}


async def check(session: TenantSession, action: Any, settings: Settings) -> None:
    if action.execution_status == "succeeded" and action.execution_result:
        return
    current = await snapshot(session, action.run_id, action.arguments, settings)
    if action.revision_document.get("freshness") != current:
        raise PreconditionsChanged("PRECONDITIONS_CHANGED")
