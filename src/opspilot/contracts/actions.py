from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator

from opspilot.contracts.common import StrictModel


class TicketProposal(StrictModel):
    customer_id: UUID
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    description: Annotated[str, StringConstraints(min_length=1, max_length=6000)]
    priority: Literal["low", "medium", "high"]
    evidence_ids: Annotated[list[str], Field(min_length=1, max_length=30)]

    @field_validator("evidence_ids")
    @classmethod
    def normalize_ids(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


class PlanDecision(StrictModel):
    proposal: TicketProposal | None
