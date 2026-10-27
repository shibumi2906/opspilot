import time

import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from opspilot.auth.context import AuthError
from opspilot.auth.http import COOKIE, cookie, cookie_name
from opspilot.auth.oidc import digest, verify_id_token
from opspilot.config import Settings
from opspilot.security.http import SecurityMiddleware


def hardened(**extra):
    values = dict(
        security_profile="hardened",
        app_origin="https://app.localhost:8443",
        oidc_issuer="https://idp.localhost:8543/realms/opspilot",
        oidc_internal_issuer="https://idp.localhost:8543/realms/opspilot",
        mcp_url="https://mcp:8001/mcp",
        session_signing_key="a" * 96,
        idp_token_key=Fernet.generate_key().decode(),
        max_actor_active_runs=8,
        max_tenant_active_runs=64,
        max_global_active_runs=128,
        allow_demo_self_approval=False,
        otel_endpoint=None,
        jaeger_url=None,
        identity_database_url=None,
        workflow_database_url=None,
        checkpoint_database_url=None,
        domain_database_url=None,
        migration_database_url=None,
    )
    return Settings(_env_file=None, **(values | extra))


@pytest.mark.parametrize(
    "change",
    [
        dict(app_origin="http://app.localhost"),
        dict(allow_demo_self_approval=True),
        dict(max_actor_active_runs=9),
        dict(identity_database_url="postgresql+psycopg://x:y@postgres/opspilot_full_test"),
        dict(oidc_issuer="https://app.localhost/realm"),
        dict(idp_token_key=None),
    ],
)
def test_hardened_startup_fails_closed(change):
    with pytest.raises(ValidationError):
        hardened(**change)


def test_production_cannot_silently_use_development():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", mcp_service_token="a" * 64)


def test_host_cookie_has_required_attributes():
    settings = hardened()
    response = JSONResponse({})
    cookie(response, settings, COOKIE, "opaque", 900)
    value = response.headers["set-cookie"]
    assert cookie_name(settings, COOKIE) == "__Host-opspilot_session"
    assert "Secure" in value and "HttpOnly" in value and "Path=/" in value
    assert "SameSite=lax" in value and "Domain" not in value


@pytest.mark.parametrize("change", ["valid", "password_only", "missing_time", "stale", "small_key"])
def test_oidc_requires_recent_mfa_and_strong_rsa(change):
    settings = hardened()
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048 if change == "small_key" else 3072
    )
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk["kid"] = "test"
    now = int(time.time())
    claims = dict(
        iss=settings.oidc_issuer,
        aud=settings.oidc_client_id,
        sub="subject",
        iat=now,
        exp=now + 60,
        nonce="nonce",
        acr="2",
        auth_time=now,
    )
    if change == "password_only":
        claims["acr"] = "1"
    if change == "missing_time":
        claims.pop("auth_time")
    if change == "stale":
        claims["auth_time"] = now - 4000
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
    if change == "valid":
        assert verify_id_token(token, {"keys": [jwk]}, settings, digest("nonce"))["acr"] == "2"
    else:
        with pytest.raises(AuthError):
            verify_id_token(token, {"keys": [jwk]}, settings, digest("nonce"))


async def test_http_admission_policies_on_success_and_denial():
    async def endpoint(request):
        return JSONResponse({"ok": True})

    settings = hardened(max_request_bytes=4096)
    app = SecurityMiddleware(
        Starlette(routes=[Route("/", endpoint, methods=["GET", "POST"])]), settings
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://app"
    ) as c:
        for response in [
            await c.get("/"),
            await c.request("TRACE", "/"),
            await c.post("/", content=b"x" * 4097),
        ]:
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            assert response.headers["strict-transport-security"].startswith("max-age=")
        assert (await c.request("TRACE", "/")).status_code == 405
        assert (await c.post("/", content=b"x" * 4097)).status_code == 413
        for value in [b'{"x":1,"x":2}', b'{"x":NaN}', b"{invalid"]:
            assert (
                await c.post("/", content=value, headers={"Content-Type": "application/json"})
            ).status_code == 400
        assert (await c.post("/", headers=[("Origin", "a"), ("Origin", "b")])).status_code == 400

        async def chunks():
            yield b"x" * 3000
            yield b"x" * 3000

        assert (await c.post("/", content=chunks())).status_code == 413


def test_secret_file_source_is_explicit_and_rejects_ambiguity(tmp_path, monkeypatch):
    monkeypatch.delenv("SESSION_SIGNING_KEY", raising=False)
    secret = tmp_path / "session.key"
    secret.write_text("b" * 96)
    settings = Settings(
        _env_file=None,
        mcp_service_token="a" * 64,
        secret_files={"session_signing_key": str(secret)},
    )
    assert settings.session_signing_key.get_secret_value() == "b" * 96
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            mcp_service_token="a" * 64,
            session_signing_key="c" * 96,
            secret_files={"session_signing_key": str(secret)},
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, mcp_service_token="a" * 64, secret_files={"app_origin": str(secret)}
        )


async def test_unexpected_failure_is_sanitized_with_response_policy():
    async def failed(scope, receive, send):
        raise RuntimeError("secret-provider-payload")

    app = SecurityMiddleware(failed, hardened())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://app"
    ) as c:
        response = await c.get("/")
        assert response.status_code == 500
        assert "secret-provider-payload" not in response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["content-security-policy"]


async def test_database_run_admission_maps_to_429_without_sql_details():
    from fastapi import FastAPI
    from sqlalchemy.exc import DBAPIError

    from opspilot.api.errors import install_errors

    class DriverError(Exception):
        sqlstate = "P0001"

    app = FastAPI()
    settings = hardened()
    install_errors(app, settings)
    app.add_middleware(SecurityMiddleware, settings=settings)

    @app.get("/quota")
    async def quota():
        raise DBAPIError("secret SQL", {"password": "secret"}, DriverError("RUN_ADMISSION_LIMIT"))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://app"
    ) as c:
        response = await c.get("/quota")
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "RUN_ADMISSION_LIMIT"
        assert "secret" not in response.text


def test_clarification_version_rejects_boolean_coercion():
    from uuid import uuid4

    from opspilot.contracts.api import ClarificationAnswer

    with pytest.raises(ValidationError):
        ClarificationAnswer(
            clarification_id=uuid4(),
            expected_version=True,
            kind="customer",
            choice="GreenShop",
            command_id=uuid4(),
        )


def test_sensitive_operations_require_recent_mfa():
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from opspilot.auth.context import Principal, auth_scope
    from opspilot.auth.session_routes import require_recent

    settings = hardened()
    with auth_scope(
        Principal(
            uuid4(),
            uuid4(),
            frozenset({"admin"}),
            uuid4(),
            auth_time=datetime.now(UTC) - timedelta(minutes=10),
        )
    ):
        with pytest.raises(AuthError) as error:
            require_recent(settings)
        assert error.value.code == "REAUTHENTICATION_REQUIRED"
    with auth_scope(
        Principal(uuid4(), uuid4(), frozenset({"admin"}), uuid4(), auth_time=datetime.now(UTC))
    ):
        require_recent(settings)
