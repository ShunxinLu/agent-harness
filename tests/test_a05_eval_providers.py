import json
from pathlib import Path

from agent_harness.evals import evaluate_session


def _write_manifest(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _clean_manifest(session_run_id: str = "session-1") -> dict:
    return {
        "session_run_id": session_run_id,
        "project_run_id": "proj-1",
        "project": "repo",
        "policy_decisions": [{"action": "data_mode.validate", "allowed": True, "reason": "ok"}],
        "contract_finding": {"allowed": True, "reason": "ok"},
        "result_summary": {"execution_status": "ok", "failed": 0, "errors": 0},
    }


def test_eval_runner_defaults_to_local_provider(tmp_path: Path):
    project = tmp_path / "repo"
    runs = project / ".harness" / "runs"
    _write_manifest(runs / "manifest-a.json", _clean_manifest("session-local"))

    report = evaluate_session(project_root=project, session_run_id="session-local")

    assert report["provider"] == "local"
    assert report["passed"] is True
    assert report["total_manifests"] == 1


def test_eval_runner_unknown_provider_returns_normalized_error(tmp_path: Path):
    project = tmp_path / "repo"
    report = evaluate_session(project_root=project, session_run_id="session-x", provider="unknown-provider")

    assert report["passed"] is False
    assert report["provider"] == "unknown-provider"
    assert report["findings"]
    assert report["findings"][0]["rule"] == "eval.provider"


def test_promptfoo_provider_reports_missing_command(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("HARNESS_PROMPTFOO_COMMAND", raising=False)

    project = tmp_path / "repo"
    runs = project / ".harness" / "runs"
    _write_manifest(runs / "manifest-b.json", _clean_manifest("session-promptfoo"))

    report = evaluate_session(project_root=project, session_run_id="session-promptfoo", provider="promptfoo")

    assert report["provider"] == "promptfoo"
    assert report["passed"] is False
    assert report["external_provider"]["status"] == "error"
    assert any(f["rule"] == "external_eval.promptfoo" for f in report["findings"])

