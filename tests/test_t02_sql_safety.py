from pathlib import Path

from agent_harness.cache import HarnessCache
from agent_harness.tracing import TraceStore, Tracer


def test_cache_get_errors_handles_global_and_project_filters(tmp_path: Path):
    cache = HarnessCache(str(tmp_path / "harness.duckdb"))
    cache.store_run(
        project="proj-a",
        run_id="proj-a-run-1",
        results=[
            {
                "name": "proj-a::test_failed",
                "status": "failed",
                "duration": 0.01,
                "error": {"message": "boom-a"},
            }
        ],
    )
    cache.store_run(
        project="proj-b",
        run_id="proj-b-run-1",
        results=[
            {
                "name": "proj-b::test_failed",
                "status": "failed",
                "duration": 0.01,
                "error": {"message": "boom-b"},
            }
        ],
    )

    # This previously generated malformed SQL when project=None.
    global_errors = cache.get_errors(limit=10)
    assert len(global_errors) == 2

    project_errors = cache.get_errors(project="proj-a", limit=10)
    assert len(project_errors) == 1
    assert project_errors[0]["test_name"] == "proj-a::test_failed"

    cache.close()


def test_trace_get_errors_handles_optional_run_filter():
    store = TraceStore(":memory:")
    tracer_a = Tracer(run_id="run-a", store=store)
    tracer_b = Tracer(run_id="run-b", store=store)

    tracer_a.log_error("step-a", RuntimeError("db failure a"), tool_name="runner-a")
    tracer_b.log_error("step-b", RuntimeError("db failure b"), tool_name="runner-b")

    all_errors = store.get_errors(limit=10)
    assert len(all_errors) == 2

    filtered_errors = store.get_errors(run_id="run-a", limit=10)
    assert len(filtered_errors) == 1
    assert filtered_errors[0]["run_id"] == "run-a"

    store.close()


def test_trace_analyze_patterns_uses_parameterized_pattern():
    store = TraceStore(":memory:")
    tracer = Tracer(run_id="run-safe", store=store)
    tracer.log_error("compile", RuntimeError("db compile failure"), tool_name="compiler")

    matching = store.analyze_patterns("compile", min_count=1)
    assert matching
    assert matching[0]["tool_name"] == "compiler"
    assert matching[0]["failure_count"] == 1

    # Should be treated as data, not SQL.
    injected_pattern = "x' OR 1=1 --"
    injected = store.analyze_patterns(injected_pattern, min_count=1)
    assert injected == []

    store.close()

