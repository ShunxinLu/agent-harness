import json
from pathlib import Path

from agent_harness.config import ProjectConfig
from agent_harness.policy import PolicyEngine
from agent_harness.policy_backends import LocalPolicyBackend, OPAPolicyBackend
from agent_harness.policy_backends.opa import OPAPolicyBackend as _OPABackendClass


def _project(path: Path, name: str = "proj", framework: str = "pytest") -> ProjectConfig:
    return ProjectConfig(
        path=path,
        name=name,
        framework=framework,
        test_dir=path,
        command=["pytest"],
    )


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


def test_policy_engine_uses_local_backend_by_default():
    engine = PolicyEngine()
    assert isinstance(engine.backend, LocalPolicyBackend)


def test_policy_engine_uses_opa_backend_when_configured(monkeypatch):
    monkeypatch.setenv("HARNESS_POLICY_BACKEND", "opa")
    engine = PolicyEngine()
    assert isinstance(engine.backend, OPAPolicyBackend)


def test_opa_backend_parses_structured_allow_response(monkeypatch, tmp_path: Path):
    project_path = tmp_path / "repo"
    project_path.mkdir()

    payload = {
        "result": {
            "allowed": True,
            "decisions": [
                {
                    "action": "framework.allowlist",
                    "allowed": True,
                    "reason": "framework allowed",
                    "metadata": {"framework": "pytest"},
                }
            ],
        }
    }
    monkeypatch.setattr("harness.policy_backends.opa.request.urlopen", lambda req, timeout: _FakeHTTPResponse(payload))

    backend = _OPABackendClass(endpoint="http://opa.local/v1/data/harness/allow")
    result = backend.evaluate_verify_request([_project(project_path)], data_mode="mock")

    assert result.allowed is True
    assert result.decisions
    assert result.decisions[0].action == "framework.allowlist"


def test_opa_backend_denies_when_response_is_unreachable(tmp_path: Path):
    project_path = tmp_path / "repo"
    project_path.mkdir()

    backend = _OPABackendClass(endpoint="http://127.0.0.1:1/v1/data/harness/allow", timeout_seconds=0.001)
    result = backend.evaluate_verify_request([_project(project_path)], data_mode="mock")

    assert result.allowed is False
    assert result.decisions
    assert result.decisions[0].action == "opa.request"

