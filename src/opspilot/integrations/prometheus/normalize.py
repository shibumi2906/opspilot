"""Typed metric evidence; absent/stale/partial data never becomes healthy or an outage claim."""

import math
from datetime import UTC, datetime
from typing import Any
from uuid import uuid5

from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.prometheus.registry import Registration
from opspilot.integrations.prometheus.transport import METRIC

MAX_POINTS = 121
FRESH_SECONDS = 120


def _number(value: object, *, string: bool) -> float:
    if (string and not isinstance(value, str)) or (
        not string and (not isinstance(value, int | float) or isinstance(value, bool))
    ):
        raise ValueError()
    result = float(value)  # type: ignore[arg-type]
    if not math.isfinite(result):
        raise ValueError()
    return result


def _rows(
    reg: Registration, body: dict[str, Any], now: float, window: tuple[datetime, datetime] | None
) -> dict[tuple[str, str], dict[int, float]]:
    data = body["data"]
    expected = "matrix" if window else "vector"
    if not isinstance(data, dict) or data.get("resultType") != expected:
        raise ValueError()
    rows = data.get("result")
    if not isinstance(rows, list) or len(rows) > 16:
        raise ValueError()
    result: dict[tuple[str, str], dict[int, float]] = {}
    required = {
        "job": "opspilot",
        "tenant_id": str(reg.tenant_id),
        "customer_id": str(reg.customer_id),
        "integration_id": str(reg.integration_id),
    }
    allowed = {*required, "__name__", "instance", "opspilot_target", "opspilot_measure"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"metric", "values" if window else "value"}:
            raise ValueError()
        labels = row["metric"]
        if not isinstance(labels, dict) or not set(labels).issubset(allowed):
            raise ValueError()
        if any(labels.get(key) != value for key, value in required.items()):
            raise ValueError()
        if labels.get("__name__", METRIC) != METRIC:
            raise ValueError()
        if any(not isinstance(v, str) or len(v) > 200 for v in labels.values()):
            raise ValueError()
        target, measure = labels.get("opspilot_target"), labels.get("opspilot_measure")
        if target not in reg.targets or measure not in {"health", "sample_time"}:
            raise ValueError()
        key = (target, measure)
        if key in result:
            raise ValueError()
        points = row["values"] if window else [row["value"]]
        if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
            raise ValueError()
        parsed: dict[int, float] = {}
        previous = -1
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError()
            at = _number(point[0], string=False)
            milliseconds = round(at * 1000)
            value = _number(point[1], string=True)
            if milliseconds <= previous or (measure == "health" and value not in {0, 0.5, 1}):
                raise ValueError()
            if window:
                if not window[0].timestamp() - 0.002 <= at < window[1].timestamp() + 0.002:
                    raise ValueError()
            elif abs(at - now) > 0.01:
                raise ValueError()
            parsed[milliseconds] = value
            previous = milliseconds
        result[key] = parsed
    return result


def normalize(
    reg: Registration,
    body: dict[str, Any],
    now: float,
    window: tuple[datetime, datetime] | None = None,
    *,
    step: int = 0,
) -> dict[str, Any]:
    try:
        if body.get("status") != "success" or body.get("warnings") or body.get("infos"):
            raise ValueError()
        rows = _rows(reg, body, now, window)
        result: dict[str, Any] = {
            "status": "unknown",
            "latest_success_at": None,
            "checked_at": datetime.fromtimestamp(now, UTC),
            "credential_status": "unknown",
            "events": [],
            "source_version": reg.source_version(),
        }
        if window is None:
            current = round(now * 1000)
            health_values, sample_times = [], []
            for target in reg.targets:
                value = rows.get((target, "health"), {}).get(current)
                stamp = rows.get((target, "sample_time"), {}).get(current)
                if value is None or stamp is None or not -5 <= now - stamp <= FRESH_SECONDS:
                    return result
                health_values.append(value)
                sample_times.append(stamp)
            result["status"] = (
                "healthy"
                if all(v == 1 for v in health_values)
                else "unavailable"
                if any(v == 0 for v in health_values)
                else "degraded"
            )
            if result["status"] == "healthy":
                # This is a proven recent healthy observation, not an unbounded historical search.
                result["latest_success_at"] = datetime.fromtimestamp(min(sample_times), UTC)
            return result
        if not 15 <= step <= 5040:
            raise ValueError()
        start, end = (value.timestamp() for value in window)
        expected = min(MAX_POINTS, math.floor((end - start - 0.001) / step) + 1)
        prefix = "Synthetic" if reg.dataset == "synthetic" else "Observed"
        events: dict[str, dict[str, Any]] = {}
        for target in reg.targets:
            values = rows.get((target, "health"), {})
            times = rows.get((target, "sample_time"), {})
            partial = len(values) < expected or set(values) != set(times)
            for evaluation, value in values.items():
                stamp = times.get(evaluation)
                if stamp is None or not -5 <= evaluation / 1000 - stamp <= FRESH_SECONDS:
                    partial = True
                    continue
                if not start <= stamp < end:
                    continue
                status = {0: "unavailable", 0.5: "degraded", 1: "healthy"}[value]
                event = str(uuid5(reg.connector_id, f"prometheus1:{target}:{stamp:.3f}:{status}"))
                events[event] = {
                    "event_id": event,
                    "occurred_at": datetime.fromtimestamp(stamp, UTC),
                    "http_status": None,
                    "event_type": "prometheus.metric.sample",
                    "summary": f"{prefix} Prometheus health sample: {status}; target {target}",
                }
            if not values or partial:
                reason = "absent" if not values else "partial_or_stale"
                event = str(uuid5(reg.connector_id, f"prometheus1:{target}:{start}:{end}:{reason}"))
                events[event] = {
                    "event_id": event,
                    "occurred_at": datetime.fromtimestamp(end - 0.001, UTC),
                    "http_status": None,
                    "event_type": "prometheus.metric." + reason,
                    "summary": (
                        f"{prefix} scoped metric {reason}; health unknown, not proof of outage"
                    ),
                }
        result["events"] = sorted(
            events.values(),
            key=lambda value: (value["occurred_at"], value["event_id"]),
            reverse=True,
        )
        return result
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ConnectorUnavailable() from None
