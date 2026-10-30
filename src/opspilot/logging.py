"""Positive-schema structured diagnostics. Arbitrary messages/exception bodies never persist."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from opspilot.observability.protocol import safe_attributes


def safe_record(record: dict[str, Any]) -> dict[str, Any]:
    from opentelemetry import trace

    from opspilot.auth.context import optional_principal
    from opspilot.observability.client import count
    from opspilot.observability.client import record as export
    from opspilot.runtime.fencing import current_fence

    level = record["level"].name if hasattr(record["level"], "name") else str(record["level"])
    event = (
        "log.error"
        if level in {"ERROR", "CRITICAL"}
        else "log.warning"
        if level == "WARNING"
        else "log.info"
    )
    extra = dict(record.get("extra", {}))
    if extra.get("security_event"):
        event = "security.denied"
        count("auth_denials", "security")
    diagnostic_codes = {
        "security_audit_database_unavailable": "AUDIT_DATABASE_UNAVAILABLE",
        "worker_database_unavailable": "WORKER_DATABASE_UNAVAILABLE",
        "tool_failed": "TOOL_FAILED",
    }
    if record.get("message") in diagnostic_codes:
        extra["diagnostic_code"] = diagnostic_codes[record["message"]]
    if record.get("message") == "security_audit_database_unavailable":
        event = "log.error"
        extra["phase"] = "security"
    user = optional_principal()
    if user is not None:
        extra.update(
            tenant_id=str(user.tenant_id) if user.tenant_id else None, actor_id=str(user.user_id)
        )
    fence = current_fence()
    if fence is not None:
        extra.update(run_id=str(fence.run), worker_epoch=fence.epoch)
    exception = record.get("exception")
    if exception is not None and getattr(exception, "type", None):
        extra["exception_class"] = exception.type.__name__
    fields = safe_attributes(extra)
    context = trace.get_current_span().get_span_context()
    output = {
        "event": event,
        "level": level
        if level in {"TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        else "WARNING",
        "time": datetime.now(UTC).isoformat(),
        **fields,
    }
    if context.is_valid:
        output.update(trace_id=f"{context.trace_id:032x}", span_id=f"{context.span_id:016x}")
    export(event, fields)
    return output


def sink(message: Any) -> None:
    try:
        output = safe_record(message.record)
        sys.stderr.write(json.dumps(output, sort_keys=True) + "\n")
    except Exception:
        sys.stderr.write('{"event":"log.error","status":"diagnostic_sink_failed"}\n')


class SafeStandardHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Keep severity and class/category; never format third-party exception/header content.
        sink(
            type(
                "SafeMessage",
                (),
                {
                    "record": {
                        "level": record.levelname,
                        "extra": {
                            "exception_class": record.exc_info[0].__name__
                            if record.exc_info and record.exc_info[0]
                            else ""
                        },
                        "message": "external",
                    }
                },
            )()
        )


def configure_logging() -> None:
    logger.remove()
    logger.add(sink, diagnose=False, backtrace=False, catch=True)
    handler = SafeStandardHandler()
    logging.basicConfig(handlers=[handler], level=logging.WARNING, force=True)
    for name in (
        "uvicorn.error",
        "uvicorn.access",
        "httpx",
        "httpcore",
        "opentelemetry",
        "sqlalchemy",
    ):
        child = logging.getLogger(name)
        child.handlers = [handler]
        child.propagate = False
