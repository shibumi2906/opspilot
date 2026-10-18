from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState


async def resolve_customer(state: AgentState, runtime: Runtime) -> None:
    hint = state.get("customer_hint")
    result = await runtime.read("find_customers", {"query": hint}, state)
    if not result.ok or result.data is None:
        state.update({"outcome": "partial", "missing_checks": ["find_customers"]})
        return
    candidates = result.data["candidates"]
    state["candidates"] = candidates
    exact = [c for c in candidates if c["name"].casefold() == str(hint).casefold()]
    selected = exact if len(exact) == 1 else candidates
    if len(selected) != 1 or (result.data["truncated"] and not exact):
        state["outcome"] = "insufficient_context"
        return
    customer = await runtime.read(
        "get_customer", {"customer_id": selected[0]["customer_id"]}, state
    )
    if not customer.ok or customer.data is None:
        state.update({"outcome": "partial", "missing_checks": ["get_customer"]})
        return
    integrations = customer.data["integrations"]
    if len(integrations) != 1:
        state["outcome"] = "insufficient_context"
        return
    state.update(
        {
            "customer_id": customer.data["customer_id"],
            "customer_name": customer.data["name"],
            "integration_id": integrations[0]["integration_id"],
            "integration_type": integrations[0]["integration_type"],
        }
    )
