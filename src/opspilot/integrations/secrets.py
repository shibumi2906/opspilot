"""Separate service ACLs for connector credentials versus webhook verification keys."""

import base64
import json
import re
import ssl
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import httpx

from opspilot.auth.context import AuthError
from opspilot.config import Settings
from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.executor import bounded
from opspilot.security.manager import BaoGrantKeys


def _read(
    settings: Settings, tenant: UUID, connector: UUID, purpose: Literal["credential", "webhook"]
) -> dict[str, Any]:
    try:
        if not (
            settings.connector_manager_url
            and settings.connector_manager_ca_file
            and settings.connector_manager_token_file
        ):
            raise ValueError()
        BaoGrantKeys(
            settings.connector_manager_url,
            settings.connector_manager_ca_file,
            settings.connector_manager_token_file,
        )
        token = Path(settings.connector_manager_token_file).read_text().strip()
        if not 20 <= len(token) <= 512 or any(c.isspace() for c in token):
            raise ValueError()
        path = f"connectors/{tenant}/{connector}/{purpose}"
        context = ssl.create_default_context(cafile=settings.connector_manager_ca_file)
        with httpx.Client(verify=context, trust_env=False, timeout=1, follow_redirects=False) as c:
            with c.stream(
                "GET",
                settings.connector_manager_url + "/v1/core/data/" + path,
                headers={"X-Vault-Token": token},
            ) as response:
                if response.status_code != 200:
                    raise ValueError()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 16384:
                        raise ValueError()
        result = json.loads(raw)["data"]["data"]
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (OSError, ValueError, KeyError, TypeError, httpx.HTTPError):
        raise ConnectorUnavailable() from None


async def read(
    settings: Settings, tenant: UUID, connector: UUID, purpose: Literal["credential", "webhook"]
) -> dict[str, Any]:
    try:
        return await bounded(_read, settings, tenant, connector, purpose, budget=1.5)
    except TimeoutError:
        raise ConnectorUnavailable() from None


async def credential(settings: Settings, tenant: UUID, connector: UUID) -> str:
    record = await read(settings, tenant, connector, "credential")
    if record.get("tenant_id") != str(tenant) or record.get("connector_id") != str(connector):
        raise ConnectorUnavailable()
    value = record.get("token")
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ConnectorUnavailable()
    return value


async def webhook_key(settings: Settings, tenant: UUID, connector: UUID, kid: str) -> bytes:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", kid):
        raise AuthError("INGRESS_INVALID", 401)
    record = await read(settings, tenant, connector, "webhook")
    if record.get("tenant_id") != str(tenant) or record.get("connector_id") != str(connector):
        raise ConnectorUnavailable()
    ring = record.get("keys")
    if not isinstance(ring, dict) or not 1 <= len(ring) <= 3:
        raise ConnectorUnavailable()
    if kid not in ring:
        raise AuthError("INGRESS_INVALID", 401)
    value = ring[kid]
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ConnectorUnavailable()
    return bytes.fromhex(value)


async def prometheus_authorization(
    settings: Settings, tenant: UUID, connector: UUID, scheme: str
) -> str:
    record = await read(settings, tenant, connector, "credential")
    if record.get("tenant_id") != str(tenant) or record.get("connector_id") != str(connector):
        raise ConnectorUnavailable()
    if scheme == "bearer":
        token = record.get("token")
        if not isinstance(token, str) or not re.fullmatch(r"[a-zA-Z0-9._~+/=-]{32,512}", token):
            raise ConnectorUnavailable()
        return "Bearer " + token
    username, password = record.get("username"), record.get("password")
    if (
        scheme != "basic"
        or not isinstance(username, str)
        or not isinstance(password, str)
        or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", username)
        or not 32 <= len(password) <= 512
        or not password.isascii()
        or any(ord(c) < 33 or ord(c) == 127 for c in password)
    ):
        raise ConnectorUnavailable()
    return "Basic " + base64.b64encode((username + ":" + password).encode()).decode()
