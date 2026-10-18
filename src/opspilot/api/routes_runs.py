from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Request, Response

from opspilot.contracts.api import CreateRun, Decision
from opspilot.runtime.run_service import RunService

router = APIRouter(prefix="/api/v1/runs")


@router.post("", status_code=202)
async def create_run(body: CreateRun, request: Request) -> dict[str, Any]:
    return await cast(RunService, request.app.state.runs).create(body)


@router.get("/{run_id}")
async def get_run(run_id: UUID, request: Request) -> dict[str, Any]:
    return await cast(RunService, request.app.state.runs).snapshot(run_id)


@router.post("/{run_id}/decision", status_code=202)
async def decide(
    run_id: UUID, body: Decision, request: Request, response: Response
) -> dict[str, Any]:
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
