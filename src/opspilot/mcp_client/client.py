from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool

from opspilot.config import Settings
from opspilot.contracts.common import ToolResult
from opspilot.mcp_client.registry import ALL_TOOLS
from opspilot.telemetry import carrier, span


class MCPClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @asynccontextmanager
    async def session(self) -> AsyncIterator[tuple[ClientSession, str]]:
        async with httpx.AsyncClient(
            headers={
                **carrier(),
                "Authorization": f"Bearer {self.settings.mcp_service_token.get_secret_value()}",
            },
            timeout=5,
            trust_env=False,
        ) as http:
            async with streamable_http_client(self.settings.mcp_url, http_client=http) as streams:
                read, write, _ = streams
                async with ClientSession(
                    read,
                    write,
                    read_timeout_seconds=timedelta(seconds=5),
                ) as session:
                    initialized = await session.initialize()
                    yield session, str(initialized.protocolVersion)

    @staticmethod
    async def discover(session: ClientSession) -> list[Tool]:
        tools = (await session.list_tools()).tools
        if len(tools) != len(ALL_TOOLS) or {t.name for t in tools} != set(ALL_TOOLS):
            raise ValueError("MCP discovery does not match tool allowlist")
        for tool in tools:
            if tool.inputSchema != ALL_TOOLS[tool.name].arguments.model_json_schema():
                raise ValueError("Incompatible tool input schema")
            if tool.outputSchema != ToolResult.model_json_schema():
                raise ValueError("Incompatible tool result schema")
        return tools

    @staticmethod
    async def call(session: ClientSession, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in ALL_TOOLS:
            raise ValueError("Tool outside tool allowlist")
        arguments = (
            ALL_TOOLS[name]
            .arguments.model_validate(arguments)
            .model_dump(mode="json", by_alias=True)
        )
        with span("mcp.client.tool", tool_name=name):
            response = await session.call_tool(name, arguments)
        result = ToolResult.model_validate(response.structuredContent)
        if bool(response.isError) == result.ok:
            raise ValueError("Inconsistent MCP error status")
        if result.ok:
            ALL_TOOLS[name].data.model_validate(result.data)
        return result
