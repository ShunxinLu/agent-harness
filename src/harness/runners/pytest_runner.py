"""
Pytest test runner with JSON output support.
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
    compress_stack_trace,
)


class PytestRunner:
    """Runner for pytest test suites."""

    def __init__(self, project_path: Path, test_dir: Optional[Path] = None):
        self.project_path = project_path
        self.test_dir = test_dir or project_path

    def run(self, extra_args: Optional[list[str]] = None) -> TestRunResult:
        """
        Run pytest and return structured results.

        Args:
            extra_args: Additional arguments to pass to pytest

        Returns:
            TestRunResult with all test outcomes
        """

        # Build pytest command
        cmd = [
            "pytest",
            str(self.test_dir),
            "-v",
            "--tb=long",  # Get full trace for compression
            "--json-report",
        ]

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

            return self._parse_result(result, cmd)

        except subprocess.TimeoutExpired:
            return TestRunResult(
                project=self.project_path.name,
                framework="pytest",
                summary="Test execution timed out after 5 minutes",
            )
        except FileNotFoundError:
            return TestRunResult(
                project=self.project_path.name,
                framework="pytest",
                summary="pytest not found. Install with: pip install pytest pytest-json-report",
            )

    def _parse_result(self, result: subprocess.CompletedProcess, cmd: list[str]) -> TestRunResult:
        """Parse pytest output into structured results."""

        # Try to parse JSON report first
        json_report_path = self.project_path / ".pytest_json" / ".report.json"
        test_results = []

        if json_report_path.exists():
            try:
                with open(json_report_path) as f:
                    report = json.load(f)

                tests = report.get("tests", [])
                for test in tests:
                    status = test.get("outcome", "unknown")

                    error = None
                    if status in ("failed", "error"):
                        traceback = test.get("traceback", "")
                        if traceback:
                            error = extract_error_info(traceback)
                        else:
                            # Try to get error from call section
                            call = test.get("call", {})
                            if call:
                                error = CompressedError(
                                    error_type=call.get("type", "Error"),
                                    message=call.get("reprcrash", {}).get("message", str(call)),
                                    category="unknown",
                                )

                    test_results.append(TestResult(
                        name=test.get("name", "unknown"),
                        status=status,
                        duration=test.get("duration", 0.0),
                        error=error,
                    ))

            except (json.JSONDecodeError, KeyError) as e:
                # Fall back to stdout parsing
                test_results = self._parse_stdout(result.stdout)
        else:
            # Fall back to stdout parsing
            test_results = self._parse_stdout(result.stdout)

        # Calculate summary stats
        passed = sum(1 for r in test_results if r.status == "passed")
        failed = sum(1 for r in test_results if r.status == "failed")
        skipped = sum(1 for r in test_results if r.status == "skipped")
        errors = sum(1 for r in test_results if r.status == "error")

        # Get total duration
        total_duration = sum(r.duration for r in test_results)

        # Parse summary line from stdout
        summary_match = re.search(
            r"(\d+) (?:passed|failed|skipped|error)?[,\s]*(\d+)?",
            result.stdout
        )

        summary = result.stdout.split("\n")[-3:] if result.stdout else ["No output"]

        return TestRunResult(
            project=self.project_path.name,
            framework="pytest",
            total=len(test_results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration=total_duration,
            results=test_results,
            summary="\n".join(summary),
        )

    def _parse_stdout(self, stdout: str) -> list[TestResult]:
        """Parse pytest stdout when JSON report is unavailable."""

        results = []

        # Pattern for test lines: test_file.py::test_name PASSED/FAILED
        line_pattern = re.compile(r"^([^:\s]+)::([^\s]+)\s+(PASSED|FAILED|SKIPPED|ERROR)\s*(.*)$")

        for line in stdout.split("\n"):
            match = line_pattern.match(line.strip())
            if match:
                file_name, test_name, status, _ = match.groups()

                results.append(TestResult(
                    name=f"{file_name}::{test_name}",
                    status=status.lower(),
                ))

        # If no structured output found, create a summary result
        if not results:
            # Check for failures in output
            has_failure = "FAILED" in stdout or "ERROR" in stdout
            has_passed = "PASSED" in stdout or "passed" in stdout

            if has_failure or has_passed:
                results.append(TestResult(
                    name="summary",
                    status="failed" if has_failure else "passed",
                    output=stdout[:2000],  # Include truncated output
                ))

        return results
