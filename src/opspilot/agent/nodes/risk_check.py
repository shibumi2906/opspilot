from opspilot.agent.evidence import can_propose, canonical_proposal
from opspilot.agent.policy import validate_proposal
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.contracts.actions import TicketProposal


async def risk_check(state: AgentState, runtime: Runtime) -> None:
    runtime.budget.check()
    proposal = state.get("proposed_action")
    if proposal:
        if not can_propose(state) or runtime.budget.read_attempts > runtime.budget.limits.reads - 1:
            state.update(
                {
                    "proposed_action": None,
                    "outcome": "partial",
                    "policy_result": {"allowed": False, "reason": "Incomplete or unsafe diagnosis"},
                }
            )
            return
        validate_proposal(TicketProposal.model_validate(proposal), state, canonical_proposal(state))
        state.update(
            {"outcome": "proposed_only", "policy_result": {"allowed": True, "execution": False}}
        )
    else:
        state.update(
            {
                "outcome": state.get("outcome") or "diagnosis_only",
                "policy_result": {"allowed": False, "reason": "No action proposed"},
            }
        )
