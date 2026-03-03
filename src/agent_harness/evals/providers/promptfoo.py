"""Promptfoo eval provider adapter."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .base import EvalProvider


class PromptfooEvalProvider(EvalProvider):
    """Adapter that can run promptfoo and combine with local deterministic checks."""

    name = "promptfoo"

    def __init__(self, local_evaluator: Callable[[Path, Optional[str]], dict]):
        self._local_evaluator = local_evaluator

    def evaluate_session(self, project_root: Path, session_run_id: Optional[str] = None) -> dict:
        base_report = self._local_evaluator(project_root, session_run_id)
        command_text = os.getenv("HARNESS_PROMPTFOO_COMMAND", "").strip()
        timeout_seconds = int(os.getenv("HARNESS_EVAL_TIMEOUT_SECONDS", "300"))

        if not command_text:
            return self._with_external_failure(
                base_report,
                "HARNESS_PROMPTFOO_COMMAND is not configured",
                missing_dependency=False,
            )

        argv = shlex.split(command_text)
        executable = argv[0] if argv else "promptfoo"
        if not shutil.which(executable):
            return self._with_external_failure(
                base_report,
                f"Promptfoo executable not found: {executable}",
                missing_dependency=True,
            )

        try:
            completed = subprocess.run(
                argv,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            return self._with_external_failure(base_report, f"Promptfoo execution failed: {exc}", missing_dependency=False)

        if completed.returncode != 0:
            return self._with_external_failure(
                base_report,
                f"Promptfoo command returned {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}",
                missing_dependency=False,
            )

        base_report["external_provider"] = {
            "name": self.name,
            "status": "ok",
            "command": argv,
            "stdout_tail": completed.stdout.splitlines()[-20:],
        }
        return base_report

    def _with_external_failure(self, base_report: dict, message: str, missing_dependency: bool) -> dict:
        report = dict(base_report)
        findings = list(report.get("findings", []))
        findings.append(
            {
                "manifest_path": None,
                "project": None,
                "severity": "error",
                "rule": "external_eval.promptfoo",
                "message": message,
            }
        )
        report["findings"] = findings
        report["passed"] = False
        report["external_provider"] = {
            "name": self.name,
            "status": "error",
            "missing_dependency": missing_dependency,
            "message": message,
        }
        return report

