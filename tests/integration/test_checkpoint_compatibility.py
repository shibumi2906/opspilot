from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from sqlalchemy import text

from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from tests.tenant_helpers import register_probe


class ProbeState(TypedDict):
    value: int


async def test_pinned_graph_and_postgres_saver_are_compatible(
    integration_settings: Settings,
) -> None:
    # Compatibility probe only. The product investigation graph belongs to stage 3.
    thread = f"compatibility-{uuid4()}"
    registration = create_engine(integration_settings.database_url("workflow"))
    try:
        await register_probe(registration, integration_settings.scenario_clock, thread)
    finally:
        await registration.dispose()
    async with postgres_checkpointer(integration_settings) as saver:
        builder = StateGraph(ProbeState)
        builder.add_node("probe", lambda state: {"value": state["value"] + 1})
        builder.add_edge(START, "probe")
        builder.add_edge("probe", END)
        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": thread}}
        assert (await graph.ainvoke({"value": 1}, config))["value"] == 2
        assert (await graph.aget_state(config)).values["value"] == 2
    engine = create_engine(integration_settings.database_url("checkpoint"))
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema='checkpoints' AND table_name='checkpoints'"
                    )
                )
                == 1
            )
    finally:
        await engine.dispose()
