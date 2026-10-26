"""Separate short-lived service context. This never forwards a browser/IdP token."""

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import jwt

from opspilot.auth.context import AuthError, actor_id
from opspilot.config import Settings
from opspilot.tenancy.context import require_tenant

_run: ContextVar[str | None] = ContextVar("service_run", default=None)
_action: ContextVar[dict[str, str] | None] = ContextVar("service_action", default=None)
_verified: ContextVar[dict[str, Any] | None] = ContextVar("verified_service_context", default=None)


@contextmanager
def run_scope(run: str) -> Iterator[None]:
    token = _run.set(str(UUID(run)))
    try:
        yield
    finally:
        _run.reset(token)


@contextmanager
def action_scope(run: str, action: str, digest: str) -> Iterator[None]:
    token = _action.set(
        {
            "run": str(UUID(run)),
            "action": str(UUID(action)),
            "hash": digest,
            "tool": "create_ticket",
        }
    )
    try:
        yield
    finally:
        _action.reset(token)


@contextmanager
def verified_scope(value: dict[str, Any]) -> Iterator[None]:
    token = _verified.set(value)
    try:
        yield
    finally:
        _verified.reset(token)


def verified_context() -> dict[str, Any] | None:
    return _verified.get()


def mint(settings: Settings) -> str:
    now = int(time.time())
    operation = _action.get()
    claims: dict[str, Any] = {
        "ver": 1,
        "iss": "urn:opspilot:core:" + settings.app_env,
        "aud": "urn:opspilot:mcp:" + settings.app_env,
        "sub": str(actor_id()),
        "tenant": str(require_tenant()),
        "iat": now,
        "nbf": now,
        "exp": now + 60,
        "jti": str(uuid4()),
        "scope": "read",
        "run": _run.get(),
    }
    if operation:
        claims.update(operation, scope="action")
    key = Path(settings.service_private_dir, settings.service_active_kid + ".pem").read_text()
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"kid": settings.service_active_kid})


def verify(token: str, settings: Settings) -> dict[str, Any]:
    try:
        if len(token) > 4096:
            raise ValueError("oversized context")
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "EdDSA" or header.get("crit"):
            raise ValueError("unsupported algorithm")
        keys = json.loads(Path(settings.service_public_keys).read_text())
        key = keys.get(header.get("kid"))
        if not isinstance(key, str):
            raise ValueError("unknown key")
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["EdDSA"],
            issuer="urn:opspilot:core:" + settings.app_env,
            audience="urn:opspilot:mcp:" + settings.app_env,
            leeway=2,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "tenant",
                    "iat",
                    "nbf",
                    "exp",
                    "jti",
                    "ver",
                    "scope",
                ]
            },
        )
        if claims["ver"] != 1 or claims["scope"] not in {"read", "action"}:
            raise ValueError("unsupported context")
        if (
            type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
            or not 0 < claims["exp"] - claims["iat"] <= 60
        ):
            raise ValueError("invalid lifetime")
        for field in ("sub", "tenant", "jti"):
            UUID(claims[field])
        if claims.get("run"):
            UUID(claims["run"])
        if claims["scope"] == "action":
            UUID(claims["action"])
            if claims.get("tool") != "create_ticket" or len(claims.get("hash", "")) != 64:
                raise ValueError("invalid action binding")
        return claims
    except (jwt.PyJWTError, ValueError, KeyError, TypeError, OSError) as exc:
        raise AuthError("SERVICE_CONTEXT_INVALID", 401) from exc
