"""Operator-owned registration; neither model arguments nor admin config select egress scope."""

import hashlib
import ipaddress
import json
import re
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from opspilot.config import Settings
from opspilot.integrations.egress import ConnectorUnavailable, origin


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    tenant_id: UUID
    connector_id: UUID
    customer_id: UUID
    integration_id: UUID
    origin: str
    addresses: tuple[str, ...] = Field(min_length=1, max_length=8)
    ca_file: str
    targets: tuple[str, ...] = Field(min_length=1, max_length=8)
    deployment: Literal["fixture", "staging", "live"]
    dataset: Literal["synthetic", "observed"]
    auth_scheme: Literal["basic", "bearer"] = "basic"
    allow_private: StrictBool = False
    tenant_header: UUID | None = None
    authorization_ref: str = Field(min_length=1, max_length=200)

    @field_validator("targets")
    @classmethod
    def target_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", value) for value in values
        ):
            raise ValueError("Unique bounded target names required")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def boundaries(self) -> "Registration":
        origin(self.origin)
        if self.deployment == "fixture" and self.dataset != "synthetic":
            raise ValueError("Fixture series must be classified synthetic")
        if len(set(self.addresses)) != len(self.addresses):
            raise ValueError("Unique addresses required")
        for value in self.addresses:
            address = ipaddress.ip_address(value)
            if (
                str(address) != value
                or address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
                or getattr(address, "ipv4_mapped", None)
                or (not address.is_global and not self.allow_private)
            ):
                raise ValueError("Unsafe registration address")
        path = Path(self.ca_file)
        if not path.is_absolute() or not path.is_file() or path.stat().st_size > 65536:
            raise ValueError("Explicit bounded CA file required")
        return self

    def mapping(self) -> dict[str, object]:
        return {
            "template": "opspilot_health_v1",
            "targets": list(self.targets),
            "deployment": self.deployment,
            "dataset": self.dataset,
            "auth_scheme": self.auth_scheme,
            "tenant_header": str(self.tenant_header) if self.tenant_header else None,
        }

    def source_version(self) -> str:
        return f"prometheus-mapping1:{self.dataset}:{self.deployment}"

    def mapping_hash(self) -> str:
        values = [
            1,
            "prometheus",
            str(self.customer_id),
            str(self.integration_id),
            self.origin,
            self.mapping(),
        ]
        return hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def registration(settings: Settings, tenant: UUID, connector: UUID) -> Registration:
    try:
        file = settings.prometheus_registry_file
        if not file:
            raise ValueError()
        path = Path(file)
        if not path.is_absolute() or path.stat().st_size > 65536:
            raise ValueError()
        with path.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError()

        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result

        from pydantic import TypeAdapter

        rows = TypeAdapter(list[Registration]).validate_python(
            json.loads(raw, object_pairs_hook=unique)
        )
        if not 1 <= len(rows) <= 100:
            raise ValueError()
        identities = [(r.tenant_id, r.connector_id) for r in rows]
        if len(set(identities)) != len(identities):
            raise ValueError()
        selected = next(r for r in rows if (r.tenant_id, r.connector_id) == (tenant, connector))
        if selected.deployment == "fixture" and settings.app_env == "production":
            raise ValueError()
        return selected
    except (OSError, ValueError, StopIteration, TypeError, RecursionError):
        raise ConnectorUnavailable() from None
