"""Temporary local synthetic scope, replaced by verified memberships in F03/F04."""

from uuid import UUID

from starlette.types import ASGIApp, Receive, Scope, Send

from opspilot.tenancy.context import tenant_scope


class LocalTenantScope:
    def __init__(self, app: ASGIApp, tenant: UUID) -> None:
        self.app = app
        self.tenant = tenant

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Configured on the server, never read from browser/model-supplied data.
        with tenant_scope(self.tenant):
            await self.app(scope, receive, send)
