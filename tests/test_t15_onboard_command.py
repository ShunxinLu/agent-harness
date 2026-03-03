from pathlib import Path

from click.testing import CliRunner

from agent_harness.config import ProjectConfig
from agent_harness.output import TestRunResult
from agent_harness.verify import app


def _passing_result() -> TestRunResult:
    return TestRunResult(
        project="repo",
        framework="pytest",
        total=1,
        passed=1,
        failed=0,
        skipped=0,
        errors=0,
        duration=0.1,
        summary="ok",
        execution_status="ok",
    )


def _failing_result() -> TestRunResult:
    return TestRunResult(
        project="repo",
        framework="pytest",
        total=0,
        passed=0,
        failed=0,
        skipped=0,
        errors=0,
        duration=0.1,
        summary="pytest not found",
        execution_status="tool_missing",
    )


def test_onboard_creates_project_yaml_and_artifacts(monkeypatch, tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()

    config = ProjectConfig(
        path=project,
        name="repo",
        framework="pytest",
        test_dir=project / "tests",
        command=["pytest"],
    )
    monkeypatch.setattr("harness.verify.detect_project", lambda project_root: config)
    monkeypatch.setattr("harness.verify.run_tests", lambda *args, **kwargs: _passing_result())

    runner = CliRunner()
    result = runner.invoke(app, ["onboard", "--project", str(project)])
    assert result.exit_code == 0, result.output

    harness_dir = project / ".harness"
    assert (harness_dir / "project.yaml").exists()
    assert (harness_dir / "init.sh").exists()
    assert (harness_dir / "feature_list.json").exists()


def test_onboard_fails_when_baseline_verification_fails(monkeypatch, tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()

    config = ProjectConfig(
        path=project,
        name="repo",
        framework="pytest",
        test_dir=project / "tests",
        command=["pytest"],
    )
    monkeypatch.setattr("harness.verify.detect_project", lambda project_root: config)
    monkeypatch.setattr("harness.verify.run_tests", lambda *args, **kwargs: _failing_result())

    runner = CliRunner()
    result = runner.invoke(app, ["onboard", "--project", str(project)])
    assert result.exit_code == 1

