from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from opspilot.db import models_identity  # noqa: F401
from opspilot.db.engine import Base
from opspilot.tenancy.models import TenantOwned


class Customer(TenantOwned, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_customers_normalized_name", "normalized_name"),
        {"schema": "domain"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerIntegration(TenantOwned, Base):
    __tablename__ = "customer_integrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"], ["domain.customers.tenant_id", "domain.customers.id"]
        ),
        UniqueConstraint("customer_id", "integration_type", "external_ref"),
        {"schema": "domain"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    customer_id: Mapped[UUID] = mapped_column(index=True)
    integration_type: Mapped[str] = mapped_column(String(80))
    external_ref: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Incident(TenantOwned, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"], ["domain.customers.tenant_id", "domain.customers.id"]
        ),
        {"schema": "domain"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    customer_id: Mapped[UUID] = mapped_column(index=True)
    integration_type: Mapped[str] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(10))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeArticle(TenantOwned, Base):
    __tablename__ = "knowledge_articles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        {"schema": "domain"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    integration_type: Mapped[str] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(10))
    version: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(TenantOwned, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"], ["domain.customers.tenant_id", "domain.customers.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "originating_action_id"],
            ["workflow.actions.tenant_id", "workflow.actions.id"],
        ),
        CheckConstraint("priority IN ('low','medium','high')", name="ck_ticket_priority"),
        CheckConstraint("status = 'open'", name="ck_ticket_status"),
        {"schema": "domain"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    customer_id: Mapped[UUID] = mapped_column(index=True)
    originating_action_id: Mapped[UUID] = mapped_column(unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), server_default="open")
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketComment(TenantOwned, Base):
    __tablename__ = "ticket_comments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "ticket_id"], ["domain.tickets.tenant_id", "domain.tickets.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"], ["domain.customers.tenant_id", "domain.customers.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "originating_action_id"],
            ["workflow.actions.tenant_id", "workflow.actions.id"],
        ),
        {"schema": "domain"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    customer_id: Mapped[UUID] = mapped_column()
    ticket_id: Mapped[UUID] = mapped_column()
    originating_action_id: Mapped[UUID] = mapped_column(unique=True)
    body: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(TenantOwned, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"], ["domain.customers.tenant_id", "domain.customers.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "originating_action_id"],
            ["workflow.actions.tenant_id", "workflow.actions.id"],
        ),
        {"schema": "domain"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    customer_id: Mapped[UUID] = mapped_column()
    recipient_id: Mapped[UUID] = mapped_column()
    originating_action_id: Mapped[UUID] = mapped_column(unique=True)
    body: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
