"""Registered HTTPS origin, all-answer DNS validation, pinned address and TLS hostname.

No redirects, proxy environment, model URLs, compressed responses or generic write API.
The explicit simulator exception admits exactly one registered address in local/test.
"""

import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from urllib.parse import urlsplit

from opspilot.config import Settings
from opspilot.integrations.contracts import AdapterScope, Health
from opspilot.integrations.executor import bounded


class ConnectorUnavailable(ValueError):
    def __init__(self) -> None:
        super().__init__("CONNECTOR_UNAVAILABLE")


def origin(value: str) -> tuple[str, int]:
    try:
        p = urlsplit(value)
        if (
            p.scheme != "https"
            or not p.hostname
            or p.username
            or p.password
            or p.path
            or p.query
            or p.fragment
            or len(value) > 300
            or not re.fullmatch(r"[a-z0-9.-]+", p.hostname)
            or p.hostname.endswith(".")
            or p.port not in {None, 443, 8443}
        ):
            raise ValueError()
        if value != f"https://{p.hostname}" + (f":{p.port}" if p.port else ""):
            raise ValueError()
        return p.hostname, p.port or 443
    except ValueError:
        raise ConnectorUnavailable() from None


def validate_addresses(addresses: list[str], *, simulator_ip: str | None = None) -> list[str]:
    if not addresses or len(addresses) > 16:
        raise ConnectorUnavailable()
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if (
            address.is_multicast
            or address.is_link_local
            or address.is_unspecified
            or address.is_reserved
            or getattr(address, "ipv4_mapped", None)
        ):
            raise ConnectorUnavailable()
        if simulator_ip is not None:
            if raw != simulator_ip:
                raise ConnectorUnavailable()
        elif not address.is_global or getattr(address, "ipv4_mapped", None):
            raise ConnectorUnavailable()
    return sorted(set(addresses))


def registered(settings: Settings, value: str) -> tuple[str, int, str]:
    host, port = origin(value)
    # F18 registers only the synthetic simulator. Vendor destinations need F19/F20.
    if (
        settings.app_env not in {"test", "local"}
        or value != settings.connector_simulator_origin
        or not settings.connector_simulator_ip
        or not settings.connector_simulator_ca_file
    ):
        raise ConnectorUnavailable()
    ipaddress.ip_address(settings.connector_simulator_ip)
    return host, port, settings.connector_simulator_ip


def _health(settings: Settings, destination: str, credential: str, scope: AdapterScope) -> Health:
    connection = None
    try:
        host, port, allowed = registered(settings, destination)
        deadline = time.monotonic() + 2
        addresses = [str(r[4][0]) for r in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
        pinned = validate_addresses(addresses, simulator_ip=allowed)[0]
        if time.monotonic() >= deadline:
            raise ConnectorUnavailable()
        context = ssl.create_default_context(cafile=settings.connector_simulator_ca_file)

        class PinnedHTTPS(http.client.HTTPSConnection):
            def connect(self) -> None:
                raw = socket.create_connection((pinned, port), timeout=0.5)
                try:
                    self.sock = context.wrap_socket(raw, server_hostname=host)
                except BaseException:
                    raw.close()
                    raise

        connection = PinnedHTTPS(host, port, timeout=0.5, context=context)
        connection.request(
            "GET",
            "/v1/health",
            headers={
                "Authorization": "Bearer " + credential,
                "Accept": "application/json",
                **{
                    "X-Ops-" + key.replace("_id", "").replace("_", "-"): str(value)
                    for key, value in scope.model_dump().items()
                },
                "Accept-Encoding": "identity",
            },
        )
        response = connection.getresponse()
        if (
            response.status != 200
            or response.getheader("Content-Encoding") not in {None, "identity"}
            or response.getheader("Content-Type", "").split(";")[0] != "application/json"
        ):
            raise ConnectorUnavailable()
        raw = bytearray()
        while True:
            if time.monotonic() >= deadline:
                raise ConnectorUnavailable()
            chunk = response.read(4096)
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 16384:
                raise ConnectorUnavailable()

        # Strict JSON rejects duplicate keys and non-finite constants.
        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result

        value = json.loads(raw, object_pairs_hook=unique)
        health = Health.model_validate_json(json.dumps(value))
        if (
            abs(time.time() - health.checked_at.timestamp()) > 300
            or health.customer_id != scope.customer_id
            or health.integration_id != scope.integration_id
        ):
            raise ConnectorUnavailable()
        return health
    except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException):
        raise ConnectorUnavailable() from None
    finally:
        if connection:
            connection.close()


async def health(
    settings: Settings, destination: str, credential: str, scope: AdapterScope
) -> Health:
    try:
        return await bounded(_health, settings, destination, credential, scope, budget=2.5)
    except TimeoutError:
        raise ConnectorUnavailable() from None
