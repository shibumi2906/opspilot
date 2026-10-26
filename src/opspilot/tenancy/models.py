from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from opspilot.tenancy.context import require_tenant


class TenantOwned:
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity.tenants.id"),
        default=require_tenant,
        server_default=text("identity.current_tenant()"),
        nullable=False,
    )
