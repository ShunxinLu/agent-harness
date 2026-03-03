import json
from pathlib import Path

from click.testing import CliRunner

from agent_harness.cache import HarnessCache
from agent_harness.config import ProjectConfig
from agent_harness.output import TestResult, TestRunResult
from agent_harness.verify import app


class _FakeCache:
    def __init__(self):
        self.store_calls = []

    def get_last_failed(self, project: str):
        return []

    def store_run(self, **kwargs):
        self.store_calls.append(kwargs)

    def close(self):
        return None


def _fake_run_tests(
    config: ProjectConfig,
    trace_enabled=False,
    extra_args=None,
    tracer=None,
    session_run_id=None,
    project_run_id=None,
):
    _ = (trace_enabled, extra_args, tracer, session_run_id, project_run_id)
    return TestRunResult(
        project=config.name,
        framework=config.framework,
        total=1,
        passed=1,
        failed=0,
        skipped=0,
        errors=0,
        duration=0.01,
        results=[TestResult(name=f"{config.name}::test_ok", status="passed", duration=0.01)],
        summary="ok",
    )


def test_cache_store_run_uses_parent_run_id(tmp_path: Path):
    db_path = tmp_path / "harness.duckdb"
    cache = HarnessCache(str(db_path))
    session_run_id = "session-run-1"

    cache.store_run(
        project="proj-a",
        run_id="proj-a-run-1",
        parent_run_id=session_run_id,
        results=[{"name": "test_a", "status": "passed", "duration": 0.01}],
    )
    cache.store_run(
        project="proj-b",
        run_id="proj-b-run-1",
        parent_run_id=session_run_id,
        results=[{"name": "test_b", "status": "failed", "duration": 0.02}],
    )

    rows = cache._conn.execute(
        "SELECT run_id, parent_run_id, project FROM run_history ORDER BY project"
    ).fetchall()
    assert rows == [
        ("proj-a-run-1", "session-run-1", "proj-a"),
        ("proj-b-run-1", "session-run-1", "proj-b"),
    ]

    # Default behavior still works for legacy callers.
    cache.store_run(
        project="proj-c",
        run_id="proj-c-run-1",
        results=[{"name": "test_c", "status": "passed", "duration": 0.01}],
    )
    parent = cache._conn.execute(
        "SELECT parent_run_id FROM run_history WHERE run_id = 'proj-c-run-1'"
    ).fetchone()
    assert parent[0] == "proj-c-run-1"

    failed = cache.get_last_failed("proj-b")
    assert failed == ["test_b"]

    cache.close()


def test_verify_json_output_includes_session_and_project_run_ids(monkeypatch, tmp_path: Path):
    project_a = tmp_path / "project_a"
    project_b = tmp_path / "project_b"
    project_a.mkdir()
    project_b.mkdir()

    projects = [
        ProjectConfig(path=project_a, name="project_a", framework="pytest", test_dir=project_a, command=["pytest"]),
        ProjectConfig(path=project_b, name="project_b", framework="pytest", test_dir=project_b, command=["pytest"]),
    ]

    fake_cache = _FakeCache()
    monkeypatch.setattr("agent_harness.verify.scan_projects", lambda base_dir: projects)
    monkeypatch.setattr("agent_harness.verify.get_default_cache", lambda: fake_cache)
    monkeypatch.setattr("agent_harness.verify.run_tests", _fake_run_tests)
    monkeypatch.setattr("agent_harness.verify.load_task_contract", lambda _path: None)

    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--all", "--base-dir", str(tmp_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["run_id"] == payload["session_run_id"]
    assert len(payload["projects"]) == 2
    assert all(project["session_run_id"] == payload["session_run_id"] for project in payload["projects"])

    project_run_ids = {project["project_run_id"] for project in payload["projects"]}
    assert len(project_run_ids) == 2

    assert len(fake_cache.store_calls) == 2
    cached_project_run_ids = {call["run_id"] for call in fake_cache.store_calls}
    cached_parent_run_ids = {call["parent_run_id"] for call in fake_cache.store_calls}
    assert cached_project_run_ids == project_run_ids
    assert cached_parent_run_ids == {payload["session_run_id"]}
