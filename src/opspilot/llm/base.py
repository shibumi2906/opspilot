from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from opspilot.contracts.common import StrictModel

Operation = Literal["classify", "investigate", "reason", "plan"]


class Usage(StrictModel):
    standard_pricing: bool = True
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    cache_write_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_cached_tokens(self) -> "Usage":
        if self.input_tokens is not None:
            cached = (self.cached_input_tokens or 0) + (self.cache_write_tokens or 0)
            if cached > self.input_tokens:
                raise ValueError("Cached/write tokens exceed total input")
        return self


class Completion(StrictModel):
    model_id: str | None = None
    output: dict[str, Any]
    usage: Usage


class ProviderFailure(Exception):
    def __init__(self, code: str, *, retryable: bool = False, usage: Usage | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.usage = usage or Usage()


class Provider(Protocol):
    async def complete(self, operation: Operation, context: dict[str, Any]) -> Completion: ...
