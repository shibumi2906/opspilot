import asyncio
import socket
from uuid import UUID, uuid5

import pytest
import uvicorn

from opspilot.auth.service_context import mint
from opspilot.fixtures.loader import GREENSHOP_ID, GREENSHOP_INTEGRATION_ID
from opspilot.mcp_client.client import MCPClient
from opspilot.mcp_server.main import create_app
from opspilot.tenancy.context import SECOND_TENANT, TenantContextError, tenant_scope


async def test_actual_mcp_uses_configured_scope_not_tool_arguments(integration_settings):
    settings = integration_settings.model_copy(update={"local_demo_tenant": SECOND_TENANT})
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    settings = settings.model_copy(
        update={"mcp_url": f"http://127.0.0.1:{sock.getsockname()[1]}/mcp"}
    )
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        for config, own, foreign, own_integration in [
            (
                integration_settings,
                GREENSHOP_ID,
                str(uuid5(SECOND_TENANT, GREENSHOP_ID)),
                GREENSHOP_INTEGRATION_ID,
            ),
            (
                settings,
                str(uuid5(SECOND_TENANT, GREENSHOP_ID)),
                GREENSHOP_ID,
                str(uuid5(SECOND_TENANT, GREENSHOP_INTEGRATION_ID)),
            ),
        ]:
            with tenant_scope(config.local_demo_tenant):
                await check_instance(config, own, foreign, own_integration)
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()


async def check_instance(config, own, foreign, own_integration):
    async with MCPClient(config).session() as (session, _):
        result = await MCPClient.call(session, "find_customers", {"query": "GreenShop"})
        assert result.ok
        ids = [str(c["customer_id"]) for c in result.data["candidates"]]
        assert own in ids and foreign not in ids
        result = await MCPClient.call(session, "get_customer", {"customer_id": own})
        assert (
            result.ok and str(result.data["integrations"][0]["integration_id"]) == own_integration
        )
        result = await MCPClient.call(session, "get_customer", {"customer_id": foreign})
        assert not result.ok and result.error.code == "NOT_FOUND"
        result = await MCPClient.call(
            session,
            "get_ticket",
            {
                "ticket_id": str(
                    uuid5(
                        SECOND_TENANT
                        if config.local_demo_tenant != SECOND_TENANT
                        else UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                        "seed-ticket",
                    )
                )
            },
        )
        assert not result.ok and result.error.code == "NOT_FOUND"
        raw = await session.call_tool(
            "get_customer", {"customer_id": foreign, "tenant_id": str(SECOND_TENANT)}
        )
        assert raw.isError


async def test_mcp_header_cannot_select_tenant_or_authorize_foreign_action(integration_settings):
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {
        "Authorization": f"Bearer {integration_settings.mcp_service_token.get_secret_value()}",
        "X-Tenant-ID": str(SECOND_TENANT),
        "X-OpsPilot-Context": mint(integration_settings),
    }
    async with httpx.AsyncClient(headers=headers, timeout=5, trust_env=False) as http:
        async with streamable_http_client(
            integration_settings.mcp_url, http_client=http
        ) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                result = await MCPClient.call(
                    session,
                    "get_customer",
                    {"customer_id": str(uuid5(SECOND_TENANT, GREENSHOP_ID))},
                )
                assert not result.ok and result.error.code == "NOT_FOUND"
                result = await MCPClient.call(
                    session,
                    "create_ticket",
                    {
                        "run_id": str(uuid5(SECOND_TENANT, "seed-run")),
                        "action_id": str(uuid5(SECOND_TENANT, "seed-action")),
                        "arguments": {
                            "customer_id": str(uuid5(SECOND_TENANT, GREENSHOP_ID)),
                            "title": "Synthetic baseline ticket",
                            "description": "F02 fixture, no upstream write",
                            "priority": "low",
                            "evidence_ids": ["synthetic:f02"],
                        },
                    },
                )
                assert not result.ok and result.error.code == "APPROVAL_REQUIRED"


async def test_mcp_client_rejects_absent_trusted_context(integration_settings):
    for tenant in (None,):
        with tenant_scope(tenant), pytest.raises(TenantContextError):
            async with MCPClient(integration_settings).session():
                raise AssertionError("Mismatched context must fail before network dispatch")
