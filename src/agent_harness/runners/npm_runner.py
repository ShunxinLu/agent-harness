"""
NPM test runner for JavaScript/TypeScript projects.
"""

import subprocess
import re
from pathlib import Path
from typing import Optional

from ..output import (
    TestRunResult,
    TestResult,
    extract_error_info,
)


class NpmRunner:
    """Runner for npm-based test suites."""

    def __init__(self, project_path: Path):
        self.project_path = project_path

    def run(self, extra_args: Optional[list[str]] = None) -> TestRunResult:
        """Run npm test and return structured results."""
        cmd = ["npm", "test"]
        if extra_args:
            cmd.extend(extra_args)

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return self._parse_result(result)
        except subprocess.TimeoutExpired:
            return TestRunResult(
                project=self.project_path.name,
                framework="npm",
                summary="Test execution timed out after 5 minutes",
                execution_status="timeout",
            )
        except FileNotFoundError:
            return TestRunResult(
                project=self.project_path.name,
                framework="npm",
                summary="npm not found. Install Node.js and npm first.",
                execution_status="tool_missing",
            )

    def _parse_result(self, result: subprocess.CompletedProcess) -> TestRunResult:
        """Parse npm test output into structured results."""
        output = result.stdout + ("\n" + result.stderr if result.stderr else "")
        parsed_counts = self._extract_counts(output)
        has_failure = result.returncode != 0

        summary_result = TestResult(
            name="summary",
            status="failed" if has_failure else "passed",
            error=extract_error_info(output) if has_failure else None,
            output=output[:2000],
        )

        total = parsed_counts["total"] if parsed_counts["total"] > 0 else 1
        passed = parsed_counts["passed"]
        failed = parsed_counts["failed"]
        skipped = parsed_counts["skipped"]
        errors = 0

        # If counts are unavailable, infer from exit status.
        if parsed_counts["total"] == 0:
            passed = 0 if has_failure else 1
            failed = 1 if has_failure else 0
            skipped = 0

        return TestRunResult(
            project=self.project_path.name,
            framework="npm",
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration=self._extract_duration(output),
            results=[summary_result],
            summary=output.split("\n")[-8:] if output else ["No output"],
            execution_status="ok",
        )

    def _extract_counts(self, output: str) -> dict[str, int]:
        """Best-effort extraction of pass/fail/total counts from common npm test frameworks."""
        counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        # Jest-style: Tests: 1 failed, 4 passed, 5 total
        jest_match = re.search(
            r"Tests:\s*(?:(\d+)\s+failed,?\s*)?(?:(\d+)\s+skipped,?\s*)?(?:(\d+)\s+passed,?\s*)?(?:(\d+)\s+total)?",
            output,
            re.IGNORECASE,
        )
        if jest_match:
            failed = int(jest_match.group(1) or 0)
            skipped = int(jest_match.group(2) or 0)
            passed = int(jest_match.group(3) or 0)
            total = int(jest_match.group(4) or 0)
            if total > 0:
                counts.update({"total": total, "passed": passed, "failed": failed, "skipped": skipped})
                return counts

        # Generic: "<n> passed", "<n> failed", "<n> skipped"
        passed_match = re.search(r"(\d+)\s+passed", output, re.IGNORECASE)
        failed_match = re.search(r"(\d+)\s+failed", output, re.IGNORECASE)
        skipped_match = re.search(r"(\d+)\s+skipped", output, re.IGNORECASE)
        if passed_match or failed_match or skipped_match:
            passed = int(passed_match.group(1)) if passed_match else 0
            failed = int(failed_match.group(1)) if failed_match else 0
            skipped = int(skipped_match.group(1)) if skipped_match else 0
            total = passed + failed + skipped
            counts.update({"total": total, "passed": passed, "failed": failed, "skipped": skipped})

        return counts

    def _extract_duration(self, output: str) -> float:
        """Extract approximate total duration in seconds."""
        # Jest-style: Time: 2.345 s
        jest_time = re.search(r"Time:\s*([\d.]+)\s*s", output, re.IGNORECASE)
        if jest_time:
            return float(jest_time.group(1))

        # Generic: done in 1.23s
        generic_time = re.search(r"done in\s*([\d.]+)\s*s", output, re.IGNORECASE)
        if generic_time:
            return float(generic_time.group(1))

        return 0.0
