from opspilot.agent.evidence import canonical_facts, missing_checks
from opspilot.agent.policy import validate_analysis
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.contracts.reports import Analysis


async def reason(state: AgentState, runtime: Runtime) -> None:
    facts = canonical_facts(state)
    missing = missing_checks(state)
    result = await runtime.llm(
        "reason",
        runtime.context(state)
        | {
            "canonical_facts": facts,
            "missing_checks": missing,
        },
        Analysis,
        state,
    )
    validate_analysis(result, state, facts)
    state["facts"] = [f.model_dump() for f in result.facts]
    state["hypotheses"] = [h.model_dump() for h in result.hypotheses]
    state["missing_checks"] = sorted(set(missing + result.missing_checks))
    if state["missing_checks"]:
        state["outcome"] = "partial"
