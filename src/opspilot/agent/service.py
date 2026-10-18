"""Create and execute checkpointed investigations; API schedules these under a run lock."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot.agent.budgets import Budget, BudgetLimits
from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.agent.graph import build_graph
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.db.models_workflow import AgentRun
from opspilot.llm.base import Provider
from opspilot.llm.real import RealProvider
from opspilot.llm.scripted import ScriptedProvider


class RunConflict(Exception):
    pass


def configured_limits(settings: Settings) -> BudgetLimits:
    return BudgetLimits(
        reads=settings.agent_max_reads,
        llm_attempts=settings.agent_max_llm_attempts,
        rounds=settings.agent_max_rounds,
        tokens=settings.agent_max_tokens,
        active_seconds=settings.agent_active_seconds,
    )


async def run_investigation(
    settings: Settings,
    request: str,
    *,
    mode: Literal["scripted", "real"] | None = None,
    client_request_id: UUID | None = None,
    provider: Provider | None = None,
    limits: BudgetLimits | None = None,
    run_id: UUID | None = None,
    queued_only: bool = False,
) -> dict[str, Any]:
    request = request.strip()
    if not 1 <= len(request) <= 4000:
        raise ValueError("Request must contain 1–4000 characters")
    mode = mode or settings.llm_mode
    limits = limits or configured_limits(settings)
    provider = provider or (RealProvider(settings) if mode == "real" else ScriptedProvider())
    client_request_id = client_request_id or uuid4()
    request_hash = hashlib.sha256(
        json.dumps(
            {
                "request": request,
                "mode": mode,
                "scenario_id": settings.scenario_id,
                "clock": settings.scenario_clock.isoformat(),
                "limits": limits.model_dump(),
                "model": settings.openai_model if mode == "real" else None,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    engine = create_engine(settings.database_url("workflow"))
    run_id = run_id or uuid4()
    try:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": client_request_id.int % (2**63 - 1)},
            )
            previous = await session.scalar(
                select(AgentRun).where(AgentRun.client_request_id == client_request_id)
            )
            if previous and previous.status == "queued" and previous.id == run_id:
                await session.execute(
                    update(AgentRun).where(AgentRun.id == run_id).values(status="running")
                )
            elif previous:
                if previous.request_hash != request_hash:
                    raise RunConflict(
                        "Request ID already exists with different input or unfinished run"
                    )
                return previous.public_snapshot or {
                    "run_id": str(previous.id),
                    "status": previous.status,
                }
            else:
                session.add(
                    AgentRun(
                        id=run_id,
                        client_request_id=client_request_id,
                        request=request,
                        request_hash=request_hash,
                        language="en",
                        status="queued" if queued_only else "running",
                        mode=mode,
                        scenario_id=settings.scenario_id,
                        scenario_clock=settings.scenario_clock,
                        thread_id=str(run_id),
                        state_schema_version=1,
                        public_snapshot={},
                        tool_results={},
                        usage={},
                    )
                )
        if queued_only:
            return {"run_id": str(run_id), "status": "queued"}
        initial: AgentState = {
            "schema_version": 1,
            "run_id": str(run_id),
            "thread_id": str(run_id),
            "client_request_id": str(client_request_id),
            "mode": mode,
            "model_id": settings.openai_model if mode == "real" else None,
            "request": request,
            "observations": {},
            "evidence": {},
            "tool_calls": {},
            "llm_calls": {},
            "errors": {},
            "hypotheses": [],
            "facts": [],
            "proposed_action": None,
            "outcome": None,
            "missing_checks": [],
        }
        try:
            async with postgres_checkpointer(settings) as saver:
                runtime = Runtime(settings, provider, Budget(limits))
                async with runtime.client.session() as (mcp_session, _):
                    await runtime.client.discover(mcp_session)
                graph = build_graph(runtime, saver)
                state = await graph.ainvoke(
                    initial,
                    {
                        "configurable": {"thread_id": str(run_id)},
                        "recursion_limit": limits.recursion_limit,
                    },
                )
            public = project(state)
            async with engine.begin() as connection:
                await connection.execute(
                    update(AgentRun)
                    .where(AgentRun.id == run_id)
                    .values(
                        status=public["status"],
                        outcome=state.get("outcome"),
                        language=state.get("language", "en"),
                        public_snapshot=public,
                        tool_results=state["observations"],
                        usage=state["budget"],
                        updated_at=datetime.now(UTC),
                    )
                )
            return public
        except Exception:
            async with engine.begin() as connection:
                await connection.execute(
                    update(AgentRun)
                    .where(AgentRun.id == run_id)
                    .values(
                        status="failed",
                        error={
                            "code": "RUN_FAILED",
                            "message": "Run failed; inspect local services",
                        },
                    )
                )
            raise RuntimeError(f"Run {run_id} failed; check service readiness") from None
    finally:
        await engine.dispose()


def project(state: dict[str, Any]) -> dict[str, Any]:
    public = {
        key: state.get(key)
        for key in (
            "schema_version",
            "run_id",
            "thread_id",
            "client_request_id",
            "mode",
            "model_id",
            "language",
            "candidates",
            "evidence",
            "hypotheses",
            "proposed_action",
            "policy_result",
            "budget",
            "errors",
            "outcome",
            "final_report",
            "action_id",
            "execution_result",
            "verification_result",
        )
    }
    public["status"] = "waiting_for_approval" if state.get("__interrupt__") else "completed"
    calls = list(state.get("tool_calls", {}).items())
    timeline: list[dict[str, Any]] = [
        {
            "id": key,
            "sequence": index,
            "node": "execute_reads",
            "type": "tool_call",
            "status": call["status"],
            "summary": call["name"],
            "started_at": call.get("started_at"),
            "duration_ms": call.get("duration_ms"),
        }
        for index, (key, call) in enumerate(calls[:100], 1)
    ]
    if state.get("action_id"):
        timeline.append(
            {
                "id": state["action_id"],
                "sequence": len(calls[:100]) + 1,
                "node": "approval",
                "type": "approval",
                "status": public["status"],
                "summary": "Human decision required"
                if state.get("__interrupt__")
                else "Decision processed",
                "started_at": None,
            }
        )
    public["timeline"] = timeline
    public["truncated"] = len(calls) > 100
    return public
