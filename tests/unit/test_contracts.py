from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from opspilot.config import Settings
from opspilot.contracts.common import Source, ToolResult
from opspilot.contracts.evidence import normalize_evidence
from opspilot.contracts.tools import EventsArgs
from opspilot.fixtures.loader import GREENSHOP_ID, GREENSHOP_INTEGRATION_ID
from opspilot.mcp_client.registry import READ_TOOLS
from opspilot.mcp_server.adapters.monitoring import observe

CLOCK = datetime(2026, 10, 18, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    "name,args",
    [
        ("find_customers", {"query": " "}),
        ("find_customers", {"query": "Green", "limit": 11}),
        ("search_incidents", {"query": "401", "limit": 0}),
        ("search_documentation", {"query": "401", "language": "fr"}),
        ("get_ticket", {"ticket_id": "bad"}),
        ("get_service_status", {"customer_id": GREENSHOP_ID, "integration_id": "bad"}),
    ],
)
def test_invalid_arguments(name, args):
    with pytest.raises(ValidationError):
        READ_TOOLS[name].arguments.model_validate(args)


@pytest.mark.parametrize(
    "start,end",
    [
        (CLOCK, CLOCK),
        (CLOCK, CLOCK - timedelta(seconds=1)),
        (CLOCK, CLOCK + timedelta(days=8)),
        (CLOCK.replace(tzinfo=None), CLOCK),
    ],
)
def test_event_range(start, end):
    with pytest.raises(ValidationError):
        EventsArgs.model_validate(
            {
                "customer_id": GREENSHOP_ID,
                "integration_id": GREENSHOP_INTEGRATION_ID,
                "from": start,
                "to": end,
            }
        )


@pytest.mark.parametrize(
    "scenario,status,credential",
    [
        ("greenshop_expired", "degraded", "expired"),
        ("healthy", "healthy", "valid"),
        ("unknown", "unknown", "unknown"),
        ("contradictory", "healthy", "valid"),
    ],
)
def test_monitoring_scenarios(scenario, status, credential):
    from uuid import UUID

    settings = Settings(_env_file=None, mcp_service_token="a" * 64, scenario_id=scenario)
    snapshot = observe(settings, UUID(GREENSHOP_ID), UUID(GREENSHOP_INTEGRATION_ID))
    assert snapshot["status"] == status
    assert snapshot["credential_status"] == credential
    if scenario == "contradictory":
        assert snapshot["events"][0]["http_status"] == 401
    assert snapshot == observe(settings, UUID(GREENSHOP_ID), UUID(GREENSHOP_INTEGRATION_ID))


def test_timeout_is_not_unknown_evidence():
    from uuid import UUID

    settings = Settings(_env_file=None, mcp_service_token="a" * 64, scenario_id="timeout")
    with pytest.raises(TimeoutError):
        observe(settings, UUID(GREENSHOP_ID), UUID(GREENSHOP_INTEGRATION_ID))
    result = ToolResult(
        ok=True,
        observed_at=CLOCK,
        data={"status": "unknown", "checked_at": CLOCK.isoformat()},
        sources=[Source(source_type="credential_status", source_id=GREENSHOP_INTEGRATION_ID)],
    )
    first = normalize_evidence("get_credential_status", result)
    assert first[0].facts["status"] == "unknown"
    assert (
        first[0].evidence_id
        == normalize_evidence(
            "get_credential_status", result.model_copy(update={"tool_call_id": UUID(int=8)})
        )[0].evidence_id
    )
