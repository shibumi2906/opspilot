from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from opspilot.tenancy.context import DEMO_ACTOR, tenant_scope


class AuthError(Exception):
    def __init__(self, code: str = "FORBIDDEN", status: int = 403) -> None:
        self.code, self.status = code, status


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID | None
    roles: frozenset[str]
    session_id: UUID
    auth_time: datetime | None = None
    expires_at: datetime | None = None
    idle_expires_at: datetime | None = None


_current: ContextVar[Principal | None] = ContextVar("principal", default=None)


def principal() -> Principal:
    value = _current.get()
    if value is None:
        raise AuthError("AUTHENTICATION_REQUIRED", 401)
    return value


def optional_principal() -> Principal | None:
    return _current.get()


def actor_id() -> UUID:
    value = _current.get()
    return value.user_id if value else DEMO_ACTOR


def require_role(role: str) -> Principal:
    value = principal()
    if value.tenant_id is None or role not in value.roles:
        raise AuthError()
    return value


@contextmanager
def auth_scope(value: Principal) -> Iterator[None]:
    token = _current.set(value)
    try:
        with tenant_scope(value.tenant_id):
            yield
    finally:
        _current.reset(token)
