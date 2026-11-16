from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool
from opentelemetry.trace import Status, StatusCode
from sqlalchemy.exc import SQLAlchemyError

from opspilot.auth.context import AuthError
from opspilot.auth.service_context import action_context, mint
from opspilot.config import Settings
from opspilot.contracts.common import ToolResult
from opspilot.mcp_client.registry import ALL_TOOLS
from opspilot.security.grants import issue
from opspilot.security.tls import client_context
from opspilot.telemetry import carrier, span
from opspilot.tenancy.context import require_tenant


class MCPClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @asynccontextmanager
    async def session(self) -> AsyncIterator[tuple[ClientSession, str]]:
        require_tenant()
        token = mint(self.settings)
        grant_headers = {}
        operation = action_context()
        if operation:
            try:
                grant_headers["X-OpsPilot-Grant"] = await issue(self.settings, operation)
            except (AuthError, SQLAlchemyError):
                # Missing/stale authorization never grants a write; MCP returns the precise denial.
                pass
        bearer = (
            token
            if self.settings.security_profile == "hardened"
            else self.settings.mcp_service_token.get_secret_value()
        )
        async with httpx.AsyncClient(
            headers={
                **carrier(),
                **grant_headers,
                "X-OpsPilot-Context": token,
                "Authorization": f"Bearer {bearer}",
            },
            verify=client_context(self.settings),
            timeout=httpx.Timeout(5, read=45),
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
        with span("mcp.client.tool", tool_name=name) as current:
            # Jira effects include independent GET verification after the single POST.
            # Ordinary tools retain their existing SDK deadline.
            deadline = (
                45
                if name in {"create_jira_issue", "create_jira_comment", "get_jira_operation"}
                else 5
            )
            response = await session.call_tool(
                name, arguments, read_timeout_seconds=timedelta(seconds=deadline)
            )
            result = ToolResult.model_validate(response.structuredContent)
            current.set_attribute("status", "ok" if result.ok else "error")
            if not result.ok:
                current.set_status(Status(StatusCode.ERROR))
                if result.error:
                    current.set_attribute("error_code", result.error.code)
        if bool(response.isError) == result.ok:
            raise ValueError("Inconsistent MCP error status")
        if result.ok:
            ALL_TOOLS[name].data.model_validate(result.data)
        return result
