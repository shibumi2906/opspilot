from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from opspilot.db.engine import Base
from opspilot.tenancy.models import TenantOwned


class RunPlan(TenantOwned, Base):
    __tablename__ = "run_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"], ["workflow.agent_runs.tenant_id", "workflow.agent_runs.id"]
        ),
        {"schema": "workflow"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(unique=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    document_hash: Mapped[str] = mapped_column(String(64))


class PlanSlot(TenantOwned, Base):
    __tablename__ = "plan_slots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "plan_id", "key"),
        ForeignKeyConstraint(
            ["tenant_id", "plan_id"], ["workflow.run_plans.tenant_id", "workflow.run_plans.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "action_id"], ["workflow.actions.tenant_id", "workflow.actions.id"]
        ),
        {"schema": "workflow"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column()
    plan_id: Mapped[UUID] = mapped_column()
    key: Mapped[str] = mapped_column(String(32))
    ordinal: Mapped[int] = mapped_column()
    wave: Mapped[int] = mapped_column()
    tool: Mapped[str] = mapped_column(String(40))
    template: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dependencies: Mapped[list[str]] = mapped_column(JSONB)
    action_id: Mapped[UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(30), default="prepared")
    verification: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=lambda: {"status": "not_started"}
    )
    verify_attempts: Mapped[int] = mapped_column(default=0)
