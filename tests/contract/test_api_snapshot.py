from uuid import uuid4

import pytest
from pydantic import ValidationError

from opspilot.contracts.api import CreateRun, Decision


def test_request_requires_id_and_normalizes_text():
    key = uuid4()
    assert (
        CreateRun(request="  Investigate GreenShop  ", client_request_id=key).request
        == "Investigate GreenShop"
    )
    for payload in (
        {"request": "test"},
        {"request": " ", "client_request_id": key},
        {"request": "x" * 4001, "client_request_id": key},
    ):
        with pytest.raises(ValidationError):
            CreateRun.model_validate(payload)


@pytest.mark.parametrize("extra", [{"arguments": {}}, {"title": "changed"}, {"approved": True}])
def test_decision_forbids_payload_and_grants(extra):
    with pytest.raises(ValidationError):
        Decision.model_validate({"action_id": str(uuid4()), "decision": "approve", **extra})
