from uuid import uuid4

from opspilot.agent.evidence import missing_reads
from opspilot.agent.policy import PolicyViolation, validate_read
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState, InvestigationDecision


async def investigate(state: AgentState, runtime: Runtime) -> None:
    runtime.budget.begin_round()
    result = await runtime.llm("investigate", runtime.context(state), InvestigationDecision, state)
    if result.stop and result.calls or not result.stop and not result.calls:
        raise PolicyViolation("Inconsistent investigation decision")
    pending = []
    for call in result.calls:
        arguments = validate_read(call, state)
        if state.get("intent") == "status_only" and call.name != "get_service_status":
            raise PolicyViolation("Status-only request permits only service status")
        call_id = str(uuid4())
        pending.append({"name": call.name, "arguments": arguments, "tool_call_id": call_id})
        state.setdefault("tool_calls", {})[f"{call_id}:pending"] = {
            "name": call.name,
            "arguments": arguments,
            "tool_call_id": call_id,
            "status": "pending",
            "attempt": 0,
        }
    state["pending_reads"] = pending

    state["continue_investigation"] = bool(result.stop and missing_reads(state))
