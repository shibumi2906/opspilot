from uuid import UUID

from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.db.engine import create_engine
from opspilot.db.models_workflow import Action, Approval
from opspilot.runtime.actions import Conflict, payload_hash, prepare


async def prepare_approval(state: AgentState, runtime: Runtime) -> None:
    engine = create_engine(runtime.settings.database_url("workflow"))
    try:
        async with AsyncSession(engine) as session, session.begin():
            action = await prepare(session, UUID(state["run_id"]), state["proposed_action"] or {})
            state["action_id"] = str(action.id)
            state["outcome"] = None
    finally:
        await engine.dispose()


async def approval(state: AgentState, runtime: Runtime) -> None:
    reference = interrupt({"action_id": state["action_id"]})
    if reference != {"action_id": state["action_id"]}:
        raise Conflict("Invalid resume reference")
    engine = create_engine(runtime.settings.database_url("workflow"))
    try:
        async with AsyncSession(engine) as session:
            row = (
                await session.execute(
                    select(Action, Approval)
                    .join(Approval, Approval.action_id == Action.id)
                    .where(
                        Action.id == UUID(state["action_id"]),
                        Action.run_id == UUID(state["run_id"]),
                    )
                )
            ).one_or_none()
            if row is None or row.Approval.decision == "pending":
                raise Conflict("No persisted decision")
            if row.Action.arguments != state[
                "proposed_action"
            ] or row.Action.arguments_hash != payload_hash(row.Action.arguments):
                raise Conflict("Action payload differs")
            state["outcome"] = "rejected" if row.Approval.decision == "rejected" else None
    finally:
        await engine.dispose()


async def execute(state: AgentState, runtime: Runtime) -> None:
    state["errors"]["execute"] = {"code": "execution_not_implemented", "node": "execute"}
    state["outcome"] = "partial"
