from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.logging import configure_logging
from opspilot.mcp_server.auth import ServiceAuth
from opspilot.mcp_server.tools_read import register_read_tools
from opspilot.security.http import SecurityMiddleware
from opspilot.telemetry import TraceMiddleware, configure


class MCPTransport:
    def __init__(self, manager: StreamableHTTPSessionManager) -> None:
        self.manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.manager.handle_request(scope, receive, send)


def create_app(settings: Settings | None = None) -> ASGIApp:
    settings = settings or Settings()
    configure(settings, "opspilot-mcp")
    engine = create_engine(settings.database_url("domain"))
    server: Server[Any, Any] = Server("OpsPilot", version="0.1.0")
    register_read_tools(server, settings, engine)
    manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=(
                [urlsplit(settings.mcp_url).netloc]
                if settings.security_profile == "hardened"
                else ["mcp:8001", "localhost:*", "127.0.0.1:*"]
            ),
            allowed_origins=(
                [settings.app_origin]
                if settings.security_profile == "hardened"
                else ["http://localhost:*", "http://127.0.0.1:*"]
            ),
        ),
    )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        try:
            async with manager.run():
                yield
        finally:
            await engine.dispose()

    app = Starlette(
        routes=[Route("/mcp", MCPTransport(manager), methods=["GET", "POST", "DELETE"])],
        lifespan=lifespan,
    )
    return SecurityMiddleware(
        ServiceAuth(TraceMiddleware(app, "http.mcp.server"), settings), settings
    )


if __name__ == "__main__":
    configure_logging()
    settings = Settings()
    if settings.security_profile == "hardened" and not (
        settings.tls_cert_file and settings.tls_key_file
    ):
        raise ValueError("Hardened server requires native TLS certificate and key")
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",
        port=8001,
        access_log=False,
        log_level="warning",
        ssl_certfile=settings.tls_cert_file,
        ssl_keyfile=settings.tls_key_file,
        proxy_headers=False,
    )
