"""Allowlisted security events; never include request bodies, tokens or exception text."""

import asyncio
from typing import Any
from uuid import uuid4

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

from opspilot.auth.context import Principal, optional_principal


async def record(scope: Any, kind: str, reason: str, user: Principal | None = None) -> None:
    user = user or optional_principal()
    path = scope.get("path", "")
    category = (
        "api" if path.startswith("/api/") else "auth" if path.startswith("/auth/") else "other"
    )
    request_id = scope.get("state", {}).get("security_request_id", str(uuid4()))
    details = {
        "reason": reason,
        "request_id": request_id,
        "endpoint_group": category,
        "method": scope.get("method")
        if scope.get("method")
        in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}
        else "OTHER",
    }
    logger.bind(
        security_event=kind,
        **details,
        actor_id=str(user.user_id) if user else None,
        tenant_id=str(user.tenant_id) if user and user.tenant_id else None,
    ).warning("security_event")
    store = getattr(getattr(scope.get("app"), "state", None), "identity", None)
    if store:
        try:
            async with asyncio.timeout(1):
                await store.audit(
                    kind,
                    user.user_id if user else None,
                    user.tenant_id if user else None,
                    details=details,
                )
        except (SQLAlchemyError, TimeoutError):
            # Authorization stays denied; the structured fallback is available independently.
            logger.bind(request_id=request_id).error("security_audit_database_unavailable")
