from opspilot.agent.evidence import canonical_facts
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.contracts.reports import Report


async def report(state: AgentState, runtime: Runtime) -> None:
    ru = state.get("language") == "ru"
    outcome = state.get("outcome") or "partial"
    summaries = {
        "proposed_only": (
            "Расследование завершено; предложен тикет без исполнения.",
            "Investigation complete; a ticket is proposed without execution.",
        ),
        "diagnosis_only": (
            "Проверка завершена; доступны только наблюдения.",
            "Read-only diagnosis complete; observations are available.",
        ),
        "partial": (
            "Данных недостаточно или они противоречивы; требуется проверка.",
            "Evidence is incomplete or contradictory; further checks are required.",
        ),
        "blocked": (
            "Запрос заблокирован политикой; запись не выполнена.",
            "Request blocked by policy; no write was performed.",
        ),
        "insufficient_context": (
            "Уточните клиента или запрос; автоматический выбор не выполнен.",
            "Clarify the customer or request; no automatic selection was made.",
        ),
        "budget_exhausted": (
            "Бюджет расследования исчерпан; тикет не предложен.",
            "Investigation budget exhausted; no ticket is proposed.",
        ),
    }
    if outcome != "proposed_only":
        state["proposed_action"] = None
    facts = state.get("facts") or canonical_facts(state)
    result = Report(
        summary=summaries[outcome][0 if ru else 1],
        facts=facts,
        hypotheses=state.get("hypotheses", []),
        missing_checks=state.get("missing_checks", []),
        action_summary=(
            "Тикет только предложен; согласование и исполнение ещё не реализованы."
            if ru
            else "Proposal only; approval and execution are not implemented."
        )
        if state.get("proposed_action")
        else ("Тикет не создан." if ru else "No ticket was created."),
        remaining_problem=(
            "Credential не обновлён; восстановление потока заказов не подтверждено."
            if ru
            else "Credentials are unchanged; order delivery recovery is not confirmed."
        ),
        outcome=outcome,
    )
    state["final_report"] = result.model_dump(mode="json")
    state["budget"] = runtime.budget.snapshot()
