from langgraph.checkpoint.memory import InMemorySaver

from opspilot.agent.budgets import Budget, BudgetLimits
from opspilot.agent.graph import build_graph
from opspilot.agent.runtime import Runtime
from opspilot.config import Settings
from opspilot.llm.scripted import ScriptedProvider


def test_real_graph_has_research_cycle_and_conditional_edges():
    runtime = Runtime(
        Settings(_env_file=None, mcp_service_token="a" * 64),
        ScriptedProvider(),
        Budget(BudgetLimits()),
    )
    graph = build_graph(runtime, InMemorySaver()).get_graph()
    edges = {(e.source, e.target) for e in graph.edges}
    assert ("investigate", "execute_reads") in edges
    assert ("execute_reads", "investigate") in edges
    assert ("investigate", "reason") in edges
    assert ("risk_check", "report") in edges
    assert any(e.conditional for e in graph.edges)
    assert {"execute", "prepare_approval", "approval"} <= graph.nodes.keys()
