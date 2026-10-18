from typing import Annotated, Any, Literal, TypedDict

from pydantic import AwareDatetime, Field

from opspilot.contracts.common import StrictModel


def merge_by_id(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Upsert observations by stable identity; replay does not append duplicates."""
    return left | right


class Classification(StrictModel):
    intent: Literal["investigate", "status_only", "forbidden"]
    language: Literal["ru", "en"]
    customer_hint: str | None
    from_: AwareDatetime
    to: AwareDatetime


class ReadCall(StrictModel):
    name: str
    arguments: dict[str, Any]


class InvestigationDecision(StrictModel):
    stop: bool
    calls: Annotated[list[ReadCall], Field(max_length=3)]


class AgentState(TypedDict, total=False):
    action_id: str
    schema_version: int
    run_id: str
    thread_id: str
    client_request_id: str
    mode: str
    model_id: str | None
    request: str
    language: str
    intent: str
    customer_hint: str | None
    customer_id: str | None
    customer_name: str | None
    integration_id: str | None
    integration_type: str | None
    time_window: dict[str, Any]
    candidates: list[dict[str, Any]]
    observations: Annotated[dict[str, Any], merge_by_id]
    evidence: Annotated[dict[str, Any], merge_by_id]
    tool_calls: Annotated[dict[str, Any], merge_by_id]
    llm_calls: Annotated[dict[str, Any], merge_by_id]
    pending_reads: list[dict[str, Any]]
    continue_investigation: bool
    hypotheses: list[dict[str, Any]]
    facts: list[dict[str, Any]]
    proposed_action: dict[str, Any] | None
    policy_result: dict[str, Any] | None
    budget: dict[str, Any]
    errors: Annotated[dict[str, Any], merge_by_id]
    missing_checks: list[str]
    outcome: str | None
    final_report: dict[str, Any] | None
