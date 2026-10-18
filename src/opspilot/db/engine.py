from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from opspilot.telemetry import span


class Base(DeclarativeBase):
    pass


def create_engine(url: str) -> AsyncEngine:
    engine = create_async_engine(url, pool_pre_ping=True, hide_parameters=True)

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        manager = span("db.operation")
        context._opspilot_span = manager
        manager.__enter__()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        context._opspilot_span.__exit__(None, None, None)

    @event.listens_for(engine.sync_engine, "handle_error")
    def failed(context):  # type: ignore[no-untyped-def]
        if context.execution_context is not None:
            manager = getattr(context.execution_context, "_opspilot_span", None)
            if manager is not None:
                manager.__exit__(None, None, None)

    return engine
