from opspilot.agent.nodes.execute import saved_action
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.contracts.tools import TicketData


async def verify(state: AgentState, runtime: Runtime) -> None:
    execution = state.get("execution_result")
    state["verification_result"] = {"status": "unknown"}
    if not execution:
        state["outcome"] = "unknown_outcome"
        return
    try:
        action = await saved_action(state, runtime)
        result = await runtime.read(
            "get_ticket", {"ticket_id": execution["ticket_id"]}, state, verification=True
        )
        if not result.ok:
            state["outcome"] = "unknown_outcome"
            return
        data = TicketData.model_validate(result.data).model_dump(mode="json")
        expected = {
            **action["arguments"],
            "ticket_id": execution["ticket_id"],
            "originating_action_id": state["action_id"],
            "status": "open",
            "created_at": execution["created_at"],
        }
        if data != expected:
            state["verification_result"] = {"status": "mismatch"}
            state["outcome"] = "partial"
            state["errors"]["verify"] = {"code": "TICKET_MISMATCH", "node": "verify"}
            return
        state["verification_result"] = {"status": "verified", "ticket_id": data["ticket_id"]}
        state["outcome"] = "actions_verified"
    except Exception:
        state["outcome"] = "unknown_outcome"
        state["errors"]["verify"] = {"code": "VERIFICATION_UNAVAILABLE", "node": "verify"}
