from opspilot.agent.evidence import can_propose, canonical_proposal
from opspilot.agent.policy import validate_proposal
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.contracts.actions import PlanDecision


async def plan(state: AgentState, runtime: Runtime) -> None:
    if not can_propose(state):
        state["proposed_action"] = None
        return
    canonical = canonical_proposal(state)
    result = await runtime.llm(
        "plan",
        runtime.context(state, "plan")
        | {
            "canonical_proposal": canonical.model_dump(mode="json"),
        },
        PlanDecision,
        state,
    )
    if result.proposal is not None:
        validate_proposal(result.proposal, state, canonical)
        state["proposed_action"] = result.proposal.model_dump(mode="json")
