"""OpenAI Evals provider adapter."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .base import EvalProvider


class OpenAIEvalsProvider(EvalProvider):
    """Adapter that can run an OpenAI Evals CLI command with local fallback grading."""

    name = "openai-evals"

    def __init__(self, local_evaluator: Callable[[Path, Optional[str]], dict]):
        self._local_evaluator = local_evaluator

    def evaluate_session(self, project_root: Path, session_run_id: Optional[str] = None) -> dict:
        base_report = self._local_evaluator(project_root, session_run_id)
        command_text = os.getenv("HARNESS_OPENAI_EVALS_COMMAND", "").strip()
        timeout_seconds = int(os.getenv("HARNESS_EVAL_TIMEOUT_SECONDS", "300"))

        if not command_text:
            return self._with_external_failure(base_report, "HARNESS_OPENAI_EVALS_COMMAND is not configured")

        argv = shlex.split(command_text)
        executable = argv[0] if argv else "oaieval"
        if not shutil.which(executable):
            return self._with_external_failure(base_report, f"OpenAI eval executable not found: {executable}")

        try:
            completed = subprocess.run(
                argv,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            return self._with_external_failure(base_report, f"OpenAI eval execution failed: {exc}")

        if completed.returncode != 0:
            return self._with_external_failure(
                base_report,
                f"OpenAI eval command returned {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}",
            )

        base_report["external_provider"] = {
            "name": self.name,
            "status": "ok",
            "command": argv,
            "stdout_tail": completed.stdout.splitlines()[-20:],
        }
        return base_report

    def _with_external_failure(self, base_report: dict, message: str) -> dict:
        report = dict(base_report)
        findings = list(report.get("findings", []))
        findings.append(
            {
                "manifest_path": None,
                "project": None,
                "severity": "error",
                "rule": "external_eval.openai_evals",
                "message": message,
            }
        )
        report["findings"] = findings
        report["passed"] = False
        report["external_provider"] = {
            "name": self.name,
            "status": "error",
            "message": message,
        }
        return report

