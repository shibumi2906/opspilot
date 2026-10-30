"""Real cryptographic/storage and export boundaries; no provider network calls."""

import asyncio
import base64
import collections
import hashlib
import json
import threading
import time
from uuid import uuid4

import httpx
import pytest
from google.protobuf.json_format import ParseDict
from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from opspilot import telemetry
from opspilot.logging import safe_record
from opspilot.observability.client import Telemetry
from opspilot.observability.collector import create_app
from opspilot.observability.journal import IntegrityError, Journal
from opspilot.observability.protocol import safe_attributes, sanitize

SENTINEL = "F16_SECRET_PASSWORD_COOKIE_SQL_SENTINEL"


def trace_message(tenant=None, run=None):
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "password", "value": {"stringValue": SENTINEL}}]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": SENTINEL,
                                "traceId": base64.b64encode(bytes(range(16))).decode(),
                                "spanId": base64.b64encode(bytes(range(8))).decode(),
                                "startTimeUnixNano": str(time.time_ns() - 1000),
                                "endTimeUnixNano": str(time.time_ns()),
                                "events": [{"name": SENTINEL}],
                                "attributes": [
                                    {
                                        "key": "tenant_id",
                                        "value": {"stringValue": str(tenant or uuid4())},
                                    },
                                    {
                                        "key": "run_id",
                                        "value": {"stringValue": str(run or uuid4())},
                                    },
                                    {"key": "operation", "value": {"stringValue": SENTINEL}},
                                    {"key": "credential", "value": {"stringValue": SENTINEL}},
                                ],
                                "status": {"message": SENTINEL, "code": "STATUS_CODE_ERROR"},
                            }
                        ]
                    }
                ],
            }
        ]
    }


def test_double_redaction_and_schema_bounds():
    clean, rows = sanitize(trace_message(), "traces", "opspilot-api")
    assert SENTINEL not in json.dumps(clean) and SENTINEL not in json.dumps(rows)
    assert rows[0]["name"] == "external.unclassified" and rows[0]["status"] == 2
    wire = ParseDict(clean, ExportTraceServiceRequest()).SerializeToString()
    assert SENTINEL.encode() not in wire
    assert (
        safe_attributes({"status": {"secret": SENTINEL}, "worker_epoch": True, "run_id": SENTINEL})
        == {}
    )
    malformed = trace_message()
    malformed["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["spanId"] = "bad"
    assert sanitize(malformed, "traces", "opspilot-api")[1] == []


@pytest.mark.parametrize("change", ["body", "truncate", "seal", "rollback"])
def test_tamper_detected_and_never_reset(tmp_path, change):
    data = tmp_path / "data"
    seals = tmp_path / "seals"
    key = b"x" * 64
    journal = Journal(data, seals, key, limit=32)
    journal.append(
        [
            {"kind": "logs", "attributes": {"tenant_id": str(uuid4())}, "name": "log.info", "n": n}
            for n in range(3)
        ]
    )
    if change == "body":
        journal.db.execute("UPDATE events SET body='{}' WHERE seq=2")
        journal.db.commit()
    elif change == "truncate":
        journal.db.execute("DELETE FROM events WHERE seq=3")
        journal.db.commit()
    elif change == "seal":
        (seals / "head.json").write_text("{}")
    else:
        state = journal.state()
        state["seq"] = 1
        journal.db.execute("UPDATE state SET body=?", (json.dumps(state),))
        journal.db.commit()
    with pytest.raises(IntegrityError):
        journal.verify()
    with pytest.raises(IntegrityError):
        journal.append([{"name": "log.error"}])
    journal.close()
    with pytest.raises(IntegrityError):
        Journal(data, seals, key, limit=32)


def test_retention_restart_and_tenant_scope(tmp_path):
    tenant, foreign, run = map(str, (uuid4(), uuid4(), uuid4()))
    key = b"y" * 64
    data = tmp_path / "data"
    seals = tmp_path / "seals"
    journal = Journal(data, seals, key, limit=32)
    journal.append(
        [
            {
                "kind": "logs",
                "name": "log.info",
                "n": n,
                "attributes": {"tenant_id": tenant if n % 2 else foreign, "run_id": run},
            }
            for n in range(60)
        ]
    )
    assert journal.verify()["seq"] == 60
    assert journal.db.execute("SELECT count(*) FROM events").fetchone()[0] == 32
    assert journal.read(tenant, run)["retention_pruned"] == 28
    assert all(r["attributes"]["tenant_id"] == tenant for r in journal.read(tenant, run)["events"])
    journal.close()
    recovered = Journal(data, seals, key, limit=32)
    assert recovered.verify()["seq"] == 60
    assert recovered.read(str(uuid4()), run)["events"] == []
    recovered.close()


def test_clock_regression_quarantines(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "data", tmp_path / "seals", b"z" * 64, limit=32)
    journal.append([{"name": "log.info"}])
    stamp = journal.state()["stamp"]
    monkeypatch.setattr("opspilot.observability.journal.time.time", lambda: stamp - 10)
    with pytest.raises(IntegrityError):
        journal.append([{"name": "log.info"}])
    assert journal.failed


async def test_collector_auth_redaction_and_tamper_response(tmp_path):
    tenant, run = uuid4(), uuid4()
    token = "a" * 64
    journal = Journal(tmp_path / "data", tmp_path / "seals", b"k" * 64, limit=32)
    app = create_app(journal, {hashlib.sha256(token.encode()).hexdigest(): "opspilot-api"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://collector"
    ) as http:
        payload = ParseDict(
            trace_message(tenant, run), ExportTraceServiceRequest()
        ).SerializeToString()
        assert (await http.post("/v1/traces", content=payload)).status_code == 401
        http.headers.update({"Authorization": "Bearer " + token})
        assert (
            await http.post(
                "/v1/traces", content=payload, headers={"Content-Type": "application/x-protobuf"}
            )
        ).status_code == 200
        assert (
            await http.post(
                "/v1/traces",
                content=b"x" * 262145,
                headers={"Content-Type": "application/x-protobuf"},
            )
        ).status_code == 413
        result = await http.get("/internal/events", params={"tenant": str(tenant), "run": str(run)})
        assert result.status_code == 200 and result.json()["integrity"] == "verified"
        assert SENTINEL not in result.text
        assert (await http.get("/internal/events", params={"tenant": str(uuid4())})).json()[
            "events"
        ] == []
        invalid = await http.get("/internal/events", params={"tenant": SENTINEL})
        assert invalid.status_code == 400 and SENTINEL not in invalid.text
        journal.db.execute("UPDATE events SET body='{}'")
        journal.db.commit()
        result = await http.get("/internal/events", params={"tenant": str(tenant)})
        assert result.status_code == 503 and result.json()["reason"] == "COLLECTOR_INTEGRITY_FAILED"


def fake_exporter(transport):
    obj = Telemetry.__new__(Telemetry)
    obj.service = "opspilot-api"
    obj.instance = str(uuid4())
    obj.lock = threading.RLock()
    obj.counters = {}
    obj.logs = collections.deque(maxlen=256)
    obj.last_success = {}
    obj.last_failure = {}
    obj.endpoint = "https://collector"
    obj.token = "b" * 64
    obj.http = httpx.Client(transport=transport, timeout=0.3)
    return obj


def test_metrics_outage_and_bounded_log_fallback():
    failing = True
    requests = []

    def response(request):
        requests.append(request.content)
        return httpx.Response(503 if failing else 200)

    obj = fake_exporter(httpx.MockTransport(response))
    for _ in range(400):
        obj.record("log.error", {"password": SENTINEL})
    assert len(obj.logs) == 256 and obj.status()["dropped_logs"] == 144
    obj.flush()
    assert obj.status()["degraded"] and len(obj.logs) == 256
    assert all(SENTINEL.encode() not in body for body in requests)
    failing = False
    obj.flush()
    assert len(obj.logs) == 224 and not obj.status()["degraded"]
    obj.http.close()


def test_structured_logging_drops_exception_and_payload():
    output = safe_record(
        {
            "level": "ERROR",
            "message": SENTINEL,
            "exception": RuntimeError(SENTINEL),
            "extra": {"password": SENTINEL, "request_id": str(uuid4()), "reason": SENTINEL},
        }
    )
    assert SENTINEL not in json.dumps(output) and output["event"] == "log.error"
    assert "request_id" in output


async def test_sse_handshake_span_finishes_before_human_wait(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", lambda *args: provider.get_tracer("test"))
    sent = asyncio.Event()
    pause = asyncio.Event()

    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream")],
            }
        )
        sent.set()
        await pause.wait()

    async def send(message):
        pass

    task = asyncio.create_task(
        telemetry.TraceMiddleware(app, "http.api")({"type": "http", "headers": []}, None, send)
    )
    await asyncio.wait_for(sent.wait(), 1)
    assert not task.done()
    assert len(exporter.get_finished_spans()) == 1
    pause.set()
    await task
    assert len(exporter.get_finished_spans()) == 1
    provider.shutdown()


def test_alert_conditions_and_safe_security_reasons():
    from opspilot.api.routes_diagnostics import alerts
    from opspilot.observability.protocol import safe_attributes

    database = {
        "queue_age_seconds": 60,
        "expired_leases": 1,
        "dead_jobs": 1,
        "unknown_operations": 1,
        "auth_denials_60s": 5,
        "exhausted_budgets": 1,
    }
    codes = {
        a["code"]
        for a in alerts(
            database,
            {"available": False, "reason": "COLLECTOR_INTEGRITY_FAILED"},
            {"degraded": True},
        )
    }
    assert codes == {
        "QUEUE_AGE",
        "LEASE_EXPIRED",
        "DEAD_COMMAND",
        "UNKNOWN_OPERATION",
        "AUTH_DENIAL_BURST",
        "BUDGET_DENIAL",
        "COLLECTOR_INTEGRITY_FAILED",
        "TELEMETRY_EXPORT_FAILED",
    }
    assert (
        alerts({}, {"available": True, "services": {"opspilot-api": {"metrics_received_at": 1}}})[
            0
        ]["code"]
        == "TELEMETRY_METRICS_STALE"
    )
    fields = safe_attributes(
        {
            "security_event": "authorization_denied",
            "reason": "FORBIDDEN",
            "method": "POST",
            "endpoint_group": "api",
            "exception_class": "OperationalError",
            "password": SENTINEL,
        }
    )
    assert fields["reason"] == "FORBIDDEN" and fields["security_event"] == "authorization_denied"
    assert fields["exception_class"] == "OperationalError"
    assert SENTINEL not in json.dumps(fields)


def test_command_lineage_survives_bounded_sql_detail_window(tmp_path):
    tenant, run = str(uuid4()), str(uuid4())
    journal = Journal(tmp_path / "data", tmp_path / "seal", b"c" * 64)
    attrs = {"tenant_id": tenant, "run_id": run}
    journal.append(
        [{"name": "command.process", "attributes": attrs}]
        + [{"name": "db.operation", "attributes": attrs} for _ in range(127)]
    )
    result = journal.read(tenant, run, limit=10)
    assert len(result["events"]) == 10
    assert result["matching_retained_records"] == 128
    assert any(r["name"] == "command.process" for r in result["events"])
    assert journal.db.execute("SELECT count(*) FROM events").fetchone()[0] == 128
    journal.close()


@pytest.mark.parametrize("operation", ["append", "read"])
def test_external_writer_cannot_cross_verified_snapshot(tmp_path, monkeypatch, operation):
    import sqlite3

    tenant, run = str(uuid4()), str(uuid4())
    journal = Journal(tmp_path / "data", tmp_path / "seal", b"a" * 64)
    journal.append(
        [{"name": "command.process", "attributes": {"tenant_id": tenant, "run_id": run}}]
    )
    external = sqlite3.connect(tmp_path / "data/journal.db", timeout=0)
    verify = journal.verify
    checked = []

    def verified():
        result = verify()
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                external.execute("UPDATE events SET body='{}'")
                external.commit()
            checked.append(True)
        finally:
            external.rollback()
        return result

    monkeypatch.setattr(journal, "verify", verified)
    if operation == "append":
        journal.append([{"name": "log.info", "attributes": {"tenant_id": tenant}}])
    else:
        assert journal.read(tenant, run)["events"][0]["name"] == "command.process"
    assert checked
    external.close()
    journal.close()
