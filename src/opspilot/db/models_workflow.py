from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from opspilot.db.engine import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = {"schema": "workflow"}
    id: Mapped[UUID] = mapped_column(primary_key=True)
    client_request_id: Mapped[UUID] = mapped_column(unique=True)
    request: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str | None] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(20))
    scenario_id: Mapped[str] = mapped_column(String(80))
    scenario_clock: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    thread_id: Mapped[str] = mapped_column(String(100), unique=True)
    state_schema_version: Mapped[int] = mapped_column(default=1)
    public_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    tool_results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (
        CheckConstraint("tool_name = 'create_ticket'", name="ck_actions_tool"),
        CheckConstraint(
            "execution_status IN ('not_started', 'succeeded', 'failed', 'unknown')",
            name="ck_actions_execution_status",
        ),
        {"schema": "workflow"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("workflow.agent_runs.id"), unique=True)
    tool_name: Mapped[str] = mapped_column(String(40))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    arguments_hash: Mapped[str] = mapped_column(String(64))
    execution_status: Mapped[str] = mapped_column(String(30), server_default="not_started")
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('pending', 'approved', 'rejected')", name="ck_approvals_decision"
        ),
        {"schema": "workflow"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    action_id: Mapped[UUID] = mapped_column(ForeignKey("workflow.actions.id"), unique=True)
    decision: Mapped[str] = mapped_column(String(20), server_default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
