from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from opspilot.contracts.common import StrictModel

Outcome = Literal[
    "actions_verified",
    "unknown_outcome",
    "rejected",
    "diagnosis_only",
    "proposed_only",
    "partial",
    "blocked",
    "insufficient_context",
    "budget_exhausted",
]


class Fact(StrictModel):
    statement: str
    evidence_ids: Annotated[list[str], Field(min_length=1, max_length=30)]


class Hypothesis(StrictModel):
    hypothesis_id: str
    summary: str
    supporting_evidence_ids: Annotated[list[str], Field(min_length=1, max_length=30)]
    contradicting_evidence_ids: Annotated[list[str], Field(max_length=30)]
    confidence_label: Literal["low", "medium", "high"]
    missing_checks: list[str]


class Analysis(StrictModel):
    facts: Annotated[list[Fact], Field(max_length=30)]
    hypotheses: Annotated[list[Hypothesis], Field(max_length=5)]
    missing_checks: Annotated[list[str], Field(max_length=15)]


class Report(StrictModel):
    summary: str
    facts: list[Fact]
    hypotheses: list[Hypothesis]
    missing_checks: list[str]
    action_summary: str
    ticket_id: UUID | None = None
    verification_status: Literal["not_started", "verified", "mismatch", "unknown"] = "not_started"
    remaining_problem: str
    outcome: Outcome
