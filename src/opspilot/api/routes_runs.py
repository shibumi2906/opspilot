from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Request, Response

from opspilot.auth.context import AuthError, principal, require_role
from opspilot.contracts.api import CancelRun, ClarificationAnswer, CreateRun, Decision
from opspilot.contracts.public import public_snapshot
from opspilot.runtime.run_service import RunService

router = APIRouter(prefix="/api/v2/runs")


@router.post("", status_code=202)
async def create_run(body: CreateRun, request: Request) -> dict[str, Any]:
    require_role("operator")
    return await cast(RunService, request.app.state.runs).create(body)


@router.get("/{run_id}")
async def get_run(run_id: UUID, request: Request) -> dict[str, Any]:
    user = principal()
    if user.tenant_id is None or not user.roles & {"operator", "approver", "auditor"}:
        raise AuthError("NOT_FOUND", 404)
    value = await cast(RunService, request.app.state.runs).snapshot(run_id)
    if not ({"approver", "auditor"} & user.roles) and not (
        "operator" in user.roles and value["actor_id"] == str(user.user_id)
    ):
        raise AuthError("NOT_FOUND", 404)
    from opspilot.api.event_cursor import encode

    result = public_snapshot(value)
    result["latest_event_id"] = encode(request, run_id, value["snapshot_version"])
    return result


@router.post("/{run_id}/decision", status_code=202)
async def decide(
    run_id: UUID, body: Decision, request: Request, response: Response
) -> dict[str, Any]:
    require_role("approver")
    snapshot = await cast(RunService, request.app.state.runs).decide(run_id, body)
    if snapshot["status"] == "completed":
        response.status_code = 200
    return {
        "run_id": str(run_id),
        "action_id": str(body.action_id),
        "decision": body.decision,
        "status": snapshot["status"],
        "ticket_id": (snapshot.get("execution_result") or {}).get("ticket_id"),
    }


@router.post("/{run_id}/clarifications", status_code=202)
async def clarify(run_id: UUID, body: ClarificationAnswer, request: Request) -> dict[str, Any]:
    require_role("operator")
    return public_snapshot(await cast(RunService, request.app.state.runs).clarify(run_id, body))


@router.post("/{run_id}/cancel", status_code=202)
async def cancel(run_id: UUID, body: CancelRun, request: Request) -> dict[str, Any]:
    require_role("operator")
    return public_snapshot(await cast(RunService, request.app.state.runs).cancel(run_id, body))
