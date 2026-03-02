"""
Zero-Trust Agent Harness

A unified test harness for Claude Code development with:
- Unified test running with JSON output optimization
- Project scaffolding with sandbox generation
- Trace-based debugging for agent execution
"""

__version__ = "0.1.0"


def __getattr__(name):
    """Lazy imports to avoid circular dependencies."""
    if name in ("SandboxConfig", "SandboxManager", "get_s3_client", "get_duckdb_connection"):
        from .sandbox import SandboxConfig, SandboxManager, get_s3_client, get_duckdb_connection
        return {"SandboxConfig": SandboxConfig, "SandboxManager": SandboxManager, "get_s3_client": get_s3_client, "get_duckdb_connection": get_duckdb_connection}[name]
    if name in ("trace", "Tracer", "TraceEvent"):
        from .tracing import trace, Tracer, TraceEvent
        return {"trace": trace, "Tracer": Tracer, "TraceEvent": TraceEvent}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {__name__!r}")


__all__ = [
    "SandboxConfig",
    "SandboxManager",
    "get_s3_client",
    "get_duckdb_connection",
    "trace",
    "Tracer",
    "TraceEvent",
]
