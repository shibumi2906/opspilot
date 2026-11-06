import ipaddress
from uuid import uuid4

import pytest
from pydantic import ValidationError

from opspilot.integrations.contracts import CAPABILITIES, ConfigChange, Health
from opspilot.integrations.egress import ConnectorUnavailable, origin, validate_addresses


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "https://user:secret@example.com",
        "https://example.com/",
        "https://example.com/x",
        "https://example.com?secret=x",
        "https://example.com#x",
        "https://example.com:80",
        "https://example.com.:443",
        "https://[::1]",
        "https://EXAMPLE.com",
        "https://example.com\\@127.0.0.1",
        "https://example.com:99999",
    ],
)
def test_origin_rejects_ambiguous_or_unregistered_shape(value):
    with pytest.raises(ConnectorUnavailable):
        origin(value)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "0.0.0.0",
        "10.1.2.3",
        "172.16.1.2",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:8.8.8.8",
        "224.0.0.1",
    ],
)
def test_all_dns_answers_must_be_public_without_simulator_exception(address):
    with pytest.raises(ConnectorUnavailable):
        validate_addresses(["8.8.8.8", address])


def test_simulator_exception_pins_exact_address_and_rejects_rebinding():
    assert validate_addresses(["10.245.18.10"], simulator_ip="10.245.18.10") == ["10.245.18.10"]
    with pytest.raises(ConnectorUnavailable):
        validate_addresses(["10.245.18.10", "10.245.18.11"], simulator_ip="10.245.18.10")
    with pytest.raises(ConnectorUnavailable):
        validate_addresses([])
    assert all(ipaddress.ip_address(x).is_global for x in validate_addresses(["8.8.8.8"]))


def test_contract_mapping_is_deterministic_and_has_no_write_capability():
    config = ConfigChange(
        expected_version=0,
        customer_id=uuid4(),
        integration_id=uuid4(),
        origin="https://adapter-simulator:8443",
    )
    assert config.mapping_hash() == config.model_copy(update={"read_enabled": True}).mapping_hash()
    assert (
        config.mapping_hash() != config.model_copy(update={"customer_id": uuid4()}).mapping_hash()
    )
    assert CAPABILITIES["simulator"]["external_write"] is False
    with pytest.raises(ValidationError):
        ConfigChange(**config.model_dump(), credential="F18_SECRET_SENTINEL")
    with pytest.raises(ValidationError):
        Health.model_validate_json('{"status":"healthy","source":"live"}')


async def test_transport_timeouts_keep_actual_threads_bounded():
    import asyncio
    from threading import Event

    from opspilot.integrations.executor import bounded

    release = Event()
    try:
        attempts = [asyncio.create_task(bounded(release.wait, budget=0.03)) for _ in range(4)]
        results = await asyncio.gather(*attempts, return_exceptions=True)
        assert all(isinstance(result, TimeoutError) for result in results)
        with pytest.raises(TimeoutError):
            await bounded(lambda: None, budget=0.03)
    finally:
        release.set()
        # Threads complete independently of the cancelled waiters.
        await asyncio.sleep(0.05)
    assert await bounded(lambda: "recovered", budget=1) == "recovered"


def test_worker_configuration_needs_no_business_or_manager_identity(monkeypatch):
    from opspilot.integrations.worker_settings import IngressWorkerSettings

    for name in (
        "MCP_SERVICE_TOKEN",
        "WORKFLOW_DATABASE_URL",
        "DOMAIN_DATABASE_URL",
        "CHECKPOINT_DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "CONNECTOR_MANAGER_TOKEN_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = IngressWorkerSettings(
        ingress_database_url="postgresql+psycopg://ops_ingress@postgres/opspilot_full_test"
    )
    assert "mcp_service_token" not in IngressWorkerSettings.model_fields
    assert "domain_database_url" not in IngressWorkerSettings.model_fields
    assert settings.database_url().startswith("postgresql+psycopg://ops_ingress@")
    with pytest.raises(ValidationError):
        IngressWorkerSettings(
            ingress_database_url="postgresql+psycopg://ops_domain@postgres/opspilot_full_test"
        )
    with pytest.raises(ValidationError):
        IngressWorkerSettings(
            app_env="production",
            security_profile="hardened",
            ingress_database_url="postgresql+psycopg://ops_ingress@postgres/opspilot_full",
        )
