from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import text

from opspilot.auth.context import require_role
from opspilot.auth.session_routes import require_recent
from opspilot.integrations.contracts import CAPABILITIES, ConfigChange
from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.service import configure

router = APIRouter(prefix="/api/v2/admin/adapters")


@router.get("")
async def configs(request: Request) -> dict[str, object]:
    require_role("admin")
    async with request.app.state.engine.connect() as c:
        rows = (
            (
                await c.execute(
                    text("""SELECT id,customer_id,integration_id,kind,mapping_version,
          version,read_enabled,ingress_enabled,adapter_mapping FROM integrations.connector_configs
          ORDER BY id LIMIT 100""")
                )
            )
            .mappings()
            .all()
        )
    return {
        "items": [
            {
                **{k: v for k, v in r.items() if k != "adapter_mapping"},
                "source": r["adapter_mapping"].get("dataset", "synthetic"),
                "write_enabled": False,
            }
            for r in rows
        ],
        "capabilities": CAPABILITIES,
    }


@router.put("/{connector}")
async def update(connector: UUID, value: ConfigChange, request: Request) -> dict[str, object]:
    require_role("admin")
    require_recent(request.app.state.identity.settings)
    try:
        return await configure(
            request.app.state.engine, request.app.state.identity.settings, connector, value
        )
    except ConnectorUnavailable:
        from opspilot.auth.context import AuthError

        raise AuthError("CONNECTOR_DESTINATION_DENIED", 422) from None
