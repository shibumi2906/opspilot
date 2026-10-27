"""Pure interrupt node; preparation is checkpointed by the preceding node."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid5

from langgraph.types import interrupt

from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState


def prepare(state: AgentState, runtime: Runtime, kind: str, options: list[dict[str, Any]]) -> None:
    version = state.get("clarification_round", 0) + 1
    if version > 2 or not options or len(options) > 100:
        state.update({"outcome": "insufficient_context", "clarification": None})
        return
    state["clarification_round"] = version
    state["clarification"] = {
        "id": str(uuid5(UUID(state["run_id"]), f"clarification:{version}")),
        "version": version,
        "kind": kind,
        "options": options,
        "expires_at": (
            datetime.now(UTC) + timedelta(seconds=runtime.settings.clarification_ttl_seconds)
        ).isoformat(),
    }


async def clarify(state: AgentState, runtime: Runtime) -> None:
    form = state.get("clarification")
    assert form is not None
    answer = interrupt(form)
    if (
        not answer.get("answered_at")
        or datetime.fromisoformat(answer["answered_at"])
        >= datetime.fromisoformat(form["expires_at"])
        or answer.get("kind") != form["kind"]
        or answer.get("choice") not in {o["id"] for o in form["options"]}
    ):
        state.update({"outcome": "insufficient_context", "clarification": None})
        return
    if form["kind"] == "customer":
        state["selected_customer"] = answer["choice"]
    elif form["kind"] == "integration":
        state["selected_integration"] = answer["choice"]
    else:
        state["timezone"] = answer["choice"]
    state["clarification"] = None
    if form["kind"] == "timezone":
        from opspilot.agent.nodes.classify import classify

        await classify(state, runtime)
