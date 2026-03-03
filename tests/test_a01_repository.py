from pathlib import Path

import duckdb

from harness.cache import HarnessCache
from harness.repository import DuckDBRepository
from harness.tracing import TraceStore, Tracer


def test_duckdb_repository_query_helpers():
    conn = duckdb.connect(":memory:")
    repo = DuckDBRepository(conn)

    repo.execute("CREATE TABLE items (name VARCHAR, value INTEGER)")
    repo.execute("INSERT INTO items (name, value) VALUES (?, ?)", ("alpha", 1))
    repo.execute("INSERT INTO items (name, value) VALUES (?, ?)", ("beta", 2))

    count_row = repo.fetchone("SELECT COUNT(*) FROM items")
    assert count_row[0] == 2

    rows = repo.fetchall("SELECT name FROM items ORDER BY name")
    assert rows == [("alpha",), ("beta",)]

    dict_rows = repo.fetchall_dict("SELECT name, value FROM items ORDER BY value DESC")
    assert dict_rows == [
        {"name": "beta", "value": 2},
        {"name": "alpha", "value": 1},
    ]

    repo.close()


def test_cache_and_trace_store_work_with_repository_layer(tmp_path: Path):
    db_path = tmp_path / "harness.duckdb"

    cache = HarnessCache(str(db_path))
    cache.store_run(
        project="proj-a",
        run_id="proj-a-run-1",
        parent_run_id="session-1",
        results=[{"name": "proj-a::test_ok", "status": "passed", "duration": 0.01}],
    )

    trend = cache.get_trend("proj-a", limit=5)
    assert len(trend) == 1
    assert trend[0]["run_id"] == "proj-a-run-1"
    assert trend[0]["parent_run_id"] == "session-1"
    assert hasattr(cache, "_repo")
    cache.close()

    store = TraceStore(str(db_path))
    tracer = Tracer(run_id="trace-run-1", store=store)
    tracer.log("step-1", event_type="info", tool_name="runner")

    events = store.query("SELECT run_id, name FROM traces WHERE run_id = ?", ("trace-run-1",))
    assert len(events) == 1
    assert events[0]["name"] == "step-1"
    assert hasattr(store, "_repo")
    store.close()
