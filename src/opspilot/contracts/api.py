from typing import Annotated, Literal
from uuid import UUID

from pydantic import StringConstraints

from opspilot.contracts.common import StrictModel


class CreateRun(StrictModel):
    request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    client_request_id: UUID


class Decision(StrictModel):
    action_id: UUID
    decision: Literal["approve", "reject"]
