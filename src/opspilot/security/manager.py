"""OpenBao KV-v2 adapter: exact paths, TLS, bounded replies, no fallback on denial/outage.

Only the local operator provisions/replaces short-lived, least-privilege tokens.
Secrets and raw provider errors never escape this boundary.
"""

import json
import re
import ssl
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from opspilot.security.keys import KeyReference, version


class ManagerUnavailable(ValueError):
    def __init__(self) -> None:
        super().__init__("SECRET_MANAGER_UNAVAILABLE")


class BaoGrantKeys:
    def __init__(self, origin: str, ca_file: str, token_file: str) -> None:
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Secret manager requires an explicit HTTPS origin")
        self.origin = origin.rstrip("/")
        self.ca_file = ca_file
        self.token_file = token_file

    def read(self, path: str) -> dict[str, Any]:
        if not re.fullmatch(r"grants/(active|public|private/[1-9][0-9]{0,8})", path):
            raise ValueError("Unregistered secret reference")
        try:
            token = Path(self.token_file).read_text().strip()
            if not 20 <= len(token) <= 512 or any(c.isspace() for c in token):
                raise ValueError()
            context = ssl.create_default_context(cafile=self.ca_file)
            with httpx.Client(
                verify=context, trust_env=False, timeout=2, follow_redirects=False
            ) as client:
                with client.stream(
                    "GET", self.origin + "/v1/core/data/" + path, headers={"X-Vault-Token": token}
                ) as response:
                    if response.status_code != 200:
                        raise ValueError()
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 16384:
                            raise ValueError()
            value = json.loads(raw)["data"]["data"]
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (OSError, ValueError, KeyError, TypeError, httpx.HTTPError):
            raise ManagerUnavailable() from None

    def signing_key(self, slot: str) -> tuple[KeyReference, bytes]:
        if slot not in {"grant-current", "grant-next"}:
            raise ValueError("Invalid grant key slot")
        try:
            active = self.read("grants/active")[slot]
            if type(active) is not int or not 1 <= active <= 999999999:
                raise ValueError()
            value = self.read("grants/private/" + str(active))
            raw = value["pem"].encode()
            key = serialization.load_pem_private_key(raw, password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError()
            kid = version(slot, key.public_key())
            # A partial rotation cannot sign a token the verifier cannot resolve.
            expected = self.verification_key(kid)
            if (
                key.public_key().public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
                )
                != expected
            ):
                raise ValueError()
            return KeyReference("execution-grant-v1", kid), raw
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ManagerUnavailable() from None

    def verification_key(self, kid: str) -> bytes:
        if not re.fullmatch(r"grant-(current|next):[0-9a-f]{64}", kid):
            raise ValueError("Invalid key identity")
        try:
            value = self.read("grants/public")[kid]
            if not isinstance(value, str):
                raise ValueError()
            raw = value.encode()
            key = serialization.load_pem_public_key(raw)
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            if not isinstance(key, Ed25519PublicKey) or version(kid.split(":")[0], key) != kid:
                raise ValueError()
            return raw
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ManagerUnavailable() from None
