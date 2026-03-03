"""
Session and feature-ledger helpers for long-running harness workflows.
"""

import json
import subprocess
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class FeatureEntry(BaseModel):
    """A single feature in the .harness feature ledger."""

    id: str
    category: str
    description: str
    priority: str = "medium"
    steps: list[str] = Field(default_factory=list)
    passes: bool = False
    last_verified_at: Optional[str] = None
    evidence: list[str] = Field(default_factory=list)


class FeatureLedger(BaseModel):
    """Feature ledger schema."""

    version: int = 1
    features: list[FeatureEntry] = Field(default_factory=list)


def get_feature_ledger_path(project_root: Path) -> Path:
    """Get feature ledger path under .harness."""
    return project_root / ".harness" / "feature_list.json"


def load_feature_ledger(project_root: Path) -> FeatureLedger:
    """Load and validate feature ledger from project root."""
    ledger_path = get_feature_ledger_path(project_root)
    if not ledger_path.exists():
        raise FileNotFoundError(f"Feature ledger not found: {ledger_path}")

    payload = json.loads(ledger_path.read_text())
    return FeatureLedger.model_validate(payload)


def save_feature_ledger(project_root: Path, ledger: FeatureLedger) -> Path:
    """Persist validated feature ledger."""
    ledger_path = get_feature_ledger_path(project_root)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger.model_dump(mode="json"), indent=2) + "\n")
    return ledger_path


def get_next_feature(project_root: Path) -> Optional[FeatureEntry]:
    """Select the next highest-priority feature that has not passed yet."""
    ledger = load_feature_ledger(project_root)
    pending = [feature for feature in ledger.features if not feature.passes]
    if not pending:
        return None

    return sorted(
        pending,
        key=lambda feature: (
            PRIORITY_ORDER.get(feature.priority.lower(), PRIORITY_ORDER["low"]),
            feature.id,
        ),
    )[0]


def update_feature_status(
    project_root: Path,
    feature_id: str,
    passes: bool,
    evidence: Optional[list[str]] = None,
) -> FeatureEntry:
    """
    Update feature pass/fail status with evidence requirements.

    Rules:
    - Setting passes=True requires at least one evidence reference.
    - Non-status metadata is immutable through this operation.
    """
    ledger = load_feature_ledger(project_root)
    evidence_refs = [ref for ref in (evidence or []) if ref.strip()]

    if passes and not evidence_refs:
        raise ValueError("Cannot mark feature as passed without evidence references")

    target: Optional[FeatureEntry] = None
    for feature in ledger.features:
        if feature.id == feature_id:
            target = feature
            break

    if target is None:
        raise ValueError(f"Feature not found: {feature_id}")

    target.passes = passes
    target.evidence = evidence_refs
    target.last_verified_at = datetime.now(UTC).isoformat() if passes else None

    save_feature_ledger(project_root, ledger)
    return target


def collect_resume_context(project_root: Path, run_smoke_check: bool = False) -> dict:
    """
    Collect startup bearings context for a new/restarted agent session.

    Returns summary with required artifact checks, recent progress, next feature,
    and optional smoke-check execution result.
    """
    harness_dir = project_root / ".harness"
    required_files = {
        "init_script": harness_dir / "init.sh",
        "feature_ledger": harness_dir / "feature_list.json",
        "progress_log": harness_dir / "progress.md",
    }

    missing = [str(path) for path in required_files.values() if not path.exists()]
    has_required_artifacts = len(missing) == 0

    progress_tail = []
    progress_path = required_files["progress_log"]
    if progress_path.exists():
        lines = progress_path.read_text().splitlines()
        progress_tail = lines[-20:]

    git_log = []
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", "5"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            git_log = [line for line in result.stdout.splitlines() if line.strip()]
    except Exception:
        git_log = []

    next_feature = None
    if required_files["feature_ledger"].exists():
        try:
            feature = get_next_feature(project_root)
            next_feature = feature.model_dump(mode="json") if feature else None
        except Exception:
            next_feature = None

    smoke_result = {"requested": run_smoke_check, "executed": False, "exit_code": None, "output_tail": []}
    if run_smoke_check and required_files["init_script"].exists():
        try:
            smoke = subprocess.run(
                [str(required_files["init_script"])],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=180,
            )
            combined_output = (smoke.stdout or "") + ("\n" + smoke.stderr if smoke.stderr else "")
            smoke_result = {
                "requested": True,
                "executed": True,
                "exit_code": smoke.returncode,
                "output_tail": combined_output.splitlines()[-20:],
            }
        except Exception as exc:
            smoke_result = {
                "requested": True,
                "executed": True,
                "exit_code": -1,
                "output_tail": [f"smoke-check execution error: {exc}"],
            }

    return {
        "project_root": str(project_root),
        "has_required_artifacts": has_required_artifacts,
        "missing_artifacts": missing,
        "progress_tail": progress_tail,
        "recent_git_log": git_log,
        "next_feature": next_feature,
        "smoke_check": smoke_result,
    }
