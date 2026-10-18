import os

import httpx
import pytest

from opspilot.config import Settings
from opspilot.contracts.tools import CustomerData
from opspilot.fixtures.loader import GREENSHOP_ID
from opspilot.mcp_client.client import MCPClient
from opspilot.mcp_client.registry import READ_TOOLS


async def test_real_sdk_discovery_and_read(integration_settings: Settings) -> None:
    client = MCPClient(integration_settings)
    async with client.session() as (session, protocol):
        assert protocol == "2025-11-25"
        tools = await client.discover(session)
        assert {t.name for t in tools} == set(READ_TOOLS)
        result = await client.call(session, "get_customer", {"customer_id": GREENSHOP_ID})
        assert result.ok
        customer = CustomerData.model_validate(result.data)
        assert customer.name == "GreenShop"
        assert customer.integrations[0].integration_type == "shopify"
        assert result.observed_at == integration_settings.scenario_clock
        missing = await client.call(
            session,
            "get_customer",
            {
                "customer_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            },
        )
        assert not missing.ok and missing.error.code == "NOT_FOUND"


@pytest.mark.parametrize("header", [None, "Bearer wrong-token"])
async def test_transport_requires_service_credential(
    integration_settings: Settings,
    header: str | None,
) -> None:
    async with httpx.AsyncClient() as http:
        response = await http.post(
            integration_settings.mcp_url,
            headers={} if header is None else {"Authorization": header},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
    assert response.status_code == 401
    assert integration_settings.mcp_service_token.get_secret_value() not in response.text


@pytest.mark.parametrize(
    "arguments",
    [
        {"customer_id": "invalid"},
        {"customer_id": GREENSHOP_ID, "extra": "not-allowed"},
    ],
)
async def test_server_validates_raw_tool_args(
    integration_settings: Settings,
    arguments: dict[str, str],
) -> None:
    async with MCPClient(integration_settings).session() as (session, _):
        result = await session.call_tool("get_customer", arguments)
        assert result.isError


async def test_health_and_mcp_network_boundary(integration_settings: Settings) -> None:
    async with httpx.AsyncClient() as http:
        response = await http.get(os.environ["TEST_API_URL"] + "/health")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ready", "migrations": "ready", "mcp": "ready"}
