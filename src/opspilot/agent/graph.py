import copy
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from opspilot.agent.budgets import BudgetExceeded
from opspilot.agent.evidence import missing_reads
from opspilot.agent.nodes.approval import approval, prepare_approval
from opspilot.agent.nodes.classify import classify
from opspilot.agent.nodes.execute import execute
from opspilot.agent.nodes.execute_reads import execute_reads
from opspilot.agent.nodes.investigate import investigate
from opspilot.agent.nodes.plan import plan
from opspilot.agent.nodes.reason import reason
from opspilot.agent.nodes.report import report
from opspilot.agent.nodes.resolve_customer import resolve_customer
from opspilot.agent.nodes.risk_check import risk_check
from opspilot.agent.nodes.verify import verify
from opspilot.agent.policy import PolicyViolation
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import AgentState
from opspilot.llm.base import ProviderFailure

Node = Callable[[AgentState, Runtime], Awaitable[None]]


def build_graph(
    runtime: Runtime, checkpointer: BaseCheckpointSaver[Any]
) -> CompiledStateGraph[Any, Any, Any, Any]:
    def guarded(name: str, node: Node) -> Callable[[AgentState], Awaitable[AgentState]]:
        async def invoke(current: AgentState) -> AgentState:
            state = copy.deepcopy(current)
            try:
                if name not in {"report", "approval", "execute", "verify"}:
                    runtime.budget.check()
                await node(state, runtime)
                if name not in {"report", "approval", "execute", "verify"}:
                    runtime.budget.check()
            except BudgetExceeded:
                state.update({"outcome": "budget_exhausted", "proposed_action": None})
                state.setdefault("errors", {})[name] = {"code": "BUDGET_EXHAUSTED", "node": name}
            except PolicyViolation:
                state.update({"outcome": "blocked", "proposed_action": None})
                state.setdefault("errors", {})[name] = {"code": "POLICY_VIOLATION", "node": name}
            except (ValidationError, ProviderFailure) as exc:
                state.update({"outcome": "partial", "proposed_action": None})
                state.setdefault("errors", {})[name] = {
                    "code": exc.code
                    if isinstance(exc, ProviderFailure)
                    else "INVALID_MODEL_OUTPUT",
                    "node": name,
                }
            state["budget"] = runtime.budget.snapshot()
            return state

        return invoke

    builder = StateGraph(AgentState)
    for name, node in (
        ("prepare_approval", prepare_approval),
        ("approval", approval),
        ("execute", execute),
        ("verify", verify),
        ("classify", classify),
        ("resolve_customer", resolve_customer),
        ("investigate", investigate),
        ("execute_reads", execute_reads),
        ("reason", reason),
        ("plan", plan),
        ("risk_check", risk_check),
        ("report", report),
    ):
        builder.add_node(name, RunnableLambda(guarded(name, node)))
    builder.add_edge(START, "classify")
    for name, next_name in (
        ("classify", "resolve_customer"),
        ("resolve_customer", "investigate"),
        ("reason", "plan"),
        ("plan", "risk_check"),
    ):
        builder.add_conditional_edges(
            name,
            lambda state, target=next_name: "report" if state.get("outcome") else target,
            {"report": "report", next_name: next_name},
        )
    builder.add_conditional_edges(
        "execute_reads",
        lambda state: (
            "report"
            if state.get("outcome")
            else ("investigate" if missing_reads(state) else "reason")
        ),
        {"report": "report", "investigate": "investigate", "reason": "reason"},
    )
    builder.add_conditional_edges(
        "investigate",
        lambda state: (
            "report"
            if state.get("outcome")
            else "execute_reads"
            if state.get("pending_reads")
            else "investigate"
            if state.get("continue_investigation")
            else "reason"
        ),
        {
            "report": "report",
            "execute_reads": "execute_reads",
            "reason": "reason",
            "investigate": "investigate",
        },
    )
    builder.add_conditional_edges(
        "risk_check",
        lambda state: "prepare_approval" if state.get("outcome") == "proposed_only" else "report",
        {"prepare_approval": "prepare_approval", "report": "report"},
    )
    builder.add_conditional_edges(
        "prepare_approval",
        lambda state: "report" if state.get("outcome") else "approval",
        {"report": "report", "approval": "approval"},
    )
    builder.add_conditional_edges(
        "approval",
        lambda state: "report" if state.get("outcome") else "execute",
        {"report": "report", "execute": "execute"},
    )
    builder.add_conditional_edges(
        "execute",
        lambda state: "report" if state.get("outcome") else "verify",
        {"report": "report", "verify": "verify"},
    )
    builder.add_edge("verify", "report")
    builder.add_edge("report", END)
    return builder.compile(checkpointer=checkpointer)
