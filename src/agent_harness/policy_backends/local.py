"""Built-in local policy backend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ..config import ProjectConfig
from ..policy_models import PolicyDecision, PolicyResult
from .base import PolicyBackend


class LocalPolicyBackend(PolicyBackend):
    """Local in-process policy checks for verify/MCP requests."""

    allowed_frameworks = {"pytest", "pyspark", "npm", "bun", "maven", "gradle", "sbt", "cargo", "go"}
    allowed_data_modes = {"mock", "metadata", "human-contract"}

    def __init__(self, allowed_project_root: Optional[Path] = None):
        env_root = os.getenv("HARNESS_ALLOWED_PROJECT_ROOT", "").strip()
        configured_root = allowed_project_root or (Path(env_root).expanduser().resolve() if env_root else None)
        self.allowed_project_root = configured_root

    def evaluate_verify_request(self, projects: list[ProjectConfig], data_mode: str) -> PolicyResult:
        decisions: list[PolicyDecision] = []

        if data_mode not in self.allowed_data_modes:
            decisions.append(
                PolicyDecision(
                    action="data_mode.validate",
                    allowed=False,
                    reason=f"Unsupported data_mode: {data_mode}",
                    metadata={"data_mode": data_mode},
                )
            )
        else:
            decisions.append(
                PolicyDecision(
                    action="data_mode.validate",
                    allowed=True,
                    reason="Data mode allowed",
                    metadata={"data_mode": data_mode},
                )
            )

        if data_mode == "mock" and os.getenv("HARNESS_ALLOW_REAL_AWS", "").lower() in {"1", "true", "yes"}:
            decisions.append(
                PolicyDecision(
                    action="aws.mock_guard",
                    allowed=False,
                    reason="HARNESS_ALLOW_REAL_AWS cannot be enabled in mock mode",
                    metadata={"env": "HARNESS_ALLOW_REAL_AWS"},
                )
            )
        else:
            decisions.append(
                PolicyDecision(
                    action="aws.mock_guard",
                    allowed=True,
                    reason="Mock-mode AWS guard satisfied",
                    metadata={"data_mode": data_mode},
                )
            )

        for project in projects:
            resolved_path = project.path.expanduser().resolve()
            framework = project.framework

            if framework not in self.allowed_frameworks:
                decisions.append(
                    PolicyDecision(
                        action="framework.allowlist",
                        allowed=False,
                        reason=f"Unsupported framework for policy engine: {framework}",
                        metadata={"project": project.name, "framework": framework},
                    )
                )
            else:
                decisions.append(
                    PolicyDecision(
                        action="framework.allowlist",
                        allowed=True,
                        reason="Framework allowed for local test execution",
                        metadata={"project": project.name, "framework": framework},
                    )
                )

            if not resolved_path.exists():
                decisions.append(
                    PolicyDecision(
                        action="path.exists",
                        allowed=False,
                        reason=f"Project path does not exist: {resolved_path}",
                        metadata={"project": project.name},
                    )
                )
                continue

            decisions.append(
                PolicyDecision(
                    action="path.exists",
                    allowed=True,
                    reason="Project path exists",
                    metadata={"project": project.name, "path": str(resolved_path)},
                )
            )

            if self.allowed_project_root is not None:
                try:
                    resolved_path.relative_to(self.allowed_project_root)
                    decisions.append(
                        PolicyDecision(
                            action="path.allowed_root",
                            allowed=True,
                            reason="Project path is within allowed root",
                            metadata={"project": project.name, "allowed_root": str(self.allowed_project_root)},
                        )
                    )
                except ValueError:
                    decisions.append(
                        PolicyDecision(
                            action="path.allowed_root",
                            allowed=False,
                            reason="Project path is outside HARNESS_ALLOWED_PROJECT_ROOT boundary",
                            metadata={
                                "project": project.name,
                                "path": str(resolved_path),
                                "allowed_root": str(self.allowed_project_root),
                            },
                        )
                    )

        return PolicyResult(
            allowed=all(decision.allowed for decision in decisions),
            decisions=decisions,
        )

