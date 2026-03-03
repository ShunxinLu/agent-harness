from pathlib import Path

from click.testing import CliRunner

from agent_harness.config import ProjectConfig
from agent_harness.output import TestResult, TestRunResult, format_summary
from agent_harness.verify import app


class _FakeCache:
    def get_last_failed(self, project: str):
        return []

    def store_run(self, **kwargs):
        return None

    def close(self):
        return None


def test_format_summary_can_avoid_stdout_side_effects(capsys):
    result = TestRunResult(
        project="proj",
        framework="pytest",
        total=1,
        passed=1,
        results=[TestResult(name="proj::test_ok", status="passed", duration=0.01)],
    )

    status = format_summary(result, print_output=False)
    captured = capsys.readouterr()

    assert status == "PASSED"
    assert captured.out == ""


def test_verify_exits_non_zero_on_execution_failure(monkeypatch, tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()

    projects = [
        ProjectConfig(path=project, name="project", framework="pytest", test_dir=project, command=["pytest"])
    ]

    def _runner_error_result(*args, **kwargs):
        return TestRunResult(
            project="project",
            framework="pytest",
            total=0,
            passed=0,
            failed=0,
            skipped=0,
            errors=0,
            summary="pytest not found",
            execution_status="tool_missing",
        )

    monkeypatch.setattr("harness.verify.scan_projects", lambda base_dir: projects)
    monkeypatch.setattr("harness.verify.get_default_cache", lambda: _FakeCache())
    monkeypatch.setattr("harness.verify.run_tests", _runner_error_result)

    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--all", "--base-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "Execution failures: 1" in result.output

