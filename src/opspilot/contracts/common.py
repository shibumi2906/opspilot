from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolError(StrictModel):
    code: Literal["NOT_FOUND", "DEPENDENCY_UNAVAILABLE", "MONITORING_TIMEOUT", "INVALID_ARGUMENTS"]
    message: str
    retryable: bool = False


class Source(StrictModel):
    source_type: str
    source_id: str
    version: str | None = None


class ToolResult(StrictModel):
    schema_version: Literal[1] = 1
    ok: bool
    tool_call_id: UUID = Field(default_factory=uuid4)
    observed_at: AwareDatetime
    data: dict[str, Any] | None = None
    sources: list[Source] = Field(default_factory=list)
    error: ToolError | None = None

    @model_validator(mode="after")
    def check_outcome(self) -> "ToolResult":
        if self.ok and (self.data is None or self.error is not None):
            raise ValueError("Successful result requires data and no error")
        if not self.ok and (self.data is not None or self.error is None or self.sources):
            raise ValueError("Failed result requires error and no data/sources")
        return self

    @classmethod
    def not_found(cls, observed_at: datetime) -> "ToolResult":
        return cls(
            ok=False,
            observed_at=observed_at,
            error=ToolError(code="NOT_FOUND", message="Customer not found"),
        )
