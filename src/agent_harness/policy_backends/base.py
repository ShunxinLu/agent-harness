"""Policy backend protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import ProjectConfig
from ..policy_models import PolicyResult


class PolicyBackend(ABC):
    """Abstract interface for policy evaluation backends."""

    @abstractmethod
    def evaluate_verify_request(self, projects: list[ProjectConfig], data_mode: str) -> PolicyResult:
        """Evaluate whether a verify request should be allowed."""
        raise NotImplementedError
