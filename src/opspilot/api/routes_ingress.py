"""Raw-body HMAC ingress: observations only; receipt and job commit before acknowledgement."""

import asyncio
import hashlib
import hmac
import re
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text

from opspilot.auth.context import AuthError
from opspilot.integrations.contracts import Observation
from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.secrets import webhook_key
from opspilot.integrations.service import admit
from opspilot.tenancy.context import tenant_scope

router = APIRouter()


def signature_input(tenant: UUID, connector: UUID, stamp: str, raw: bytes) -> bytes:
    return f"opspilot-ingress-v1\n{tenant}\n{connector}\n{stamp}\n".encode() + raw


@router.post("/ingress/v1/{tenant}/{connector}")
async def ingress(tenant: UUID, connector: UUID, request: Request) -> JSONResponse:
    engine = request.app.state.ingress_engine
    if engine is None:
        raise AuthError("INGRESS_UNAVAILABLE", 503)
    headers = request.headers
    if (
        request.url.query
        or headers.get("content-type") != "application/json"
        or headers.get("content-encoding") not in {None, "identity"}
        or headers.get("cookie")
        or headers.get("authorization")
    ):
        raise AuthError("INGRESS_INVALID", 401)
    stamp, kid, signed = (
        headers.get(n, "") for n in ("x-ops-timestamp", "x-ops-key-id", "x-ops-signature")
    )
    if not re.fullmatch(r"[0-9]{10}", stamp) or not re.fullmatch(r"[a-f0-9]{64}", signed):
        raise AuthError("INGRESS_INVALID", 401)
    raw = await request.body()
    if not raw or len(raw) > 16384:
        raise AuthError("INGRESS_SIZE", 413)
    slots = request.app.state.ingress_slots
    try:
        await asyncio.wait_for(slots.acquire(), 0.05)
    except TimeoutError:
        raise AuthError("INGRESS_LIMIT", 429) from None
    try:
        async with engine.begin() as c:
            config = (
                (
                    await c.execute(
                        text("SELECT * FROM integrations.ingress_config(:t,:c)"),
                        {"t": tenant, "c": connector},
                    )
                )
                .mappings()
                .one_or_none()
            )
            now = float(await c.scalar(text("SELECT extract(epoch FROM clock_timestamp())")))
            if config is None or not config["ingress_enabled"] or abs(now - int(stamp)) > 300:
                raise AuthError("INGRESS_INVALID", 401)
            key = await webhook_key(request.app.state.identity.settings, tenant, connector, kid)
            expected = hmac.new(
                key, signature_input(tenant, connector, stamp, raw), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, signed):
                raise AuthError("INGRESS_INVALID", 401)
            try:
                body = Observation.model_validate_json(raw)
            except ValidationError:
                raise AuthError("INGRESS_INVALID", 400) from None
            if (
                body.customer_id != config["customer_id"]
                or body.integration_id != config["integration_id"]
                or not now - 86400 <= body.observed_at.timestamp() <= now + 30
            ):
                raise AuthError("INGRESS_SCOPE", 403)
            with tenant_scope(tenant):
                await c.execute(
                    text("SELECT set_config('app.tenant_id',:t,true)"), {"t": str(tenant)}
                )
                created = await admit(
                    c, connector, body.model_dump(mode="json"), hashlib.sha256(raw).hexdigest(), kid
                )
        # Leaving the transaction above is a mandatory boundary before any 2xx.
        return JSONResponse(
            {"accepted": True, "replayed": not created, "source": "synthetic"},
            status_code=202 if created else 200,
        )
    except ConnectorUnavailable:
        raise AuthError("INGRESS_UNAVAILABLE", 503) from None
    finally:
        slots.release()
