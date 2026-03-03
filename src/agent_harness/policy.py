"""
Runtime policy evaluation for harness operations.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .config import ProjectConfig
from .policy_backends import LocalPolicyBackend, OPAPolicyBackend, PolicyBackend
from .policy_models import PolicyResult


class PolicyEngine:
    """Policy evaluator with pluggable backend selection."""

    def __init__(
        self,
        allowed_project_root: Optional[Path] = None,
        backend: Optional[PolicyBackend] = None,
    ):
        self.allowed_project_root = allowed_project_root
        self.backend = backend or self._build_backend()

    def _build_backend(self) -> PolicyBackend:
        backend_name = os.getenv("HARNESS_POLICY_BACKEND", "local").strip().lower()
        if backend_name == "opa":
            return OPAPolicyBackend(allowed_project_root=self.allowed_project_root)
        return LocalPolicyBackend(allowed_project_root=self.allowed_project_root)

    def evaluate_verify_request(self, projects: list[ProjectConfig], data_mode: str) -> PolicyResult:
        """Evaluate verify request against selected policy backend."""
        return self.backend.evaluate_verify_request(projects, data_mode)
