from opspilot.agent.evidence import missing_checks
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState


async def execute_reads(state: AgentState, runtime: Runtime) -> None:
    for call in state.get("pending_reads", []):
        result = await runtime.read(call["name"], call["arguments"], state, call["tool_call_id"])
        state["tool_calls"][f"{call['tool_call_id']}:pending"]["status"] = "dispatched"
        if not result.ok:
            state.update({"outcome": "partial", "missing_checks": missing_checks(state)})
            break
    state["pending_reads"] = []
