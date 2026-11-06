"""Admin configuration and atomic observation-only ingress processing."""

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opspilot.auth.context import actor_id
from opspilot.config import Settings
from opspilot.integrations.contracts import ConfigChange
from opspilot.integrations.egress import registered
from opspilot.runtime.actions import Conflict
from opspilot.tenancy.context import require_tenant


async def audit(c: AsyncConnection, connector: UUID, kind: str, event: UUID | None = None) -> None:
    await c.execute(
        text("""INSERT INTO integrations.audit
      (id,tenant_id,connector_id,event_id,actor_id,kind) VALUES(:id,:t,:c,:e,:a,:k)"""),
        {
            "id": uuid4(),
            "t": require_tenant(),
            "c": connector,
            "e": event,
            "a": actor_id() if kind == "configured" else None,
            "k": kind,
        },
    )


async def configure(
    engine: AsyncEngine, settings: Settings, connector: UUID, value: ConfigChange
) -> dict[str, Any]:
    registered(settings, value.origin)
    tenant = require_tenant()
    async with engine.begin() as c:
        await c.execute(text("SELECT pg_advisory_xact_lock(1801202618)"))
        row = (
            (
                await c.execute(
                    text(
                        "SELECT * FROM integrations.connector_configs "
                        "WHERE tenant_id=:t AND id=:id FOR UPDATE"
                    ),
                    {"t": tenant, "id": connector},
                )
            )
            .mappings()
            .one_or_none()
        )
        if (row is None and value.expected_version != 0) or (
            row is not None
            and (
                row["version"] != value.expected_version
                or row["mapping_hash"] != value.mapping_hash()
            )
        ):
            raise Conflict("Configuration changed; immutable mapping requires a new connector")
        params = {
            "t": tenant,
            "id": connector,
            "customer": value.customer_id,
            "integration": value.integration_id,
            "origin": value.origin,
            "hash": value.mapping_hash(),
            "read": value.read_enabled,
            "ingress": value.ingress_enabled,
            "credential": f"connectors/{tenant}/{connector}/credential",
            "webhook": f"connectors/{tenant}/{connector}/webhook",
        }
        if row is None:
            if await c.scalar(text("SELECT count(*)>=100 FROM integrations.connector_configs")):
                raise Conflict("Connector configuration bound reached")
            await c.execute(
                text("""INSERT INTO integrations.connector_configs
              (tenant_id,id,customer_id,integration_id,kind,mapping_version,origin,mapping_hash,
               credential_ref,webhook_ref,read_enabled,ingress_enabled)
              VALUES(:t,:id,:customer,:integration,'simulator',1,:origin,:hash,:credential,
               :webhook,:read,:ingress)"""),
                params,
            )
        else:
            await c.execute(
                text("""UPDATE integrations.connector_configs
              SET read_enabled=:read,ingress_enabled=:ingress,version=version+1,
              updated_at=clock_timestamp() WHERE tenant_id=:t AND id=:id"""),
                params,
            )
        await audit(c, connector, "configured")
        return {
            "id": str(connector),
            "version": 1 if row is None else row["version"] + 1,
            "mapping_version": 1,
            "source": "synthetic",
            "write_enabled": False,
        }


async def process_one(engine: AsyncEngine) -> bool:
    # The job row lock, cursor CAS, observation and completion share one transaction.
    # A process crash before commit leaves the same pending job; no external effect exists.
    async with engine.begin() as c:
        job = (
            (
                await c.execute(
                    text("""SELECT * FROM integrations.ingress_jobs
          WHERE tenant_id=:t AND status='pending' ORDER BY created_at,event_id
          LIMIT 1 FOR UPDATE SKIP LOCKED"""),
                    {"t": require_tenant()},
                )
            )
            .mappings()
            .one_or_none()
        )
        if job is None:
            return False
        p = {"t": require_tenant(), "c": job["connector_id"], "e": job["event_id"]}
        config = (
            (
                await c.execute(
                    text("SELECT ingress_enabled FROM integrations.lock_config(:c)"),
                    p,
                )
            )
            .mappings()
            .one()
        )
        receipt = (
            (
                await c.execute(
                    text("""SELECT payload FROM integrations.webhook_receipts
          WHERE tenant_id=:t AND connector_id=:c AND event_id=:e FOR UPDATE"""),
                    p,
                )
            )
            .mappings()
            .one()
        )
        body = receipt["payload"]
        status = "quarantined"
        if config["ingress_enabled"]:
            advanced = await c.scalar(
                text("""INSERT INTO integrations.ingress_cursors
              (tenant_id,connector_id,sequence) VALUES(:t,:c,:s)
              ON CONFLICT(tenant_id,connector_id) DO UPDATE SET sequence=EXCLUDED.sequence
              WHERE integrations.ingress_cursors.sequence<EXCLUDED.sequence RETURNING sequence"""),
                {**p, "s": body["sequence"]},
            )
            status = "ignored" if advanced is None else "processed"
            if advanced is not None:
                await c.execute(
                    text("""INSERT INTO integrations.observations
                  (tenant_id,connector_id,event_id,sequence,status,observed_at)
                  VALUES(:t,:c,:e,:s,:status,CAST(:at AS timestamptz))"""),
                    {
                        **p,
                        "s": body["sequence"],
                        "status": body["status"],
                        "at": body["observed_at"],
                    },
                )
        await c.execute(
            text("""UPDATE integrations.webhook_receipts SET status=:status
          WHERE tenant_id=:t AND connector_id=:c AND event_id=:e"""),
            {**p, "status": status},
        )
        await c.execute(
            text("""UPDATE integrations.ingress_jobs SET status='done',
          finished_at=clock_timestamp() WHERE tenant_id=:t AND connector_id=:c AND event_id=:e"""),
            p,
        )
        await audit(c, job["connector_id"], status, job["event_id"])
        return True


async def admit(
    c: AsyncConnection, connector: UUID, body: dict[str, Any], digest: str, kid: str
) -> bool:
    await c.execute(text("SELECT pg_advisory_xact_lock(1801202618)"))
    p = {"t": require_tenant(), "c": connector, "e": UUID(body["event_id"])}
    enabled = await c.scalar(
        text("SELECT ingress_enabled FROM integrations.lock_config(:c)"),
        p,
    )
    if not enabled:
        from opspilot.auth.context import AuthError

        raise AuthError("INGRESS_INVALID", 401)
    previous = await c.scalar(
        text("""SELECT body_hash FROM integrations.webhook_receipts
      WHERE tenant_id=:t AND connector_id=:c AND event_id=:e"""),
        p,
    )
    if previous:
        if previous != digest:
            raise Conflict("Event identity already reserved")
        return False
    allowed = await c.scalar(text("SELECT integrations.admit_ingress()"))
    count = await c.scalar(
        text("""SELECT count(*) FROM integrations.ingress_jobs
      WHERE tenant_id=:t AND connector_id=:c AND status='pending'"""),
        p,
    )
    retained = await c.scalar(
        text("""SELECT count(*) FROM integrations.webhook_receipts
      WHERE tenant_id=:t AND connector_id=:c"""),
        p,
    )
    minute = await c.scalar(text("SELECT floor(extract(epoch FROM clock_timestamp())/60)::bigint"))
    quota = await c.scalar(
        text("""INSERT INTO integrations.ingress_budgets
      (tenant_id,connector_id,minute,used) VALUES(:t,:c,:m,1)
      ON CONFLICT(tenant_id,connector_id) DO UPDATE SET minute=EXCLUDED.minute,
      used=CASE WHEN ingress_budgets.minute=EXCLUDED.minute THEN ingress_budgets.used+1 ELSE 1 END
      WHERE ingress_budgets.minute<>EXCLUDED.minute OR ingress_budgets.used<60 RETURNING used"""),
        {**p, "m": minute},
    )
    if not allowed or count >= 100 or retained >= 10000 or quota is None:
        from opspilot.auth.context import AuthError

        raise AuthError("INGRESS_LIMIT", 429)
    await c.execute(
        text("""INSERT INTO integrations.webhook_receipts
      (tenant_id,connector_id,event_id,body_hash,kid,payload)
      VALUES(:t,:c,:e,:hash,:kid,CAST(:p AS jsonb))"""),
        {**p, "hash": digest, "kid": kid, "p": json.dumps(body)},
    )
    await c.execute(
        text("""INSERT INTO integrations.ingress_jobs(tenant_id,connector_id,event_id)
      VALUES(:t,:c,:e)"""),
        p,
    )
    await audit(c, connector, "accepted", UUID(body["event_id"]))
    return True
