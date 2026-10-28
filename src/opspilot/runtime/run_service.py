import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from psycopg import Error as PsycopgError
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from opspilot.agent.budgets import Budget, BudgetLimits
from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.agent.graph import build_graph
from opspilot.agent.runtime import Runtime
from opspilot.agent.service import project, run_investigation
from opspilot.auth.context import AuthError, actor_id, optional_principal
from opspilot.auth.execution import execution_scope, persisted_worker
from opspilot.config import Settings
from opspilot.contracts.api import CancelRun, ClarificationAnswer, CreateRun, Decision
from opspilot.db.engine import create_engine
from opspilot.db.models_workflow import Action, AgentRun, Approval
from opspilot.llm.real import RealProvider
from opspilot.llm.scripted import ScriptedProvider
from opspilot.runtime.actions import Conflict
from opspilot.runtime.jobs import enqueue
from opspilot.security.tls import client_context
from opspilot.telemetry import carrier, span
from opspilot.tenancy.session import TenantSession as AsyncSession


class RunService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = create_engine(settings.database_url("workflow"))
        self.locks: dict[UUID, asyncio.Lock] = {}

    def lock(self, run_id: UUID) -> asyncio.Lock:
        return self.locks.setdefault(run_id, asyncio.Lock())

    async def clarify(self, run_id: UUID, body: ClarificationAnswer) -> dict[str, Any]:
        from opspilot.runtime.human_commands import answer

        await answer(self, run_id, body)
        return await self.snapshot(run_id)

    async def cancel(self, run_id: UUID, body: CancelRun) -> dict[str, Any]:
        from opspilot.runtime.human_commands import cancel

        await cancel(self, run_id, body)
        return await self.snapshot(run_id)

    async def create(self, body: CreateRun) -> dict[str, Any]:
        run_id = uuid4()
        result = await run_investigation(
            self.settings,
            body.request,
            client_request_id=body.client_request_id,
            run_id=run_id,
            queued_only=True,
        )
        return {
            "run_id": result["run_id"],
            "status": result["status"],
            "snapshot_url": f"/api/v2/runs/{result['run_id']}",
        }

    @persisted_worker
    async def execute(self, run_id: UUID, body: CreateRun) -> None:
        async with self.lock(run_id):
            try:
                async with AsyncSession(self.engine) as session:
                    run = await session.get(AgentRun, run_id)
                    if run is None:
                        raise LookupError("Run not found")
                    command = run.usage.get("command", {})
                    settings = self.settings.model_copy(
                        update={
                            "llm_mode": run.mode,
                            "scenario_id": run.scenario_id,
                            "scenario_clock": run.scenario_clock,
                            "openai_model": command.get("model", self.settings.openai_model),
                        }
                    )
                    limits = BudgetLimits.model_validate(command["limits"]) if command else None
                await run_investigation(
                    settings,
                    body.request,
                    limits=limits,
                    client_request_id=body.client_request_id,
                    run_id=run_id,
                )
            except (SQLAlchemyError, PsycopgError):
                raise
            except Exception:
                await self.fail(run_id)

    async def fail(self, run_id: UUID, code: str = "RUN_FAILED") -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id)
                .values(
                    status="needs_attention"
                    if code
                    in {
                        "RESTART_INTERRUPTED",
                        "UNSUPPORTED_WORKFLOW_VERSION",
                        "CHECKPOINT_UNSUPPORTED",
                    }
                    else "failed",
                    error={
                        "code": code,
                        "message": "Interrupted. Review the saved action before a new run.",
                    },
                )
            )

    async def snapshot(self, run_id: UUID) -> dict[str, Any]:
        async with AsyncSession(
            self.engine.execution_options(isolation_level="REPEATABLE READ")
        ) as session:
            run = await session.get(AgentRun, run_id)
            if run is None:
                raise LookupError("Run not found")
            stream = (
                await session.execute(
                    text("SELECT projection,sequence FROM workflow.run_streams WHERE run_id=:r"),
                    {"r": run_id},
                )
            ).one()
            public = dict(stream.projection)
            public.update(dto_version=1, snapshot_version=stream.sequence)
            public.update(
                schema_version=run.state_schema_version,
                actor_id=str(run.actor_id),
                run_id=str(run.id),
                status=run.status,
                clarification=run.clarification,
                cancellation=run.cancellation,
                error=run.error,
                request=run.request,
                language=run.language,
                mode=run.mode,
                outcome=run.outcome,
                trace_id=run.trace_id,
                created_at=run.created_at.isoformat().replace("+00:00", "Z"),
                updated_at=run.updated_at.isoformat().replace("+00:00", "Z"),
                report=public.get("final_report"),
                missing_checks=public.get("missing_checks") or [],
                timeline=public.get("timeline", []),
                hypotheses=public.get("hypotheses") or [],
                evidence=list((public.get("evidence") or {}).values()),
                usage={
                    "llm_calls": run.usage.get("llm_attempts", 0),
                    "read_calls": run.usage.get("read_attempts", 0),
                    "input_tokens": None
                    if run.usage.get("unknown_usage_count")
                    else run.usage.get("input_tokens"),
                    "output_tokens": None
                    if run.usage.get("unknown_usage_count")
                    else run.usage.get("output_tokens"),
                    "unknown_usage_count": run.usage.get("unknown_usage_count", 0),
                    "active_ms": round(run.usage.get("active_seconds", 0) * 1000),
                    "human_wait_ms": 0,
                },
            )
            rows = (
                await session.execute(
                    select(Action, Approval)
                    .join(Approval, Action.id == Approval.action_id)
                    .where(Action.run_id == run_id, Action.superseded_at.is_(None))
                )
            ).all()
            row = rows[0] if rows else None
            public["action"] = (
                None
                if row is None
                else {
                    "action_id": str(row.Action.id),
                    "tool_name": row.Action.tool_name,
                    "arguments": row.Action.arguments,
                    "arguments_hash": row.Action.arguments_hash,
                    "revision_hash": row.Action.revision_hash,
                    "logical_action_id": str(row.Action.logical_action_id),
                    "revision_id": str(row.Action.id),
                    "expected_version": row.Approval.version,
                    "expires_at": row.Approval.expires_at.isoformat(),
                    "approval_status": row.Approval.decision,
                    "execution_status": row.Action.execution_status,
                    "result": row.Action.execution_result,
                    "verification": public.get("verification_result") or {"status": "not_started"},
                }
            )
            if row is not None:
                end = row.Approval.decided_at or datetime.now(UTC)
                public["usage"]["human_wait_ms"] = max(
                    0, round((end - row.Approval.created_at).total_seconds() * 1000)
                )
            from opspilot.runtime.plans import projection

            public["plan"], public["actions"] = await projection(session, run_id)
            if public["plan"]:
                public["usage"]["verification_reads"] = public["plan"]["verification_reads"]
                public["usage"]["read_calls"] += public["plan"]["verification_reads"]
            if public["plan"] and public["actions"]:
                public["action"] = next(
                    (a for a in public["actions"] if a["approval_status"] == "pending"),
                    public["actions"][0],
                )
            public["traces"] = []
        available = False
        if self.settings.jaeger_url and public.get("trace_context"):
            try:
                async with httpx.AsyncClient(
                    timeout=0.3, trust_env=False, verify=client_context(self.settings)
                ) as client:
                    available = (
                        await client.get(self.settings.jaeger_query_url + "/api/services")
                    ).is_success
            except httpx.HTTPError:
                pass
        if available and self.settings.jaeger_url:
            for label, key in (
                ("Investigation", "trace_context"),
                ("Continuation", "continuation_context"),
            ):
                context = public.get(key)
                if context:
                    public["traces"].append(
                        {
                            "label": label,
                            "url": self.settings.jaeger_url.rstrip("/")
                            + "/trace/"
                            + context.split("-")[1],
                        }
                    )
        public.pop("trace_context", None)
        public.pop("continuation_context", None)
        return public

    async def decide(self, run_id: UUID, body: Decision) -> dict[str, Any]:
        from opspilot.auth.session_routes import require_recent

        if self.settings.security_profile == "hardened" and optional_principal() is None:
            raise AuthError("AUTHENTICATION_REQUIRED", 401)
        if optional_principal() is not None:
            require_recent(self.settings)
        async with self.lock(run_id):
            async with AsyncSession(self.engine) as session, session.begin():
                run = await session.scalar(
                    select(AgentRun).where(AgentRun.id == run_id).with_for_update()
                )
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
                from opspilot.security.revisions import valid_revision

                if row.Action.superseded_at or row.Approval.version != body.expected_version:
                    raise Conflict("Stale revision/version")
                if not valid_revision(row.Action):
                    raise Conflict("Revision digest mismatch")
                if not await session.scalar(
                    text("SELECT identity.lock_role(:u,:t,'approver')"),
                    {"u": actor_id(), "t": run.tenant_id},
                ):
                    raise AuthError()
                now = await session.scalar(select(func.clock_timestamp()))
                assert now is not None
                if row.Approval.decision in {"expired", "revoked", "superseded"}:
                    raise AuthError(
                        "APPROVAL_" + row.Approval.decision.upper(),
                        410 if row.Approval.decision == "expired" else 409,
                    )
                if now >= row.Approval.expires_at and row.Action.execution_status != "succeeded":
                    raise AuthError("APPROVAL_EXPIRED", 410)
                choice = "approved" if body.decision == "approve" else "rejected"
                if row.Approval.decision != "pending":
                    if row.Approval.decision != choice:
                        raise Conflict("Decision already recorded")
                    return await self.snapshot(run_id)
                if run.cancellation or run.status != "waiting_for_approval":
                    raise Conflict("Run is not waiting for approval")
                async with (
                    execution_scope(self.engine, run_id),
                    postgres_checkpointer(self.settings) as saver,
                ):
                    checkpoint = await saver.aget_tuple(
                        {"configurable": {"thread_id": run.thread_id}}
                    )
                    if checkpoint is None or not any(
                        item[1] == "__interrupt__" for item in (checkpoint.pending_writes or [])
                    ):
                        raise Conflict("Saved approval interrupt missing")
                actor = optional_principal()
                if actor is not None:
                    if "approver" not in actor.roles:
                        raise AuthError()
                    same = run.actor_id == actor.user_id
                    if same and not self.settings.allow_demo_self_approval:
                        raise AuthError("SELF_APPROVAL_FORBIDDEN")
                    row.Approval.decided_by = actor.user_id
                    row.Approval.self_approval_exception = same
                else:
                    # Explicit internal local-demo CLI/test actor; not a browser-supplied identity.
                    row.Approval.decided_by = actor_id()
                    same = run.actor_id == actor_id()
                    if same and not self.settings.allow_demo_self_approval:
                        raise AuthError("SELF_APPROVAL_FORBIDDEN")
                    row.Approval.self_approval_exception = same
                row.Approval.decision = choice
                row.Approval.decided_at = now
                await session.flush()
                from opspilot.runtime.plans import pending_wave

                if row.Action.plan_binding:
                    wave, actions, pending = await pending_wave(session, run_id)
                    if wave != row.Action.plan_binding["wave"] or body.action_id not in {
                        a.id for a in actions
                    }:
                        raise Conflict("Decision outside current approval wave")
                else:
                    pending = False
                run.status = "waiting_for_approval" if pending else "running"
                if not pending:
                    run.updated_at = datetime.now(UTC)
                    await enqueue(session, run_id, "resume", body.action_id)
        return await self.snapshot(run_id)

    @persisted_worker
    async def resume(
        self,
        run_id: UUID,
        action_id: UUID,
        *,
        continuation: bool = False,
        clarification: bool = False,
    ) -> None:
        async with self.lock(run_id):
            try:
                async with postgres_checkpointer(self.settings) as saver:
                    config: RunnableConfig = {"configurable": {"thread_id": str(run_id)}}
                    saved = await saver.aget_tuple(config)
                    if saved is None:
                        raise Conflict("Checkpoint missing")
                    values = saved.checkpoint["channel_values"]
                    if (
                        values.get("schema_version") != 1
                        or values.get("run_id") != str(run_id)
                        or values.get("thread_id") != str(run_id)
                        or values.get("mode") not in {"scripted", "real"}
                    ):
                        raise ValueError("Unsupported checkpoint binding")
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
                    runtime_settings = self.settings.model_copy(
                        update={
                            "llm_mode": values.get("mode", "scripted"),
                            "openai_model": values.get("model_id") or self.settings.openai_model,
                        }
                    )
                    provider = (
                        RealProvider(runtime_settings)
                        if runtime_settings.llm_mode == "real"
                        else ScriptedProvider()
                    )
                    runtime = Runtime(runtime_settings, provider, budget)
                    async with AsyncSession(self.engine) as session:
                        run = await session.get(AgentRun, run_id)
                        if (
                            run is None
                            or values.get("workflow_version", "full-graph-v1")
                            != run.workflow_version
                        ):
                            raise ValueError("Pinned workflow/checkpoint mismatch")
                        form = (run.clarification or {}) if run else {}
                        answer = {**form.get("answer", {}), "answered_at": form.get("answered_at")}
                        linked = run.public_snapshot.get("trace_context") if run else None
                    with span(
                        "graph.continuation",
                        linked=linked,
                        run_id=str(run_id),
                        action_id=str(action_id),
                    ):
                        continuation_context = carrier().get("traceparent")
                        state = await build_graph(
                            runtime, saver, version=run.workflow_version if run else "full-graph-v1"
                        ).ainvoke(
                            None
                            if continuation
                            else Command(
                                resume=answer if clarification else {"action_id": str(action_id)}
                            ),
                            config,
                        )
                    public = project(state)
                    public["trace_context"] = linked
                    public["continuation_context"] = continuation_context
                async with self.engine.begin() as conn:
                    await conn.execute(
                        update(AgentRun)
                        .where(AgentRun.id == run_id)
                        .values(
                            status=public["status"],
                            clarification=state.get("clarification"),
                            outcome=state.get("outcome"),
                            public_snapshot=public,
                            usage=state["budget"],
                            updated_at=datetime.now(UTC),
                        )
                    )
            except (ValueError, KeyError, TypeError):
                await self.fail(run_id, "CHECKPOINT_UNSUPPORTED")
            except (SQLAlchemyError, PsycopgError):
                raise
            except Exception:
                await self.fail(run_id)

    async def close(self) -> None:
        await self.engine.dispose()
