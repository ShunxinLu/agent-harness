"""Feature-flagged OpenTelemetry span helpers.

The harness keeps local DuckDB traces as the default. OpenTelemetry is optional
and enabled only when HARNESS_OTEL_ENABLED=1.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Optional


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_otel_enabled() -> bool:
    """Whether OpenTelemetry integration is explicitly enabled."""
    return _as_bool(os.getenv("HARNESS_OTEL_ENABLED", "0"))


@dataclass
class _OtelState:
    enabled: bool = False
    initialized: bool = False
    reason: str = "disabled"
    exporter: str = "none"


_STATE = _OtelState()
_STATE_LOCK = threading.Lock()
_TRACER = None


class NoopSpan:
    """No-op span object used when OpenTelemetry is disabled/unavailable."""

    def set_attribute(self, key: str, value: Any):
        _ = (key, value)

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None):
        _ = (name, attributes)


def _sanitize_attribute_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return json.dumps(value, default=str, sort_keys=True)
    return str(value)


def _initialize_otel():
    global _TRACER

    if _STATE.initialized:
        return

    with _STATE_LOCK:
        if _STATE.initialized:
            return

        if not is_otel_enabled():
            _STATE.enabled = False
            _STATE.initialized = True
            _STATE.reason = "HARNESS_OTEL_ENABLED is not set"
            return

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
        except Exception as exc:  # pragma: no cover - exercised in dependency-light envs
            _STATE.enabled = False
            _STATE.initialized = True
            _STATE.reason = f"OpenTelemetry import failed: {exc}"
            return

        service_name = os.getenv("HARNESS_OTEL_SERVICE_NAME", "harness")
        service_namespace = os.getenv("HARNESS_OTEL_SERVICE_NAMESPACE", "agent-harness")
        exporter = os.getenv("HARNESS_OTEL_EXPORTER", "none").strip().lower()
        _STATE.exporter = exporter

        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.namespace": service_namespace,
                }
            )
        )

        try:
            if exporter == "otlp":
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                endpoint = os.getenv("HARNESS_OTEL_OTLP_ENDPOINT")
                if endpoint:
                    span_exporter = OTLPSpanExporter(endpoint=endpoint)
                else:
                    span_exporter = OTLPSpanExporter()
                provider.add_span_processor(BatchSpanProcessor(span_exporter))
            elif exporter == "console":
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        except Exception as exc:  # pragma: no cover - exporter-specific environment failures
            _STATE.enabled = False
            _STATE.initialized = True
            _STATE.reason = f"OpenTelemetry exporter init failed: {exc}"
            return

        # If another provider is already configured, this call is ignored by OTel.
        # That is acceptable; we still acquire a tracer from the active provider.
        trace.set_tracer_provider(provider)
        scope_name = os.getenv("HARNESS_OTEL_SCOPE_NAME", "harness")
        _TRACER = trace.get_tracer(scope_name, "0.1.0")

        _STATE.enabled = True
        _STATE.initialized = True
        _STATE.reason = "initialized"


def get_otel_status() -> dict[str, Any]:
    """Return current OpenTelemetry integration status."""
    _initialize_otel()
    return {
        "enabled": _STATE.enabled,
        "initialized": _STATE.initialized,
        "reason": _STATE.reason,
        "exporter": _STATE.exporter,
    }


def set_span_attributes(span: Any, attributes: Optional[dict[str, Any]]):
    """Set span attributes, coercing unsupported types to strings."""
    if not attributes:
        return
    for key, value in attributes.items():
        sanitized = _sanitize_attribute_value(value)
        if sanitized is None:
            continue
        try:
            span.set_attribute(key, sanitized)
        except Exception:
            continue


@contextmanager
def start_span(name: str, attributes: Optional[dict[str, Any]] = None):
    """Start an OpenTelemetry span when enabled, else yield a no-op span."""
    _initialize_otel()
    if not _STATE.enabled or _TRACER is None:
        span = NoopSpan()
        set_span_attributes(span, attributes)
        yield span
        return

    with _TRACER.start_as_current_span(name) as span:
        set_span_attributes(span, attributes)
        yield span

