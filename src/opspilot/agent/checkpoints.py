from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from opspilot.auth.context import actor_id
from opspilot.config import Settings
from opspilot.runtime.fencing import current_fence
from opspilot.tenancy.context import require_tenant


class FencedPostgresSaver(AsyncPostgresSaver):
    async def bind_fence(self) -> None:
        self.execution_fence = current_fence()
        fence = self.execution_fence
        assert isinstance(self.conn, AsyncConnection)
        # This dedicated connection is never pooled or rebound to another execution.
        await self.conn.execute(
            """SELECT set_config('app.execution_run',%s,false),
          set_config('app.execution_owner',%s,false),set_config('app.execution_epoch',%s,false)""",
            (
                str(fence.run) if fence else "",
                str(fence.owner) if fence else "",
                str(fence.epoch) if fence else "",
            ),
        )

    @asynccontextmanager
    async def _cursor(self, *, pipeline: bool = False) -> AsyncIterator[Any]:
        assert isinstance(self.conn, AsyncConnection)
        async with self.lock, self.conn.transaction():
            async with self.conn.cursor(binary=True, row_factory=dict_row) as cur:
                fence = self.execution_fence
                if pipeline and fence is None:
                    raise RuntimeError("Checkpoint writes require execution ownership")
                if pipeline and fence is not None:
                    await cur.execute("SELECT workflow.check_fence(%s)", (fence.run,))
                yield cur


@asynccontextmanager
async def postgres_checkpointer(settings: Settings) -> AsyncIterator[AsyncPostgresSaver]:
    url = make_url(settings.database_url("checkpoint")).set(drivername="postgresql")
    if url.database not in {"opspilot_full", "opspilot_full_test"}:
        raise ValueError("Full checkpoint requires an isolated Full database")
    conninfo = make_conninfo(
        url.render_as_string(hide_password=False),
        options=str(url.query.get("options", ""))
        + " -c idle_in_transaction_session_timeout=5000 -c statement_timeout=5000",
    )
    tenant = require_tenant()
    async with FencedPostgresSaver.from_conn_string(conninfo) as saver:
        assert isinstance(saver.conn, AsyncConnection)
        cursor = await saver.conn.execute(
            "SELECT current_schema() AS schema, current_database() AS database"
        )
        row = await cursor.fetchone()
        if row is None or row["schema"] != "checkpoints" or row["database"] != url.database:
            raise ValueError("Checkpoint connection must use checkpoints schema")
        await saver.conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant),))
        await saver.conn.execute("SELECT set_config('app.actor_id', %s, false)", (str(actor_id()),))
        version = await saver.conn.execute("SELECT max(v) AS version FROM checkpoint_migrations")
        row = await version.fetchone()
        if row is None or row["version"] != 9:
            raise ValueError("Checkpoint schema must be migrated by the Full administrator")
        assert isinstance(saver, FencedPostgresSaver)
        await saver.bind_fence()
        yield saver
