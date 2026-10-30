"""F16 real PostgreSQL/HTTP diagnostics, lineage and tenant/actor authorization."""

import asyncio
import os
import sys
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT
from tests.auth_helpers import session_client


async def worker(tenant, run):
    environment = dict(os.environ)
    for variable, name in (
        ("TELEMETRY_CA_FILE", "ca.crt"),
        ("TELEMETRY_CERT_FILE", "client.crt"),
        ("TELEMETRY_KEY_FILE", "client.key"),
        ("TELEMETRY_TOKEN_FILE", "token"),
    ):
        environment[variable] = "/run/observability-worker/" + name
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.observability_worker",
        str(tenant),
        str(run),
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), 30)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode == 0, (
        "Independent worker failed (private output retained only in memory)"
    )


@pytest.mark.parametrize("decision", ["reject", "approve"])
async def test_private_diagnostics_and_restart_trace_links(
    integration_settings, admin_engine, decision
):
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        await session_client(client, integration_settings)
        response = await client.post(
            "/api/v2/runs",
            json={"request": "Investigate GreenShop", "client_request_id": str(uuid4())},
        )
        assert response.status_code == 202
        run = UUID(response.json()["run_id"])
        path = response.json()["snapshot_url"]
        await worker(DEMO_TENANT, run)
        snapshot = (await client.get(path)).json()
        assert snapshot["status"] == "waiting_for_approval"

        async def diagnostics():
            async with asyncio.timeout(12):
                while True:
                    value = await client.get(path + "/diagnostics")
                    assert value.status_code == 200
                    data = value.json()
                    if any(
                        e["name"] == "command.process" for e in data["collector"].get("events", [])
                    ):
                        return data
                    await asyncio.sleep(0.2)

        first = await diagnostics()
        commands = [e for e in first["collector"]["events"] if e["name"] == "command.process"]
        assert (
            commands[0]["attributes"]["job_id"] and commands[0]["attributes"]["worker_epoch"] >= 1
        )
        assert commands[0]["links"]
        assert all(j["traceparent"] for j in first["database"]["jobs"])
        initial_id = commands[0]["trace_id"]
        # Human pause has released the process/span and execution ownership.
        async with admin_engine.connect() as c:
            assert await c.scalar(
                text("SELECT owner IS NULL FROM workflow.run_execution_leases WHERE run_id=:r"),
                {"r": run},
            )
        rejected = await client.post(
            path + "/decision",
            json={
                "action_id": snapshot["action"]["action_id"],
                "decision": decision,
                "expected_version": 1,
            },
        )
        assert rejected.status_code == 202
        await worker(DEMO_TENANT, run)
        async with asyncio.timeout(12):
            while True:
                final = (await client.get(path + "/diagnostics")).json()
                commands = [
                    e
                    for e in final["collector"].get("events", [])
                    if e["name"] == "command.process"
                ]
                if len(commands) >= 2:
                    break
                await asyncio.sleep(0.2)
        assert initial_id in {e["trace_id"] for e in commands}
        assert len({e["trace_id"] for e in commands}) >= 2
        assert max(e["attributes"]["worker_epoch"] for e in commands) > min(
            e["attributes"]["worker_epoch"] for e in commands
        )
        assert any(
            e.get("links")
            for e in final["collector"]["events"]
            if e["name"] == "graph.continuation"
        )
        assert (await client.get(path)).json()["status"] == "completed"
        if decision == "approve":
            names = {e["name"] for e in final["collector"]["events"]}
            assert {
                "adapter.call",
                "verification.read",
                "mcp.server.tool",
                "reconciliation.check",
            } <= names
        assert "request" not in final["database"]["run"]
        assert "private_key" not in str(final)


async def test_diagnostics_tenant_actor_and_live_role_denial(integration_settings, admin_engine):
    async with (
        httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as owner,
        httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as other,
    ):
        _, actor = await session_client(owner, integration_settings, "operator", DEMO_TENANT)
        created = await owner.post(
            "/api/v2/runs", json={"request": "Status GreenShop", "client_request_id": str(uuid4())}
        )
        assert created.status_code == 202
        path = created.json()["snapshot_url"] + "/diagnostics"
        assert (await owner.get(path)).status_code == 200
        await session_client(other, integration_settings, "demo", DEMO_TENANT)
        assert (await other.get(path)).status_code == 404
        overview = (await other.get("/api/v2/diagnostics")).json()
        assert all(j["run_id"] != created.json()["run_id"] for j in overview["database"]["jobs"])
        await session_client(other, integration_settings, "operator", SECOND_TENANT)
        assert (await other.get(path)).status_code == 404
        await session_client(other, integration_settings, "approver", DEMO_TENANT)
        assert (await other.get("/api/v2/diagnostics")).status_code == 403
        async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as anonymous:
            assert (await anonymous.get("/api/v2/diagnostics")).status_code == 401
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "DELETE FROM identity.tenant_memberships "
                    "WHERE tenant_id=:t AND user_id=:u AND role='operator'"
                ),
                {"t": DEMO_TENANT, "u": actor},
            )
        try:
            assert (await owner.get(path)).status_code in (403, 404)
        finally:
            async with admin_engine.begin() as c:
                await c.execute(
                    text(
                        "INSERT INTO identity.tenant_memberships(tenant_id,user_id,role) "
                        "VALUES(:t,:u,'operator') ON CONFLICT DO NOTHING"
                    ),
                    {"t": DEMO_TENANT, "u": actor},
                )


async def test_diagnostic_alert_conditions_use_actual_database_state(
    integration_settings, admin_engine
):
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        await session_client(client, integration_settings)
        result = await client.post(
            "/api/v2/runs", json={"request": "Status GreenShop", "client_request_id": str(uuid4())}
        )
        run = UUID(result.json()["run_id"])
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "UPDATE workflow.command_jobs "
                    "SET created_at=clock_timestamp()-interval '90 seconds' WHERE run_id=:r"
                ),
                {"r": run},
            )
        data = (await client.get(result.json()["snapshot_url"] + "/diagnostics")).json()
        assert data["database"]["queue_age_seconds"] >= 80
        assert "QUEUE_AGE" in {x["code"] for x in data["alerts"]}
        assert data["thresholds_are_project_conditions"]
        assert "request" not in str(data["database"]["jobs"])


async def test_idle_database_is_quiet_and_active_sql_errors_remain_traced(
    admin_engine, monkeypatch
):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from sqlalchemy.exc import DBAPIError

    from opspilot.telemetry import span

    provider = TracerProvider()
    output = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(output))
    monkeypatch.setattr(trace, "get_tracer", lambda *args: provider.get_tracer("test"))
    async with admin_engine.connect() as c:
        await c.execute(text("SELECT 1"))
    assert not output.get_finished_spans()
    with span("command.process"):
        async with admin_engine.connect() as c:
            await c.execute(text("SELECT 1"))
        with pytest.raises(DBAPIError):
            async with admin_engine.connect() as c:
                await c.execute(text("SELECT 'F16_PRIVATE_SQL_ERROR_SENTINEL'::integer"))
    records = output.get_finished_spans()
    assert any(r.name == "db.operation" for r in records)
    assert any(r.name == "db.operation" and r.status.status_code.name == "ERROR" for r in records)
    assert "F16_PRIVATE_SQL_ERROR_SENTINEL" not in str(
        [(r.attributes, r.events, r.status.description) for r in records]
    )
    provider.shutdown()
