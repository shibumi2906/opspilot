from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot.agent.budgets import BudgetExceeded
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.contracts.tools import CreateTicketData
from opspilot.db.engine import create_engine
from opspilot.db.models_workflow import Action, Approval
from opspilot.runtime.actions import payload_hash


async def saved_action(state: AgentState, runtime: Runtime) -> dict[str, Any]:
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
            if row is None or row.Approval.decision != "approved":
                raise ValueError("Approved action missing")
            action = row.Action
            if action.tool_name != "create_ticket" or action.arguments_hash != payload_hash(
                action.arguments
            ):
                raise ValueError("Action mismatch")
            return {
                "arguments": action.arguments,
                "result": action.execution_result,
                "execution_status": action.execution_status,
            }
    finally:
        await engine.dispose()


async def execute(state: AgentState, runtime: Runtime) -> None:
    # Human wait is excluded by the resume runtime; active processing still has a limit.
    try:
        runtime.budget.check()
    except BudgetExceeded:
        state["outcome"] = "budget_exhausted"
        return
    # Never dispatch model/state arguments and never automatically retry an uncertain write.
    try:
        action = await saved_action(state, runtime)
        if action["execution_status"] == "succeeded" and action["result"]:
            state["execution_result"] = CreateTicketData.model_validate(
                action["result"]
            ).model_dump(mode="json")
            return
        async with runtime.client.session() as (session, _):
            result = await runtime.client.call(
                session,
                "create_ticket",
                {
                    "run_id": state["run_id"],
                    "action_id": state["action_id"],
                    "arguments": action["arguments"],
                },
            )
        if not result.ok:
            if result.error and result.error.retryable:
                raise RuntimeError("Write response uncertain")
            state["outcome"] = "partial"
            state["errors"]["execute"] = {
                "code": result.error.code if result.error else "WRITE_FAILED",
                "node": "execute",
            }
            return
        state["execution_result"] = CreateTicketData.model_validate(result.data).model_dump(
            mode="json"
        )
    except Exception:
        # A committed write with a lost response is recovered from the atomic workflow result.
        try:
            action = await saved_action(state, runtime)
            if action["execution_status"] == "succeeded" and action["result"]:
                state["execution_result"] = CreateTicketData.model_validate(
                    action["result"]
                ).model_dump(mode="json")
                return
        except Exception:
            pass
        engine = create_engine(runtime.settings.database_url("workflow"))
        try:
            async with engine.begin() as connection:
                # If a late commit won the row lock, leave its succeeded result intact.
                await connection.execute(
                    update(Action)
                    .where(
                        Action.id == UUID(state["action_id"]),
                        Action.run_id == UUID(state["run_id"]),
                        Action.execution_result.is_(None),
                    )
                    .values(execution_status="unknown")
                )
        except Exception:
            pass
        finally:
            await engine.dispose()
        state["outcome"] = "unknown_outcome"
        state["errors"]["execute"] = {"code": "WRITE_OUTCOME_UNKNOWN", "node": "execute"}
