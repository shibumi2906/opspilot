import hashlib
import hmac
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request as StarletteRequest
from starlette.types import ASGIApp, Receive, Scope, Send

from opspilot.auth.context import AuthError, auth_scope, principal
from opspilot.auth.oidc import OIDC
from opspilot.auth.store import IdentityStore
from opspilot.config import Settings

COOKIE = "opspilot_session"
BINDING = "opspilot_login"


def csrf(settings: Settings, raw: str) -> str:
    key = settings.session_signing_key.get_secret_value()
    if len(key) < 64:
        raise RuntimeError("Independent session signing key required")
    return hmac.new(key.encode(), raw.encode(), hashlib.sha256).hexdigest()


def denial(exc: AuthError) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "schema_version": 1,
                "request_id": str(uuid4()),
                "code": exc.code,
                "message": "Access denied",
                "retryable": False,
            }
        },
        status_code=exc.status,
    )


class SessionMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app, self.settings = app, settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        protected = path.startswith("/api/") or path in {"/auth/me", "/auth/logout", "/auth/tenant"}
        if scope["type"] != "http" or not protected:
            await self.app(scope, receive, send)
            return
        request = StarletteRequest(scope)
        try:
            store = cast(IdentityStore, scope["app"].state.identity)
            raw = request.cookies.get(COOKIE, "")
            user = await store.authenticate(raw)
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                if request.headers.get(
                    "origin"
                ) != self.settings.app_origin or not hmac.compare_digest(
                    request.headers.get("x-csrf-token", ""), csrf(self.settings, raw)
                ):
                    raise AuthError("CSRF_INVALID")

            async def private_send(message: Any) -> None:
                if message["type"] == "http.response.start":
                    message.setdefault("headers", []).append((b"cache-control", b"no-store"))
                await send(message)

            with auth_scope(user):
                await self.app(scope, receive, private_send)
        except AuthError as exc:
            await denial(exc)(scope, receive, send)


router = APIRouter()


def cookie(response: Any, settings: Settings, name: str, value: str, age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=age,
        httponly=True,
        secure=settings.app_origin.startswith("https://"),
        samesite="lax",
        path="/",
    )


@router.get("/auth/login")
async def login(request: Request) -> RedirectResponse:
    store = request.app.state.identity
    state, binding, nonce, verifier = await store.new_login()
    response = RedirectResponse(
        OIDC(store.settings).authorization(state, nonce, verifier), status_code=302
    )
    cookie(response, store.settings, BINDING, binding, 300)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/auth/callback")
async def callback(request: Request, state: str = "", code: str = "") -> Any:
    store = request.app.state.identity
    try:
        if not code or len(code) > 4096 or len(state) > 256:
            raise AuthError("OIDC_INVALID", 400)
        attempt = await store.consume_login(state, request.cookies.get(BINDING, ""))
        claims = await OIDC(store.settings).exchange(
            code, attempt["verifier"], attempt["nonce_hash"]
        )
        raw = await store.new_session(claims["sub"], request.cookies.get(COOKIE, ""))
        response = RedirectResponse(store.settings.app_origin + "/", status_code=303)
        cookie(response, store.settings, COOKIE, raw, store.settings.session_ttl_seconds)
        response.delete_cookie(BINDING, path="/")
        response.headers["Cache-Control"] = "no-store"
        return response
    except (AuthError, httpx.HTTPError, KeyError, ValueError):
        await store.audit("login_denied")
        return denial(AuthError("OIDC_INVALID", 400))


@router.get("/api/v2/me")
@router.get("/auth/me")
async def me(request: Request) -> dict[str, Any]:
    user = principal()
    store = request.app.state.identity
    return {
        "user_id": str(user.user_id),
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "roles": sorted(user.roles),
        "memberships": await store.memberships(user.user_id),
        "csrf_token": csrf(store.settings, request.cookies.get(COOKIE, "")),
        "demo_self_approval": store.settings.allow_demo_self_approval,
    }


class TenantSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID


@router.post("/auth/tenant")
async def select_tenant(body: TenantSelection, request: Request) -> dict[str, bool]:
    await request.app.state.identity.select_tenant(principal(), body.tenant_id)
    return {"ok": True}


@router.post("/auth/logout")
async def logout(request: Request) -> JSONResponse:
    await request.app.state.identity.logout(principal())
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return response
