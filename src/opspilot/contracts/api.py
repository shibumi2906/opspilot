from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from opspilot.contracts.actions import CommentProposal, NotificationProposal, TicketProposal
from opspilot.contracts.common import StrictModel


class CreateRun(StrictModel):
    request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    client_request_id: UUID


class Decision(StrictModel):
    action_id: UUID
    decision: Literal["approve", "reject"]
    expected_version: Annotated[int, Field(strict=True, ge=1, le=10)]


class ClarificationAnswer(StrictModel):
    clarification_id: UUID
    expected_version: Annotated[int, Field(strict=True, ge=1, le=2)]
    kind: Literal["customer", "integration", "timezone"]
    choice: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    command_id: UUID


class CancelRun(StrictModel):
    command_id: UUID


class RevisionChange(StrictModel):
    expected_version: Annotated[int, Field(strict=True, ge=1, le=10)]
    arguments: TicketProposal | CommentProposal | NotificationProposal


class RevokeApproval(StrictModel):
    expected_version: Annotated[int, Field(strict=True, ge=1, le=10)]
