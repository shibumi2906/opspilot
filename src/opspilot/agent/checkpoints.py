from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from sqlalchemy.engine import make_url

from opspilot.config import Settings


@asynccontextmanager
async def postgres_checkpointer(settings: Settings) -> AsyncIterator[AsyncPostgresSaver]:
    url = make_url(settings.database_url("checkpoint")).set(drivername="postgresql")
    async with AsyncPostgresSaver.from_conn_string(
        url.render_as_string(hide_password=False)
    ) as saver:
        assert isinstance(saver.conn, AsyncConnection)
        cursor = await saver.conn.execute("SELECT current_schema() AS schema")
        row = await cursor.fetchone()
        if row is None or row["schema"] != "checkpoints":
            raise ValueError("Checkpoint connection must use checkpoints schema")
        await saver.setup()
        yield saver
