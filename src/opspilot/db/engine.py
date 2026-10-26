from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from opspilot.telemetry import span
from opspilot.tenancy.context import current_tenant


class Base(DeclarativeBase):
    pass


def create_engine(url: str) -> AsyncEngine:
    expected = make_url(url).database
    if expected not in {"opspilot_full", "opspilot_full_test"}:
        raise ValueError("Full requires opspilot_full or opspilot_full_test")
    engine = create_async_engine(url, pool_pre_ping=True, hide_parameters=True)

    @event.listens_for(engine.sync_engine, "connect")
    def identity(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != expected:
                raise ValueError("Full connected database identity mismatch")
        finally:
            cursor.close()
        dbapi_connection.rollback()

    @event.listens_for(engine.sync_engine, "begin")
    def tenant_transaction(connection):  # type: ignore[no-untyped-def]
        tenant = current_tenant()
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant) if tenant else ""},
        )

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
