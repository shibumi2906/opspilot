from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from opspilot.contracts.actions import TicketProposal
from opspilot.contracts.common import StrictModel


class GetCustomerArgs(StrictModel):
    customer_id: UUID


class IntegrationSummary(StrictModel):
    integration_id: UUID
    integration_type: str


class CustomerData(StrictModel):
    customer_id: UUID
    name: str
    integrations: list[IntegrationSummary]


Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Limit = Annotated[int, Field(strict=True, ge=1, le=10)]


class FindCustomersArgs(StrictModel):
    query: Query
    limit: Limit = 10


class IntegrationArgs(GetCustomerArgs):
    integration_id: UUID


class EventsArgs(IntegrationArgs):
    from_: AwareDatetime = Field(alias="from")
    to: AwareDatetime
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 100

    @model_validator(mode="after")
    def check_range(self) -> "EventsArgs":
        if not timedelta(0) < self.to - self.from_ <= timedelta(days=7):
            raise ValueError("Event range must be positive and at most seven days")
        return self


class SearchDocumentationArgs(FindCustomersArgs):
    integration_type: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None
    language: Literal["ru", "en"] | None = None


class SearchIncidentsArgs(SearchDocumentationArgs):
    customer_id: UUID | None = None


class GetTicketArgs(StrictModel):
    ticket_id: UUID


class Candidate(StrictModel):
    customer_id: UUID
    name: str


class CustomersData(StrictModel):
    candidates: list[Candidate]
    truncated: bool


class ServiceData(StrictModel):
    status: Literal["healthy", "degraded", "unavailable", "unknown"]
    latest_success_at: AwareDatetime | None
    checked_at: AwareDatetime


class CredentialData(StrictModel):
    status: Literal["valid", "expired", "revoked", "unknown"]
    checked_at: AwareDatetime


class Event(StrictModel):
    event_id: UUID
    occurred_at: AwareDatetime
    http_status: int | None = None
    event_type: str
    summary: str


class EventsData(StrictModel):
    events: list[Event]
    truncated: bool


class IncidentHit(StrictModel):
    incident_id: UUID
    customer_id: UUID
    summary: str
    root_cause: str
    resolution: str
    score: float
    occurred_at: AwareDatetime


class IncidentsData(StrictModel):
    hits: list[IncidentHit]


class ArticleHit(StrictModel):
    article_id: UUID
    version: str
    language: Literal["ru", "en"]
    title: str
    excerpt: str
    score: float


class DocumentationData(StrictModel):
    hits: list[ArticleHit]


class TicketData(StrictModel):
    ticket_id: UUID
    customer_id: UUID
    title: str
    description: str
    priority: Literal["low", "medium", "high"]
    status: Literal["open"]
    evidence_ids: list[str]
    originating_action_id: UUID
    created_at: AwareDatetime


class CreateTicketArgs(StrictModel):
    run_id: UUID
    action_id: UUID
    arguments: TicketProposal


class CreateTicketData(StrictModel):
    ticket_id: UUID
    created_at: AwareDatetime
    replayed: bool
