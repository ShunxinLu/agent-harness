"""OpenTelemetry integration helpers for harness runtime spans."""

from .otel import (
    NoopSpan,
    is_otel_enabled,
    get_otel_status,
    start_span,
    set_span_attributes,
)

__all__ = [
    "NoopSpan",
    "is_otel_enabled",
    "get_otel_status",
    "start_span",
    "set_span_attributes",
]

