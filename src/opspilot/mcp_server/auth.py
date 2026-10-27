import secrets
from uuid import UUID

from loguru import logger
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from opspilot.auth.context import AuthError, Principal, auth_scope
from opspilot.auth.service_context import verified_scope, verify
from opspilot.config import Settings
from opspilot.security.grants import grant_scope


class ServiceAuth:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app, self.settings = app, settings
        self.expected = f"Bearer {settings.mcp_service_token.get_secret_value()}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            auth = [v for k, v in scope["headers"] if k.lower() == b"authorization"]
            contexts = [v for k, v in scope["headers"] if k.lower() == b"x-opspilot-context"]
            if (
                len(auth) != 1
                or not secrets.compare_digest(
                    auth[0],
                    b"Bearer " + contexts[0]
                    if self.settings.security_profile == "hardened" and len(contexts) == 1
                    else self.expected,
                )
                or len(contexts) != 1
            ):
                raise AuthError("SERVICE_CONTEXT_REQUIRED", 401)
            claims = verify(contexts[0].decode(), self.settings)
            user = Principal(UUID(claims["sub"]), UUID(claims["tenant"]), frozenset(), UUID(int=0))
            grants = [v for k, v in scope["headers"] if k.lower() == b"x-opspilot-grant"]
            if len(grants) > 1 or grants and len(grants[0]) > 8192:
                raise AuthError("GRANT_INVALID")
            with (
                auth_scope(user),
                verified_scope(claims),
                grant_scope(grants[0].decode() if grants else None),
            ):
                await self.app(scope, receive, send)
        except (AuthError, UnicodeError):
            logger.bind(
                security_event="service_authentication_denied", reason="INVALID_SERVICE_CONTEXT"
            ).warning("security_event")
            response = JSONResponse(
                {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Scoped service authentication required",
                    }
                },
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
