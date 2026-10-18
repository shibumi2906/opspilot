from datetime import datetime
from typing import Literal

from pydantic import Field

from opspilot.agent.budgets import BudgetLimits
from opspilot.contracts.common import StrictModel
from opspilot.contracts.reports import Outcome


class DBAssertions(StrictModel):
    ticket_delta: int = Field(ge=0, le=1)
    action_count: int = Field(ge=0, le=1)


class Scenario(StrictModel):
    id: str = Field(pattern=r"^E\d{2}$")
    fixture: Literal["greenshop_expired", "healthy", "unknown", "timeout", "contradictory"]
    clock: datetime
    request: str
    language: Literal["en", "ru"]
    required_tools: set[str]
    allowed_tools: set[str]
    forbidden_tools: set[str]
    human_decisions: list[Literal["approve", "reject"]]
    expected_outcome: Outcome
    required_evidence_predicates: list[str]
    forbidden_claims: list[str]
    db_assertions: DBAssertions
    limits: BudgetLimits = Field(default_factory=BudgetLimits)
    article_overlay: Literal["none", "stale", "injection"] = "none"
