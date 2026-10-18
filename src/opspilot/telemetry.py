"""Explicit, allowlisted telemetry: never record payloads, SQL or exception bodies."""

from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Link, Span, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from opspilot.config import Settings

propagator = TraceContextTextMapPropagator()
_initialized = False
ALLOWED = {
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
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_endpoint, timeout=1),
            schedule_delay_millis=200,
            export_timeout_millis=1500,
        )
    )
    trace.set_tracer_provider(provider)
    _initialized = True


@contextmanager
def span(
    name: str, *, parent: Context | None = None, linked: str | None = None, **attributes: Any
) -> Iterator[Span]:
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
        set_status_on_exception=False,
        attributes={
            key: value for key, value in attributes.items() if key in ALLOWED and value is not None
        },
    ) as current:
        try:
            yield current
        except BaseException:
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
        with span(self.name, parent=propagator.extract(headers)):
            await self.app(scope, receive, send)
