from typing import Any, Literal
from uuid import UUID

from opspilot.contracts.common import StrictModel


class CustomerFixture(StrictModel):
    id: UUID
    name: str


class IntegrationFixture(StrictModel):
    id: UUID
    customer_id: UUID
    integration_type: str
    external_ref: str


class IncidentFixture(StrictModel):
    id: UUID
    customer_id: UUID
    integration_type: str
    language: Literal["ru", "en"]
    days_before_clock: int
    summary: str
    root_cause: str
    resolution: str


class ArticleFixture(StrictModel):
    id: UUID
    title: str
    body: str
    integration_type: str
    language: Literal["ru", "en"]
    version: str


class Fixtures(StrictModel):
    customers: list[CustomerFixture]
    integrations: list[IntegrationFixture]
    incidents: list[IncidentFixture]
    articles: list[ArticleFixture]


class MonitoringFixture(StrictModel):
    status: Literal["degraded", "healthy", "unavailable", "unknown"]
    credential_status: Literal["expired", "valid", "revoked", "unknown"]
    last_success_minutes_before_clock: int
    events: list[dict[str, Any]]
