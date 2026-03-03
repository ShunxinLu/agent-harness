import asyncio
import json
from contextlib import contextmanager
from pathlib import Path

from agent_harness.config import ProjectConfig
from agent_harness.mcp_server import handle_run_tests
from agent_harness.observability import NoopSpan, start_span
from agent_harness.output import TestResult, TestRunResult
from agent_harness.verify import run_tests


class _FakeSpan:
    def __init__(self, name: str, initial_attributes: dict | None):
        self.name = name
        self.initial_attributes = initial_attributes or {}
        self.attributes: dict[str, object] = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


def test_start_span_defaults_to_noop_when_feature_flag_is_disabled():
    with start_span("harness.test.noop", {"harness.example": "value"}) as span:
        assert isinstance(span, NoopSpan)


def test_verify_run_tests_includes_run_ids_in_span_attributes(monkeypatch, tmp_path: Path):
    captured_spans: list[_FakeSpan] = []

    @contextmanager
    def _fake_start_span(name: str, attributes=None):
        span = _FakeSpan(name=name, initial_attributes=attributes)
        captured_spans.append(span)
        yield span

    class _FakeRunner:
        def run(self, extra_args=None):
            _ = extra_args
            return TestRunResult(
                project="proj",
                framework="pytest",
                total=1,
                passed=1,
                failed=0,
                skipped=0,
                errors=0,
                duration=0.05,
                results=[TestResult(name="proj::test_ok", status="passed", duration=0.05)],
                summary="ok",
                execution_status="ok",
            )

    monkeypatch.setattr("agent_harness.verify.start_span", _fake_start_span)
    monkeypatch.setattr("agent_harness.verify.get_runner", lambda _config: _FakeRunner())

    config = ProjectConfig(
        path=tmp_path,
        name="proj",
        framework="pytest",
        test_dir=tmp_path,
        command=["pytest"],
    )

    result = run_tests(
        config=config,
        trace_enabled=False,
        session_run_id="session-123",
        project_run_id="project-abc",
    )

    assert result.execution_status == "ok"
    assert captured_spans
    span = captured_spans[0]
    assert span.name == "harness.verify.project_run"
    assert span.initial_attributes["harness.session_run_id"] == "session-123"
    assert span.initial_attributes["harness.project_run_id"] == "project-abc"
    assert span.attributes["harness.execution_status"] == "ok"


def test_mcp_run_tests_emits_preflight_and_project_spans(monkeypatch, tmp_path: Path):
    captured_spans: list[_FakeSpan] = []

    @contextmanager
    def _fake_start_span(name: str, attributes=None):
        span = _FakeSpan(name=name, initial_attributes=attributes)
        captured_spans.append(span)
        yield span

    class _FakeRunner:
        def run(self, extra_args=None):
            _ = extra_args
            return TestRunResult(
                project="proj",
                framework="pytest",
                total=1,
                passed=1,
                failed=0,
                skipped=0,
                errors=0,
                duration=0.01,
                results=[TestResult(name="proj::test_ok", status="passed", duration=0.01)],
                summary="ok",
                execution_status="ok",
            )

    class _FakeCache:
        def get_last_failed(self, project):
            _ = project
            return []

        def store_run(self, **kwargs):
            _ = kwargs

        def close(self):
            return None

    project = ProjectConfig(
        path=tmp_path,
        name="proj",
        framework="pytest",
        test_dir=tmp_path,
        command=["pytest"],
    )

    monkeypatch.setattr("agent_harness.mcp_server.start_span", _fake_start_span)
    monkeypatch.setattr("agent_harness.mcp_server.detect_project", lambda path: project)
    monkeypatch.setattr("agent_harness.mcp_server.get_runner", lambda _cfg: _FakeRunner())
    monkeypatch.setattr("agent_harness.mcp_server.create_cache", lambda: _FakeCache())
    monkeypatch.setattr("agent_harness.mcp_server.load_task_contract", lambda path: None)
    monkeypatch.setattr(
        "agent_harness.mcp_server.write_project_run_manifest",
        lambda **kwargs: tmp_path / ".harness" / "runs" / "manifest.json",
    )

    response = asyncio.run(
        handle_run_tests(
            {
                "project_path": str(tmp_path),
                "json_output": True,
                "last_failed": False,
                "data_mode": "mock",
            }
        )
    )
    payload = json.loads(response[0].text)

    preflight = next(span for span in captured_spans if span.name == "harness.mcp.preflight")
    project_span = next(span for span in captured_spans if span.name == "harness.mcp.project_run")

    assert preflight.initial_attributes["harness.session_run_id"] == payload["session_run_id"]
    assert preflight.initial_attributes["harness.project_run_id"] == payload["project_run_id"]
    assert project_span.initial_attributes["harness.session_run_id"] == payload["session_run_id"]
    assert project_span.initial_attributes["harness.project_run_id"] == payload["project_run_id"]
    assert project_span.attributes["harness.execution_status"] == "ok"
