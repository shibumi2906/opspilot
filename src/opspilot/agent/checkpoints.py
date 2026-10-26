from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from sqlalchemy.engine import make_url

from opspilot.config import Settings
from opspilot.tenancy.context import require_tenant


@asynccontextmanager
async def postgres_checkpointer(settings: Settings) -> AsyncIterator[AsyncPostgresSaver]:
    url = make_url(settings.database_url("checkpoint")).set(drivername="postgresql")
    if url.database not in {"opspilot_full", "opspilot_full_test"}:
        raise ValueError("Full checkpoint requires an isolated Full database")
    tenant = require_tenant()
    async with AsyncPostgresSaver.from_conn_string(
        url.render_as_string(hide_password=False)
    ) as saver:
        assert isinstance(saver.conn, AsyncConnection)
        cursor = await saver.conn.execute(
            "SELECT current_schema() AS schema, current_database() AS database"
        )
        row = await cursor.fetchone()
        if row is None or row["schema"] != "checkpoints" or row["database"] != url.database:
            raise ValueError("Checkpoint connection must use checkpoints schema")
        await saver.conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant),))
        version = await saver.conn.execute("SELECT max(v) AS version FROM checkpoint_migrations")
        row = await version.fetchone()
        if row is None or row["version"] != 9:
            raise ValueError("Checkpoint schema must be migrated by the Full administrator")
        yield saver
