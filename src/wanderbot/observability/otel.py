"""OpenTelemetry tracing setup.

OTel is the portability layer; LangSmith (set via env: ``LANGCHAIN_TRACING_V2``)
is the agent-native lens and works automatically for LangChain/LangGraph. Spans
flow asynchronously and add no request latency.
"""

from __future__ import annotations

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

_CONFIGURED = False


def setup_tracing(settings: Settings | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    settings = settings or get_settings()
    endpoint = getattr(settings, "otel_exporter_otlp_endpoint", None)

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "wanderbot"}))
        if endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        _CONFIGURED = True
        log.info("otel_configured", endpoint=endpoint or "console-only")
    except Exception as exc:  # pragma: no cover - optional dependency path
        log.warning("otel_setup_failed", error=str(exc))
