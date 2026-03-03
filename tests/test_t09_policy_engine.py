from pathlib import Path

from harness.config import ProjectConfig
from harness.policy import PolicyEngine


def _project(path: Path, name: str = "project", framework: str = "pytest") -> ProjectConfig:
    return ProjectConfig(
        path=path,
        name=name,
        framework=framework,
        test_dir=path,
        command=["pytest"],
    )


def test_policy_allows_standard_local_verify_request(tmp_path: Path):
    project_path = tmp_path / "repo"
    project_path.mkdir()
    result = PolicyEngine().evaluate_verify_request([_project(project_path)], data_mode="mock")

    assert result.allowed is True
    assert any(d.action == "framework.allowlist" and d.allowed for d in result.decisions)
    assert any(d.action == "path.exists" and d.allowed for d in result.decisions)


def test_policy_denies_mock_mode_when_real_aws_opt_in_enabled(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HARNESS_ALLOW_REAL_AWS", "1")
    project_path = tmp_path / "repo"
    project_path.mkdir()

    result = PolicyEngine().evaluate_verify_request([_project(project_path)], data_mode="mock")
    assert result.allowed is False
    assert any(d.action == "aws.mock_guard" and not d.allowed for d in result.decisions)


def test_policy_denies_projects_outside_allowed_root(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()

    result = PolicyEngine(allowed_project_root=allowed_root).evaluate_verify_request(
        [_project(outside_root)],
        data_mode="metadata",
    )

    assert result.allowed is False
    assert any(d.action == "path.allowed_root" and not d.allowed for d in result.decisions)

