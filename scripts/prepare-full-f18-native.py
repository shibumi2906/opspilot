"""Operator-only fixture in native test DB; run after baseline MFA tests, not in Full dev."""

import asyncio
import sys
from uuid import UUID

sys.path.insert(0, "/work")
from sqlalchemy import text

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.integrations.contracts import ConfigChange
from tests.f18_cases import CASES


async def main():
    settings = Settings()
    engine = create_engine(settings.database_url("migration"))
    case = CASES[1]
    value = ConfigChange(
        expected_version=0,
        customer_id=UUID(case["customer_id"]),
        integration_id=UUID(case["integration_id"]),
        origin="https://adapter-simulator:8443",
    )
    p = {k: UUID(v) for k, v in case.items()}
    p.update(
        origin=value.origin,
        hash=value.mapping_hash(),
        credential=f"connectors/{case['tenant_id']}/{case['connector_id']}/credential",
        webhook=f"connectors/{case['tenant_id']}/{case['connector_id']}/webhook",
    )
    try:
        async with engine.begin() as c:
            assert await c.scalar(text("SELECT current_database()")) == "opspilot_full_test"
            await c.execute(
                text("""INSERT INTO integrations.connector_configs
                (tenant_id,id,customer_id,integration_id,kind,mapping_version,origin,mapping_hash,credential_ref,webhook_ref,read_enabled,ingress_enabled)
                VALUES(:tenant_id,:connector_id,:customer_id,:integration_id,'simulator',1,:origin,:hash,:credential,:webhook,false,true)
                ON CONFLICT(tenant_id,id) DO UPDATE SET ingress_enabled=true"""),
                p,
            )
    finally:
        await engine.dispose()
    print("Native test-only tenant B observation mapping prepared after MFA baseline")


asyncio.run(main())
