"""Worker-owned checkpoint recovery for a claimed durable command."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select, text, update

from opspilot.agent.budgets import Budget, BudgetLimits
from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.agent.graph import build_graph
from opspilot.agent.runtime import Runtime
from opspilot.agent.service import project
from opspilot.auth.context import AuthError
from opspilot.auth.execution import execution_scope
from opspilot.db.models_workflow import Action, AgentRun, Approval
from opspilot.llm.scripted import ScriptedProvider
from opspilot.runtime.actions import payload_hash
from opspilot.runtime.fencing import execution_lease
from opspilot.tenancy.session import TenantSession as AsyncSession

if TYPE_CHECKING:
    from opspilot.runtime.run_service import RunService


async def recover(service: "RunService", only_run: UUID | None = None) -> None:
    async with AsyncSession(service.engine) as session:
        ids = list(
            await session.scalars(
                select(AgentRun.id).where(
                    AgentRun.status.in_(
                        ["queued", "running", "waiting_for_approval", "waiting_for_input"]
                    )
                )
            )
        )
    for run_id in ids:
        if only_run is not None and run_id != only_run:
            continue
        try:
            async with (
                execution_scope(service.engine, run_id),
                execution_lease(service.engine, run_id, service.settings),
                postgres_checkpointer(service.settings) as saver,
            ):
                async with service.engine.begin() as conn:
                    await conn.execute(text("SELECT workflow.record_recovery(:r)"), {"r": run_id})
                graph = build_graph(
                    Runtime(service.settings, ScriptedProvider(), Budget(BudgetLimits())), saver
                )
                async with AsyncSession(service.engine) as session:
                    run = await session.get(AgentRun, run_id)
                    assert run is not None
                    row = (
                        await session.execute(
                            select(Action, Approval)
                            .join(Approval, Approval.action_id == Action.id)
                            .where(Action.run_id == run_id, Action.superseded_at.is_(None))
                        )
                    ).one_or_none()
                config: RunnableConfig = {"configurable": {"thread_id": str(run_id)}}
                saved = await graph.aget_state(config)
                values = saved.values
                if values and (
                    values.get("schema_version") != 1
                    or values.get("run_id") != str(run_id)
                    or values.get("thread_id") != run.thread_id
                    or values.get("mode") not in {"scripted", "real"}
                ):
                    raise ValueError("Unsupported checkpoint binding")
                valid = (
                    row is not None
                    and (
                        values.get("action_id") == str(row.Action.id)
                        or await session_old_revision(
                            service, values.get("action_id"), row.Action.logical_action_id
                        )
                    )
                    and row.Action.arguments_hash == payload_hash(row.Action.arguments)
                )
                interrupted = any(task.interrupts for task in saved.tasks)
                if interrupted and values.get("clarification"):
                    form = run.clarification
                    checkpoint_form = values["clarification"]
                    if not form or form["id"] != checkpoint_form["id"]:
                        if form and checkpoint_form["version"] != form["version"] + 1:
                            raise ValueError("Clarification binding mismatch")
                        # The next interrupt checkpoint committed before its run projection.
                        form = checkpoint_form
                    if form.get("answer") or datetime.now(UTC) >= datetime.fromisoformat(
                        form["expires_at"]
                    ):
                        await service.resume(run_id, UUID(int=0), clarification=True)
                    else:
                        public = project({**values, "__interrupt__": True})
                        async with service.engine.begin() as conn:
                            await conn.execute(
                                update(AgentRun)
                                .where(AgentRun.id == run_id)
                                .values(
                                    status="waiting_for_input",
                                    clarification=form,
                                    public_snapshot=public,
                                    usage=values["budget"],
                                    updated_at=datetime.now(UTC),
                                )
                            )
                elif valid and row is not None and interrupted:
                    public = project({**values, "__interrupt__": True})
                    public["trace_context"] = run.public_snapshot.get("trace_context")
                    async with service.engine.begin() as conn:
                        await conn.execute(
                            update(AgentRun)
                            .where(AgentRun.id == run_id)
                            .values(
                                public_snapshot=public,
                                usage=values["budget"],
                                status="waiting_for_approval"
                                if row.Approval.decision == "pending"
                                else "running",
                                updated_at=datetime.now(UTC),
                            )
                        )
                    if row.Approval.decision != "pending":
                        await service.resume(run_id, row.Action.id)
                elif (
                    valid
                    and row is not None
                    and row.Approval.decision == "approved"
                    and (row.Action.execution_status == "succeeded" and row.Action.execution_result)
                    and set(saved.next) <= {"execute", "verify", "report"}
                ):
                    await service.resume(run_id, row.Action.id, continuation=True)
                elif row is None and saved.next and values.get("budget"):
                    # Resume the pinned graph from its persisted read/model boundary.
                    await service.resume(run_id, UUID(int=0), continuation=True)
                elif (valid or row is None) and not saved.next and values.get("final_report"):
                    public = project(values)
                    for key in ("trace_context", "continuation_context"):
                        public[key] = run.public_snapshot.get(key)
                    async with service.engine.begin() as conn:
                        await conn.execute(
                            update(AgentRun)
                            .where(AgentRun.id == run_id)
                            .values(
                                status="completed",
                                public_snapshot=public,
                                outcome=values["outcome"],
                                usage=values["budget"],
                                updated_at=datetime.now(UTC),
                            )
                        )
                else:
                    await service.fail(run_id, code="RESTART_INTERRUPTED")
        except (ValueError, KeyError, TypeError):
            async with execution_lease(service.engine, run_id, service.settings):
                await service.fail(run_id, "CHECKPOINT_UNSUPPORTED")
        except AuthError:
            await service.fail(run_id, "AUTHORIZATION_REVOKED")


async def session_old_revision(service: "RunService", value: str | None, logical: UUID) -> bool:
    if value is None:
        return False
    async with AsyncSession(service.engine) as session:
        old = await session.get(Action, UUID(value))
        return old is not None and old.logical_action_id == logical
