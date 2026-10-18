from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from opspilot.config import Settings
from opspilot.contracts.common import ToolResult
from opspilot.contracts.tools import GetCustomerArgs
from opspilot.fixtures.loader import load_fixtures, monitoring_snapshot


def test_fixture_ids_and_references() -> None:
    fixtures = load_fixtures()
    assert (len(fixtures.customers), len(fixtures.incidents), len(fixtures.articles)) == (3, 10, 5)
    customer_ids = {c.id for c in fixtures.customers}
    assert len(customer_ids) == 3
    assert all(i.customer_id in customer_ids for i in fixtures.integrations + fixtures.incidents)
    assert {a.language for a in fixtures.articles} == {"ru", "en"}


def test_monitoring_uses_scenario_clock() -> None:
    clock = datetime(2026, 10, 18, 9, tzinfo=UTC)
    first = monitoring_snapshot(clock)
    assert first == monitoring_snapshot(clock)
    assert first["latest_success_at"] == clock - timedelta(minutes=40)
    assert first["credential_status"] == "expired"
    assert all(e["http_status"] == 401 for e in first["events"])
    assert monitoring_snapshot(clock + timedelta(days=2))["checked_at"] == clock + timedelta(days=2)


@pytest.mark.parametrize("token", ["", "password", "g" * 64])
def test_weak_or_nonhex_service_token_rejected(token: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mcp_service_token=token)


def test_settings_never_render_token() -> None:
    token = "a" * 64
    settings = Settings(_env_file=None, mcp_service_token=token)
    assert token not in repr(settings)


def test_naive_clock_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mcp_service_token="a" * 64, scenario_clock="2026-10-18T09:00:00")


def test_arguments_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GetCustomerArgs(customer_id=UUID(int=1), tenant_id="untrusted")


def test_error_result_cannot_contain_data() -> None:
    with pytest.raises(ValidationError):
        ToolResult(ok=False, observed_at=datetime.now(UTC), data={})
