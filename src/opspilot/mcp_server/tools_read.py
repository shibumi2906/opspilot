from typing import Any

from loguru import logger
from mcp.server.lowlevel import Server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from opspilot.config import Settings
from opspilot.contracts.common import Source, ToolError, ToolResult
from opspilot.contracts.tools import (
    CreateTicketArgs,
    EventsArgs,
    FindCustomersArgs,
    GetCustomerArgs,
    GetTicketArgs,
    IntegrationArgs,
    SearchDocumentationArgs,
)
from opspilot.db.models_domain import Customer, CustomerIntegration, Ticket
from opspilot.mcp_client.registry import ALL_TOOLS, READ_TOOLS
from opspilot.mcp_server.adapters.monitoring import observe
from opspilot.mcp_server.services.customers import get_customer
from opspilot.mcp_server.services.retrieval import search
from opspilot.mcp_server.services.tickets import WriteDenied
from opspilot.mcp_server.tools_write import write_tool
from opspilot.telemetry import traced


async def read_tool(
    name: str, args: Any, engine: AsyncEngine, settings: Settings
) -> tuple[dict[str, Any], list[Source]] | None:
    if name == "get_customer":
        assert isinstance(args, GetCustomerArgs)
        customer = await get_customer(engine, args.customer_id)
        return (
            None
            if customer is None
            else (
                customer.model_dump(mode="json"),
                [Source(source_type="customer", source_id=str(args.customer_id))],
            )
        )
    if name == "find_customers":
        assert isinstance(args, FindCustomersArgs)
        async with AsyncSession(engine) as session:
            rows = list(
                await session.scalars(
                    select(Customer)
                    .where(
                        Customer.normalized_name.contains(args.query.casefold(), autoescape=True)
                    )
                    .order_by(Customer.normalized_name, Customer.id)
                    .limit(args.limit + 1)
                )
            )
        return (
            {
                "candidates": [{"customer_id": c.id, "name": c.name} for c in rows[: args.limit]],
                "truncated": len(rows) > args.limit,
            },
            [Source(source_type="customer", source_id=str(c.id)) for c in rows[: args.limit]],
        )
    if name.startswith("search_"):
        assert isinstance(args, SearchDocumentationArgs)
        incidents = name == "search_incidents"
        hits = await search(engine, args, incidents=incidents)
        return {"hits": hits}, [
            Source(
                source_type="incident" if incidents else "knowledge_article",
                source_id=str(h["incident_id" if incidents else "article_id"]),
                version=None if incidents else h["version"],
            )
            for h in hits
        ]
    if name == "get_ticket":
        assert isinstance(args, GetTicketArgs)
        async with AsyncSession(engine) as session:
            ticket = await session.get(Ticket, args.ticket_id)
            if ticket is None:
                return None
            data = {
                key: getattr(ticket, key)
                for key in (
                    "customer_id",
                    "title",
                    "description",
                    "priority",
                    "status",
                    "evidence_ids",
                    "originating_action_id",
                    "created_at",
                )
            }
            data["ticket_id"] = ticket.id
        return data, [Source(source_type="ticket", source_id=str(args.ticket_id))]
    assert isinstance(args, IntegrationArgs)
    async with AsyncSession(engine) as session:
        integration = await session.scalar(
            select(CustomerIntegration).where(
                CustomerIntegration.id == args.integration_id,
                CustomerIntegration.customer_id == args.customer_id,
            )
        )
        if integration is None:
            return None
    snapshot = observe(settings, args.customer_id, args.integration_id)
    if name == "get_service_status":
        return {k: snapshot[k] for k in ("status", "latest_success_at", "checked_at")}, [
            Source(source_type="integration_status", source_id=str(args.integration_id))
        ]
    if name == "get_credential_status":
        return {"status": snapshot["credential_status"], "checked_at": snapshot["checked_at"]}, [
            Source(source_type="credential_status", source_id=str(args.integration_id))
        ]
    assert name == "get_integration_events" and isinstance(args, EventsArgs)
    events = sorted(
        (e for e in snapshot["events"] if args.from_ <= e["occurred_at"] < args.to),
        key=lambda e: (e["occurred_at"], e["event_id"]),
        reverse=True,
    )
    selected = events[: args.limit]
    return {"events": selected, "truncated": len(events) > args.limit}, [
        Source(source_type="integration_event", source_id=str(e["event_id"])) for e in selected
    ]


def register_read_tools(server: Server[Any, Any], settings: Settings, engine: AsyncEngine) -> None:
    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=name,
                description=f"Synthetic operational data: {name}",
                inputSchema=contract.arguments.model_json_schema(),
                outputSchema=ToolResult.model_json_schema(),
                annotations=ToolAnnotations(readOnlyHint=name in READ_TOOLS, destructiveHint=False),
            )
            for name, contract in ALL_TOOLS.items()
        ]

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    @traced("mcp.server.tool")
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        if name not in ALL_TOOLS:
            raise ValueError("Unknown read tool")
        contract = ALL_TOOLS[name]
        try:
            args = contract.arguments.model_validate(arguments)
            response = (
                await write_tool(CreateTicketArgs.model_validate(arguments), engine)
                if name == "create_ticket"
                else await read_tool(name, args, engine, settings)
            )
            if response is None:
                result = ToolResult(
                    ok=False,
                    observed_at=settings.scenario_clock,
                    error=ToolError(code="NOT_FOUND", message="Resource not found"),
                )
            else:
                data, sources = response
                result = ToolResult(
                    ok=True,
                    observed_at=settings.scenario_clock,
                    data=contract.data.model_validate(data).model_dump(mode="json"),
                    sources=sources,
                )
        except WriteDenied as exc:
            result = ToolResult(
                ok=False,
                observed_at=settings.scenario_clock,
                error=ToolError(code=exc.code, message="Write authorization or payload rejected"),
            )
        except ValidationError:
            result = ToolResult(
                ok=False,
                observed_at=settings.scenario_clock,
                error=ToolError(code="INVALID_ARGUMENTS", message="Invalid tool arguments"),
            )
        except (SQLAlchemyError, TimeoutError) as exc:
            code = (
                "MONITORING_TIMEOUT" if isinstance(exc, TimeoutError) else "DEPENDENCY_UNAVAILABLE"
            )
            logger.warning("tool_failed tool={} code={}", name, code)
            result = ToolResult(
                ok=False,
                observed_at=settings.scenario_clock,
                error=ToolError(code=code, message="Source unavailable", retryable=True),
            )
        return CallToolResult(
            content=[TextContent(type="text", text=result.model_dump_json())],
            structuredContent=result.model_dump(mode="json"),
            isError=not result.ok,
        )
