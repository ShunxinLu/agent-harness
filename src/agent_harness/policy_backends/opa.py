"""OPA-backed policy evaluator."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from urllib import error, request

from ..config import ProjectConfig
from ..policy_models import PolicyDecision, PolicyResult
from .base import PolicyBackend


class OPAPolicyBackend(PolicyBackend):
    """
    Policy backend that delegates decisions to Open Policy Agent.

    Expected OPA response forms:
    1. {"result": true|false}
    2. {"result": {"allowed": true|false, "decisions": [...]} }
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout_seconds: float = 3.0,
        allowed_project_root: Optional[Path] = None,
    ):
        self.endpoint = endpoint or os.getenv("HARNESS_OPA_URL", "http://localhost:8181/v1/data/harness/allow")
        self.timeout_seconds = float(os.getenv("HARNESS_OPA_TIMEOUT_SECONDS", str(timeout_seconds)))
        self.allowed_project_root = allowed_project_root

    def evaluate_verify_request(self, projects: list[ProjectConfig], data_mode: str) -> PolicyResult:
        payload = {
            "input": {
                "operation": "verify",
                "data_mode": data_mode,
                "projects": [
                    {
                        "name": project.name,
                        "framework": project.framework,
                        "path": str(project.path.expanduser().resolve()),
                    }
                    for project in projects
                ],
                "allowed_project_root": str(self.allowed_project_root) if self.allowed_project_root else None,
                "allow_real_aws": os.getenv("HARNESS_ALLOW_REAL_AWS", "").lower() in {"1", "true", "yes"},
            }
        }

        req = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
        except error.URLError as exc:
            return PolicyResult(
                allowed=False,
                decisions=[
                    PolicyDecision(
                        action="opa.request",
                        allowed=False,
                        reason=f"OPA request failed: {exc}",
                        metadata={"endpoint": self.endpoint},
                    )
                ],
            )

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            return PolicyResult(
                allowed=False,
                decisions=[
                    PolicyDecision(
                        action="opa.response",
                        allowed=False,
                        reason=f"OPA returned invalid JSON: {exc}",
                        metadata={"endpoint": self.endpoint},
                    )
                ],
            )

        result = parsed.get("result")
        if isinstance(result, bool):
            return PolicyResult(
                allowed=result,
                decisions=[
                    PolicyDecision(
                        action="opa.allow",
                        allowed=result,
                        reason="OPA boolean decision",
                        metadata={"endpoint": self.endpoint},
                    )
                ],
            )

        if isinstance(result, dict):
            allowed = bool(result.get("allowed", False))
            raw_decisions = result.get("decisions", [])
            decisions: list[PolicyDecision] = []
            for item in raw_decisions:
                if isinstance(item, dict):
                    decisions.append(
                        PolicyDecision(
                            action=item.get("action", "opa.decision"),
                            allowed=bool(item.get("allowed", allowed)),
                            reason=str(item.get("reason", "OPA decision")),
                            metadata=item.get("metadata", {}),
                        )
                    )

            if not decisions:
                decisions = [
                    PolicyDecision(
                        action="opa.allow",
                        allowed=allowed,
                        reason="OPA structured decision",
                        metadata={"endpoint": self.endpoint},
                    )
                ]

            return PolicyResult(allowed=allowed and all(d.allowed for d in decisions), decisions=decisions)

        return PolicyResult(
            allowed=False,
            decisions=[
                PolicyDecision(
                    action="opa.response",
                    allowed=False,
                    reason="OPA response missing expected result",
                    metadata={"endpoint": self.endpoint},
                )
            ],
        )

