"""
Manifest-based eval checks for harness runs.
"""

import json
import os
from pathlib import Path
from typing import Optional

from .providers import LocalEvalProvider, OpenAIEvalsProvider, PromptfooEvalProvider


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


def evaluate_manifest(path: Path) -> dict:
    """Evaluate a single project run manifest."""
    manifest = _load_manifest(path)
    findings = []

    for decision in manifest.get("policy_decisions", []):
        if not decision.get("allowed", False):
            findings.append(
                {
                    "severity": "error",
                    "rule": "policy_decisions",
                    "message": f"Policy denied action {decision.get('action')}: {decision.get('reason')}",
                }
            )

    contract_finding = manifest.get("contract_finding")
    if contract_finding and not contract_finding.get("allowed", False):
        findings.append(
            {
                "severity": "error",
                "rule": "task_contract",
                "message": contract_finding.get("reason", "Task contract invalid"),
            }
        )

    result_summary = manifest.get("result_summary", {})
    execution_status = result_summary.get("execution_status", "ok")
    if execution_status != "ok":
        findings.append(
            {
                "severity": "error",
                "rule": "execution_status",
                "message": f"Execution status is {execution_status}",
            }
        )

    if result_summary.get("failed", 0) > 0 or result_summary.get("errors", 0) > 0:
        findings.append(
            {
                "severity": "error",
                "rule": "test_outcome",
                "message": "Manifest reports failed/error test outcomes",
            }
        )

    return {
        "manifest_path": str(path),
        "session_run_id": manifest.get("session_run_id"),
        "project_run_id": manifest.get("project_run_id"),
        "project": manifest.get("project"),
        "passed": len(findings) == 0,
        "findings": findings,
    }


def _evaluate_session_local(project_root: Path, session_run_id: Optional[str] = None) -> dict:
    """Evaluate all manifests for a session under .harness/runs."""
    runs_dir = project_root / ".harness" / "runs"
    if not runs_dir.exists():
        return {
            "passed": False,
            "error": f"Runs directory not found: {runs_dir}",
            "session_run_id": session_run_id,
            "manifest_reports": [],
            "findings": [],
        }

    manifest_paths = sorted(runs_dir.glob("*.json"))
    if not manifest_paths:
        return {
            "passed": False,
            "error": f"No manifests found in {runs_dir}",
            "session_run_id": session_run_id,
            "manifest_reports": [],
            "findings": [],
        }

    if session_run_id is None:
        latest_manifest = max(manifest_paths, key=lambda p: p.stat().st_mtime)
        session_run_id = _load_manifest(latest_manifest).get("session_run_id")

    selected = []
    for path in manifest_paths:
        manifest = _load_manifest(path)
        if manifest.get("session_run_id") == session_run_id:
            selected.append(path)

    if not selected:
        return {
            "passed": False,
            "error": f"No manifests found for session_run_id={session_run_id}",
            "session_run_id": session_run_id,
            "manifest_reports": [],
            "findings": [],
        }

    reports = [evaluate_manifest(path) for path in selected]
    findings = []
    for report in reports:
        for finding in report["findings"]:
            findings.append(
                {
                    "manifest_path": report["manifest_path"],
                    "project": report.get("project"),
                    "severity": finding["severity"],
                    "rule": finding["rule"],
                    "message": finding["message"],
                }
            )

    return {
        "passed": all(report["passed"] for report in reports),
        "session_run_id": session_run_id,
        "total_manifests": len(reports),
        "passed_manifests": sum(1 for report in reports if report["passed"]),
        "manifest_reports": reports,
        "findings": findings,
    }


def _normalize_report(report: dict, provider_name: str, session_run_id: Optional[str]) -> dict:
    """Normalize provider output shape for downstream CLI/MCP consumers."""
    normalized = dict(report)
    normalized["provider"] = provider_name
    normalized.setdefault("passed", False)
    normalized.setdefault("session_run_id", session_run_id)
    normalized.setdefault("total_manifests", 0)
    normalized.setdefault("passed_manifests", 0)
    normalized.setdefault("manifest_reports", [])
    normalized.setdefault("findings", [])
    return normalized


def _resolve_provider(provider_name: str):
    provider_name = provider_name.strip().lower()
    if provider_name == "local":
        return LocalEvalProvider(_evaluate_session_local)
    if provider_name == "promptfoo":
        return PromptfooEvalProvider(_evaluate_session_local)
    if provider_name in {"openai-evals", "openai_evals"}:
        return OpenAIEvalsProvider(_evaluate_session_local)
    return None


def evaluate_session(
    project_root: Path,
    session_run_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> dict:
    """Evaluate manifests for a session using selected provider backend."""
    provider_name = provider or os.getenv("HARNESS_EVAL_PROVIDER", "local")
    provider_instance = _resolve_provider(provider_name)

    if provider_instance is None:
        return {
            "passed": False,
            "session_run_id": session_run_id,
            "provider": provider_name,
            "error": f"Unsupported eval provider: {provider_name}",
            "manifest_reports": [],
            "findings": [
                {
                    "manifest_path": None,
                    "project": None,
                    "severity": "error",
                    "rule": "eval.provider",
                    "message": f"Unsupported eval provider: {provider_name}",
                }
            ],
        }

    report = provider_instance.evaluate_session(project_root, session_run_id)
    return _normalize_report(report, provider_instance.name, session_run_id)
