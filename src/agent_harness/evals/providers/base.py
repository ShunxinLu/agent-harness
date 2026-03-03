"""Eval provider protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class EvalProvider(ABC):
    """Abstract interface for evaluation providers."""

    name: str

    @abstractmethod
    def evaluate_session(self, project_root: Path, session_run_id: Optional[str] = None) -> dict:
        """Evaluate manifests/session and return normalized report dictionary."""
        raise NotImplementedError

