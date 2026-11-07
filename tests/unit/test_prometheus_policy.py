"""Pure contract cases; actual Prometheus/TLS tests live in the dedicated F19 lab."""

import copy
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from opspilot.agent.evidence import canonical_facts
from opspilot.config import Settings
from opspilot.integrations.contracts import ConfigChange
from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.prometheus.normalize import normalize
from opspilot.integrations.prometheus.registry import Registration, registration
from opspilot.integrations.prometheus.transport import _query, decode, expression
from opspilot.integrations.secrets import prometheus_authorization
from tests.f18_cases import CASES

NOW = 1794000000.0


@pytest.fixture
def reg(tmp_path):
    ca = tmp_path / "ca.crt"
    ca.write_text("test CA")
    return Registration(
        **CASES[0],
        origin="https://prometheus:8443",
        addresses=("10.245.24.10",),
        ca_file=str(ca),
        targets=("primary", "replica"),
        deployment="fixture",
        dataset="synthetic",
        allow_private=True,
        authorization_ref="local F19 fixture",
    )


def envelope(reg, *, window=False):
    rows = []
    for target in reg.targets:
        for measure in ("health", "sample_time"):
            labels = {
                "job": "opspilot",
                "tenant_id": str(reg.tenant_id),
                "customer_id": str(reg.customer_id),
                "integration_id": str(reg.integration_id),
                "opspilot_target": target,
                "opspilot_measure": measure,
            }
            points = [[NOW, "1" if measure == "health" else str(NOW - 1)]]
            rows.append(
                {"metric": labels, "values" if window else "value": points if window else points[0]}
            )
    return {
        "status": "success",
        "data": {"resultType": "matrix" if window else "vector", "result": rows},
    }


@pytest.mark.parametrize(
    "value,status", [("1", "healthy"), ("0.5", "degraded"), ("0", "unavailable")]
)
def test_status_and_expiration_unknown(reg, value, status):
    body = envelope(reg)
    body["data"]["result"][0]["value"][1] = value
    observed = normalize(reg, body, NOW)
    assert observed["status"] == status
    assert observed["credential_status"] == "unknown"
    assert observed["source_version"] == "prometheus-mapping1:synthetic:fixture"
    assert (observed["latest_success_at"] is not None) == (status == "healthy")


@pytest.mark.parametrize("case", ["absent", "partial", "stale", "future_sample"])
def test_missing_or_old_samples_never_become_healthy(reg, case):
    body = envelope(reg)
    if case == "absent":
        body["data"]["result"] = []
    elif case == "partial":
        body["data"]["result"].pop()
    else:
        body["data"]["result"][1]["value"][1] = str(NOW - 121 if case == "stale" else NOW + 6)
    assert normalize(reg, body, NOW)["status"] == "unknown"


@pytest.mark.parametrize(
    "case",
    [
        "warnings",
        "infos",
        "foreign_tenant",
        "foreign_customer",
        "foreign_integration",
        "extra_label",
        "target",
        "duplicate",
        "cardinality",
        "nan",
        "bool_time",
        "bad_health",
        "wrong_time",
        "scalar",
        "error",
    ],
)
def test_invalid_or_partial_envelopes_fail_closed(reg, case):
    body = envelope(reg)
    row = body["data"]["result"][0]
    if case in {"warnings", "infos"}:
        body[case] = ["partial data"]
    elif case.startswith("foreign_"):
        row["metric"][case.removeprefix("foreign_") + "_id"] = str(UUID(int=999999))
    elif case == "extra_label":
        row["metric"]["unexpected"] = "value"
    elif case == "target":
        row["metric"]["opspilot_target"] = "unregistered"
    elif case in {"duplicate", "cardinality"}:
        body["data"]["result"] += [copy.deepcopy(row)] * (1 if case == "duplicate" else 17)
    elif case in {"nan", "bad_health"}:
        row["value"][1] = "NaN" if case == "nan" else "2"
    elif case in {"bool_time", "wrong_time"}:
        row["value"][0] = True if case == "bool_time" else NOW - 1
    elif case == "scalar":
        body["data"]["resultType"] = "scalar"
    else:
        body["status"] = "error"
    with pytest.raises(ConnectorUnavailable):
        normalize(reg, body, NOW)


def test_range_is_sample_evidence_not_business_event(reg):
    body = envelope(reg, window=True)
    window = (datetime.fromtimestamp(NOW - 2, UTC), datetime.fromtimestamp(NOW + 1, UTC))
    result = normalize(reg, body, NOW, window, step=15)
    assert len(result["events"]) == 2
    assert all(e["event_type"] == "prometheus.metric.sample" for e in result["events"])
    assert all(
        e["summary"].startswith("Synthetic Prometheus health sample") for e in result["events"]
    )
    assert normalize(reg, body, NOW, window, step=15) == result
    body["data"]["result"] = []
    absent = normalize(reg, body, NOW, window, step=15)
    assert len(absent["events"]) == 2
    assert all("unknown" in e["summary"] for e in absent["events"])


@pytest.mark.parametrize("case", ["oversized", "unsorted", "outside", "missing_pair"])
def test_range_contract(reg, case):
    body = envelope(reg, window=True)
    point = body["data"]["result"][0]["values"][0]
    if case == "oversized":
        body["data"]["result"][0]["values"] *= 122
    elif case == "unsorted":
        body["data"]["result"][0]["values"].append(point)
    elif case == "outside":
        point[0] = NOW + 2
    else:
        body["data"]["result"].pop()
    window = (datetime.fromtimestamp(NOW - 2, UTC), datetime.fromtimestamp(NOW + 1, UTC))
    if case == "missing_pair":
        result = normalize(reg, body, NOW, window, step=15)
        assert any(e["event_type"].endswith("partial_or_stale") for e in result["events"])
    else:
        with pytest.raises(ConnectorUnavailable):
            normalize(reg, body, NOW, window, step=15)


@pytest.mark.parametrize("raw", [b'{"status":"success","status":"error"}', b'{"data":NaN}', b"[]"])
def test_strict_json(raw):
    with pytest.raises(ValueError):
        decode(raw)


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "169.254.169.254", "0.0.0.0", "224.0.0.1", "::1", "::ffff:127.0.0.1"]
)
def test_registration_rejects_unsafe_addresses(reg, address):
    with pytest.raises(ValidationError):
        Registration.model_validate({**reg.model_dump(), "addresses": [address]})


def test_registry_scope_mapping_and_production(reg, tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps([reg.model_dump(mode="json")]))
    settings = Settings(prometheus_registry_file=str(path))
    assert registration(settings, reg.tenant_id, reg.connector_id) == reg
    assert expression(reg).count(str(reg.tenant_id)) == 2
    assert "up{" not in expression(reg)
    assert reg.mapping_hash() != reg.model_copy(update={"targets": ("primary",)}).mapping_hash()
    with pytest.raises(ConnectorUnavailable):
        registration(settings, UUID(int=1), reg.connector_id)
    with pytest.raises(ConnectorUnavailable):
        registration(
            settings.model_copy(update={"app_env": "production"}), reg.tenant_id, reg.connector_id
        )


@pytest.mark.parametrize("days,future", [(8, 0), (-1, 0), (1, 60)])
def test_range_bounds_before_network(reg, days, future):
    end = datetime.fromtimestamp(NOW + future, UTC)
    with pytest.raises(ConnectorUnavailable):
        _query(reg, "redacted", NOW, (end - timedelta(days=days), end))


def test_no_ingress_for_prometheus(reg):
    with pytest.raises(ValidationError):
        ConfigChange(
            kind="prometheus",
            expected_version=0,
            customer_id=reg.customer_id,
            integration_id=reg.integration_id,
            origin=reg.origin,
            read_enabled=True,
            ingress_enabled=True,
        )


@pytest.mark.parametrize("attack", ["duplicate_key", "duplicate_identity", "query_field"])
def test_operator_registry_is_unambiguous(reg, tmp_path, attack):
    value = [reg.model_dump(mode="json")]
    if attack == "duplicate_identity":
        value *= 2
    elif attack == "query_field":
        value[0]["query"] = "up"
    raw = json.dumps(value)
    if attack == "duplicate_key":
        raw = raw.replace('"deployment": "fixture"', '"deployment":"live","deployment":"fixture"')
    path = tmp_path / "registry.json"
    path.write_text(raw)
    with pytest.raises(ConnectorUnavailable):
        registration(Settings(prometheus_registry_file=str(path)), reg.tenant_id, reg.connector_id)


@pytest.mark.parametrize(
    "scheme,override",
    [
        ("basic", {"tenant_id": "foreign"}),
        ("basic", {"connector_id": "foreign"}),
        ("basic", {"username": "name:injection"}),
        ("basic", {"password": "a" * 32 + "\r\nHeader: bad"}),
        ("basic", {"password": "short"}),
        ("bearer", {"token": "a" * 32 + "\nHeader"}),
        ("bearer", {"token": "short"}),
        ("unknown", {}),
    ],
)
async def test_credential_metadata_and_header_injection_fail_closed(
    reg, monkeypatch, scheme, override
):
    async def read_record(*args):
        return {
            "tenant_id": str(reg.tenant_id),
            "connector_id": str(reg.connector_id),
            "username": "reader",
            "password": "a" * 64,
            "token": "b" * 64,
            **override,
        }

    monkeypatch.setattr("opspilot.integrations.secrets.read", read_record)
    with pytest.raises(ConnectorUnavailable):
        await prometheus_authorization(Settings(), reg.tenant_id, reg.connector_id, scheme)


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("dataset,deployment", [("synthetic", "fixture"), ("observed", "staging")])
def test_metric_facts_preserve_provenance_and_never_invent_delivery(language, dataset, deployment):
    version = f"prometheus-mapping1:{dataset}:{deployment}"
    summary = (
        "Synthetic" if dataset == "synthetic" else "Observed"
    ) + " Prometheus health sample: degraded"
    state = {
        "language": language,
        "evidence": {
            "status": {
                "source_type": "integration_status",
                "source_version": version,
                "facts": {"status": "degraded"},
            },
            "sample": {
                "source_type": "integration_event",
                "source_version": version,
                "facts": {
                    "event_type": "prometheus.metric.sample",
                    "summary": summary,
                    "http_status": None,
                },
            },
        },
    }
    facts = canonical_facts(state)
    assert facts[1]["statement"] == summary
    assert all(
        "Delivery event" not in f["statement"] and "Событие доставки" not in f["statement"]
        for f in facts
    )
    if dataset == "synthetic":
        assert facts[0]["statement"].startswith(
            "Synthetic" if language == "en" else "Синтетические"
        )


def test_legacy_delivery_fact_format_stays_compatible():
    facts = canonical_facts(
        {
            "language": "en",
            "evidence": {
                "delivery": {
                    "source_type": "integration_event",
                    "source_version": None,
                    "facts": {"http_status": 401},
                },
            },
        }
    )
    assert facts[0]["statement"] == "Delivery event: 401"
