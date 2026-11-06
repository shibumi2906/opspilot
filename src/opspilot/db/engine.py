from contextlib import nullcontext

from opentelemetry import trace
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from opspilot.auth.context import actor_id
from opspilot.auth.service_context import verified_context
from opspilot.runtime.fencing import current_fence
from opspilot.telemetry import span
from opspilot.tenancy.context import current_tenant


class Base(DeclarativeBase):
    pass


def create_engine(url: str) -> AsyncEngine:
    expected = make_url(url).database
    if expected not in {"opspilot_full", "opspilot_full_test"}:
        raise ValueError("Full requires opspilot_full or opspilot_full_test")
    parsed = make_url(url)
    connect_args = {}
    if parsed.username in {"ops_workflow", "ops_checkpoint", "ops_domain"}:
        connect_args["options"] = (
            str(parsed.query.get("options", ""))
            + " -c idle_in_transaction_session_timeout=5000 -c statement_timeout=5000"
        )
    engine = create_async_engine(
        url, pool_pre_ping=True, hide_parameters=True, connect_args=connect_args
    )

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
        if parsed.username in {"ops_workflow", "ops_checkpoint", "ops_domain"}:
            # Runtime readers/writers coexist. A bounded administrative compaction
            # takes the exclusive counterpart before inspecting eligibility.
            connection.execute(
                text("SELECT pg_advisory_xact_lock_shared(1801202617)").execution_options(
                    opspilot_internal_lock=True
                )
            )
        tenant = current_tenant()
        fence = current_fence()
        claims = verified_context() or {}
        values = {
            "tenant": tenant,
            "actor": actor_id(),
            "run": fence.run if fence else claims.get("run"),
            "owner": fence.owner if fence else claims.get("execution_owner"),
            "epoch": fence.epoch if fence else claims.get("execution_epoch"),
        }
        connection.execute(
            text("""SELECT set_config('app.tenant_id',:tenant,true),
          set_config('app.actor_id',:actor,true),set_config('app.execution_run',:run,true),
          set_config('app.execution_owner',:owner,true),set_config('app.execution_epoch',:epoch,true)"""),
            {key: str(value) if value is not None else "" for key, value in values.items()},
        )

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        # Idle queue/SSE polls have no live recorded operation. Their failures
        # retain worker/API diagnostics; they must not flood the receiver with roots.
        recorded = trace.get_current_span().is_recording() and not context.execution_options.get(
            "opspilot_internal_lock"
        )
        manager = span("db.operation") if recorded else nullcontext()
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
                error = context.original_exception
                manager.__exit__(type(error), error, error.__traceback__)

    return engine
