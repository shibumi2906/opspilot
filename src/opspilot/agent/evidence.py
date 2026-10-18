from typing import Any

from opspilot.agent.state import AgentState
from opspilot.contracts.actions import TicketProposal
from opspilot.contracts.reports import Fact

REQUIRED = (
    "get_service_status",
    "get_integration_events",
    "get_credential_status",
    "search_incidents",
    "search_documentation",
)


def latest_data(state: AgentState, name: str) -> dict[str, Any] | None:
    matches = [v for v in state.get("observations", {}).values() if v["name"] == name]
    if not matches:
        return None
    result = matches[-1]["result"]
    return result["data"] if result["ok"] else None


def missing_checks(state: AgentState) -> list[str]:
    required = ("get_service_status",) if state.get("intent") == "status_only" else REQUIRED
    missing = [name for name in required if latest_data(state, name) is None]
    status = latest_data(state, "get_service_status")
    credential = latest_data(state, "get_credential_status")
    events = latest_data(state, "get_integration_events")
    if status and status["status"] == "unknown":
        missing.append("service_status_unknown")
    if credential and credential["status"] == "unknown" and state.get("intent") != "status_only":
        missing.append("credential_status_unknown")
    if (
        status
        and events
        and status["status"] == "healthy"
        and any(e.get("http_status", 0) and e["http_status"] >= 400 for e in events["events"])
    ):
        missing.append("contradictory_observations")
    return sorted(set(missing))


def canonical_facts(state: AgentState) -> list[dict[str, Any]]:
    ru = state.get("language") == "ru"
    facts = []
    for identity, evidence in state.get("evidence", {}).items():
        data = evidence["facts"]
        source = evidence["source_type"]
        statement = None
        if source == "integration_status":
            statement = ("Статус интеграции: " if ru else "Integration status: ") + data["status"]
        elif source == "credential_status":
            statement = ("Статус credential: " if ru else "Credential status: ") + data["status"]
        elif source == "integration_event":
            statement = ("Событие доставки: " if ru else "Delivery event: ") + str(
                data.get("http_status")
            )
        elif source == "incident":
            statement = ("Исторический инцидент: " if ru else "Historical incident: ") + data[
                "summary"
            ]
        elif source == "knowledge_article":
            statement = ("Документация: " if ru else "Documentation: ") + data["title"]
        if statement:
            facts.append(Fact(statement=statement, evidence_ids=[identity]).model_dump())
    return facts[:30]


def canonical_proposal(state: AgentState) -> TicketProposal:
    ru = state.get("language") == "ru"
    name = state.get("customer_name") or "customer"
    title = f"{name}: " + ("проверить сбой интеграции" if ru else "investigate integration failure")
    statements = [f["statement"] for f in state.get("facts", [])]
    description = "\n".join(statements)
    for hypothesis in state.get("hypotheses", []):
        description += "\n" + ("Гипотеза: " if ru else "Hypothesis: ") + hypothesis["summary"]
    description += "\n" + (
        "Тикет не исправляет интеграцию; credential не обновлён, поток заказов не восстановлен."
        if ru
        else (
            "A ticket does not repair the integration; credentials are unchanged "
            "and order delivery is not restored."
        )
    )
    refs = sorted(
        {ref for f in state.get("facts", []) for ref in f["evidence_ids"]}
        | {
            ref
            for h in state.get("hypotheses", [])
            for ref in h["supporting_evidence_ids"] + h["contradicting_evidence_ids"]
        }
    )
    return TicketProposal(
        customer_id=state["customer_id"],
        title=title[:200],
        description=description[:6000],
        priority="medium",
        evidence_ids=refs[:30],
    )


def can_propose(state: AgentState) -> bool:
    if state.get("outcome") or state.get("intent") != "investigate" or missing_checks(state):
        return False
    status = latest_data(state, "get_service_status")
    return bool(status and status["status"] in ("degraded", "unavailable") and state.get("facts"))
