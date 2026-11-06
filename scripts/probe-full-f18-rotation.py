"""Operator-run F18 rotation probe; only producer credentials enter this test container."""

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import text

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.secrets import webhook_key
from opspilot.integrations.service import process_one
from opspilot.tenancy.context import tenant_scope
from tests.auth_helpers import session_client
from tests.f18_cases import CASES
from tests.integration.test_adapter_platform import Producer


async def main():
    settings = Settings()
    phase = os.environ["F18_ROTATION_PHASE"]
    producer = Producer()
    case = CASES[0]
    if phase == "revoked":
        try:
            await webhook_key(settings, UUID(case["tenant_id"]), UUID(case["connector_id"]), "h2")
        except ConnectorUnavailable:
            print("Revoked service token failed closed; no file fallback")
            return
        raise AssertionError("Revoked token still admitted")
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        await session_client(client, settings, "admin", UUID(case["tenant_id"]))
        rows = (await client.get("/api/v2/admin/adapters")).json()["items"]
        current = next(r for r in rows if r["id"] == case["connector_id"])
        response = await client.put(
            "/api/v2/admin/adapters/" + case["connector_id"],
            json={
                "expected_version": current["version"],
                "customer_id": case["customer_id"],
                "integration_id": case["integration_id"],
                "origin": "https://adapter-simulator:8443",
                "read_enabled": True,
                "ingress_enabled": True,
            },
        )
        assert response.status_code == 200
    events = []
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        for kid in ("h1", "h2"):
            body = producer.body()
            response = await producer.post(client, body, kid=kid)
            assert response.status_code == (401 if phase == "retired" and kid == "h1" else 202)
            if response.status_code == 202:
                events.append(body["event_id"])
    if phase == "overlap":
        Path("/reports/rotation-state.json").write_text(json.dumps(events))
    if phase == "retired":
        engine = create_engine(settings.database_url("ingress"))
        try:
            with tenant_scope(UUID(case["tenant_id"])):
                while await process_one(engine):
                    pass
        finally:
            await engine.dispose()
        admin = create_engine(settings.database_url("migration"))
        try:
            async with admin.connect() as c:
                for event in json.loads(Path("/reports/rotation-state.json").read_text()):
                    assert await c.scalar(
                        text("SELECT status FROM integrations.webhook_receipts WHERE event_id=:e"),
                        {"e": UUID(event)},
                    ) in {"processed", "ignored"}
        finally:
            await admin.dispose()
    print("HMAC rotation phase passed:", phase)


asyncio.run(main())
