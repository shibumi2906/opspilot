"""Explicit, allowlisted telemetry: never record payloads, SQL or exception bodies."""

from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Link, Span, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from opspilot.config import Settings
from opspilot.observability import client as observations
from opspilot.observability.protocol import safe_attributes

propagator = TraceContextTextMapPropagator()
_initialized = False
ALLOWED = {
    "job_id",
    "worker_epoch",
    "tenant_id",
    "actor_id",
    "run_id",
    "action_id",
    "tool_name",
    "status",
    "error_code",
    "operation",
    "input_tokens",
    "output_tokens",
    "unknown_usage_count",
    "active_seconds",
}


def configure(settings: Settings, service: str) -> None:
    global _initialized
    if _initialized or not settings.otel_endpoint:
        return
    observations.configure(settings, service)
    from opspilot.logging import configure_logging

    configure_logging()
    provider = TracerProvider(resource=Resource({"service.name": service}))
    provider.add_span_processor(
        BatchSpanProcessor(
            observations.SafeSpanExporter(),
            max_queue_size=256,
            max_export_batch_size=32,
            schedule_delay_millis=200,
            export_timeout_millis=1500,
        )
    )
    trace.set_tracer_provider(provider)
    _initialized = True


@contextmanager
def span(
    name: str,
    *,
    parent: Context | None = None,
    linked: str | None = None,
    end_on_exit: bool = True,
    **attributes: Any,
) -> Iterator[Span]:
    from opspilot.auth.context import optional_principal
    from opspilot.auth.service_context import verified_context
    from opspilot.runtime.fencing import current_fence

    inherited = getattr(trace.get_current_span(), "attributes", {}) or {}
    for key in ("tenant_id", "actor_id", "run_id", "job_id", "worker_epoch"):
        if key in inherited:
            attributes.setdefault(key, inherited[key])
    verified = verified_context()
    if verified and verified.get("run"):
        attributes.setdefault("run_id", verified["run"])
    user = optional_principal()
    fence = current_fence()
    if user is not None:
        attributes.setdefault("tenant_id", str(user.tenant_id) if user.tenant_id else None)
        attributes.setdefault("actor_id", str(user.user_id))
    if fence is not None:
        attributes.setdefault("run_id", str(fence.run))
        attributes.setdefault("worker_epoch", fence.epoch)
    links = []
    if linked:
        context = trace.get_current_span(
            propagator.extract({"traceparent": linked})
        ).get_span_context()
        if context.is_valid:
            links.append(Link(context))
    with trace.get_tracer("opspilot").start_as_current_span(
        name,
        context=parent,
        links=links,
        record_exception=False,
        end_on_exit=end_on_exit,
        set_status_on_exception=False,
        attributes=safe_attributes(
            {
                key: value
                for key, value in attributes.items()
                if key in ALLOWED and value is not None
            }
        ),
    ) as current:
        try:
            yield current
        except BaseException:
            if current.is_recording():
                current.set_status(Status(StatusCode.ERROR, "OPERATION_INTERRUPTED"))
            raise


def carrier() -> dict[str, str]:
    headers: dict[str, str] = {}
    propagator.inject(headers)
    return headers


P = ParamSpec("P")
R = TypeVar("R")


def traced(
    name: str,
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    def decorate(
        function: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(function)
        async def invoke(*args: P.args, **kwargs: P.kwargs) -> R:
            with span(name):
                return await function(*args, **kwargs)

        return invoke

    return decorate


class TraceMiddleware:
    def __init__(self, app: Any, name: str) -> None:
        self.app, self.name = app, name

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode(): v.decode() for k, v in scope["headers"] if k == b"traceparent"}
        import time

        from opspilot.observability.client import count

        started = time.monotonic()
        status = 500
        # API clients cannot choose another tenant's trace. Signed MCP requests may propagate.
        parent = propagator.extract(headers) if self.name == "http.mcp.server" else Context()
        with span(self.name, parent=parent, end_on_exit=False) as current:
            ended = False

            async def observe(message: Any) -> None:
                nonlocal status, ended
                if message["type"] == "http.response.start":
                    status = message["status"]
                    if any(
                        k.lower() == b"content-type" and b"text/event-stream" in v
                        for k, v in message.get("headers", [])
                    ):
                        current.end()
                        ended = True
                await send(message)

            try:
                await self.app(scope, receive, observe)
            finally:
                count("http_requests", "api" if self.name == "http.api" else "mcp")
                count("http_duration_ms", "api", round((time.monotonic() - started) * 1000))
                if status >= 500:
                    count("upstream_errors", "api")
                if not ended:
                    current.end()
