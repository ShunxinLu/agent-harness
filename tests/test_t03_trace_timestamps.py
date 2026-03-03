from datetime import datetime

from harness.trace_viewer import format_db_timestamp
from harness.tracing import TraceStore


def test_row_to_event_accepts_datetime_timestamp():
    store = TraceStore(":memory:")
    now = datetime.now()
    row = {
        "id": "event-1",
        "run_id": "run-1",
        "timestamp": now,
        "event_type": "info",
        "name": "test",
        "payload": "{}",
        "status": "ok",
        "error_message": None,
        "duration_ms": None,
    }

    event = store._row_to_event(row)
    assert event.timestamp == now
    store.close()


def test_row_to_event_accepts_iso_timestamp_string():
    store = TraceStore(":memory:")
    iso = "2026-03-03T12:34:56.123456"
    row = {
        "id": "event-2",
        "run_id": "run-2",
        "timestamp": iso,
        "event_type": "info",
        "name": "test",
        "payload": "{}",
        "status": "ok",
        "error_message": None,
        "duration_ms": None,
    }

    event = store._row_to_event(row)
    assert event.timestamp.isoformat() == iso
    store.close()


def test_trace_viewer_formats_datetime_and_string_timestamps():
    dt = datetime(2026, 3, 3, 9, 10, 11, 999999)
    assert format_db_timestamp(dt) == "2026-03-03 09:10:11"
    assert format_db_timestamp("2026-03-03T09:10:11.111111") == "2026-03-03T09:10:11"
    assert format_db_timestamp(None) == "N/A"

