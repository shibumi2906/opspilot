"""Repository guard: explicit tenant criteria as well as database RLS."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from opspilot.tenancy.context import TenantContextError, require_tenant
from opspilot.tenancy.models import TenantOwned


def check_scope(session: Session) -> None:
    tenant = require_tenant()
    bound = session.info.setdefault("tenant_id", tenant)
    if bound != tenant:
        raise TenantContextError("A repository session cannot change tenant")


class TenantSession(AsyncSession):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.info["tenant_repository"] = True

    async def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
        check_scope(self.sync_session)
        return await super().get(entity, ident, **kwargs)


@event.listens_for(TenantSession.sync_session_class, "do_orm_execute")
def tenant_criteria(state: ORMExecuteState) -> None:
    # Only the explicitly scoped repository sessions, not administrative SQL sessions.
    if "tenant_repository" not in state.session.info:
        return
    check_scope(state.session)
    tenant = require_tenant()
    if state.is_orm_statement:
        state.statement = state.statement.options(
            with_loader_criteria(
                TenantOwned, lambda cls: cls.tenant_id == tenant, include_aliases=True
            )
        )


@event.listens_for(TenantSession.sync_session_class, "before_flush")
def tenant_inserts(session: Session, flush_context: Any, instances: Any) -> None:
    if "tenant_repository" not in session.info:
        return
    check_scope(session)
    tenant = require_tenant()
    for obj in session.new.union(session.dirty):
        if isinstance(obj, TenantOwned) and obj.tenant_id is not None and obj.tenant_id != tenant:
            raise TenantContextError("Repository row belongs to another tenant")
