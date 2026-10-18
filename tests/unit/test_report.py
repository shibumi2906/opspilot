from uuid import UUID

import pytest

from opspilot.agent.evidence import canonical_proposal
from opspilot.agent.policy import PolicyViolation, validate_proposal
from opspilot.contracts.actions import TicketProposal
from opspilot.fixtures.loader import GREENSHOP_ID


def test_proposal_is_grounded_and_rejects_tampering():
    state = {
        "customer_id": GREENSHOP_ID,
        "customer_name": "GreenShop",
        "language": "en",
        "facts": [{"statement": "Credential status: expired", "evidence_ids": ["ev1"]}],
        "evidence": {"ev1": {}},
        "hypotheses": [],
    }
    proposal = canonical_proposal(state)
    validate_proposal(proposal, state, proposal)
    for patch in (
        {"customer_id": UUID(int=2)},
        {"evidence_ids": ["missing"]},
        {"description": "The integration is fixed"},
    ):
        with pytest.raises(PolicyViolation):
            validate_proposal(
                TicketProposal.model_validate(proposal.model_dump() | patch), state, proposal
            )
    assert "not restored" in proposal.description
