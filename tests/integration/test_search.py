import pytest

from opspilot.mcp_client.client import MCPClient


@pytest.mark.parametrize(
    "name,query,language",
    [
        ("search_incidents", "заказы", "ru"),
        ("search_incidents", "expired", "en"),
        ("search_documentation", "истёкший", "ru"),
        ("search_documentation", "credential", "en"),
    ],
)
async def test_search_language_and_stable_order(integration_settings, name, query, language):
    args = {"query": query, "language": language, "integration_type": "shopify"}
    async with MCPClient(integration_settings).session() as (session, _):
        first = await MCPClient.call(session, name, args)
        second = await MCPClient.call(session, name, args)
        assert first.ok and first.data["hits"]
        assert first.data == second.data
        empty = await MCPClient.call(session, name, args | {"integration_type": "missing"})
        assert empty.ok and empty.data["hits"] == []
        empty = await MCPClient.call(session, name, args | {"query": "zzzznomatch"})
        assert empty.ok and empty.data["hits"] == []
        if name == "search_incidents":
            filtered = await MCPClient.call(
                session, name, args | {"customer_id": "ffffffff-ffff-ffff-ffff-ffffffffffff"}
            )
            assert filtered.data["hits"] == []
        else:
            assert all(h["language"] == language for h in first.data["hits"])
