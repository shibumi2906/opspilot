"""Human revision and revocation commands; effects remain exclusively MCP-owned."""

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text

from opspilot.auth.context import AuthError, actor_id, require_role
from opspilot.auth.session_routes import require_recent
from opspilot.contracts.api import RevisionChange, RevokeApproval
from opspilot.contracts.public import public_snapshot
from opspilot.db.models_workflow import Action, AgentRun, Approval, LogicalAction
from opspilot.runtime.actions import Conflict, new_revision
from opspilot.runtime.fencing import execution_lease
from opspilot.runtime.jobs import enqueue
from opspilot.tenancy.session import TenantSession

router = APIRouter(prefix="/api/v2/actions")


@router.post("/{logical_id}/revisions", status_code=201)
async def revise(logical_id: UUID, body: RevisionChange, request: Request) -> dict[str, Any]:
    actor = require_role("operator")
    service = request.app.state.runs
    async with TenantSession(service.engine) as session:
        logical = await session.get(LogicalAction, logical_id)
        if logical is None:
            raise AuthError("NOT_FOUND", 404)
        run_id = logical.run_id
    async with execution_lease(service.engine, run_id, service.settings):
        async with TenantSession(service.engine) as session, session.begin():
            logical = await session.scalar(
                select(LogicalAction).where(LogicalAction.id == logical_id).with_for_update()
            )
            assert logical is not None
            run = await session.get(AgentRun, run_id)
            if run is None or run.actor_id != actor.user_id:
                raise AuthError("NOT_FOUND", 404)
            if not await session.scalar(
                text("SELECT identity.lock_role(:u,:t,'operator')"),
                {"u": actor.user_id, "t": actor.tenant_id},
            ):
                raise AuthError()
            old = await session.scalar(
                select(Action).where(Action.id == logical.current_revision_id).with_for_update()
            )
            assert old is not None
            arguments = body.arguments.model_dump(mode="json")
            if logical.version != body.expected_version:
                if logical.version == body.expected_version + 1 and old.arguments == arguments:
                    return public_snapshot(await service.snapshot(run_id))
                raise Conflict("Stale revision")
            if (
                old.execution_status != "not_started"
                or run.cancellation
                or run.status not in {"waiting_for_approval", "running"}
                or logical.version >= 10
            ):
                raise Conflict("Revision cannot change an executed/uncertain/closed intent")
            if (
                arguments["customer_id"] != old.arguments["customer_id"]
                or arguments["evidence_ids"] != old.arguments["evidence_ids"]
            ):
                raise AuthError("REVISION_SCOPE_FORBIDDEN")
            if arguments == old.arguments:
                return public_snapshot(await service.snapshot(run_id))
            approval = await session.scalar(
                select(Approval).where(Approval.action_id == old.id).with_for_update()
            )
            assert approval is not None
            if approval.decision not in {"pending", "approved"}:
                raise Conflict("Approval terminal")
            approval.decision = "superseded"
            old.superseded_at = await session.scalar(select(func.clock_timestamp()))
            await session.execute(
                text(
                    "UPDATE workflow.execution_grants SET revoked_at=clock_timestamp() WHERE "
                    "revision_id=:a AND tenant_id=identity.current_tenant() AND "
                    "revoked_at IS NULL"
                ),
                {"a": old.id},
            )
            logical.version += 1
            logical.current_revision_id = uuid4()
            await session.flush()
            await new_revision(session, logical, arguments, service.settings)
            run.status = "waiting_for_approval"
            await session.execute(
                text(
                    "UPDATE workflow.command_jobs SET "
                    "status='done',finished_at=clock_timestamp() "
                    "WHERE tenant_id=identity.current_tenant() AND run_id=:r AND "
                    "kind='resume' AND "
                    "status='pending'"
                ),
                {"r": run_id},
            )
    return public_snapshot(await service.snapshot(run_id))


@router.post("/{revision_id}/revoke")
async def revoke(revision_id: UUID, body: RevokeApproval, request: Request) -> dict[str, bool]:
    actor = require_role("approver")
    service = request.app.state.runs
    require_recent(service.settings)
    async with TenantSession(service.engine) as session:
        action = await session.get(Action, revision_id)
        if action is None:
            raise AuthError("NOT_FOUND", 404)
        run_id = action.run_id
    async with execution_lease(service.engine, run_id, service.settings):
        async with TenantSession(service.engine) as session, session.begin():
            action = await session.scalar(
                select(Action).where(Action.id == revision_id).with_for_update()
            )
            approval = await session.scalar(
                select(Approval).where(Approval.action_id == revision_id).with_for_update()
            )
            assert action and approval
            if not await session.scalar(
                text("SELECT identity.lock_role(:u,:t,'approver')"),
                {"u": actor_id(), "t": actor.tenant_id},
            ):
                raise AuthError()
            if (
                approval.version != body.expected_version
                or action.execution_status != "not_started"
                or action.superseded_at
            ):
                raise Conflict("Stale/committed revision")
            if approval.decision == "revoked":
                return {"ok": True}
            if approval.decision != "approved" or approval.decided_by != actor.user_id:
                raise AuthError()
            approval.decision = "revoked"
            await session.execute(
                text(
                    "UPDATE workflow.execution_grants SET revoked_at=clock_timestamp() WHERE "
                    "revision_id=:a AND tenant_id=identity.current_tenant() AND "
                    "revoked_at IS NULL"
                ),
                {"a": revision_id},
            )
            await enqueue(session, run_id, "resume", revision_id)
    return {"ok": True}
