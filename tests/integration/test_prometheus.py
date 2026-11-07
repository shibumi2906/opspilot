"""Actual Prometheus, HTTPS faults, manager ACL, database roles and MCP boundaries."""

import asyncio
import ipaddress
import json
import os
import ssl
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from opspilot.agent.service import run_investigation
from opspilot.db.engine import create_engine
from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.prometheus.normalize import normalize
from opspilot.integrations.prometheus.registry import Registration, registration
from opspilot.integrations.prometheus.transport import _request, build_info, expression, query
from opspilot.integrations.secrets import prometheus_authorization, read
from opspilot.mcp_client.client import MCPClient
from opspilot.mcp_server.adapters.platform import snapshot as connector_snapshot
from opspilot.security.freshness import PreconditionsChanged, snapshot
from opspilot.tenancy.context import tenant_scope
from opspilot.tenancy.session import TenantSession
from tests.auth_helpers import session_client
from tests.f19_cases import CASES

pytestmark = pytest.mark.skipif(
    os.environ.get("F19_CONTRACT") != "1", reason="Dedicated real local F19 Prometheus profile"
)


def registered(settings, index=0):
    case = CASES[index]
    return registration(settings, UUID(case["tenant_id"]), UUID(case["connector_id"]))


async def authorization(settings, reg):
    return await prometheus_authorization(
        settings, reg.tenant_id, reg.connector_id, reg.auth_scheme
    )


async def mode(value):
    raw = await asyncio.to_thread(Path("/run/f19-probe/fixture.json").read_text)
    control = json.loads(raw)["control"]
    context = ssl.create_default_context(cafile="/run/prometheus-client/ca.crt")
    async with httpx.AsyncClient(verify=context, trust_env=False) as c:
        r = await c.post(
            "https://metric-fixture:8443/control",
            headers={"Authorization": "Bearer " + control},
            json={"mode": value},
        )
        assert r.status_code == 200


@pytest.fixture
async def normal():
    await mode("normal")
    await asyncio.sleep(1.6)
    yield
    await mode("normal")


@pytest.fixture
async def configured(integration_settings, admin_engine, normal):
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as c:
        for case in CASES:
            await session_client(c, integration_settings, "admin", UUID(case["tenant_id"]))
            items = (await c.get("/api/v2/admin/adapters")).json()["items"]
            version = next((r["version"] for r in items if r["id"] == case["connector_id"]), 0)
            r = await c.put(
                "/api/v2/admin/adapters/" + case["connector_id"],
                json={
                    "expected_version": version,
                    "kind": "prometheus",
                    "customer_id": case["customer_id"],
                    "integration_id": case["integration_id"],
                    "origin": "https://prometheus:8443",
                    "read_enabled": True,
                    "ingress_enabled": False,
                },
            )
            assert r.status_code == 200, r.text
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("UPDATE integrations.connector_health SET failures=0,open_until=NULL")
            )
    return CASES


async def rpc(settings, index=0, name="get_service_status", **extra):
    case = CASES[index]
    with tenant_scope(UUID(case["tenant_id"])):
        async with MCPClient(settings).session() as (session, _):
            return await MCPClient.call(
                session,
                name,
                {
                    "customer_id": case["customer_id"],
                    "integration_id": case["integration_id"],
                    **extra,
                },
            )


async def test_native_version_scope_and_sample_age(integration_settings, normal):
    reg = registered(integration_settings)
    auth = await authorization(integration_settings, reg)
    info = await build_info(reg, auth)
    assert info["data"]["version"] == "3.16.0"
    now = round(time.time(), 3)
    body, step = await query(reg, auth, now, None)
    assert step == 0
    assert normalize(reg, body, now)["status"] == "degraded"
    assert len(body["data"]["result"]) == 4
    assert all(r["metric"]["tenant_id"] == CASES[0]["tenant_id"] for r in body["data"]["result"])
    # Real engine evaluation time advances; the actual scrape timestamp does not.
    future = round(time.time() + 125, 3)
    old, _ = await query(reg, auth, future, None)
    assert old["data"]["result"], "Exercise lookback with real old samples, not an empty mock"
    assert normalize(reg, old, future)["status"] == "unknown"
    if directory := os.environ.get("F19_REPORT_DIR"):
        report = {
            "passed": True,
            "scope": "local real engine, synthetic series; no staging acceptance",
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "build": {
                key: info["data"].get(key)
                for key in ("version", "revision", "goVersion", "buildDate")
            },
            "tenant_id": str(reg.tenant_id),
            "customer_id": str(reg.customer_id),
            "integration_id": str(reg.integration_id),
            "connector_id": str(reg.connector_id),
            "origin": reg.origin,
            "targets": list(reg.targets),
            "auth_scheme": reg.auth_scheme,
            "source_version": reg.source_version(),
            "status": "degraded",
            "series": len(body["data"]["result"]),
            "stale_sample_check": "unknown",
            "credential_expiration": "unknown",
            "staging_live_gate": "OPEN",
            "secrets_exported": False,
        }
        await asyncio.to_thread(
            (Path(directory) / "prometheus-smoke.json").write_text,
            json.dumps(report, indent=2) + "\n",
        )


@pytest.mark.parametrize(
    "value,status",
    [
        ("healthy", "healthy"),
        ("unavailable", "unavailable"),
        ("absent", "unknown"),
        ("partial", "unknown"),
    ],
)
async def test_native_status_absent_partial(integration_settings, value, status, normal):
    reg = registered(integration_settings)
    auth = await authorization(integration_settings, reg)
    await mode(value)
    async with asyncio.timeout(12):
        while True:
            now = round(time.time(), 3)
            body, _ = await query(reg, auth, now, None)
            if normalize(reg, body, now)["status"] == status:
                break
            await asyncio.sleep(0.4)


async def test_mcp_provenance_tenant_events_and_expiration(configured, integration_settings):
    a, b = await rpc(integration_settings), await rpc(integration_settings, 1)
    assert a.ok and b.ok and a.data["status"] == "degraded" and b.data["status"] == "healthy"
    assert all(s.version == "prometheus-mapping1:synthetic:fixture" for s in a.sources)
    expiry = await rpc(integration_settings, name="get_credential_status")
    assert expiry.ok and expiry.data["status"] == "unknown"
    end = datetime.now(UTC)
    events = await rpc(
        integration_settings,
        name="get_integration_events",
        **{"from": (end - timedelta(seconds=45)).isoformat(), "to": end.isoformat(), "limit": 1},
    )
    assert events.ok and len(events.data["events"]) == 1 and events.data["truncated"]
    assert events.data["events"][0]["summary"].startswith("Synthetic")
    assert all(s.version == "prometheus-mapping1:synthetic:fixture" for s in events.sources)
    with tenant_scope(UUID(CASES[1]["tenant_id"])):
        async with MCPClient(integration_settings).session() as (session, _):
            denied = await MCPClient.call(
                session,
                "get_service_status",
                {
                    "customer_id": CASES[0]["customer_id"],
                    "integration_id": CASES[0]["integration_id"],
                },
            )
            assert not denied.ok and denied.error.code == "NOT_FOUND"


@pytest.mark.parametrize(
    "attack",
    [
        "401",
        "403",
        "429",
        "500",
        "503",
        "redirect",
        "slow",
        "drip",
        "oversized",
        "duplicate_json",
        "compressed",
        "warnings",
        "infos",
        "invalid",
    ],
)
async def test_actual_https_error_boundaries(integration_settings, normal, attack):
    await mode(attack)
    reg = Registration.model_validate(
        {
            **registered(integration_settings).model_dump(),
            "origin": "https://metric-fixture:8443",
            "addresses": [
                str(ipaddress.ip_address(registered(integration_settings).addresses[0]) + 1)
            ],
        }
    )
    auth = await authorization(integration_settings, reg)
    started = time.monotonic()
    with pytest.raises(ConnectorUnavailable):
        await query(reg, auth, round(time.time(), 3), None)
    assert time.monotonic() - started < 3


async def test_real_credential_scope_and_native_denial(integration_settings, normal):
    reg = registered(integration_settings)
    assert await authorization(integration_settings, reg) != await authorization(
        integration_settings, registered(integration_settings, 1)
    )
    with pytest.raises(ConnectorUnavailable):
        await query(reg, "Basic aW52YWxpZDppbnZhbGlk", time.time(), None)
    with pytest.raises(ConnectorUnavailable):
        await read(integration_settings, reg.tenant_id, reg.connector_id, "webhook")
    with pytest.raises(ConnectorUnavailable):
        await read(integration_settings, reg.tenant_id, uuid4(), "credential")
    with pytest.raises(ConnectorUnavailable):
        await read(
            integration_settings, UUID(CASES[1]["tenant_id"]), reg.connector_id, "credential"
        )


async def test_native_engine_cardinality_limit(integration_settings, normal):
    reg = registered(integration_settings)
    auth = await authorization(integration_settings, reg)
    await mode("cardinality")
    await asyncio.sleep(1.6)
    with pytest.raises(ConnectorUnavailable):
        await query(reg, auth, round(time.time(), 3), None)


async def test_manager_denial_persists_breaker(configured, integration_settings):
    settings = integration_settings.model_copy(
        update={
            "connector_manager_token_file": "/run/f19-probe/invalid.token",
        }
    )
    engine = create_engine(settings.database_url("domain"))
    case = CASES[0]
    try:
        for _ in range(3):
            with pytest.raises(ConnectorUnavailable):
                await connector_snapshot(
                    engine,
                    settings,
                    UUID(case["customer_id"]),
                    UUID(case["integration_id"]),
                    probe=True,
                )
        async with engine.connect() as c:
            state = (
                await c.execute(
                    text(
                        "SELECT failures,open_until>clock_timestamp() "
                        "FROM integrations.connector_health "
                        "WHERE tenant_id=:t AND connector_id=:c"
                    ),
                    {"t": UUID(case["tenant_id"]), "c": UUID(case["connector_id"])},
                )
            ).one()
            assert state == (3, True)
        with pytest.raises(ConnectorUnavailable):
            await connector_snapshot(
                engine,
                integration_settings,
                UUID(case["customer_id"]),
                UUID(case["integration_id"]),
                probe=True,
            )
    finally:
        await engine.dispose()


@pytest.mark.parametrize("attack", ["dns_pin", "wrong_ca", "hostname", "free_query", "admin_path"])
async def test_native_egress_tls_query_scope(integration_settings, normal, attack):
    reg = registered(integration_settings)
    auth = await authorization(integration_settings, reg)
    path = "/api/v1/query"
    params = {"query": expression(reg), "time": str(time.time()), "timeout": "500ms", "limit": "17"}
    if attack == "dns_pin":
        reg = reg.model_copy(update={"addresses": ("10.245.24.12",)})
    elif attack == "wrong_ca":
        reg = reg.model_copy(update={"ca_file": "/run/prometheus-client/manager-ca.crt"})
    elif attack == "hostname":
        reg = reg.model_copy(
            update={
                "origin": "https://untrusted-fixture:8443",
                "addresses": (str(ipaddress.ip_address(reg.addresses[0]) + 1),),
            }
        )
    elif attack == "free_query":
        params["query"] = "up"
    else:
        path = "/api/v1/admin/tsdb/delete_series"
    with pytest.raises(ConnectorUnavailable):
        await asyncio.to_thread(_request, reg, auth, path, params, time.monotonic() + 2)


async def test_admin_readonly_mapping_cas_and_db_guards(
    configured, integration_settings, admin_engine
):
    case = CASES[0]
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as c:
        await session_client(c, integration_settings, "operator")
        assert (await c.get("/api/v2/admin/adapters")).status_code == 403
        await session_client(c, integration_settings, "admin")
        public = (await c.get("/api/v2/admin/adapters")).json()
        assert "credential_ref" not in json.dumps(public) and "token" not in json.dumps(public)
        current = next(r for r in public["items"] if r["id"] == case["connector_id"])
        value = {
            "expected_version": current["version"],
            "kind": "prometheus",
            "customer_id": case["customer_id"],
            "integration_id": case["integration_id"],
            "origin": "https://prometheus:8443",
            "read_enabled": True,
            "ingress_enabled": False,
        }
        assert (
            await c.put("/api/v2/admin/adapters/" + case["connector_id"], json=value)
        ).status_code == 200
        assert (
            await c.put("/api/v2/admin/adapters/" + case["connector_id"], json=value)
        ).status_code == 409
        for override in ({"ingress_enabled": True}, {"query": "up"}, {"credential_ref": "foreign"}):
            assert (
                await c.put(
                    "/api/v2/admin/adapters/" + case["connector_id"], json={**value, **override}
                )
            ).status_code == 422
    with pytest.raises(DBAPIError):
        async with admin_engine.begin() as c:
            await c.execute(
                text("UPDATE integrations.connector_configs SET adapter_mapping='{}' WHERE id=:id"),
                {"id": UUID(case["connector_id"])},
            )
    with pytest.raises(DBAPIError):
        async with admin_engine.begin() as c:
            await c.execute(
                text("UPDATE integrations.connector_configs SET ingress_enabled=true WHERE id=:id"),
                {"id": UUID(case["connector_id"])},
            )


async def test_configured_source_preconditions_fail_closed(configured, integration_settings):
    value = await run_investigation(integration_settings, "Status GreenShop", mode="scripted")
    engine = create_engine(integration_settings.database_url("workflow"))
    try:
        async with TenantSession(engine) as session, session.begin():
            with pytest.raises(PreconditionsChanged) as exc:
                await snapshot(
                    session,
                    UUID(str(value["run_id"])),
                    {"customer_id": CASES[0]["customer_id"]},
                    integration_settings,
                )
            assert exc.value.code == "PRECONDITIONS_UNKNOWN"
        with tenant_scope(UUID(CASES[1]["tenant_id"])):
            async with engine.connect() as c:
                assert not await c.scalar(
                    text("SELECT integrations.has_binding(:i)"),
                    {"i": UUID(CASES[0]["integration_id"])},
                )
    finally:
        await engine.dispose()
