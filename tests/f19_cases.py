"""Public F19 identities; fixture data is synthetic even in a real Prometheus."""

from uuid import UUID, uuid5

from tests.f18_cases import CASES as F18_CASES

CASES = [
    {**case, "connector_id": str(uuid5(UUID(case["tenant_id"]), "f19-prometheus-v1"))}
    for case in F18_CASES
]
