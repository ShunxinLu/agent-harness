import json
from pathlib import Path

from harness.evals import evaluate_session


def _write_manifest(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def test_evaluate_session_passes_when_manifest_is_clean(tmp_path: Path):
    project = tmp_path / "repo"
    runs = project / ".harness" / "runs"
    _write_manifest(
        runs / "manifest-a.json",
        {
            "session_run_id": "session-1",
            "project_run_id": "proj-1",
            "project": "repo",
            "policy_decisions": [{"action": "data_mode.validate", "allowed": True, "reason": "ok"}],
            "contract_finding": {"allowed": True, "reason": "ok"},
            "result_summary": {"execution_status": "ok", "failed": 0, "errors": 0},
        },
    )

    report = evaluate_session(project_root=project, session_run_id="session-1")
    assert report["passed"] is True
    assert report["total_manifests"] == 1
    assert report["findings"] == []


def test_evaluate_session_fails_on_policy_contract_or_test_issues(tmp_path: Path):
    project = tmp_path / "repo"
    runs = project / ".harness" / "runs"
    _write_manifest(
        runs / "manifest-b.json",
        {
            "session_run_id": "session-2",
            "project_run_id": "proj-2",
            "project": "repo",
            "policy_decisions": [{"action": "path.allowed_root", "allowed": False, "reason": "outside root"}],
            "contract_finding": {"allowed": False, "reason": "missing contract"},
            "result_summary": {"execution_status": "tool_missing", "failed": 1, "errors": 0},
        },
    )

    report = evaluate_session(project_root=project, session_run_id="session-2")
    assert report["passed"] is False
    assert report["total_manifests"] == 1
    assert len(report["findings"]) >= 3

