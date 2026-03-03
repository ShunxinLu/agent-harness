"""
Task/data contract loading and validation utilities.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class TaskContract(BaseModel):
    """Required task contract fields for non-trivial runs."""

    version: int = 1
    goal: str = Field(min_length=1)
    constraints: list[str] = Field(min_length=1)
    files_in_scope: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    validation_steps: list[str] = Field(min_length=1)


def get_task_contract_path(project_root: Path) -> Path:
    return project_root / ".harness" / "task-contract.yaml"


def load_task_contract(project_root: Path) -> TaskContract:
    """Load and validate task contract from project root."""
    path = get_task_contract_path(project_root)
    if not path.exists():
        raise FileNotFoundError(f"Task contract not found: {path}")

    payload = yaml.safe_load(path.read_text()) or {}
    return TaskContract.model_validate(payload)

