"""
Run manifest helpers.
"""

import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .config import ProjectConfig
from .output import TestRunResult


class ProjectRunManifest(BaseModel):
    """Manifest artifact for a single project run."""

    version: int = 1
    created_at: str
    session_run_id: str
    project_run_id: str
    project: str
    project_path: str
    framework: str
    data_mode: str
    last_failed_requested: bool
    last_failed_applied: bool
    policy_decisions: list[dict] = Field(default_factory=list)
    contract_finding: Optional[dict] = None
    result_summary: dict
    failed_tests: list[str] = Field(default_factory=list)


def write_project_run_manifest(
    project_config: ProjectConfig,
    session_run_id: str,
    project_run_id: str,
    data_mode: str,
    last_failed_requested: bool,
    last_failed_applied: bool,
    policy_decisions: list[dict],
    result: TestRunResult,
    contract_finding: Optional[dict] = None,
) -> Path:
    """Persist run manifest under .harness/runs in project root."""
    failed_tests = [test.name for test in result.results if test.status in {"failed", "error"}]
    manifest = ProjectRunManifest(
        created_at=datetime.now(UTC).isoformat(),
        session_run_id=session_run_id,
        project_run_id=project_run_id,
        project=project_config.name,
        project_path=str(project_config.path),
        framework=project_config.framework,
        data_mode=data_mode,
        last_failed_requested=last_failed_requested,
        last_failed_applied=last_failed_applied,
        policy_decisions=policy_decisions,
        contract_finding=contract_finding,
        result_summary={
            "total": result.total,
            "passed": result.passed,
            "failed": result.failed,
            "skipped": result.skipped,
            "errors": result.errors,
            "duration": result.duration,
            "execution_status": result.execution_status,
        },
        failed_tests=failed_tests,
    )

    manifest_dir = project_config.path / ".harness" / "runs"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{session_run_id}-{project_run_id}.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n")
    return manifest_path

