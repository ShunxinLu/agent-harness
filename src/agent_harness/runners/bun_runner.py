"""
Bun test runner for TypeScript/JavaScript projects.
"""

import subprocess
import json
import re
from pathlib import Path
from typing import Optional

from ..output import (
    TestRunResult,
    TestResult,
    CompressedError,
    extract_error_info,
)


class BunRunner:
    """Runner for Bun test suites."""

    def __init__(self, project_path: Path):
        self.project_path = project_path

    def run(self, extra_args: Optional[list[str]] = None) -> TestRunResult:
        """
        Run bun test and return structured results.

        Args:
            extra_args: Additional arguments to pass to bun test

        Returns:
            TestRunResult with all test outcomes
        """

        # Build bun test command
        cmd = ["bun", "test"]

        if extra_args:
            cmd.extend(extra_args)

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            return self._parse_result(result)

        except subprocess.TimeoutExpired:
            return TestRunResult(
                project=self.project_path.name,
                framework="bun",
                summary="Test execution timed out after 5 minutes",
            )
        except FileNotFoundError:
            return TestRunResult(
                project=self.project_path.name,
                framework="bun",
                summary="bun not found. Install from https://bun.sh",
            )

    def _parse_result(self, result: subprocess.CompletedProcess) -> TestRunResult:
        """Parse bun test output into structured results."""

        test_results = self._parse_stdout(result.stdout, result.returncode)

        # Calculate summary stats
        passed = sum(1 for r in test_results if r.status == "passed")
        failed = sum(1 for r in test_results if r.status == "failed")
        skipped = sum(1 for r in test_results if r.status == "skipped")
        errors = sum(1 for r in test_results if r.status == "error")

        # Get total duration (estimate from output)
        total_duration = self._extract_duration(result.stdout)

        return TestRunResult(
            project=self.project_path.name,
            framework="bun",
            total=len(test_results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration=total_duration,
            results=test_results,
            summary=result.stdout.split("\n")[-5:] if result.stdout else ["No output"],
        )

    def _parse_stdout(self, stdout: str, returncode: int) -> list[TestResult]:
        """Parse bun test stdout."""

        results = []

        # Bun output patterns
        # ✓ package/src/test.ts > some test [1.23ms]
        # ✗ package/src/test.ts > failing test
        bun_pattern = re.compile(r"^([✓✗])\s+([^\s]+)\s+>\s+([^\[]+)(?:\s*\[([^\]]+)\])?")

        for line in stdout.split("\n"):
            match = bun_pattern.match(line.strip())
            if match:
                icon, file_path, test_name, duration = match.groups()

                status = "passed" if icon == "✓" else "failed"

                results.append(TestResult(
                    name=f"{file_path} > {test_name.strip()}",
                    status=status,
                    duration=self._parse_duration(duration) if duration else 0.0,
                ))

        # If no structured output found, create a summary result
        if not results:
            has_failure = returncode != 0
            has_passed = "pass" in stdout.lower()

            if has_failure or has_passed:
                # Try to extract error info
                error = None
                if has_failure:
                    error = extract_error_info(stdout)

                results.append(TestResult(
                    name="summary",
                    status="failed" if has_failure else "passed",
                    error=error,
                    output=stdout[:2000],  # Include truncated output
                ))

        return results

    def _parse_duration(self, duration_str: str) -> float:
        """Parse duration string like '1.23ms' to float seconds."""

        if not duration_str:
            return 0.0

        match = re.search(r"([\d.]+)\s*(ms|s)?", duration_str)
        if match:
            value = float(match.group(1))
            unit = match.group(2) or "ms"

            if unit == "s":
                return value
            return value / 1000.0

        return 0.0

    def _extract_duration(self, stdout: str) -> float:
        """Extract total test duration from output."""

        # Look for patterns like "10 tests, 5 passed, 1.23s total"
        match = re.search(r"([\d.]+)\s*s\s*(?:total|elapsed)", stdout)
        if match:
            return float(match.group(1))

        # Or "Done in 1.23s"
        match = re.search(r"Done in\s+([\d.]+)\s*s", stdout)
        if match:
            return float(match.group(1))

        return 0.0
