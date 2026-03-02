"""
Configuration and project auto-detection for the harness.

Supports: pytest, bun, npm, maven, gradle, sbt, cargo, go, pyspark
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class ProjectConfig(BaseModel):
    """Configuration for a detected project."""
    path: Path
    name: str
    framework: str  # pytest, bun, npm, maven, gradle, sbt, cargo, go, pyspark
    test_dir: Optional[Path] = None
    config_file: Optional[Path] = None
    command: list[str] = []

    class Config:
        arbitrary_types_allowed = True


def detect_framework(project_path: Path) -> Optional[str]:
    """Detect the test framework used in a project."""

    # Maven (Java/Scala/Spark)
    if (project_path / "pom.xml").exists():
        return "maven"

    # Gradle (Java/Scala/Kotlin)
    if (project_path / "build.gradle").exists() or (project_path / "build.gradle.kts").exists():
        return "gradle"

    # SBT (Scala)
    if (project_path / "build.sbt").exists():
        return "sbt"

    # Cargo (Rust)
    if (project_path / "Cargo.toml").exists():
        return "cargo"

    # Go
    if (project_path / "go.mod").exists():
        return "go"

    # Check for pytest (pytest.ini, conftest.py, or test_*.py files)
    if (project_path / "pytest.ini").exists():
        return "pytest"
    if (project_path / "pyproject.toml").exists():
        content = (project_path / "pyproject.toml").read_text()
        if "[tool.pytest" in content or "pytest" in content:
            # Check if there are test files
            if list(project_path.glob("test_*.py")) or list(project_path.glob("**/test_*.py")):
                return "pytest"
    if list(project_path.glob("conftest.py")):
        return "pytest"
    if list(project_path.glob("tests/**/*.py")) or list(project_path.glob("test_*.py")):
        # Check for PySpark
        if list(project_path.glob("**/spark*.py")) or list(project_path.glob("**/*_spark.py")):
            return "pyspark"
        return "pytest"

    # PySpark specific detection
    if list(project_path.glob("**/spark*.py")) or list(project_path.glob("**/*_spark.py")):
        return "pyspark"

    # Check for Bun test (bunfig.toml or .test.ts files)
    if (project_path / "bunfig.toml").exists():
        return "bun"
    if list(project_path.glob("**/*.test.ts")) or list(project_path.glob("**/*.spec.ts")):
        # Check if package.json has bun as test runner
        pkg_json = project_path / "package.json"
        if pkg_json.exists():
            content = pkg_json.read_text()
            if "@playwright/test" in content or "bun test" in content:
                return "bun"

    # Check for npm/Jest (package.json with test script)
    pkg_json = project_path / "package.json"
    if pkg_json.exists():
        content = pkg_json.read_text()
        if '"test"' in content:
            return "npm"

    return None


def get_test_command(framework: str, project_path: Path) -> list[str]:
    """Get the command to run tests for a given framework."""

    if framework == "pytest":
        # Look for test directory
        test_dir = project_path / "tests"
        if not test_dir.exists():
            test_dir = project_path

        return ["pytest", str(test_dir), "-v", "--tb=short", "--json-report"]

    elif framework == "pyspark":
        # PySpark uses pytest with spark configuration
        test_dir = project_path / "tests"
        if not test_dir.exists():
            test_dir = project_path
        return ["pytest", str(test_dir), "-v", "--tb=short", "--spark-home=find"]

    elif framework == "maven":
        return ["mvn", "test"]

    elif framework == "gradle":
        return ["gradle", "test"]

    elif framework == "sbt":
        return ["sbt", "test"]

    elif framework == "cargo":
        return ["cargo", "test"]

    elif framework == "go":
        return ["go", "test", "./..."]

    elif framework == "bun":
        return ["bun", "test"]

    elif framework == "npm":
        return ["npm", "test"]

    return []


def detect_project(project_path: Path) -> Optional[ProjectConfig]:
    """Detect and configure a project for testing."""

    if not project_path.exists():
        return None

    framework = detect_framework(project_path)
    if not framework:
        return None

    test_dir = project_path / "tests"
    if not test_dir.exists():
        test_dir = project_path

    config_file = None
    config_candidates = [
        "pytest.ini", "pyproject.toml", "bunfig.toml", "package.json",
        "pom.xml", "build.gradle", "build.gradle.kts", "build.sbt",
        "Cargo.toml", "go.mod"
    ]
    for candidate in config_candidates:
        if (project_path / candidate).exists():
            config_file = project_path / candidate
            break

    command = get_test_command(framework, project_path)

    return ProjectConfig(
        path=project_path,
        name=project_path.name,
        framework=framework,
        test_dir=test_dir,
        config_file=config_file,
        command=command,
    )


def scan_projects(base_path: Path) -> list[ProjectConfig]:
    """Scan a directory for testable projects."""

    projects = []

    if not base_path.exists():
        return projects

    # Check immediate subdirectories
    for item in base_path.iterdir():
        if item.is_dir() and not item.name.startswith((".", "__", "node_modules", ".venv")):
            project = detect_project(item)
            if project:
                projects.append(project)

    # Also check the base path itself
    base_project = detect_project(base_path)
    if base_project and not any(p.path == base_path for p in projects):
        projects.append(base_project)

    return projects
