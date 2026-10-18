import re
from typing import Any

from opspilot.agent.state import AgentState, ReadCall
from opspilot.contracts.actions import TicketProposal
from opspilot.contracts.reports import Analysis
from opspilot.mcp_client.registry import READ_TOOLS


class PolicyViolation(Exception):
    pass


def forbidden_request(request: str) -> bool:
    return bool(
        re.search(
            r"\b(delete|drop|truncate|erase|execute|shell|repair|rotate|revoke)\b|"
            r"удал\w*|сотр\w*|выполни\w*\s+(sql|команд)|обнови\w*\s+(токен|credential)",
            request.casefold(),
        )
    )


def validate_read(call: ReadCall, state: AgentState) -> dict[str, Any]:
    if call.name not in READ_TOOLS:
        raise PolicyViolation("Unknown or forbidden tool")
    args = (
        READ_TOOLS[call.name]
        .arguments.model_validate(call.arguments)
        .model_dump(mode="json", by_alias=True)
    )
    for key in ("customer_id", "integration_id", "integration_type"):
        if args.get(key) is not None and str(args[key]) != str(state.get(key)):
            raise PolicyViolation("Read outside resolved customer/integration scope")
    if (
        call.name == "find_customers"
        and args["query"].casefold() != str(state.get("customer_name")).casefold()
    ):
        raise PolicyViolation("Customer already resolved")
    if call.name == "get_ticket":
        raise PolicyViolation("No trusted ticket reference exists at this stage")
    return args


def validate_analysis(
    analysis: Analysis, state: AgentState, canonical_facts: list[dict[str, Any]]
) -> None:
    allowed = {(f["statement"], tuple(f["evidence_ids"])) for f in canonical_facts}
    for fact in analysis.facts:
        if (fact.statement, tuple(fact.evidence_ids)) not in allowed:
            raise PolicyViolation("Unsupported fact or evidence reference")
    for hypothesis in analysis.hypotheses:
        refs = hypothesis.supporting_evidence_ids + hypothesis.contradicting_evidence_ids
        if any(ref not in state.get("evidence", {}) for ref in refs):
            raise PolicyViolation("Unknown hypothesis evidence reference")


def validate_proposal(
    proposal: TicketProposal, state: AgentState, canonical: TicketProposal
) -> None:
    if str(proposal.customer_id) != state.get("customer_id"):
        raise PolicyViolation("Proposal customer mismatch")
    if any(ref not in state.get("evidence", {}) for ref in proposal.evidence_ids):
        raise PolicyViolation("Unknown proposal evidence reference")
    if proposal.model_dump(exclude={"priority"}) != canonical.model_dump(exclude={"priority"}):
        raise PolicyViolation("Proposal differs from grounded canonical payload")
