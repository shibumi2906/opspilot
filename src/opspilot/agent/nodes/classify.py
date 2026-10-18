import re
from datetime import timedelta

from opspilot.agent.policy import forbidden_request
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState, Classification
from opspilot.contracts.tools import EventsArgs


async def classify(state: AgentState, runtime: Runtime) -> None:
    text = state["request"]
    # Explicit destructive intents cannot be overruled by a model classification.
    state["language"] = "ru" if re.search("[а-яА-ЯёЁ]", text) else "en"
    if forbidden_request(text):
        state.update({"intent": "forbidden", "outcome": "blocked"})
        return
    if re.search(r"[\u0590-\u05ff\u0600-\u06ff\u4e00-\u9fff]", text):
        state["outcome"] = "insufficient_context"
        return
    result = await runtime.llm(
        "classify",
        {
            "request": text,
            "scenario_clock": runtime.settings.scenario_clock.isoformat(),
            "timezone": "Asia/Jerusalem",
        },
        Classification,
        state,
    )
    state.update(
        {
            "intent": result.intent,
            "language": result.language,
            "customer_hint": result.customer_hint,
            "time_window": {"from": result.from_.isoformat(), "to": result.to.isoformat()},
        }
    )
    # Validate the model's requested time window before any read dispatch.
    from uuid import UUID

    EventsArgs.model_validate(
        {"customer_id": UUID(int=0), "integration_id": UUID(int=0), **state["time_window"]}
    )
    if result.to > runtime.settings.scenario_clock + timedelta(seconds=1):
        state["outcome"] = "insufficient_context"
    elif result.intent == "forbidden":
        state["outcome"] = "blocked"
    elif not result.customer_hint:
        state["outcome"] = "insufficient_context"
