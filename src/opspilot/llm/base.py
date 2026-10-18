from typing import Any, Literal, Protocol

from pydantic import Field

from opspilot.contracts.common import StrictModel

Operation = Literal["classify", "investigate", "reason", "plan"]


class Usage(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


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
