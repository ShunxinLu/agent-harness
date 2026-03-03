from pathlib import Path

from pydantic import ValidationError

from agent_harness.contracts import load_task_contract


def test_load_task_contract_valid(tmp_path: Path):
    project = tmp_path / "repo"
    contract_dir = project / ".harness"
    contract_dir.mkdir(parents=True)
    (contract_dir / "task-contract.yaml").write_text(
        """version: 1
goal: "Implement feature X"
constraints:
  - "No out-of-scope file edits"
files_in_scope:
  - "src/module.py"
acceptance_criteria:
  - "All tests pass"
validation_steps:
  - "harness-verify verify --project . --json --data-mode mock"
"""
    )

    contract = load_task_contract(project)
    assert contract.goal == "Implement feature X"
    assert contract.files_in_scope == ["src/module.py"]


def test_load_task_contract_missing_file_raises(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()

    try:
        load_task_contract(project)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_load_task_contract_invalid_payload_raises_validation_error(tmp_path: Path):
    project = tmp_path / "repo"
    contract_dir = project / ".harness"
    contract_dir.mkdir(parents=True)
    (contract_dir / "task-contract.yaml").write_text(
        """version: 1
goal: ""
constraints: []
files_in_scope: []
acceptance_criteria: []
validation_steps: []
"""
    )

    try:
        load_task_contract(project)
        assert False, "expected ValidationError"
    except ValidationError:
        pass

