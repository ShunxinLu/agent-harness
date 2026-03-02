"""
Generic test runner for JVM-based and other frameworks.

Supports: Maven, Gradle, SBT, Cargo, Go
"""

import subprocess
import re
from pathlib import Path
from typing import Optional, Callable

from ..config import ProjectConfig
from ..output import TestRunResult, TestResult, CompressedError


class GenericRunner:
    """Runner for JVM-based frameworks and other command-line test runners."""

    def __init__(self, project_path: Path, framework: str):
        self.project_path = project_path
        self.framework = framework

    def run(self) -> TestRunResult:
        """Run tests and return results."""
        framework_commands = {
            "maven": ["mvn", "test"],
            "gradle": ["gradle", "test"],
            "sbt": ["sbt", "test"],
            "cargo": ["cargo", "test"],
            "go": ["go", "test", "./..."],
        }

        command = framework_commands.get(self.framework)
        if not command:
            return TestRunResult(
                project=self.project_path.name,
                framework=self.framework,
                summary=f"Unknown framework: {self.framework}",
            )

        try:
            result = subprocess.run(
                command,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            parsed = self._parse_output(result.stdout + result.stderr)

            return TestRunResult(
                project=self.project_path.name,
                framework=self.framework,
                total=parsed["total"],
                passed=parsed["passed"],
                failed=parsed["failed"],
                skipped=parsed["skipped"],
                errors=parsed["errors"],
                duration=0,  # Would need to parse from output
                results=parsed["results"],
                summary=self._format_summary(parsed),
            )

        except subprocess.TimeoutExpired:
            return TestRunResult(
                project=self.project_path.name,
                framework=self.framework,
                summary="Test execution timed out after 10 minutes",
            )
        except Exception as e:
            return TestRunResult(
                project=self.project_path.name,
                framework=self.framework,
                summary=f"Error running tests: {str(e)}",
            )

    def _parse_output(self, output: str) -> dict:
        """Parse test output based on framework."""
        results = []
        total = passed = failed = skipped = errors = 0

        if self.framework in ("maven", "gradle", "sbt"):
            # JVM frameworks typically have similar output patterns
            # --- Maven Surefire ---
            # Tests run: 10, Failures: 1, Errors: 0, Skipped: 0
            # [ERROR] testMethod(com.example.TestClass)

            # --- Gradle ---
            # > Task :test
            # 10 tests completed, 1 failed

            # Parse summary lines
            maven_pattern = r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)"
            gradle_pattern = r"(\d+) tests? completed, (\d+) failed"

            match = re.search(maven_pattern, output)
            if match:
                total = int(match.group(1))
                failed = int(match.group(2))
                errors = int(match.group(3))
                skipped = int(match.group(4))
                passed = total - failed - errors - skipped

            if not match:
                match = re.search(gradle_pattern, output)
                if match:
                    total = int(match.group(1))
                    failed = int(match.group(2))
                    passed = total - failed

            # Parse individual test results
            test_pattern = r"^\[?(?:INFO|DEBUG|WARN)\]?\s*(?:Test|Running)[:\s]+(.+)$"
            for line in output.split("\n"):
                if "<<< FAILURE" in line or "<<< ERROR" in line:
                    # Extract test name
                    test_match = re.search(r"([^\s(]+)\(([^\)]+)\)", line)
                    if test_match:
                        test_name = f"{test_match.group(2)}.{test_match.group(1)}"
                        status = "failed" if "FAILURE" in line else "error"
                        results.append(TestResult(
                            name=test_name,
                            status=status,
                            output=line.strip(),
                        ))

        elif self.framework == "cargo":
            # Cargo test output:
            # test result: ok. 10 passed; 1 failed; 0 ignored; 0 measured
            pattern = r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored"
            match = re.search(pattern, output)
            if match:
                passed = int(match.group(2))
                failed = int(match.group(3))
                skipped = int(match.group(4))
                total = passed + failed + skipped

        elif self.framework == "go":
            # Go test output:
            # ok   package/name  0.123s
            # FAIL package/name
            for line in output.split("\n"):
                if line.startswith("ok\t"):
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        results.append(TestResult(
                            name=parts[1],
                            status="passed",
                        ))
                        passed += 1
                        total += 1
                elif line.startswith("FAIL\t"):
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        results.append(TestResult(
                            name=parts[1],
                            status="failed",
                        ))
                        failed += 1
                        total += 1

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "results": results,
        }

    def _format_summary(self, parsed: dict) -> str:
        """Format a summary string."""
        parts = [
            f"Total: {parsed['total']}",
            f"Passed: {parsed['passed']}",
            f"Failed: {parsed['failed']}",
        ]
        if parsed['skipped'] > 0:
            parts.append(f"Skipped: {parsed['skipped']}")
        return " | ".join(parts)


def get_runner(config: ProjectConfig):
    """Factory function to get appropriate runner."""
    from .pytest_runner import PytestRunner
    from .bun_runner import BunRunner
    from .npm_runner import NpmRunner

    if config.framework == "pytest":
        return PytestRunner(config.path, config.test_dir)
    elif config.framework == "pyspark":
        return PytestRunner(config.path, config.test_dir)
    elif config.framework == "bun":
        return BunRunner(config.path)
    elif config.framework == "npm":
        return NpmRunner(config.path)
    elif config.framework in ("maven", "gradle", "sbt", "cargo", "go"):
        return GenericRunner(config.path, config.framework)
    return None
