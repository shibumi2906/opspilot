import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator


class ConfigChange(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    expected_version: int = Field(ge=0, le=2147483646)
    kind: Literal["simulator", "prometheus"] = "simulator"
    mapping_version: Literal[1] = 1
    customer_id: UUID
    integration_id: UUID
    origin: str = Field(min_length=8, max_length=300)
    read_enabled: StrictBool = False
    ingress_enabled: StrictBool = False

    @model_validator(mode="after")
    def read_only_prometheus(self) -> "ConfigChange":
        if self.kind == "prometheus" and self.ingress_enabled:
            raise ValueError("Prometheus read connector has no webhook ingress capability")
        return self

    def mapping_hash(self) -> str:
        value = [1, self.kind, str(self.customer_id), str(self.integration_id), self.origin]
        return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    event_id: UUID
    sequence: int = Field(ge=0, le=9223372036854775806)
    customer_id: UUID
    integration_id: UUID
    status: Literal["healthy", "degraded", "unavailable", "unknown"]
    observed_at: AwareDatetime


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    status: Literal["healthy", "degraded", "unavailable", "unknown"]
    checked_at: AwareDatetime
    source: Literal["synthetic"]
    mapping_version: Literal[1]
    customer_id: UUID
    integration_id: UUID


class AdapterScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: UUID
    connector_id: UUID
    customer_id: UUID
    integration_id: UUID


CAPABILITIES = {
    "simulator": {
        "mapping_version": 1,
        "source": "synthetic",
        "service_status": True,
        "webhook_observations": True,
        "credential_expiration": False,
        "external_write": False,
        "native_idempotency": False,
    },
    "prometheus": {
        "mapping_version": 1,
        "source": "registered deployment/dataset; never inferred from transport",
        "service_status": True,
        "webhook_observations": False,
        "credential_expiration": False,
        "external_write": False,
        "native_idempotency": False,
    },
}
