from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.config import Settings
from opspilot.db.engine import create_engine


class ProbeState(TypedDict):
    value: int


async def test_pinned_graph_and_postgres_saver_are_compatible(
    integration_settings: Settings,
) -> None:
    # Compatibility probe only. The product investigation graph belongs to stage 3.
    url = make_url(integration_settings.database_url("checkpoint"))
    conninfo = url.set(drivername="postgresql").render_as_string(hide_password=False)
    async with AsyncPostgresSaver.from_conn_string(conninfo) as saver:
        await saver.setup()
        builder = StateGraph(ProbeState)
        builder.add_node("probe", lambda state: {"value": state["value"] + 1})
        builder.add_edge(START, "probe")
        builder.add_edge("probe", END)
        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": f"compatibility-{uuid4()}"}}
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
