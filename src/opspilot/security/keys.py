"""Purpose/version-bound key contract, with an explicit local-development adapter."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from opspilot.config import Settings

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


@dataclass(frozen=True)
class KeyReference:
    purpose: str
    kid: str
    algorithm: str = "EdDSA"


class GrantKeyProvider(Protocol):
    def signing_key(self, slot: str) -> tuple[KeyReference, bytes]: ...
    def verification_key(self, kid: str) -> bytes: ...


def grant_keys(settings: "Settings") -> GrantKeyProvider:
    if settings.secret_manager_url:
        from opspilot.security.manager import BaoGrantKeys

        return BaoGrantKeys(
            settings.secret_manager_url,
            settings.secret_manager_ca_file or "",
            settings.secret_manager_token_file or "",
        )
    return FileGrantKeys(settings.service_private_dir, settings.service_public_keys)


def version(slot: str, key: Ed25519PublicKey) -> str:
    if slot not in {"grant-current", "grant-next"}:
        raise ValueError("Invalid grant key slot")
    raw = key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return slot + ":" + hashlib.sha256(raw).hexdigest()


class FileGrantKeys:
    """Local adapter only; never reuses service/session keys or resolves a user-supplied path."""

    def __init__(self, private: str, public: str) -> None:
        self.private = Path(private)
        self.public = Path(public).with_name("grants.json")

    def signing_key(self, slot: str) -> tuple[KeyReference, bytes]:
        if slot not in {"grant-current", "grant-next"}:
            raise ValueError("Invalid grant key slot")
        raw = (self.private / (slot + ".pem")).read_bytes()
        key = serialization.load_pem_private_key(raw, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("Ed25519 grant key required")
        return KeyReference("execution-grant-v1", version(slot, key.public_key())), raw

    def verification_key(self, kid: str) -> bytes:
        slot = kid.split(":")[0]
        if slot not in {"grant-current", "grant-next"}:
            raise ValueError("Invalid grant key slot")
        ring = json.loads(self.public.read_text())
        value = ring[slot]
        if not isinstance(value, str):
            raise ValueError("Invalid verification key")
        raw = value.encode()
        key = serialization.load_pem_public_key(raw)
        if not isinstance(key, Ed25519PublicKey) or version(slot, key) != kid:
            raise ValueError("Grant key version unavailable")
        return raw
