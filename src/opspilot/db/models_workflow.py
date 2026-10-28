from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from opspilot.auth.context import actor_id
from opspilot.db import models_identity  # noqa: F401
from opspilot.db.engine import Base
from opspilot.tenancy.models import TenantOwned


class AgentRun(TenantOwned, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "client_request_id"),
        UniqueConstraint("tenant_id", "thread_id"),
        {"schema": "workflow"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity.users.id"), default=actor_id)
    client_request_id: Mapped[UUID] = mapped_column()
    request: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str | None] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(20))
    scenario_id: Mapped[str] = mapped_column(String(80))
    scenario_clock: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    thread_id: Mapped[str] = mapped_column(String(100), unique=True)
    workflow_version: Mapped[str] = mapped_column(String(40), server_default="full-graph-v1")
    state_schema_version: Mapped[int] = mapped_column(default=1)
    public_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    tool_results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    clarification: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cancellation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    trace_id: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Action(TenantOwned, Base):
    __tablename__ = "actions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"], ["workflow.agent_runs.tenant_id", "workflow.agent_runs.id"]
        ),
        CheckConstraint(
            "tool_name IN ('create_ticket','add_ticket_comment','notify_manager')",
            name="ck_actions_tool",
        ),
        CheckConstraint(
            "execution_status IN ('not_started', 'succeeded', 'failed', 'unknown')",
            name="ck_actions_execution_status",
        ),
        {"schema": "workflow"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column()
    logical_action_id: Mapped[UUID] = mapped_column()
    revision_number: Mapped[int] = mapped_column(default=1)
    plan_version: Mapped[int] = mapped_column(default=1)
    revision_document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    revision_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tool_name: Mapped[str] = mapped_column(String(40))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    arguments_hash: Mapped[str] = mapped_column(String(64))
    execution_status: Mapped[str] = mapped_column(String(30), server_default="not_started")
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(TenantOwned, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "action_id"], ["workflow.actions.tenant_id", "workflow.actions.id"]
        ),
        CheckConstraint(
            "decision IN ('pending', 'approved', 'rejected', 'expired', 'revoked', 'superseded')",
            name="ck_approvals_decision",
        ),
        {"schema": "workflow"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    action_id: Mapped[UUID] = mapped_column(unique=True)
    decision: Mapped[str] = mapped_column(String(20), server_default="pending")
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp() + text("interval '15 minutes'"),
    )
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity.users.id"))
    self_approval_exception: Mapped[bool] = mapped_column(default=False, server_default="false")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LogicalAction(TenantOwned, Base):
    __tablename__ = "logical_actions"
    __table_args__ = (UniqueConstraint("tenant_id", "id"), {"schema": "workflow"})
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column()
    current_revision_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(default=1)
