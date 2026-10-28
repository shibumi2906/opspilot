from opspilot.contracts.actions import TicketProposal
from opspilot.contracts.common import StrictModel
from opspilot.contracts.plans import MixedPlan


class PlanDecision(StrictModel):
    proposal: TicketProposal | None
    plan: MixedPlan | None = None
