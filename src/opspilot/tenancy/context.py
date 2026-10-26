"""Trusted in-process tenant scope. Never populated from request arguments/headers."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

DEMO_TENANT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SECOND_TENANT = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
DEMO_ACTOR = UUID("11111111-1111-4111-8111-111111111111")
_current: ContextVar[UUID | None] = ContextVar("opspilot_tenant", default=None)


class TenantContextError(ValueError):
    pass


def current_tenant() -> UUID | None:
    return _current.get()


def require_tenant() -> UUID:
    tenant = current_tenant()
    if tenant is None:
        raise TenantContextError("Trusted tenant context required")
    return tenant


@contextmanager
def tenant_scope(tenant: UUID | None) -> Iterator[None]:
    token = _current.set(tenant)
    try:
        yield
    finally:
        _current.reset(token)
