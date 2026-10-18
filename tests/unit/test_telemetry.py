from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from opspilot import telemetry


def test_propagation_links_and_no_secret_export(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", lambda *args: provider.get_tracer("test"))
    sentinel = "SENTINEL_PRIVATE_CREDENTIAL"
    with telemetry.span("http.api", run_id="run", credential=sentinel):
        context = telemetry.carrier()["traceparent"]
        with telemetry.span("graph.node", run_id="run"):
            with telemetry.span("mcp.client.tool", tool_name="get_customer"):
                headers = telemetry.carrier()
                with telemetry.span(
                    "http.mcp.server", parent=telemetry.propagator.extract(headers)
                ):
                    with telemetry.span("db.operation"):
                        pass
    with telemetry.span("graph.continuation", parent=Context(), linked=context):
        pass
    spans = exporter.get_finished_spans()
    initial = next(s for s in spans if s.name == "http.api")
    continuation = spans[-1]
    assert continuation.context.trace_id != initial.context.trace_id
    assert continuation.links[0].context.trace_id == initial.context.trace_id
    assert all(s.context.trace_id == initial.context.trace_id for s in spans[:-1])
    assert sentinel not in str([s.to_json() for s in spans])
    assert len(spans) == 6
    provider.shutdown()
