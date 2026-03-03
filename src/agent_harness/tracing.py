"""
Harness Tracing - Agent execution tracing with DuckDB persistence.

Design Principle: Traces are stored in DuckDB, enabling complex SQL queries
across thousands of agent executions for trend analysis.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from contextlib import contextmanager

from pydantic import BaseModel

import duckdb

from .observability import set_span_attributes, start_span
from .repository import DuckDBRepository


class TraceEvent(BaseModel):
    """A single trace event."""
    id: str
    run_id: str
    timestamp: datetime
    event_type: str
    name: str
    payload: dict[str, Any] = {}
    status: str = "ok"  # ok, error, skipped
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None

    class Config:
        arbitrary_types_allowed = True

    def model_dump(self, **kwargs):
        """Custom serialization for DuckDB."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "name": self.name,
            "payload": json.dumps(self.payload),
            "status": self.status,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }


class TraceStore:
    """
    DuckDB-backed trace persistence.

    Enables complex SQL queries across agent runs:

    Example:
        SELECT tool_name, COUNT(*) as failures
        FROM traces
        WHERE status = 'error'
          AND error_type LIKE '%dbt compilation%'
        GROUP BY tool_name
        HAVING COUNT(*) > 3
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize trace store.

        Args:
            db_path: Path to DuckDB file. Uses in-memory if not specified.
        """
        self.db_path = db_path or ":memory:"

        if self.db_path != ":memory:":
            # Ensure directory exists
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)

        self._conn = duckdb.connect(self.db_path)
        self._repo = DuckDBRepository(self._conn)
        self._closed = False
        self._init_schema()

    def _init_schema(self):
        """Initialize the traces table schema."""
        self._repo.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                id VARCHAR PRIMARY KEY,
                run_id VARCHAR,
                timestamp TIMESTAMP,
                event_type VARCHAR,
                name VARCHAR,
                payload JSON,
                status VARCHAR,
                error_message VARCHAR,
                duration_ms DOUBLE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for common queries
        self._repo.execute("CREATE INDEX IF NOT EXISTS idx_traces_run_id ON traces(run_id)")
        self._repo.execute("CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(timestamp)")
        self._repo.execute("CREATE INDEX IF NOT EXISTS idx_traces_event_type ON traces(event_type)")
        self._repo.execute("CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status)")

    def store(self, event: TraceEvent):
        """Store a trace event."""
        self._repo.execute("""
            INSERT INTO traces (id, run_id, timestamp, event_type, name, payload, status, error_message, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.id,
            event.run_id,
            event.timestamp,
            event.event_type,
            event.name,
            json.dumps(event.payload),
            event.status,
            event.error_message,
            event.duration_ms,
        ))

    def query(self, sql: str, params: Optional[tuple[Any, ...]] = None) -> list[dict]:
        """Execute a SQL query and return results as dicts."""
        return self._repo.fetchall_dict(sql, params)

    def get_by_run(self, run_id: str) -> list[TraceEvent]:
        """Get all events for a specific run."""
        results = self.query(
            "SELECT * FROM traces WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        )
        return [self._row_to_event(r) for r in results]

    def get_errors(self, run_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        """Get error events, optionally filtered by run."""
        if run_id:
            sql = """
                SELECT * FROM traces
                WHERE run_id = ? AND status = 'error'
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (run_id, limit)
        else:
            sql = """
                SELECT * FROM traces
                WHERE status = 'error'
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (limit,)

        return self.query(sql, params)

    def analyze_patterns(self, error_pattern: str, min_count: int = 3) -> list[dict]:
        """
        Analyze error patterns across runs.

        Example: Find tools that fail with specific errors more than N times.
        """
        return self.query(
            """
                SELECT payload->>'tool_name' as tool_name,
                       COUNT(*) as failure_count
                FROM traces
                WHERE status = 'error'
                  AND error_message LIKE ?
                GROUP BY payload->>'tool_name'
                HAVING COUNT(*) >= ?
                ORDER BY failure_count DESC
            """,
            (f"%{error_pattern}%", min_count),
        )

    def _row_to_event(self, row: dict) -> TraceEvent:
        """Convert a database row to TraceEvent."""
        return TraceEvent(
            id=row["id"],
            run_id=row["run_id"],
            timestamp=self._coerce_timestamp(row["timestamp"]),
            event_type=row["event_type"],
            name=row["name"],
            payload=json.loads(row["payload"]) if row["payload"] else {},
            status=row["status"],
            error_message=row["error_message"],
            duration_ms=row["duration_ms"],
        )

    def _coerce_timestamp(self, value: Any) -> datetime:
        """Normalize DuckDB timestamp values to datetime."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)

        raise TypeError(f"Unsupported timestamp type: {type(value)!r}")

    def close(self):
        """Close the database connection."""
        if not self._closed:
            self._repo.close()
            self._closed = True

    @property
    def is_closed(self) -> bool:
        """Whether the underlying DuckDB connection has been closed."""
        return self._closed


class Tracer:
    """
    Capture and store trace events.

    Usage:
        tracer = Tracer()
        tracer.log("starting", context={"step": 1})
        tracer.log("tool_call", tool="search", args={...})
    """

    def __init__(self, run_id: Optional[str] = None, store: Optional[TraceStore] = None):
        """Initialize tracer.

        Args:
            run_id: Unique run identifier. Auto-generated if not provided.
            store: TraceStore instance. Creates default if not provided.
        """
        self.run_id = run_id or str(uuid.uuid4())
        self._store = store or TraceStore()
        self._events: list[TraceEvent] = []
        self._start_times: dict[str, datetime] = {}

    def log(self, name: str, event_type: str = "info", **kwargs):
        """Log a trace event."""
        now = datetime.now()

        # Calculate duration if we have a start time for this name
        duration_ms = None
        if name in self._start_times:
            duration_ms = (now - self._start_times[name]).total_seconds() * 1000
            del self._start_times[name]

        event = TraceEvent(
            id=str(uuid.uuid4()),
            run_id=self.run_id,
            timestamp=now,
            event_type=event_type,
            name=name,
            payload=kwargs,
            status="ok",
            duration_ms=duration_ms,
        )

        self._events.append(event)
        self._store.store(event)

    def log_error(self, name: str, error: Exception, **kwargs):
        """Log an error event."""
        now = datetime.now()

        event = TraceEvent(
            id=str(uuid.uuid4()),
            run_id=self.run_id,
            timestamp=now,
            event_type="error",
            name=name,
            payload=kwargs,
            status="error",
            error_message=str(error),
        )

        self._events.append(event)
        self._store.store(event)

    def start_timing(self, name: str):
        """Start timing an operation."""
        self._start_times[name] = datetime.now()

    def stop_timing(self, name: str):
        """Stop timing and log the operation with duration."""
        if name in self._start_times:
            self.log(name, event_type="timed", **{"timed": True})

    def get_events(self) -> list[TraceEvent]:
        """Get all captured events."""
        return self._events

    def export_json(self) -> str:
        """Export traces as JSON."""
        return json.dumps([e.model_dump() for e in self._events], indent=2, default=str)


# Global trace store for the default tracer
_default_store: Optional[TraceStore] = None


def get_default_db_path() -> str:
    """Get the default persistent DuckDB path used by the harness."""
    data_dir = Path.home() / ".harness" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "harness.duckdb")


def get_default_store(db_path: Optional[str] = None) -> TraceStore:
    """Get or create default trace store."""
    global _default_store
    if db_path is None:
        db_path = get_default_db_path()
    if _default_store is None or _default_store.is_closed:
        _default_store = TraceStore(db_path)
    return _default_store


def create_trace_store(db_path: Optional[str] = None) -> TraceStore:
    """Create a fresh trace-store connection to the default or provided database."""
    return TraceStore(db_path or get_default_db_path())


# Trace decorator
def trace(func=None, *, event_type: str = "function"):
    """
    Decorator to trace function execution.

    Usage:
        @trace
        def my_function(args):
            pass

        @trace(event_type="tool_call")
        def tool_function(args):
            pass
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            with start_span(
                "harness.trace.decorated_function",
                {
                    "harness.function_name": fn.__name__,
                    "harness.event_type": event_type,
                },
            ) as span:
                tracer = Tracer(store=get_default_store())
                set_span_attributes(span, {"harness.trace_run_id": tracer.run_id})

                # Log start
                tracer.start_timing(fn.__name__)
                tracer.log(fn.__name__, event_type=event_type, args=args, kwargs=kwargs)

                try:
                    result = fn(*args, **kwargs)
                    tracer.log(f"{fn.__name__}.complete", event_type=f"{event_type}.success")
                    set_span_attributes(span, {"harness.status": "ok"})
                    return result
                except Exception as e:
                    tracer.log_error(fn.__name__, e, event_type=event_type)
                    set_span_attributes(
                        span,
                        {
                            "harness.status": "error",
                            "harness.error_message": str(e),
                        },
                    )
                    raise

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


@contextmanager
def trace_context(name: str, event_type: str = "block"):
    """
    Context manager for tracing code blocks.

    Usage:
        with trace_context("agent_loop"):
            # ... code ...
    """
    with start_span(
        "harness.trace.context",
        {
            "harness.context_name": name,
            "harness.event_type": event_type,
        },
    ) as span:
        tracer = Tracer(store=get_default_store())
        set_span_attributes(span, {"harness.trace_run_id": tracer.run_id})
        tracer.log(f"{name}.start", event_type=f"{event_type}.start")

        try:
            yield tracer
            tracer.log(f"{name}.complete", event_type=f"{event_type}.complete")
            set_span_attributes(span, {"harness.status": "ok"})
        except Exception as e:
            tracer.log_error(name, e, event_type=f"{event_type}.error")
            set_span_attributes(
                span,
                {
                    "harness.status": "error",
                    "harness.error_message": str(e),
                },
            )
            raise
