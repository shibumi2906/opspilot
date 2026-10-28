from opspilot.agent.evidence import can_propose, canonical_proposal
from opspilot.agent.policy import validate_proposal
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.contracts.planning import PlanDecision


async def plan(state: AgentState, runtime: Runtime) -> None:
    if not can_propose(state):
        state["proposed_action"] = None
        return
    from opspilot.runtime.plans import VERSION, canonical_plan

    mixed = await canonical_plan(state) if state.get("workflow_version") == VERSION else None
    canonical = canonical_proposal(state)
    result = await runtime.llm(
        "plan",
        runtime.context(state, "plan")
        | {
            "canonical_proposal": canonical.model_dump(mode="json"),
            "canonical_plan": mixed.model_dump(mode="json") if mixed else None,
        },
        PlanDecision,
        state,
    )
    if mixed is not None:
        from opspilot.agent.policy import PolicyViolation

        if result.plan != mixed or result.proposal is not None:
            raise PolicyViolation("Mixed plan differs from trusted scoped proposal")
        state["proposed_plan"] = mixed.model_dump(mode="json")
        state["proposed_action"] = canonical.model_dump(mode="json")
        return
    if result.plan is not None:
        from opspilot.agent.policy import PolicyViolation

        raise PolicyViolation("Unrequested mixed plan")
    if result.proposal is not None:
        validate_proposal(result.proposal, state, canonical)
        state["proposed_action"] = result.proposal.model_dump(mode="json")
