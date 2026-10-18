import pytest
from sqlalchemy import text

from opspilot.cli.diagnose import diagnose
from opspilot.fixtures.loader import GREENSHOP_ID, GREENSHOP_INTEGRATION_ID
from opspilot.mcp_client.client import MCPClient

SCOPE = {"customer_id": GREENSHOP_ID, "integration_id": GREENSHOP_INTEGRATION_ID}


async def test_all_reads_and_no_mutations(integration_settings, admin_engine):
    async with admin_engine.connect() as conn:
        before = (
            (
                await conn.execute(
                    text("SELECT row_to_json(t)::text FROM domain.tickets t ORDER BY id")
                )
            )
            .scalars()
            .all()
        )
    report = await diagnose(integration_settings, "GreenShop", "ru")
    assert report["outcome"] == "diagnosis_only"
    results = report["results"]
    assert results["get_service_status"]["data"]["status"] == "degraded"
    assert results["get_integration_events"]["data"]["events"][0]["http_status"] == 401
    assert results["get_credential_status"]["data"]["status"] == "expired"
    assert results["search_incidents"]["data"]["hits"]
    assert results["search_documentation"]["data"]["hits"]
    assert all(e["evidence_id"].startswith("ev_") for e in report["evidence"])
    assert (await diagnose(integration_settings, "Green", "ru"))[
        "outcome"
    ] == "insufficient_context"
    client = MCPClient(integration_settings)
    async with client.session() as (session, _):
        missing = await client.call(
            session, "get_ticket", {"ticket_id": "ffffffff-ffff-ffff-ffff-ffffffffffff"}
        )
        assert not missing.ok and missing.error.code == "NOT_FOUND"
        for name in ("get_service_status", "get_credential_status", "get_integration_events"):
            args = SCOPE | {"integration_id": "00000000-0000-0000-0000-000000000102"}
            if name == "get_integration_events":
                args |= {"from": "2026-10-18T07:00:00Z", "to": "2026-10-18T09:00:00Z"}
            result = await client.call(session, name, args)
            assert not result.ok and result.error.code == "NOT_FOUND"
        for name, args in [
            ("find_customers", {"query": "Green", "limit": 11}),
            ("search_incidents", {"query": "401", "limit": 100}),
            ("get_service_status", SCOPE | {"scenario_id": "healthy"}),
        ]:
            assert (await session.call_tool(name, args)).isError
    await diagnose(integration_settings, "GreenShop", "ru")
    async with admin_engine.connect() as conn:
        after = (
            (
                await conn.execute(
                    text("SELECT row_to_json(t)::text FROM domain.tickets t ORDER BY id")
                )
            )
            .scalars()
            .all()
        )
    assert before == after


async def test_event_limit_and_half_open_range(integration_settings):
    async with MCPClient(integration_settings).session() as (session, _):
        result = await MCPClient.call(
            session,
            "get_integration_events",
            SCOPE | {"from": "2026-10-18T08:25:00Z", "to": "2026-10-18T08:55:00Z", "limit": 1},
        )
        assert result.ok and result.data["truncated"]
        assert len(result.data["events"]) == 1
        assert result.data["events"][0]["occurred_at"].startswith("2026-10-18T08:40")


@pytest.mark.parametrize(
    "scenario,expected",
    [("healthy", "valid"), ("unknown", "unknown"), ("contradictory", "valid"), ("timeout", None)],
)
async def test_overlay_through_real_transport(integration_settings, scenario, expected):
    import asyncio
    import socket

    import uvicorn

    from opspilot.mcp_server.main import create_app

    settings = integration_settings.model_copy(update={"scenario_id": scenario})
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        client = MCPClient(settings.model_copy(update={"mcp_url": f"http://127.0.0.1:{port}/mcp"}))
        async with client.session() as (session, _):
            result = await client.call(session, "get_credential_status", SCOPE)
            if expected is None:
                assert not result.ok and result.error.code == "MONITORING_TIMEOUT"
                from opspilot.contracts.evidence import normalize_evidence

                assert normalize_evidence("get_credential_status", result) == []
            else:
                assert result.ok and result.data["status"] == expected
            assert "Bearer" not in result.model_dump_json()
            if scenario == "contradictory":
                status = await client.call(session, "get_service_status", SCOPE)
                events = await client.call(
                    session,
                    "get_integration_events",
                    SCOPE | {"from": "2026-10-18T07:00:00Z", "to": "2026-10-18T09:00:00Z"},
                )
                assert status.data["status"] == "healthy"
                assert events.data["events"][0]["http_status"] == 401
        if scenario == "timeout":
            report = await diagnose(client.settings, "GreenShop", "ru")
            assert report["outcome"] == "partial"
            assert set(report["missing_checks"]) == {
                "get_service_status",
                "get_integration_events",
                "get_credential_status",
            }
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()
