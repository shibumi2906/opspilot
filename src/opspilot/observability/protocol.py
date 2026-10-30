"""F16 OTLP subset: positive schema, bounded values, no arbitrary payload fields."""

import base64
import math
from typing import Any
from uuid import UUID

SERVICES = {"opspilot-api", "opspilot-worker", "opspilot-mcp", "opspilot-probe"}
NAMES = {
    "http.api",
    "http.mcp.server",
    "graph.investigation",
    "graph.continuation",
    "mcp.client.tool",
    "mcp.server.tool",
    "db.operation",
    "llm.request",
    "command.process",
    "command.enqueue",
    "lease.heartbeat",
    "adapter.call",
    "verification.read",
    "reconciliation.check",
    "graph.node",
}
NODES = {
    "prepare_approval",
    "execute_reads",
    "risk_check",
    "classify",
    "resolve",
    "investigate",
    "reason",
    "plan",
    "approval",
    "execute",
    "verify",
    "report",
    "clarify",
    "plan_step",
    "plan_wait",
    "plan_report",
    "retrieve",
    "resolve_customer",
    "gather",
}
EVENTS = {
    "log.info",
    "log.warning",
    "log.error",
    "log.unclassified",
    "security.denied",
    "tool.failed",
    "worker.database_unavailable",
    "proxy.error",
    "telemetry.export_failed",
}
METRICS = {
    "http_requests",
    "http_duration_ms",
    "job_claims",
    "job_duration_ms",
    "lease_losses",
    "llm_attempts",
    "mcp_calls",
    "upstream_errors",
    "budget_denials",
    "auth_denials",
    "export_failures",
    "export_dropped",
    "log_dropped",
    "operation_duration_ms",
}
PHASES = {
    "api",
    "jobs",
    "llm",
    "mcp",
    "verification",
    "reconciliation",
    "traces",
    "metrics",
    "logs",
    "database",
    "security",
    "source",
}
CODES = {
    "OPERATION_INTERRUPTED",
    "RUN_FAILED",
    "TOOL_FAILED",
    "PROVIDER_UNAVAILABLE",
    "BUDGET_EXCEEDED",
    "RATE_LIMITED",
    "APPROVAL_REQUIRED",
    "INVALID_SERVICE_CONTEXT",
    "FORBIDDEN",
    "AUTHENTICATION_REQUIRED",
    "MONITORING_TIMEOUT",
    "COMMAND_RETRY",
    "COMMAND_DEAD_LETTER",
    "CHECKPOINT_UNSUPPORTED",
    "STALE_EXECUTION",
    "UNKNOWN_OUTCOME",
    "PROVIDER_RATE_LIMITED",
    "PRECONDITIONS_CHANGED",
    "UNCLASSIFIED_ERROR",
    "VALIDATION_ERROR",
    "INTERNAL_ERROR",
    "RUN_ADMISSION_LIMIT",
    "METHOD_NOT_ALLOWED",
    "HEADERS_TOO_LARGE",
    "BODY_TOO_LARGE",
    "INVALID_CONTENT_TYPE",
    "INVALID_SESSION",
    "SESSION_EXPIRED",
    "CSRF_INVALID",
    "TENANT_REQUIRED",
    "ACTOR_REVOKED",
    "NOT_FOUND",
    "INVALID_ORIGIN",
    "HTTP_TIMEOUT",
}
UUID_KEYS = {"run_id", "tenant_id", "actor_id", "action_id", "job_id", "request_id"}
INTEGER_KEYS = {
    "worker_epoch",
    "input_tokens",
    "output_tokens",
    "unknown_usage_count",
    "http_status",
    "attempt",
    "duration_ms",
}
TOOL_NAMES = {
    "find_customers",
    "get_customer",
    "get_service_status",
    "get_integration_events",
    "search_incidents",
    "search_documentation",
    "get_ticket",
    "get_ticket_comment",
    "get_notification",
    "create_ticket",
    "add_ticket_comment",
    "notify_manager",
}


def safe_attributes(values: dict[str, Any], *, metric: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in list(values.items())[:64]:
        if metric and key not in {"phase", "status", "tool_name", "error_code"}:
            continue
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            continue
        if key in UUID_KEYS:
            try:
                result[key] = str(UUID(str(value)))
            except (ValueError, TypeError, AttributeError):
                pass
        elif key in INTEGER_KEYS and type(value) is int and 0 <= value <= 1000000000:
            result[key] = value
        elif (
            key == "active_seconds" and type(value) in (int, float) and math.isfinite(float(value))
        ):
            result[key] = min(3600, max(0, value))
        elif key == "exception_class" and value in {
            "TimeoutError",
            "ConnectionError",
            "OSError",
            "ValueError",
            "RuntimeError",
            "SQLAlchemyError",
            "OperationalError",
            "IntegrityError",
            "HTTPError",
            "ReadTimeout",
            "ConnectTimeout",
            "ConnectError",
            "SSLError",
        }:
            result[key] = value
        elif key in {"error_code", "reason"} and value in CODES:
            result[key] = value
        elif key == "security_event" and value in {
            "authentication_denied",
            "authorization_denied",
            "service_authentication_denied",
            "write_authorization_denied",
            "validation_denied",
            "http_admission_denied",
            "run_admission_denied",
            "login_denied",
            "unexpected_error",
            "tenant_selected",
            "logout",
            "login",
            "membership_changed",
        }:
            result[key] = value
        elif key == "method" and value in {
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "HEAD",
            "OPTIONS",
            "TRACE",
            "OTHER",
        }:
            result[key] = value
        elif key == "endpoint_group" and value in {"api", "auth", "other"}:
            result[key] = value
        elif key == "diagnostic_code" and value in {
            "AUDIT_DATABASE_UNAVAILABLE",
            "WORKER_DATABASE_UNAVAILABLE",
            "TOOL_FAILED",
        }:
            result[key] = value
        elif key == "phase" and value in PHASES:
            result[key] = value
        elif key == "status" and value in {
            "ok",
            "error",
            "denied",
            "unknown",
            "retry",
            "queued",
            "running",
            "waiting_for_approval",
            "waiting_for_input",
            "completed",
            "failed",
            "cancelled",
            "needs_attention",
            "pending",
            "done",
            "dead",
        }:
            result[key] = value
        elif key == "tool_name" and value in TOOL_NAMES:
            result[key] = value
        elif key == "operation" and value in {
            "classify",
            "investigate",
            "reason",
            "plan",
            "start",
            "resume",
        }:
            result[key] = value
        elif key == "event" and value in EVENTS:
            result[key] = value
    return result


def attributes(values: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "value": {
                (
                    "intValue"
                    if type(value) is int
                    else "doubleValue"
                    if type(value) is float
                    else "stringValue"
                ): str(value) if type(value) is int else value
            },
        }
        for key, value in values.items()
    ]


def decode_attributes(values: Any) -> dict[str, Any]:
    if not isinstance(values, list):
        return {}
    result = {}
    for entry in values[:64]:
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
            continue
        value = entry.get("value", {})
        if not isinstance(value, dict):
            continue
        if "stringValue" in value:
            result[entry["key"]] = value["stringValue"]
        elif "intValue" in value:
            try:
                result[entry["key"]] = int(value["intValue"])
            except (ValueError, TypeError):
                pass
        elif "doubleValue" in value and type(value["doubleValue"]) in (int, float):
            result[entry["key"]] = value["doubleValue"]
    return result


def hex_id(value: Any, length: int) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError:
        return None
    return raw.hex() if len(raw) == length and any(raw) else None


def sanitize(
    payload: dict[str, Any], kind: str, service: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Both before client export and at authenticated ingress. Unknown fields are discarded."""
    group = {"traces": "resourceSpans", "metrics": "resourceMetrics", "logs": "resourceLogs"}[kind]
    scope = {"traces": "scopeSpans", "metrics": "scopeMetrics", "logs": "scopeLogs"}[kind]
    field = {"traces": "spans", "metrics": "metrics", "logs": "logRecords"}[kind]
    clean: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for resource in payload.get(group, [])[:8]:
        for section in resource.get(scope, [])[:8]:
            for item in section.get(field, [])[:128]:
                if len(clean) >= 128:
                    break
                attrs = safe_attributes(
                    decode_attributes(item.get("attributes", [])), metric=kind == "metrics"
                )
                row: dict[str, Any] = {"service": service, "kind": kind, "attributes": attrs}
                if kind == "traces":
                    trace_id = hex_id(item.get("traceId"), 16)
                    span_id = hex_id(item.get("spanId"), 8)
                    if not trace_id or not span_id:
                        continue
                    name = item.get("name")
                    if name not in NAMES and name not in {"graph.node." + n for n in NODES}:
                        name = "external.unclassified"
                    start = int(item.get("startTimeUnixNano", 0))
                    end = int(item.get("endTimeUnixNano", 0))
                    if start <= 0 or end < start or end - start > 3600 * 1000000000:
                        continue
                    links = []
                    for link in item.get("links", [])[:8]:
                        if hex_id(link.get("traceId"), 16) and hex_id(link.get("spanId"), 8):
                            links.append({"traceId": link["traceId"], "spanId": link["spanId"]})
                    value = {
                        "name": name,
                        "traceId": item["traceId"],
                        "spanId": item["spanId"],
                        "startTimeUnixNano": str(start),
                        "endTimeUnixNano": str(end),
                        "attributes": attributes(attrs),
                        "links": links,
                        "status": {
                            "code": 2
                            if item.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR")
                            else 1
                        },
                    }
                    if hex_id(item.get("parentSpanId"), 8):
                        value["parentSpanId"] = item["parentSpanId"]
                    row.update(
                        name=name,
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=hex_id(item.get("parentSpanId"), 8),
                        links=[
                            {
                                "trace_id": hex_id(x["traceId"], 16),
                                "span_id": hex_id(x["spanId"], 8),
                            }
                            for x in links
                        ],
                        start_ns=start,
                        end_ns=end,
                        status=value["status"]["code"],
                    )
                elif kind == "logs":
                    event = attrs.get("event", "log.unclassified")
                    value = {
                        "timeUnixNano": str(int(item.get("timeUnixNano", 0))),
                        "severityNumber": 17
                        if str(item.get("severityNumber", "")).endswith("ERROR")
                        else 9,
                        "body": {"stringValue": event},
                        "attributes": attributes(attrs),
                    }
                    for key, length in (("traceId", 16), ("spanId", 8)):
                        if hex_id(item.get(key), length):
                            value[key] = item[key]
                    row.update(
                        name=event,
                        trace_id=hex_id(item.get("traceId"), 16),
                        source_timestamp_ns=int(item.get("timeUnixNano", 0)),
                    )
                else:
                    name = item.get("name", "").removeprefix("opspilot.")
                    if name not in METRICS:
                        continue
                    points = item.get("sum", item.get("gauge", {})).get("dataPoints", [])[:32]
                    safe_points = []
                    numeric = []
                    for point in points:
                        number = float(point.get("asInt", point.get("asDouble", 0)))
                        if not math.isfinite(number) or not 0 <= number <= 1e15:
                            continue
                        labels = safe_attributes(
                            decode_attributes(point.get("attributes", [])), metric=True
                        )
                        safe_points.append(
                            {
                                "asDouble": number,
                                "timeUnixNano": str(int(point.get("timeUnixNano", 0))),
                                "attributes": attributes(labels),
                            }
                        )
                        numeric.append({"value": number, "labels": labels})
                    value = {"name": "opspilot." + name, "gauge": {"dataPoints": safe_points}}
                    row.update(name=name, points=numeric)
                clean.append(value)
                records.append(row)
    output = {
        group: [
            {
                "resource": {"attributes": attributes({"service.name": service})},
                scope: [{field: clean}],
            }
        ]
    }
    return output, records
