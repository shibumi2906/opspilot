import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from opspilot.agent.policy import forbidden_request
from opspilot.agent.state import AgentState, Classification, InvestigationDecision
from opspilot.contracts.actions import PlanDecision
from opspilot.contracts.reports import Analysis, Hypothesis
from opspilot.llm.base import Completion, Operation, Usage


class ScriptedProvider:
    """Explicit fixture decisions; orchestration, transport and persistence stay real."""

    async def complete(self, operation: Operation, context: dict[str, Any]) -> Completion:
        if operation == "classify":
            request = context["request"]
            ru = bool(re.search("[а-яА-ЯёЁ]", request))
            clock = datetime.fromisoformat(context["scenario_clock"])
            start = clock - timedelta(hours=2)
            if re.search(r"сегодня|\btoday\b", request, re.I):
                local = clock.astimezone(ZoneInfo("Asia/Jerusalem"))
                start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(
                    clock.tzinfo
                )
            hint = re.search(r"GreenShop(?:\s+EU)?|BlueMarket|\bGreen\b", request, re.I)
            if hint is None:
                hint = re.search(r"(?:customer|client|клиент\w*)\s+[\"«]?([\w-]+)", request, re.I)
                name = hint.group(1) if hint else None
            else:
                name = hint.group(0)
            intent = (
                "forbidden"
                if forbidden_request(request)
                else (
                    "status_only"
                    if re.search(r"\bstatus\b|статус|здоров", request, re.I)
                    and not re.search(r"investigat|расслед|почему|why", request, re.I)
                    else "investigate"
                )
            )
            output = Classification(
                intent=intent,
                language="ru" if ru else "en",
                customer_hint=name,
                from_=start,
                to=clock,
            ).model_dump(mode="json")
        elif operation == "investigate":
            state: AgentState = context["state"]
            scope = {"customer_id": state["customer_id"], "integration_id": state["integration_id"]}
            observed = {v["name"] for v in state.get("observations", {}).values()}
            names = ["get_service_status"]
            if state["intent"] != "status_only":
                names += [
                    "get_integration_events",
                    "get_credential_status",
                    "search_incidents",
                    "search_documentation",
                ]
            calls = []
            for name in names:
                if name in observed:
                    continue
                arguments = dict(scope)
                if name == "get_integration_events":
                    arguments |= state["time_window"]
                elif name.startswith("search_"):
                    arguments = {
                        "query": "401",
                        "integration_type": state["integration_type"],
                        "language": state["language"],
                    }
                calls.append({"name": name, "arguments": arguments})
            output = InvestigationDecision(stop=not calls, calls=calls[:3]).model_dump()
        elif operation == "reason":
            state = context["state"]
            hypotheses = []
            credential = next(
                (
                    e["facts"]
                    for e in state["evidence"].values()
                    if e["source_type"] == "credential_status"
                ),
                None,
            )
            if credential and credential["status"] == "expired" and not context["missing_checks"]:
                refs = [
                    key
                    for key, value in state["evidence"].items()
                    if value["source_type"] in ("credential_status", "integration_event")
                ]
                hypotheses.append(
                    Hypothesis(
                        hypothesis_id="credential-expiration",
                        summary=(
                            "Истечение credential могло вызвать отказы доставки."
                            if state["language"] == "ru"
                            else "Credential expiration may explain delivery failures."
                        ),
                        supporting_evidence_ids=refs,
                        contradicting_evidence_ids=[],
                        confidence_label="high",
                        missing_checks=[],
                    )
                )
            output = Analysis(
                facts=context["canonical_facts"],
                hypotheses=hypotheses,
                missing_checks=context["missing_checks"],
            ).model_dump()
        else:
            output = PlanDecision(proposal=context["canonical_proposal"]).model_dump(mode="json")
        # Scripted mode makes no provider request and incurs no model token usage.
        return Completion(output=output, usage=Usage(input_tokens=0, output_tokens=0))
