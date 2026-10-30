"""Bounded OTLP exporters. Telemetry failure never changes business authorization."""

import atexit
import base64
import collections
import ssl
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from google.protobuf.json_format import MessageToDict, ParseDict
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from opspilot.config import Settings
from opspilot.observability.protocol import METRICS, attributes, safe_attributes, sanitize

_runtime: "Telemetry | None" = None


class Telemetry:
    def __init__(self, settings: Settings, service: str) -> None:
        self.service = service
        self.instance = str(uuid.uuid4())
        self.lock = threading.RLock()
        self.counters: dict[tuple[str, str], float] = {}
        self.logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=256)
        self.last_success: dict[str, float] = {}
        self.last_failure: dict[str, float] = {}
        self.stop = threading.Event()
        self.endpoint = (settings.otel_endpoint or "").removesuffix("/v1/traces").rstrip("/")
        self.token = Path(settings.telemetry_token_file or "").read_text().strip()
        context = ssl.create_default_context(cafile=settings.telemetry_ca_file)
        context.load_cert_chain(settings.telemetry_cert_file or "", settings.telemetry_key_file)
        self.http = httpx.Client(
            verify=context,
            trust_env=False,
            timeout=0.3,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )
        self.thread = threading.Thread(target=self._loop, name="safe-telemetry", daemon=True)
        self.thread.start()

    def count(self, name: str, phase: str = "api", value: float = 1) -> None:
        if name not in METRICS:
            return
        labels = safe_attributes({"phase": phase}, metric=True)
        if not labels:
            return
        with self.lock:
            key = (name, phase)
            self.counters[key] = min(1e15, self.counters.get(key, 0) + max(0, min(value, 3600000)))

    def record(self, event: str, fields: dict[str, Any]) -> None:
        safe = safe_attributes({**fields, "event": event})
        context = trace.get_current_span().get_span_context()
        item = {
            "timeUnixNano": str(time.time_ns()),
            "severityNumber": 17 if event == "log.error" else 9,
            "attributes": attributes(safe),
        }
        if context.is_valid:
            item.update(
                traceId=base64.b64encode(context.trace_id.to_bytes(16, "big")).decode(),
                spanId=base64.b64encode(context.span_id.to_bytes(8, "big")).decode(),
            )
        with self.lock:
            if len(self.logs) == self.logs.maxlen:
                self.count("log_dropped", "logs")
            self.logs.append(item)

    def send(self, kind: str, message: Any) -> bool:
        clean, _ = sanitize(MessageToDict(message), kind, self.service)
        safe = ParseDict(clean, type(message)())
        try:
            response = self.http.post(
                self.endpoint + "/v1/" + kind,
                content=safe.SerializeToString(),
                headers={
                    "Content-Type": "application/x-protobuf",
                    "Authorization": "Bearer " + self.token,
                },
            )
            accepted = response.status_code == 200
        except (httpx.HTTPError, RuntimeError):
            accepted = False
        if accepted:
            self.last_success[kind] = time.time()
        else:
            self.last_failure[kind] = time.time()
            self.count("export_failures", kind)
        return accepted

    def flush(self) -> None:
        with self.lock:
            records = list(self.logs)[:32]
            values = list(self.counters.items())
        resource = {
            "attributes": attributes(
                {"service.name": self.service, "service.instance.id": self.instance}
            )
        }
        if records:
            message = ParseDict(
                {"resourceLogs": [{"resource": resource, "scopeLogs": [{"logRecords": records}]}]},
                ExportLogsServiceRequest(),
            )
            if self.send("logs", message):
                with self.lock:
                    acknowledged = {id(r) for r in records}
                    self.logs = collections.deque(
                        (r for r in self.logs if id(r) not in acknowledged), maxlen=256
                    )
        points = []
        for (name, phase), number in values:
            points.append(
                {
                    "name": "opspilot." + name,
                    "gauge": {
                        "dataPoints": [
                            {
                                "asDouble": number,
                                "timeUnixNano": str(time.time_ns()),
                                "attributes": attributes({"phase": phase}),
                            }
                        ]
                    },
                }
            )
        # Heartbeat is emitted even when no application event occurred.
        if not points:
            points = [
                {
                    "name": "opspilot.http_requests",
                    "gauge": {"dataPoints": [{"asDouble": 0, "timeUnixNano": str(time.time_ns())}]},
                }
            ]
        metrics = ParseDict(
            {"resourceMetrics": [{"resource": resource, "scopeMetrics": [{"metrics": points}]}]},
            ExportMetricsServiceRequest(),
        )
        self.send("metrics", metrics)

    def _loop(self) -> None:
        while not self.stop.wait(2):
            try:
                self.flush()
            except Exception:
                self.count("export_failures", "metrics")

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=1)
        self.http.close()

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "queued_logs": len(self.logs),
                "queue_limit": 256,
                "export_failures": sum(
                    v for (n, _), v in self.counters.items() if n == "export_failures"
                ),
                "dropped_logs": sum(v for (n, _), v in self.counters.items() if n == "log_dropped"),
                "last_success": dict(self.last_success),
                "degraded": any(
                    stamp > self.last_success.get(kind, 0)
                    for kind, stamp in self.last_failure.items()
                ),
            }


class SafeSpanExporter(SpanExporter):
    def export(self, spans: Any) -> SpanExportResult:
        if _runtime is None:
            return SpanExportResult.FAILURE
        return (
            SpanExportResult.SUCCESS
            if _runtime.send("traces", encode_spans(spans))
            else SpanExportResult.FAILURE
        )

    def shutdown(self) -> None:
        pass


def configure(settings: Settings, service: str) -> None:
    global _runtime
    if _runtime is not None or not settings.otel_endpoint:
        return
    _runtime = Telemetry(settings, service)
    atexit.register(_runtime.close)


def count(name: str, phase: str = "api", value: float = 1) -> None:
    if _runtime is not None:
        _runtime.count(name, phase, value)


def record(event: str, fields: dict[str, Any]) -> None:
    if _runtime is not None:
        _runtime.record(event, fields)


def local_status() -> dict[str, Any]:
    return (
        _runtime.status()
        if _runtime
        else {"configured": False, "queued_logs": 0, "export_failures": 0}
    )


async def query(
    settings: Settings, tenant: str, run: str | None = None, actor: str | None = None
) -> dict[str, Any]:
    if not settings.otel_endpoint:
        return {"available": False, "reason": "NOT_CONFIGURED"}
    context = ssl.create_default_context(cafile=settings.telemetry_ca_file)
    context.load_cert_chain(settings.telemetry_cert_file or "", settings.telemetry_key_file)
    token = await __import__("asyncio").to_thread(
        Path(settings.telemetry_token_file or "").read_text
    )
    endpoint = settings.otel_endpoint.removesuffix("/v1/traces").rstrip("/")
    try:
        async with httpx.AsyncClient(verify=context, trust_env=False, timeout=2.0) as http:
            response = await http.get(
                endpoint + "/internal/events",
                params={
                    "tenant": tenant,
                    **({"run": run} if run else {}),
                    **({"actor": actor} if actor else {}),
                },
                headers={"Authorization": "Bearer " + token.strip()},
            )
        if response.status_code != 200:
            reason = "COLLECTOR_REJECTED"
            if len(response.content) < 1024:
                try:
                    if response.json().get("reason") in {
                        "COLLECTOR_INTEGRITY_FAILED",
                        "COLLECTOR_BUSY",
                    }:
                        reason = response.json()["reason"]
                except ValueError:
                    pass
            return {"available": False, "reason": reason}
        if len(response.content) > 262144:
            return {"available": False, "reason": "COLLECTOR_RESPONSE_BOUND"}
        return {"available": True, **response.json()}
    except (httpx.HTTPError, ValueError):
        return {"available": False, "reason": "COLLECTOR_UNAVAILABLE"}
