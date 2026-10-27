from typing import Any

from opspilot.agent.nodes.clarify import prepare
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState


async def resolve_customer(state: AgentState, runtime: Runtime) -> None:
    if state.get("selected_customer"):
        selected = [{"customer_id": state["selected_customer"]}]
    else:
        await find(state, runtime)
        if state.get("outcome") or state.get("clarification"):
            return
        selected = state["candidates"]
    await select_integration(state, runtime, selected)


async def find(state: AgentState, runtime: Runtime) -> None:
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
        prepare(
            state,
            runtime,
            "customer",
            [{"id": str(c["customer_id"]), "label": c["name"]} for c in candidates],
        )
        return
    state["candidates"] = selected


async def select_integration(
    state: AgentState, runtime: Runtime, selected: list[dict[str, Any]]
) -> None:
    customer = await runtime.read(
        "get_customer", {"customer_id": selected[0]["customer_id"]}, state
    )
    if not customer.ok or customer.data is None:
        state.update({"outcome": "partial", "missing_checks": ["get_customer"]})
        return
    integrations = customer.data["integrations"]
    if state.get("selected_integration"):
        integrations = [
            i for i in integrations if str(i["integration_id"]) == state["selected_integration"]
        ]
    if len(integrations) != 1:
        state["selected_customer"] = str(customer.data["customer_id"])
        prepare(
            state,
            runtime,
            "integration",
            [
                {"id": str(i["integration_id"]), "label": i["integration_type"]}
                for i in integrations
            ],
        )
        return
    state.update(
        {
            "customer_id": customer.data["customer_id"],
            "customer_name": customer.data["name"],
            "integration_id": integrations[0]["integration_id"],
            "integration_type": integrations[0]["integration_type"],
        }
    )
