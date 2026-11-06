"""Public deterministic simulator identities; secret values stay in ignored operator files."""

from uuid import UUID, uuid5

from opspilot.fixtures.loader import GREENSHOP_ID, GREENSHOP_INTEGRATION_ID
from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT

CASES = [
    {
        "tenant_id": str(t),
        "connector_id": str(uuid5(t, "f18-contract-simulator")),
        "customer_id": GREENSHOP_ID if t == DEMO_TENANT else str(uuid5(t, GREENSHOP_ID)),
        "integration_id": GREENSHOP_INTEGRATION_ID
        if t == DEMO_TENANT
        else str(uuid5(t, GREENSHOP_INTEGRATION_ID)),
    }
    for t in (DEMO_TENANT, SECOND_TENANT)
]


def scope(index: int) -> tuple[UUID, UUID]:
    return UUID(CASES[index]["tenant_id"]), UUID(CASES[index]["connector_id"])
