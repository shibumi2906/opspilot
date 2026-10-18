import pytest

from opspilot.agent.policy import (
    PolicyViolation,
    forbidden_request,
    validate_analysis,
    validate_read,
)
from opspilot.agent.state import ReadCall
from opspilot.contracts.reports import Analysis
from opspilot.fixtures.loader import GREENSHOP_ID, GREENSHOP_INTEGRATION_ID


@pytest.mark.parametrize(
    "user_text", ["Delete GreenShop", "Удалить клиента GreenShop", "DROP TABLE tickets"]
)
def test_destructive_requests_blocked(user_text):
    assert forbidden_request(user_text)


@pytest.mark.parametrize(
    "name,args",
    [
        ("create_ticket", {}),
        ("unknown_tool", {}),
        (
            "get_service_status",
            {"customer_id": GREENSHOP_ID, "integration_id": "00000000-0000-0000-0000-000000000102"},
        ),
    ],
)
def test_read_allowlist_and_scope(name, args):
    with pytest.raises(PolicyViolation):
        validate_read(
            ReadCall(name=name, arguments=args),
            {"customer_id": GREENSHOP_ID, "integration_id": GREENSHOP_INTEGRATION_ID},
        )


def test_unknown_fact_references_and_hallucinated_statements_are_rejected():
    for statement, refs in [("Expired", ["missing"]), ("Invented cause", ["ev1"])]:
        analysis = Analysis(
            facts=[{"statement": statement, "evidence_ids": refs}], hypotheses=[], missing_checks=[]
        )
        with pytest.raises(PolicyViolation):
            validate_analysis(
                analysis,
                {"evidence": {"ev1": {}}},
                [{"statement": "HTTP 401", "evidence_ids": ["ev1"]}],
            )
