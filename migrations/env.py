import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from opspilot.config import Settings
from opspilot.db import models_domain, models_workflow  # noqa: F401
from opspilot.db.engine import Base


def run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_schemas=True,
        version_table_schema="workflow",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(Settings().database_url("migration"), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url("migration"),
        target_metadata=Base.metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema="workflow",
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
