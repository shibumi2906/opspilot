import asyncio
import json

from opspilot.config import Settings
from opspilot.contracts.tools import CustomerData
from opspilot.fixtures.loader import GREENSHOP_ID
from opspilot.logging import configure_logging
from opspilot.mcp_client.client import MCPClient


async def main() -> None:
    client = MCPClient(Settings())
    async with client.session() as (session, protocol):
        tools = await client.discover(session)
        result = await client.call(session, "get_customer", {"customer_id": GREENSHOP_ID})
        if not result.ok:
            raise RuntimeError("Smoke failed: customer unavailable")
        customer = CustomerData.model_validate(result.data)
        if customer.name != "GreenShop" or not customer.integrations:
            raise RuntimeError("Smoke failed: unexpected customer fixture")
        missing = await client.call(
            session,
            "get_customer",
            {
                "customer_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            },
        )
        if missing.ok or missing.error is None or missing.error.code != "NOT_FOUND":
            raise RuntimeError("Smoke failed: missing customer must return NOT_FOUND")
        print(
            json.dumps(
                {
                    "protocol": protocol,
                    "tools": [t.name for t in tools],
                    "customer": customer.model_dump(mode="json"),
                    "missing": "NOT_FOUND",
                }
            )
        )


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
