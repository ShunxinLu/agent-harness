import json
import os
from pathlib import Path

from click.testing import CliRunner

from agent_harness.verify import app


def test_init_project_creates_expected_artifacts(tmp_path: Path):
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["init-project", "--project", str(project_dir)])

    assert result.exit_code == 0, result.output

    harness_dir = project_dir / ".harness"
    expected_files = [
        harness_dir / "init.sh",
        harness_dir / "feature_list.json",
        harness_dir / "progress.md",
        harness_dir / "task-contract.yaml",
        harness_dir / "data-contract.yaml",
    ]
    for file_path in expected_files:
        assert file_path.exists(), f"missing {file_path}"

    feature_payload = json.loads((harness_dir / "feature_list.json").read_text())
    assert feature_payload["version"] == 1
    assert feature_payload["features"][0]["id"] == "FEAT-001"

    init_script = harness_dir / "init.sh"
    assert init_script.read_text().startswith("#!/usr/bin/env bash")
    assert os.access(init_script, os.X_OK)


def test_init_project_preserves_existing_files_without_force(tmp_path: Path):
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    runner = CliRunner()
    first = runner.invoke(app, ["init-project", "--project", str(project_dir)])
    assert first.exit_code == 0, first.output

    init_script = project_dir / ".harness" / "init.sh"
    init_script.write_text("custom-init\n")

    second = runner.invoke(app, ["init-project", "--project", str(project_dir)])
    assert second.exit_code == 0, second.output
    assert "Skipped: 5" in second.output
    assert init_script.read_text() == "custom-init\n"


def test_init_project_force_overwrites_existing_files(tmp_path: Path):
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    runner = CliRunner()
    first = runner.invoke(app, ["init-project", "--project", str(project_dir)])
    assert first.exit_code == 0, first.output

    init_script = project_dir / ".harness" / "init.sh"
    init_script.write_text("custom-init\n")

    forced = runner.invoke(app, ["init-project", "--project", str(project_dir), "--force"])
    assert forced.exit_code == 0, forced.output
    assert "Overwritten: 5" in forced.output
    assert init_script.read_text().startswith("#!/usr/bin/env bash")

