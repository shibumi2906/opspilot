"""Bounded HTTP admission and response policy, independent of authentication success."""

import asyncio
import json
from typing import Any
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from opspilot.config import Settings
from opspilot.security.audit import record

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)


def response_headers(settings: Settings) -> dict[str, str]:
    result = {
        "Content-Security-Policy": CSP,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cache-Control": "no-store",
    }
    if settings.app_origin.startswith("https://"):
        result["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return result


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app, self.settings = app, settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["security_request_id"] = request_id

        started = False
        completed = False

        async def protected_send(message: Any) -> None:
            nonlocal started, completed
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True
            if message["type"] == "http.response.start":
                started = True
                policy = response_headers(self.settings)
                policy["X-Request-ID"] = request_id
                names = {k.lower().encode() for k in policy}
                message["headers"] = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() not in names
                ]
                message["headers"].extend(
                    (k.lower().encode(), v.encode()) for k, v in policy.items()
                )
            await send(message)

        async def reject(status: int, code: str) -> None:
            await record(scope, "http_admission_denied", code)
            await JSONResponse(
                {
                    "error": {
                        "schema_version": 1,
                        "request_id": request_id,
                        "code": code,
                        "message": "Request rejected",
                        "retryable": False,
                    }
                },
                status_code=status,
            )(scope, receive, protected_send)

        headers = scope.get("headers", [])
        if scope.get("method") == "TRACE":
            await reject(405, "METHOD_NOT_ALLOWED")
            return
        if (
            len(headers) > 100
            or sum(len(k) + len(v) for k, v in headers) > 16384
            or len(scope.get("query_string", b"")) > 8192
        ):
            await reject(431, "HEADERS_TOO_LARGE")
            return
        single = {
            b"origin",
            b"content-type",
            b"authorization",
            b"x-csrf-token",
            b"cookie",
            b"x-opspilot-context",
            b"x-opspilot-grant",
        }
        if any(sum(k.lower() == name for k, _ in headers) > 1 for name in single):
            await reject(400, "AMBIGUOUS_HEADERS")
            return
        lengths = [v for k, v in headers if k.lower() == b"content-length"]
        try:
            if (
                len(lengths) > 1
                or lengths
                and not lengths[0].isdigit()
                or lengths
                and (int(lengths[0]) < 0 or int(lengths[0]) > self.settings.max_request_bytes)
            ):
                raise ValueError()
        except ValueError:
            await reject(413, "REQUEST_TOO_LARGE")
            return
        chunks = []
        size = 0
        deadline = asyncio.get_running_loop().time() + 10
        while True:
            try:
                async with asyncio.timeout_at(deadline):
                    msg = await receive()
            except TimeoutError:
                await reject(408, "BODY_TIMEOUT")
                return
            if msg["type"] == "http.disconnect":
                return
            data = msg.get("body", b"")
            size += len(data)
            if size > self.settings.max_request_bytes:
                await reject(413, "REQUEST_TOO_LARGE")
                return
            chunks.append(data)
            if not msg.get("more_body", False):
                break
        content_types = [v.lower() for k, v in headers if k.lower() == b"content-type"]
        if (
            size
            and content_types
            and content_types[0].split(b";")[0].strip() == b"application/json"
        ):

            def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for k, v in pairs:
                    if k in result:
                        raise ValueError("duplicate field")
                    result[k] = v
                return result

            def invalid_number(value: str) -> None:
                raise ValueError("non-finite JSON number")

            try:
                json.loads(
                    b"".join(chunks), object_pairs_hook=unique, parse_constant=invalid_number
                )
            except (ValueError, UnicodeError, RecursionError):
                await reject(400, "INVALID_JSON")
                return
        delivered = False

        async def bounded_receive() -> Any:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        try:
            await self.app(scope, bounded_receive, protected_send)
        except Exception:
            # Do not propagate provider/SQL/payload exception strings into Uvicorn logs.
            await record(scope, "unexpected_error", "INTERNAL_ERROR")
            if not started:
                await JSONResponse(
                    {
                        "error": {
                            "schema_version": 1,
                            "request_id": request_id,
                            "code": "INTERNAL_ERROR",
                            "message": "Request could not be completed",
                            "retryable": False,
                        }
                    },
                    status_code=500,
                )(scope, bounded_receive, protected_send)
            elif not completed:
                await protected_send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )
