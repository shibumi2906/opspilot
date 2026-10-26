from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.config import Settings
from opspilot.contracts.common import Source
from opspilot.contracts.tools import CreateTicketArgs
from opspilot.mcp_server.services.tickets import create_ticket


async def write_tool(
    args: CreateTicketArgs, engine: AsyncEngine, settings: Settings
) -> tuple[dict[str, Any], list[Source]]:
    data = await create_ticket(engine, args, settings=settings)
    return data, [Source(source_type="ticket", source_id=data["ticket_id"])]
