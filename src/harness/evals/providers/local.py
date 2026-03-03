"""Local deterministic eval provider."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .base import EvalProvider


class LocalEvalProvider(EvalProvider):
    """Wrap local deterministic manifest grading logic."""

    name = "local"

    def __init__(self, evaluator: Callable[[Path, Optional[str]], dict]):
        self._evaluator = evaluator

    def evaluate_session(self, project_root: Path, session_run_id: Optional[str] = None) -> dict:
        return self._evaluator(project_root, session_run_id)

