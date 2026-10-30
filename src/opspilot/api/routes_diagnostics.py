"""Scoped live operator views; telemetry never authorizes a business mutation."""

import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import text

from opspilot.auth.context import AuthError, principal
from opspilot.observability.client import local_status, query

router = APIRouter(prefix="/api/v2")


def alerts(
    database: dict[str, Any], collector: dict[str, Any], exporter: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    result = []
    for name, metric, threshold in (
        ("QUEUE_AGE", "queue_age_seconds", 60),
        ("LEASE_EXPIRED", "expired_leases", 1),
        ("DEAD_COMMAND", "dead_jobs", 1),
        ("UNKNOWN_OPERATION", "unknown_operations", 1),
        ("AUTH_DENIAL_BURST", "auth_denials_60s", 5),
        ("BUDGET_DENIAL", "exhausted_budgets", 1),
    ):
        value = database.get(metric, 0) or 0
        if value >= threshold:
            result.append(
                {"code": name, "severity": "warning", "observed": value, "threshold": threshold}
            )
    if not collector.get("available"):
        result.append(
            {
                "code": collector.get("reason", "COLLECTOR_UNAVAILABLE"),
                "severity": "error",
                "threshold": 1,
                "observed": 1,
            }
        )
    else:
        if any(e.get("source_clock_skew") for e in collector.get("events", [])):
            result.append(
                {
                    "code": "SOURCE_CLOCK_SKEW",
                    "severity": "warning",
                    "threshold": 30,
                    "observed": True,
                }
            )
        if collector.get("counters", {}).get("rate_denials", 0):
            result.append(
                {
                    "code": "TELEMETRY_RATE_LIMIT",
                    "severity": "warning",
                    "observed": collector["counters"]["rate_denials"],
                    "threshold": 1,
                }
            )
    if exporter and exporter.get("degraded"):
        result.append(
            {
                "code": "TELEMETRY_EXPORT_FAILED",
                "severity": "warning",
                "threshold": 1,
                "observed": 1,
            }
        )
    if collector.get("available"):
        if any(
            time.time() - s.get("metrics_received_at", 0) > 10
            for name, s in collector.get("services", {}).items()
            if name != "opspilot-probe"
        ):
            result.append(
                {
                    "code": "TELEMETRY_METRICS_STALE",
                    "severity": "warning",
                    "threshold": 10,
                    "observed": True,
                }
            )
    return result


async def view(request: Request, run: UUID | None) -> dict[str, Any]:
    user = principal()
    if user.tenant_id is None or not user.roles & {"operator", "admin", "auditor"}:
        raise AuthError()
    async with request.app.state.engine.connect() as conn:
        data = await conn.scalar(text("SELECT workflow.operator_diagnostics(:r)"), {"r": run})
    if data is None:
        raise AuthError("NOT_FOUND", 404)
    collector = await query(
        request.app.state.runs.settings,
        str(user.tenant_id),
        str(run) if run else None,
        data.pop("scope_actor_id", None),
    )
    # Per-tenant business aggregates come from the live scoped DB view.
    # Do not expose other tenants' process-wide business counters.
    for service in collector.get("services", {}).values():
        service.pop("metrics", None)
    events = collector.get("events", [])
    retained = {
        "record_count": len(events),
        "upstream_errors": sum(
            e.get("status") == 2
            and e.get("name")
            in {"mcp.client.tool", "mcp.server.tool", "llm.request", "adapter.call"}
            for e in events
        ),
        "llm_attempts": sum(e.get("name") == "llm.request" for e in events),
        "mcp_calls": sum(e.get("name") == "mcp.client.tool" for e in events),
        "window": (
            "Bounded authorized workflow/security records first; "
            "DB/HTTP fill remaining slots; incomplete during outage"
        ),
    }
    exporter = local_status()
    return {
        "schema_version": 1,
        "scope": {"tenant_id": str(user.tenant_id), "run_id": str(run) if run else None},
        "database": data,
        "collector": collector,
        "exporter": exporter,
        "retained_metrics": retained,
        "alerts": alerts(data, collector, exporter),
        "thresholds_are_project_conditions": True,
    }


@router.get("/diagnostics")
async def dashboard(request: Request) -> dict[str, Any]:
    return await view(request, None)


@router.get("/runs/{run_id}/diagnostics")
async def run_diagnostics(run_id: UUID, request: Request) -> dict[str, Any]:
    return await view(request, run_id)
