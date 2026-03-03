import json
from pathlib import Path

from agent_harness.config import ProjectConfig
from agent_harness.manifest import write_project_run_manifest
from agent_harness.output import TestResult, TestRunResult


def test_write_project_run_manifest_creates_artifact(tmp_path: Path):
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    config = ProjectConfig(
        path=project_dir,
        name="repo",
        framework="pytest",
        test_dir=project_dir,
        command=["pytest"],
    )
    result = TestRunResult(
        project="repo",
        framework="pytest",
        total=2,
        passed=1,
        failed=1,
        skipped=0,
        errors=0,
        duration=0.5,
        execution_status="ok",
        results=[
            TestResult(name="test_ok", status="passed", duration=0.1),
            TestResult(name="test_fail", status="failed", duration=0.2),
        ],
    )

    manifest_path = write_project_run_manifest(
        project_config=config,
        session_run_id="session-1",
        project_run_id="project-1",
        data_mode="mock",
        last_failed_requested=False,
        last_failed_applied=False,
        policy_decisions=[{"action": "data_mode.validate", "allowed": True}],
        result=result,
        contract_finding={"project": "repo", "allowed": True, "reason": "ok"},
    )

    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text())
    assert payload["session_run_id"] == "session-1"
    assert payload["project_run_id"] == "project-1"
    assert payload["result_summary"]["failed"] == 1
    assert payload["failed_tests"] == ["test_fail"]

