from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from opspilot.db.engine import Base


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "identity"}
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("issuer", "subject"), {"schema": "identity"})
    id: Mapped[UUID] = mapped_column(primary_key=True)
    issuer: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        CheckConstraint("role IN ('operator','approver','auditor','admin')"),
        {"schema": "identity"},
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("identity.tenants.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity.users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String, primary_key=True)


class ServerSession(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": "identity"}
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity.users.id"))
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("identity.tenants.id"))
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
