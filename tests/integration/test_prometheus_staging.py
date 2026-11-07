"""Explicit opt-in: actual authorized single-tenant AWS staging, never fixture modes."""

import asyncio
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.prometheus.normalize import normalize
from opspilot.integrations.prometheus.registry import Registration
from opspilot.integrations.prometheus.transport import build_info, query
from opspilot.integrations.secrets import prometheus_authorization, read
from opspilot.mcp_client.client import MCPClient
from opspilot.tenancy.context import SECOND_TENANT, tenant_scope
from tests.auth_helpers import session_client

pytestmark = pytest.mark.skipif(os.environ.get("F19_AWS") != "1", reason="Authorized AWS only")


async def test_authorized_aws_scope_mcp(integration_settings):
    reg = Registration.model_validate(
        json.loads(
            await asyncio.to_thread(Path(integration_settings.prometheus_registry_file).read_text)
        )[0]
    )
    assert reg.deployment == "staging" and reg.dataset == "observed"
    auth = await prometheus_authorization(
        integration_settings, reg.tenant_id, reg.connector_id, "basic"
    )
    info = await build_info(reg, auth)
    assert info["data"]["version"] == "3.16.0"
    now = round(time.time(), 3)
    body, _ = await query(reg, auth, now, None)
    result = normalize(reg, body, now)
    expected = os.environ.get("F19_AWS_EXPECTED", "healthy")
    assert result["status"] == expected
    assert len(body["data"]["result"]) == 4
    assert all(r["metric"]["tenant_id"] == str(reg.tenant_id) for r in body["data"]["result"])
    with pytest.raises(ConnectorUnavailable):
        await query(reg, "Basic aW52YWxpZDppbnZhbGlk", time.time(), None)
    with pytest.raises(ConnectorUnavailable):
        await read(integration_settings, SECOND_TENANT, reg.connector_id, "credential")
    foreign = reg.model_copy(update={"tenant_id": uuid4()})
    absent, _ = await query(foreign, auth, round(time.time(), 3), None)
    assert absent["data"]["result"] == []
    assert normalize(foreign, absent, round(time.time(), 3))["status"] == "unknown"
    future = round(time.time() + 125, 3)
    stale, _ = await query(reg, auth, future, None)
    assert stale["data"]["result"]
    assert normalize(reg, stale, future)["status"] == "unknown"
    partial = reg.model_copy(update={"targets": (*reg.targets, "unconfigured")})
    part_body, _ = await query(partial, auth, now, None)
    assert normalize(partial, part_body, now)["status"] == "unknown"
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        await session_client(client, integration_settings, "admin", reg.tenant_id)
        items = (await client.get("/api/v2/admin/adapters")).json()["items"]
        version = next((r["version"] for r in items if r["id"] == str(reg.connector_id)), 0)
        response = await client.put(
            "/api/v2/admin/adapters/" + str(reg.connector_id),
            json={
                "expected_version": version,
                "kind": "prometheus",
                "customer_id": str(reg.customer_id),
                "integration_id": str(reg.integration_id),
                "origin": reg.origin,
                "read_enabled": True,
                "ingress_enabled": False,
            },
        )
        assert response.status_code == 200

    async def rpc(name, **extra):
        with tenant_scope(reg.tenant_id):
            async with MCPClient(integration_settings).session() as (session, _):
                return await MCPClient.call(
                    session,
                    name,
                    {
                        "customer_id": str(reg.customer_id),
                        "integration_id": str(reg.integration_id),
                        **extra,
                    },
                )

    status = await rpc("get_service_status")
    assert status.ok and status.data["status"] == expected
    assert all(s.version == "prometheus-mapping1:observed:staging" for s in status.sources)
    expiry = await rpc("get_credential_status")
    assert expiry.ok and expiry.data["status"] == "unknown"
    end = datetime.now(UTC)
    events = await rpc(
        "get_integration_events",
        **{"from": (end - timedelta(seconds=45)).isoformat(), "to": end.isoformat(), "limit": 5},
    )
    assert events.ok and events.data["events"]
    assert all(e["summary"].startswith("Observed") for e in events.data["events"])
    with tenant_scope(SECOND_TENANT):
        async with MCPClient(integration_settings).session() as (session, _):
            denied = await MCPClient.call(
                session,
                "get_service_status",
                {"customer_id": str(reg.customer_id), "integration_id": str(reg.integration_id)},
            )
            assert not denied.ok and denied.error.code == "NOT_FOUND"
    report = {
        "passed": True,
        "checked_at": datetime.now(UTC).isoformat(),
        "classification": "actual owned staging service measurements; not customer/live data",
        "build": {k: info["data"].get(k) for k in ("version", "revision", "goVersion")},
        "source_version": reg.source_version(),
        "status": expected,
        "series": 4,
        "tenant_scope": str(reg.tenant_id),
        "connector": str(reg.connector_id),
        "targets": list(reg.targets),
        "bad_auth": "denied",
        "foreign_scope": "empty/NOT_FOUND",
        "stale_absent_partial": "unknown",
        "credential_expiry": "unknown",
        "mcp": "passed",
    }
    await asyncio.to_thread(
        Path("/reports/" + expected + "-smoke.json").write_text, json.dumps(report, indent=2)
    )
