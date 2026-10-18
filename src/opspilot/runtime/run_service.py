import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot.agent.budgets import Budget, BudgetLimits
from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.agent.graph import build_graph
from opspilot.agent.runtime import Runtime
from opspilot.agent.service import project, run_investigation
from opspilot.config import Settings
from opspilot.contracts.api import CreateRun, Decision
from opspilot.db.engine import create_engine
from opspilot.db.models_workflow import Action, AgentRun, Approval
from opspilot.llm.scripted import ScriptedProvider
from opspilot.runtime.actions import Conflict


class RunService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = create_engine(settings.database_url("workflow"))
        self.locks: dict[UUID, asyncio.Lock] = {}
        self.tasks: set[asyncio.Task[None]] = set()

    def lock(self, run_id: UUID) -> asyncio.Lock:
        return self.locks.setdefault(run_id, asyncio.Lock())

    def spawn(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def create(self, body: CreateRun) -> dict[str, Any]:
        run_id = uuid4()
        result = await run_investigation(
            self.settings,
            body.request,
            client_request_id=body.client_request_id,
            run_id=run_id,
            queued_only=True,
        )
        if result["run_id"] == str(run_id):
            self.spawn(self.execute(run_id, body))
        return {
            "run_id": result["run_id"],
            "status": result["status"],
            "snapshot_url": f"/api/v1/runs/{result['run_id']}",
        }

    async def execute(self, run_id: UUID, body: CreateRun) -> None:
        async with self.lock(run_id):
            try:
                await run_investigation(
                    self.settings,
                    body.request,
                    client_request_id=body.client_request_id,
                    run_id=run_id,
                )
            except Exception:
                await self.fail(run_id)

    async def fail(self, run_id: UUID) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id)
                .values(status="failed", error={"code": "RUN_FAILED"})
            )

    async def snapshot(self, run_id: UUID) -> dict[str, Any]:
        async with AsyncSession(self.engine) as session:
            run = await session.get(AgentRun, run_id)
            if run is None:
                raise LookupError("Run not found")
            public = dict(run.public_snapshot)
            public.update(
                schema_version=run.state_schema_version,
                run_id=str(run.id),
                status=run.status,
                error=run.error,
                request=run.request,
                language=run.language,
                mode=run.mode,
                outcome=run.outcome,
                trace_id=run.trace_id,
                created_at=run.created_at.isoformat().replace("+00:00", "Z"),
                updated_at=run.updated_at.isoformat().replace("+00:00", "Z"),
                report=public.get("final_report"),
                timeline=public.get("timeline", []),
                hypotheses=public.get("hypotheses") or [],
                evidence=list((public.get("evidence") or {}).values()),
                usage={
                    "llm_calls": run.usage.get("llm_attempts", 0),
                    "read_calls": run.usage.get("read_attempts", 0),
                    "input_tokens": run.usage.get("input_tokens"),
                    "output_tokens": run.usage.get("output_tokens"),
                    "active_ms": round(run.usage.get("active_seconds", 0) * 1000),
                    "human_wait_ms": 0,
                },
            )
            row = (
                await session.execute(
                    select(Action, Approval)
                    .join(Approval, Action.id == Approval.action_id)
                    .where(Action.run_id == run_id)
                )
            ).one_or_none()
            public["action"] = (
                None
                if row is None
                else {
                    "action_id": str(row.Action.id),
                    "tool_name": row.Action.tool_name,
                    "arguments": row.Action.arguments,
                    "arguments_hash": row.Action.arguments_hash,
                    "approval_status": row.Approval.decision,
                    "execution_status": row.Action.execution_status,
                    "result": row.Action.execution_result,
                    "verification": {"status": "not_started"},
                }
            )
            if row is not None:
                end = row.Approval.decided_at or datetime.now(UTC)
                public["usage"]["human_wait_ms"] = max(
                    0, round((end - row.Approval.created_at).total_seconds() * 1000)
                )
            return public

    async def decide(self, run_id: UUID, body: Decision) -> dict[str, Any]:
        async with self.lock(run_id):
            async with AsyncSession(self.engine) as session, session.begin():
                run = await session.get(AgentRun, run_id)
                if run is None:
                    raise LookupError("Run not found")
                row = (
                    await session.execute(
                        select(Action, Approval)
                        .join(Approval, Action.id == Approval.action_id)
                        .where(Action.run_id == run_id, Action.id == body.action_id)
                        .with_for_update()
                    )
                ).one_or_none()
                if row is None:
                    if await session.get(Action, body.action_id) is None:
                        raise LookupError("Action not found")
                    raise Conflict("Action does not belong to run")
                choice = "approved" if body.decision == "approve" else "rejected"
                if row.Approval.decision != "pending":
                    if row.Approval.decision != choice:
                        raise Conflict("Decision already recorded")
                    return await self.snapshot(run_id)
                if run.status != "waiting_for_approval":
                    raise Conflict("Run is not waiting for approval")
                async with postgres_checkpointer(self.settings) as saver:
                    checkpoint = await saver.aget_tuple(
                        {"configurable": {"thread_id": run.thread_id}}
                    )
                    if checkpoint is None or not any(
                        item[1] == "__interrupt__" for item in (checkpoint.pending_writes or [])
                    ):
                        raise Conflict("Saved approval interrupt missing")
                row.Approval.decision = choice
                row.Approval.decided_at = datetime.now(UTC)
                run.status = "running"
                run.updated_at = datetime.now(UTC)
            self.spawn(self.resume(run_id, body.action_id))
        return await self.snapshot(run_id)

    async def resume(self, run_id: UUID, action_id: UUID) -> None:
        async with self.lock(run_id):
            try:
                async with postgres_checkpointer(self.settings) as saver:
                    config: RunnableConfig = {"configurable": {"thread_id": str(run_id)}}
                    saved = await saver.aget_tuple(config)
                    if saved is None:
                        raise Conflict("Checkpoint missing")
                    values = saved.checkpoint["channel_values"]
                    counters = values["budget"]
                    budget = Budget(BudgetLimits.model_validate(counters["limits"]))
                    for key in (
                        "rounds",
                        "read_attempts",
                        "llm_attempts",
                        "input_tokens",
                        "output_tokens",
                        "unknown_usage_count",
                    ):
                        setattr(budget, key, counters[key])
                    budget.started -= counters["active_seconds"]
                    runtime = Runtime(self.settings, ScriptedProvider(), budget)
                    state = await build_graph(runtime, saver).ainvoke(
                        Command(resume={"action_id": str(action_id)}), config
                    )
                    public = project(state)
                async with self.engine.begin() as conn:
                    await conn.execute(
                        update(AgentRun)
                        .where(AgentRun.id == run_id)
                        .values(
                            status=public["status"],
                            outcome=state.get("outcome"),
                            public_snapshot=public,
                            usage=state["budget"],
                            updated_at=datetime.now(UTC),
                        )
                    )
            except Exception:
                await self.fail(run_id)

    async def close(self) -> None:
        if self.tasks:
            await asyncio.gather(*self.tasks)
        await self.engine.dispose()
