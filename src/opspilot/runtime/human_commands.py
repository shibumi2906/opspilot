"""Human commands share database serialization with dispatch and committed local effects."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select, text, update

from opspilot.auth.context import AuthError, actor_id, optional_principal
from opspilot.config import Settings
from opspilot.contracts.api import CancelRun, ClarificationAnswer
from opspilot.db.engine import create_engine
from opspilot.db.models_workflow import Action, AgentRun
from opspilot.runtime.actions import Conflict
from opspilot.runtime.fencing import current_engine, current_fence
from opspilot.runtime.jobs import enqueue
from opspilot.tenancy.session import TenantSession

if TYPE_CHECKING:
    from opspilot.runtime.run_service import RunService


class RunCancelled(Exception):
    pass


async def check_cancelled(settings: Settings) -> None:
    fence = current_fence()
    if fence is None:
        return
    owned_engine = current_engine()
    engine = owned_engine or create_engine(settings.database_url("workflow"))
    try:
        async with TenantSession(engine) as session:
            run = await session.get(AgentRun, fence.run)
            if run and run.cancellation:
                raise RunCancelled()
    finally:
        if owned_engine is None:
            await engine.dispose()


async def lock_run(session: TenantSession, run_id: UUID) -> AgentRun:
    # Same lock order as MCP local writes and execution projections.
    await session.execute(
        text("SELECT run_id FROM workflow.run_execution_leases WHERE run_id=:r FOR UPDATE"),
        {"r": run_id},
    )
    run = await session.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
    if run is None:
        raise LookupError("Run not found")
    user = optional_principal()
    if user and ("operator" not in user.roles or run.actor_id != actor_id()):
        raise AuthError("NOT_FOUND", 404)
    return run


async def command_replay(
    session: TenantSession, run_id: UUID, body: ClarificationAnswer | CancelRun
) -> bool:
    payload = body.model_dump(mode="json")
    saved = await session.scalar(
        text("SELECT payload FROM workflow.human_commands WHERE run_id=:r AND command_id=:c"),
        {"r": run_id, "c": body.command_id},
    )
    if saved is not None:
        if saved != payload:
            raise Conflict("Command key already used")
        return True
    await session.execute(
        text(
            "INSERT INTO workflow.human_commands(run_id,command_id,payload) "
            "VALUES(:r,:c,CAST(:p AS jsonb))"
        ),
        {"r": run_id, "c": body.command_id, "p": json.dumps(payload)},
    )
    return False


async def answer(service: "RunService", run_id: UUID, body: ClarificationAnswer) -> None:
    async with TenantSession(service.engine) as session, session.begin():
        run = await lock_run(session, run_id)
        if await command_replay(session, run_id, body):
            return
        form = run.clarification
        if (
            not form
            or form["id"] != str(body.clarification_id)
            or form["version"] != body.expected_version
        ):
            raise Conflict("Stale clarification")
        now = await session.scalar(text("SELECT clock_timestamp()"))
        assert isinstance(now, datetime)
        value = {"kind": body.kind, "choice": body.choice}
        if form.get("answer"):
            if form["answer"] == value and form["command_id"] == str(body.command_id):
                return
            raise Conflict("Answer already recorded")
        if (
            run.cancellation
            or run.status != "waiting_for_input"
            or now >= datetime.fromisoformat(form["expires_at"])
        ):
            raise Conflict("Clarification is closed")
        if body.kind != form["kind"] or body.choice not in {o["id"] for o in form["options"]}:
            raise Conflict("Choice is not allowed")
        run.clarification = {
            **form,
            "answer": value,
            "command_id": str(body.command_id),
            "answered_at": now.isoformat(),
        }
        run.status = "queued"
        await session.flush()
        await enqueue(session, run_id, f"clarify{form['version']}")


async def cancel(service: "RunService", run_id: UUID, body: CancelRun) -> None:
    async with TenantSession(service.engine) as session, session.begin():
        run = await lock_run(session, run_id)
        if await command_replay(session, run_id, body):
            return
        if run.cancellation:
            if run.cancellation["command_id"] == str(body.command_id):
                return
            raise Conflict("Cancellation already requested")
        if run.status in {"completed", "cancelled", "failed", "needs_attention"}:
            raise Conflict("Run is terminal")
        run.status = "cancelling"
        run.cancellation = {
            "command_id": str(body.command_id),
            "requested_at": datetime.now(UTC).isoformat(),
        }
        await session.flush()
        await enqueue(session, run_id, "cancel")


async def finalize_cancel(service: "RunService", run_id: UUID) -> bool:
    async with TenantSession(service.engine) as session, session.begin():
        run = await session.get(AgentRun, run_id)
        if run is None or not run.cancellation:
            return False
        actions = list(await session.scalars(select(Action).where(Action.run_id == run_id)))
        effects: list[dict[str, Any]] = [
            {"action_id": str(a.id), "status": a.execution_status, "result": a.execution_result}
            for a in actions
            if a.execution_status != "not_started"
        ]
        ru = run.language == "ru"
        report: dict[str, Any] = {
            "summary": "Выполнение отменено; выполненные действия сохранены."
            if ru
            else "Run cancelled; completed effects are preserved.",
            "action_summary": "; ".join(
                f"{item['action_id']}: {item['status']}"
                + (f"; ticket {item['result']['ticket_id']}" if item["result"] else "")
                for item in effects
            )
            if effects
            else ("Записи не выполнены." if ru else "No writes were performed."),
            "outcome": "cancelled",
            "facts": [],
            "hypotheses": [],
            "missing_checks": [],
            "verification_status": (run.public_snapshot.get("verification_result") or {}).get(
                "status", "not_started"
            ),
            "effects": effects,
            "cancelled_actions": [
                str(a.id) for a in actions if a.execution_status == "not_started"
            ],
            "remaining_problem": "Review completed effects; remaining work was cancelled.",
            "ticket_id": next(
                (a.execution_result.get("ticket_id") for a in actions if a.execution_result), None
            ),
        }
        public = {
            **run.public_snapshot,
            "status": "cancelled",
            "outcome": "cancelled",
            "final_report": report,
        }
        await session.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status="cancelled",
                outcome="cancelled",
                public_snapshot=public,
                updated_at=datetime.now(UTC),
            )
        )
        return True


async def expire(service: "RunService") -> None:
    async with TenantSession(service.engine) as session, session.begin():
        runs = list(
            await session.scalars(
                select(AgentRun)
                .where(
                    AgentRun.status == "waiting_for_input",
                    AgentRun.cancellation.is_(None),
                    text("(clarification->>'expires_at')::timestamptz<=clock_timestamp()"),
                )
                .order_by(AgentRun.id)
                .limit(100)
            )
        )
        for run in runs:
            form = run.clarification
            if form and datetime.now(UTC) >= datetime.fromisoformat(form["expires_at"]):
                await enqueue(session, run.id, f"clarify{form['version']}")
