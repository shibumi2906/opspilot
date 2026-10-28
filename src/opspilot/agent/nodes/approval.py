from uuid import UUID

from langgraph.types import interrupt
from sqlalchemy import select

from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.db.engine import create_engine
from opspilot.db.models_workflow import Action, Approval, LogicalAction
from opspilot.runtime.actions import Conflict, payload_hash, prepare
from opspilot.tenancy.session import TenantSession as AsyncSession


async def prepare_approval(state: AgentState, runtime: Runtime) -> None:
    if state.get("proposed_plan"):
        from opspilot.runtime.plans import prepare_node

        await prepare_node(state, runtime)
        return
    engine = create_engine(runtime.settings.database_url("workflow"))
    try:
        async with AsyncSession(engine) as session, session.begin():
            action = await prepare(
                session, UUID(state["run_id"]), state["proposed_action"] or {}, runtime.settings
            )
            state["action_id"] = str(action.id)
            state["outcome"] = None
    finally:
        await engine.dispose()


async def approval(state: AgentState, runtime: Runtime) -> None:
    reference = interrupt({"action_id": state["action_id"]})
    if not isinstance(reference, dict) or set(reference) != {"action_id"}:
        raise Conflict("Invalid resume reference")
    engine = create_engine(runtime.settings.database_url("workflow"))
    try:
        async with AsyncSession(engine) as session:
            row = (
                await session.execute(
                    select(Action, Approval)
                    .join(Approval, Approval.action_id == Action.id)
                    .where(
                        Action.id == UUID(reference["action_id"]),
                        Action.run_id == UUID(state["run_id"]),
                    )
                )
            ).one_or_none()
            old = await session.get(Action, UUID(state["action_id"]))
            logical = (
                await session.get(LogicalAction, row.Action.logical_action_id) if row else None
            )
            if (
                old is None
                or row is None
                or old.logical_action_id != row.Action.logical_action_id
                or logical is None
                or logical.current_revision_id != row.Action.id
            ):
                raise Conflict("Resume revision binding mismatch")
            if row.Approval.decision == "pending":
                raise Conflict("No persisted decision")
            if row.Action.superseded_at is not None or row.Action.arguments_hash != payload_hash(
                row.Action.arguments
            ):
                raise Conflict("Action payload differs")
            # Resolve a human-edited revision from authoritative storage, never resume payload.
            state["action_id"] = str(row.Action.id)
            state["proposed_action"] = row.Action.arguments
            state["outcome"] = "rejected" if row.Approval.decision == "rejected" else None
            if row.Approval.decision in {"expired", "revoked", "superseded"}:
                state["outcome"] = "partial"
                state.setdefault("errors", {})["approval"] = {
                    "code": "APPROVAL_" + row.Approval.decision.upper(),
                    "node": "approval",
                }
    finally:
        await engine.dispose()
