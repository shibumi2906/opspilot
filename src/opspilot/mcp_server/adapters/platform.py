"""F18 platform behind existing canonical MCP contracts; no vendor write dispatch."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from weakref import WeakKeyDictionary

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.auth.context import AuthError
from opspilot.config import Settings
from opspilot.integrations.contracts import AdapterScope
from opspilot.integrations.egress import ConnectorUnavailable, health
from opspilot.integrations.secrets import credential
from opspilot.tenancy.context import require_tenant

_slots: WeakKeyDictionary[AsyncEngine, asyncio.Semaphore] = WeakKeyDictionary()


async def configured(engine: AsyncEngine, integration: UUID) -> bool:
    async with engine.connect() as c:
        return bool(
            await c.scalar(
                text("""SELECT EXISTS(SELECT 1 FROM integrations.connector_configs
          WHERE tenant_id=:t AND integration_id=:i)"""),
                {"t": require_tenant(), "i": integration},
            )
        )


async def _snapshot(
    engine: AsyncEngine, settings: Settings, customer: UUID, integration: UUID, *, probe: bool
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unknown",
        "latest_success_at": None,
        "checked_at": datetime.now(UTC),
        "credential_status": "unknown",
        "events": [],
    }
    failed = False
    async with engine.begin() as c:
        config = (
            (
                await c.execute(
                    text("""SELECT * FROM integrations.connector_configs
          WHERE tenant_id=:t AND integration_id=:i AND customer_id=:customer"""),
                    {"t": require_tenant(), "i": integration, "customer": customer},
                )
            )
            .mappings()
            .one_or_none()
        )
        if config is None or not config["read_enabled"]:
            raise AuthError("NOT_FOUND", 404)
        p = {"t": require_tenant(), "c": config["id"]}
        config = (
            (await c.execute(text("SELECT * FROM integrations.lock_config(:c)"), p))
            .mappings()
            .one()
        )
        if not config["read_enabled"]:
            raise AuthError("NOT_FOUND", 404)
        await c.execute(
            text("""INSERT INTO integrations.connector_health(tenant_id,connector_id)
          VALUES(:t,:c) ON CONFLICT DO NOTHING"""),
            p,
        )
        state = (
            (
                await c.execute(
                    text("""SELECT *,open_until>clock_timestamp() AS blocked
          FROM integrations.connector_health WHERE tenant_id=:t AND connector_id=:c
          FOR UPDATE"""),
                    p,
                )
            )
            .mappings()
            .one()
        )
        if probe:
            if state["blocked"]:
                raise ConnectorUnavailable()
            try:
                token = await credential(settings, require_tenant(), config["id"])
                observed = await health(
                    settings,
                    config["origin"],
                    token,
                    AdapterScope(
                        tenant_id=require_tenant(),
                        connector_id=config["id"],
                        customer_id=customer,
                        integration_id=integration,
                    ),
                )
                result.update(status=observed.status, checked_at=observed.checked_at)
                await c.execute(
                    text("""UPDATE integrations.connector_health SET failures=0,
                  open_until=NULL,checked_at=clock_timestamp()
                  WHERE tenant_id=:t AND connector_id=:c"""),
                    p,
                )
            except ConnectorUnavailable:
                failed = True
                await c.execute(
                    text("""UPDATE integrations.connector_health SET failures=LEAST(failures+1,3),
                  open_until=CASE WHEN failures>=2 THEN clock_timestamp()+interval '30 seconds'
                  ELSE NULL END,checked_at=clock_timestamp()
                  WHERE tenant_id=:t AND connector_id=:c"""),
                    p,
                )
        rows = (
            (
                await c.execute(
                    text("""SELECT event_id,status,observed_at FROM integrations.observations
          WHERE tenant_id=:t AND connector_id=:c ORDER BY observed_at DESC,event_id LIMIT 101"""),
                    p,
                )
            )
            .mappings()
            .all()
        )
        result["events"] = [
            {
                "event_id": r["event_id"],
                "occurred_at": r["observed_at"],
                "http_status": None,
                "event_type": "synthetic.connector_observation",
                "summary": "Synthetic connector status: " + r["status"],
            }
            for r in rows
        ]
    if failed:
        raise ConnectorUnavailable()
    return result


async def snapshot(
    engine: AsyncEngine, settings: Settings, customer: UUID, integration: UUID, *, probe: bool
) -> dict[str, Any]:
    slots = _slots.setdefault(engine, asyncio.Semaphore(4))
    try:
        await asyncio.wait_for(slots.acquire(), 0.05)
    except TimeoutError:
        raise ConnectorUnavailable() from None
    try:
        return await _snapshot(engine, settings, customer, integration, probe=probe)
    finally:
        slots.release()
