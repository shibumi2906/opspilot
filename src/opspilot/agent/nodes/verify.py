from opspilot.agent.nodes.execute import saved_action
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.mcp_client.registry import READ_TOOLS


async def verify(state: AgentState, runtime: Runtime) -> None:
    execution = state.get("execution_result")
    state["verification_result"] = {"status": "unknown"}
    if not execution:
        state["outcome"] = "unknown_outcome"
        return
    try:
        action = await saved_action(state, runtime)
        read, id_field = {
            "create_ticket": ("get_ticket", "ticket_id"),
            "add_ticket_comment": ("get_ticket_comment", "comment_id"),
            "notify_manager": ("get_notification", "notification_id"),
        }[action["tool"]]
        result = await runtime.read(read, {id_field: execution[id_field]}, state, verification=True)
        if not result.ok:
            state["outcome"] = "unknown_outcome"
            return
        data = READ_TOOLS[read].data.model_validate(result.data).model_dump(mode="json")
        expected = {
            **action["arguments"],
            id_field: execution[id_field],
            "originating_action_id": state["action_id"],
            **({"status": "open"} if action["tool"] == "create_ticket" else {}),
            "created_at": execution["created_at"],
        }
        if data != expected:
            state["verification_result"] = {"status": "mismatch"}
            state["outcome"] = "partial"
            state["errors"]["verify"] = {"code": "TICKET_MISMATCH", "node": "verify"}
            return
        state["verification_result"] = {"status": "verified", id_field: data[id_field]}
        state["outcome"] = "actions_verified"
    except Exception:
        state["outcome"] = "unknown_outcome"
        state["errors"]["verify"] = {"code": "VERIFICATION_UNAVAILABLE", "node": "verify"}
