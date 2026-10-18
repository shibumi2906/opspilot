"""Bounded startup recovery. Call only after acquiring the process singleton lock."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot.agent.budgets import Budget, BudgetLimits
from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.agent.graph import build_graph
from opspilot.agent.runtime import Runtime
from opspilot.agent.service import project
from opspilot.db.models_workflow import Action, AgentRun, Approval
from opspilot.llm.scripted import ScriptedProvider
from opspilot.runtime.actions import payload_hash

if TYPE_CHECKING:
    from opspilot.runtime.run_service import RunService


async def recover(service: "RunService") -> None:
    async with AsyncSession(service.engine) as session:
        ids = list(
            await session.scalars(
                select(AgentRun.id).where(
                    AgentRun.status.in_(["queued", "running", "waiting_for_approval"])
                )
            )
        )
    async with postgres_checkpointer(service.settings) as saver:
        graph = build_graph(
            Runtime(service.settings, ScriptedProvider(), Budget(BudgetLimits())), saver
        )
        for run_id in ids:
            async with AsyncSession(service.engine) as session:
                run = await session.get(AgentRun, run_id)
                assert run is not None
                row = (
                    await session.execute(
                        select(Action, Approval)
                        .join(Approval, Approval.action_id == Action.id)
                        .where(Action.run_id == run_id)
                    )
                ).one_or_none()
            config: RunnableConfig = {"configurable": {"thread_id": str(run_id)}}
            saved = await graph.aget_state(config)
            values = saved.values
            valid = (
                row is not None
                and values.get("action_id") == str(row.Action.id)
                and row.Action.arguments == values.get("proposed_action")
                and row.Action.arguments_hash == payload_hash(row.Action.arguments)
            )
            interrupted = any(task.interrupts for task in saved.tasks)
            if valid and row is not None and interrupted:
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
                    service.spawn(service.resume(run_id, row.Action.id))
            elif (
                valid
                and row is not None
                and row.Approval.decision == "approved"
                and (row.Action.execution_status == "succeeded" and row.Action.execution_result)
                and set(saved.next) <= {"execute", "verify", "report"}
            ):
                service.spawn(service.resume(run_id, row.Action.id, continuation=True))
            elif valid and not saved.next and values.get("final_report"):
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
