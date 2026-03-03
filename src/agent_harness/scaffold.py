"""
Harness Scaffold - Project scaffolding with sandbox generation.

Usage:
    harness-scaffold create <name> --framework pytest|bun|npm
    harness-scaffold add-sandbox <project-path> --services s3,duckdb,sqs
    harness-scaffold daemon start    # Start LocalStack daemon
    harness-scaffold daemon stop     # Stop daemon
    harness-scaffold daemon status   # Check health
    harness-scaffold daemon reset    # Purge bucket states
"""

import subprocess
from pathlib import Path

import click

from .sandbox import SandboxConfig, SandboxManager


@click.group()
@click.version_option(version="0.1.0")
def app():
    """Project scaffolding with sandbox generation for agent testing."""
    pass


def style(text: str, fg: str = None, bold: bool = False) -> str:
    """Add ANSI style to text."""
    if fg == "green":
        code = "32"
    elif fg == "red":
        code = "31"
    elif fg == "yellow":
        code = "33"
    elif fg == "blue":
        code = "34"
    elif fg == "cyan":
        code = "36"
    else:
        code = None

    result = text
    if code:
        result = f"\033[{code}m{result}\033[0m"
    if bold:
        result = f"\033[1m{result}\033[0m"
    return result


def console_print(text: str):
    """Simple print function."""
    click.echo(text)


def create_pytest_template(project_path: Path):
    """Create pytest project template."""
    # Create directory structure
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "tests").mkdir(exist_ok=True)
    (project_path / "src" / "agent").mkdir(parents=True, exist_ok=True)
    (project_path / ".harness" / "duckdb").mkdir(parents=True, exist_ok=True)

    # conftest.py with sandbox fixtures
    conftest_content = '''"""Pytest fixtures with sandbox integration."""
import pytest
from agent_harness.sandbox import SandboxManager, SandboxConfig


@pytest.fixture(scope="session")
def sandbox():
    """Session-level sandbox manager."""
    config = SandboxConfig.from_yaml(".harness/sandbox.yaml")
    manager = SandboxManager(config)
    manager.ensure_daemon_running()
    yield manager
    # Cleanup happens at session end


@pytest.fixture
def s3_client(sandbox):
    """Boto3 S3 client connected to LocalStack."""
    return sandbox.get_s3_client()


@pytest.fixture
def duckdb_conn(sandbox):
    """DuckDB connection."""
    return sandbox.get_duckdb_connection()
'''

    (project_path / "tests" / "conftest.py").write_text(conftest_content)

    # Sample test file
    test_agent_content = '''"""Sample agent tests."""
import pytest


def test_agent_basic():
    """Basic test placeholder."""
    assert True


def test_with_s3(s3_client):
    """Test using S3 sandbox."""
    # Create bucket
    s3_client.create_bucket(Bucket="test-bucket")

    # Put object
    s3_client.put_object(
        Bucket="test-bucket",
        Key="test-key",
        Body=b"test content"
    )

    # Get object
    response = s3_client.get_object(Bucket="test-bucket", Key="test-key")
    content = response["Body"].read()
    assert content == b"test content"


def test_with_duckdb(duckdb_conn):
    """Test using DuckDB sandbox."""
    cursor = duckdb_conn.cursor()

    # Create table
    cursor.execute("CREATE TABLE test_data (id INTEGER, value VARCHAR)")
    cursor.execute("INSERT INTO test_data VALUES (1, 'hello'), (2, 'world')")

    # Query
    cursor.execute("SELECT COUNT(*) FROM test_data")
    count = cursor.fetchone()[0]
    assert count == 2
'''

    (project_path / "tests" / "test_agent.py").write_text(test_agent_content)

    # Sample agent module
    agent_main_content = '''"""Agent main module."""
from typing import Any


class Agent:
    """Base agent class."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def run(self, input_data: str) -> str:
        """Run the agent on input data."""
        # TODO: Implement agent logic
        return f"Processed: {input_data}"
'''

    (project_path / "src" / "agent" / "main.py").write_text(agent_main_content)
    (project_path / "src" / "agent" / "__init__.py").write_text('from .main import Agent\n')
    (project_path / "src" / "__init__.py").write_text('')

    # pyproject.toml
    pyproject_content = f'''[project]
name = "{project_path.name}"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "boto3>=1.34.0",
    "duckdb>=0.10.0",
    "pytest>=7.4.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]
'''

    (project_path / "pyproject.toml").write_text(pyproject_content)

    # pytest.ini
    pytest_ini_content = '''[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short
'''

    (project_path / "pytest.ini").write_text(pytest_ini_content)

    # Create agent instruction files
    create_agent_instructions(project_path)

    # Create tach.toml for architecture enforcement
    create_tach_config(project_path)

    # Create capabilities.json
    create_capabilities_manifest(project_path)

    # Create docs structure
    create_docs_structure(project_path)

    # Create execution plan template
    create_execution_plan_template(project_path)


def create_agent_instructions(project_path: Path):
    """Create agent instruction files for different AI agents."""

    # AGENTS.md - Universal agent guide
    agents_md = f'''# Agent Guide: {project_path.name}

This project is designed for AI agent development. Any AI agent can:
1. Read this file for navigation
2. Run `harness-verify verify --json` to test
3. Run `harness-lint check` to validate structure
4. Run `harness-cleanup run --dry-run` to find issues

## Quick Navigation

- Code: `./src/`
- Tests: `./tests/`
- Config: `.harness/`
- Docs: `./docs/`

## Available Tools

| Command | Purpose | Returns |
|---------|---------|---------|
| `harness-verify verify --json` | Run tests | JSON result |
| `harness-lint check` | Validate code | JSON errors |
| `harness-cleanup run` | Fix entropy | Changes |
| `harness-scaffold daemon start` | Start sandbox | LocalStack ready |

## Feedback Loop

1. Make change
2. Run `harness-verify verify --json`
3. If failed -> read error -> fix -> repeat
4. If passed -> run `harness-lint check`
5. If lint passes -> commit

## Common Issues

| Problem | Fix |
|---------|-----|
| S3 bucket not found | Run `harness-scaffold daemon start` |
| Test cache stale | Run `harness-verify cache clear` |
| Lint failed | Run `harness-lint check --format json` |
| Architecture violation | Check `tach.toml` for layer rules |

## Agent-Specific Files

- **Claude Code**: See `CLAUDE.md`
- **Cursor**: See `.cursorrules`
- **GitHub Copilot**: See `.github/copilot-instructions.md`
'''
    (project_path / "AGENTS.md").write_text(agents_md)

    # CLAUDE.md - Claude Code specific
    claude_md = f'''# Claude Code Instructions

## Project Overview
{project_path.name} - AI agent development project using harness framework.

## Key Commands
- Test: `harness-verify verify --json`
- Lint: `harness-lint check --format json`
- Cleanup: `harness-cleanup run --dry-run`
- Sandbox: `harness-scaffold daemon start`

## MCP Server
This project uses the harness MCP server. Available tools:
- `run_tests` - Run tests for the project
- `list_projects` - List detectable projects
- `get_cache_status` - Get cache statistics
- `get_trace` - Get trace events for a run ID
- `analyze_errors` - Analyze error patterns

## Workflow
1. Read AGENTS.md for project structure
2. Make changes
3. Run tests with JSON output
4. Run lint check
5. Commit when both pass

## Sandbox Services
Configured: LocalStack (S3, SQS), DuckDB
'''
    (project_path / "CLAUDE.md").write_text(claude_md)

    # .cursorrules - Cursor IDE rules
    cursorrules = f'''# Cursor Rules for {project_path.name}

## Always
- Run `harness-verify verify --json` after making code changes
- Run `harness-lint check --format json` before committing
- Read AGENTS.md for project navigation
- Check tach.toml for layer boundaries

## Never
- Import from higher architectural layers (see tach.toml)
- Leave TODO comments without tracking issue
- Commit without running tests and lint

## Testing
- Tests are in `./tests/`
- Use pytest fixtures: `s3_client`, `duckdb_conn`
- Run: `harness-verify verify --json`

## Code Style
- Follow existing patterns
- Add docstrings to public functions
- Type hints required
'''
    (project_path / ".cursorrules").write_text(cursorrules)

    # .github/copilot-instructions.md
    github_dir = project_path / ".github"
    github_dir.mkdir(exist_ok=True)
    copilot_md = f'''# GitHub Copilot Instructions

## Project Context
{project_path.name} uses the agent-harness framework for testing.

## Guidelines
- All code must pass `harness-verify verify` and `harness-lint check`
- Follow layer architecture defined in `tach.toml`
- Write docstrings for all public functions
- Prefer JSON output for CLI commands
- Use type hints

## Testing
- Tests are in `./tests/`
- Run: `harness-verify verify --json`
- Fixtures: `s3_client`, `duckdb_conn`

## Architecture
- Domain layer: `src/` - business logic
- Infrastructure: External services via sandbox
- Tests verify both
'''
    (github_dir / "copilot-instructions.md").write_text(copilot_md)


def create_tach_config(project_path: Path):
    """Create tach.toml for architectural boundary enforcement."""

    tach_toml = '''# Tach architecture enforcement
# https://github.com/gauge-sh/tach

# Define layers (lower number = lower layer)
# Lower layers CANNOT import from higher layers
layers = [
    { name = "domain", level = 0 },
    { name = "application", level = 1 },
    { name = "infrastructure", level = 2 },
    { name = "interface", level = 3 },
]

# Module definitions
[[modules]]
path = "src"
layer = "domain"

[[modules]]
path = "tests"
layer = "interface"

# Dependencies (explicit allowed imports)
# Anything not listed is forbidden
[[dependencies]]
from = "src"
to = "src"

[[dependencies]]
from = "tests"
to = "src"

[[dependencies]]
from = "tests"
to = "tests"
'''
    (project_path / "tach.toml").write_text(tach_toml)


def create_capabilities_manifest(project_path: Path):
    """Create .harness/capabilities.json self-describing manifest."""

    capabilities = {
        "harness_version": "0.1.0",
        "agent_compatible": ["claude-code", "cursor", "copilot", "codex", "any-shell"],
        "supported_frameworks": ["pytest", "bun", "maven", "gradle", "sbt", "cargo", "go"],
        "sandbox_services": ["s3", "sqs", "dynamodb", "duckdb"],
        "commands": {
            "harness-verify": ["verify", "list", "detect", "cache", "trace"],
            "harness-scaffold": ["create", "add-sandbox", "daemon"],
            "harness-lint": ["check", "fix", "init"],
            "harness-cleanup": ["run", "init"]
        },
        "mcp_tools": ["run_tests", "list_projects", "get_cache_status", "get_trace", "analyze_errors"]
    }

    import json
    harness_dir = project_path / ".harness"
    harness_dir.mkdir(exist_ok=True)
    (harness_dir / "capabilities.json").write_text(json.dumps(capabilities, indent=2))


def create_docs_structure(project_path: Path):
    """Create docs/ directory structure for knowledge system."""

    # Create base docs directory
    docs_dir = project_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # docs/README.md - Docs navigation
    docs_readme = f'''# Documentation Index: {project_path.name}

This directory contains structured documentation for the project.

## Directory Structure

```
docs/
├── README.md           # This file - docs navigation
├── architecture/       # Architectural documentation
│   ├── layers.md       # Layer definitions
│   └── decisions/      # ADRs (Architectural Decision Records)
├── execution-plans/    # Active execution plans
├── taste/             # "Taste invariants" - what good looks like
│   ├── code-style.md
│   └── testing-patterns.md
└── changelog/         # Machine-readable changelog
    └── auto.md
```

## Quick Links

- **Architecture**: See [`architecture/layers.md`](architecture/layers.md)
- **Code Style**: See [`taste/code-style.md`](taste/code-style.md)
- **Testing Patterns**: See [`taste/testing-patterns.md`](taste/testing-patterns.md)
- **Execution Plans**: See [`execution-plans/`](execution-plans/)

## For AI Agents

When making changes:
1. Check relevant docs for context
2. Update docs if behavior changes
3. Create execution plan for complex changes
'''
    (project_path / "docs" / "README.md").write_text(docs_readme, encoding='utf-8')

    # docs/architecture/layers.md
    arch_dir = project_path / "docs" / "architecture"
    arch_dir.mkdir(parents=True, exist_ok=True)

    layers_md = '''# Architecture Layers

This project follows a layered architecture pattern.

## Layer Hierarchy

| Layer | Level | Purpose | Can Import |
|-------|-------|---------|------------|
| Domain | 0 | Pure business logic | Domain only |
| Application | 1 | Use cases, commands, queries | Domain, Application |
| Infrastructure | 2 | DB, HTTP, external services | All lower layers |
| Interface | 3 | HTTP handlers, CLI, UI | All layers |

## Rules

1. **Lower layers cannot import higher layers** - This is enforced by `tach`
2. **Domain layer has zero external dependencies** - Pure business logic
3. **All public functions must have docstrings** - For agent legibility

## Enforcement

Run `harness-lint check` to validate architecture boundaries.

See `tach.toml` in the project root for the machine-readable configuration.
'''
    (arch_dir / "layers.md").write_text(layers_md, encoding='utf-8')

    # docs/architecture/decisions/ directory
    (arch_dir / "decisions").mkdir(exist_ok=True)

    # docs/taste/ directory
    taste_dir = project_path / "docs" / "taste"
    taste_dir.mkdir(parents=True, exist_ok=True)

    code_style_md = '''# Code Style Guide

## General Principles

1. **Clarity over cleverness** - Code should be obvious
2. **Consistent formatting** - Let ruff handle formatting
3. **Type hints required** - All public functions must have types
4. **Docstrings for public APIs** - Explain what, not how

## Python Style

- Use `str | None` instead of `Optional[str]` (Python 3.10+)
- Prefer `dict[str, Any]` over `Dict` from typing
- Use f-strings for formatting
- Max line length: 100 characters (enforced by ruff)

## Naming Conventions

- `snake_case` for functions and variables
- `PascalCase` for classes
- `SCREAMING_SNAKE_CASE` for constants
- Prefix private functions with `_`

## Error Handling

- Use specific exception types
- Add context to error messages
- Log errors at appropriate levels
'''
    (taste_dir / "code-style.md").write_text(code_style_md)

    testing_patterns_md = '''# Testing Patterns

## Test Organization

- Tests live in `./tests/` directory
- Test files: `test_*.py`
- Test functions: `test_*`

## Test Structure

```python
def test_feature_behavior(fixture_dependency):
    """Docstring describes what is being tested."""
    # Arrange
    # Act
    # Assert
```

## Fixtures

- Use provided fixtures: `s3_client`, `duckdb_conn`
- Keep fixtures minimal and focused
- Document custom fixtures

## Running Tests

```bash
# Run all tests
harness-verify verify --project .

# Run with JSON output (for agents)
harness-verify verify --project . --json

# Run specific test file
harness-verify verify --project . tests/test_specific.py
```

## After Changes

Always run:
1. `harness-verify verify --json` - Verify tests pass
2. `harness-lint check` - Verify code quality
'''
    (taste_dir / "testing-patterns.md").write_text(testing_patterns_md, encoding='utf-8')

    # docs/changelog/ directory
    changelog_dir = project_path / "docs" / "changelog"
    changelog_dir.mkdir(parents=True, exist_ok=True)

    auto_md = f'''# Changelog

This file is auto-generated from git commits.

## {project_path.name}

### [Unreleased]

- Initial project scaffold

---

Generated by harness-cleanup
'''
    (changelog_dir / "auto.md").write_text(auto_md, encoding='utf-8')

    # docs/execution-plans/ directory
    plans_dir = project_path / "docs" / "execution-plans"
    plans_dir.mkdir(parents=True, exist_ok=True)


def create_execution_plan_template(project_path: Path):
    """Create execution plan template in .harness/plans/."""

    plans_dir = project_path / ".harness" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    template_md = '''# Execution Plan: {{intent}}

## Status

- [ ] Not started
- [ ] In progress
- [ ] Complete
- [ ] Abandoned

## Intent

One sentence describing what we're building/fixing.

## Context

Links to relevant docs/, issues, or discussions.

## Plan

1. Step one
2. Step two
3. Step three

## Pre-flight Checklist

- [ ] Tests passing before change
- [ ] Lint passing before change
- [ ] Related docs reviewed

## Execution Log

| Turn | Agent | What changed | Why |
|------|-------|--------------|-----|
| 1 | | | |

## Post-flight Checklist

- [ ] Tests passing after change
- [ ] Lint passing after change
- [ ] Docs updated
- [ ] Plan linked/updated

## Related

- Links to PRs, issues, discussions
'''
    (plans_dir / "template.md").write_text(template_md, encoding='utf-8')


def create_bun_template(project_path: Path):
    """Create Bun project template."""
    # Create directory structure
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "src").mkdir(exist_ok=True)
    (project_path / ".harness" / "duckdb").mkdir(parents=True, exist_ok=True)

    # package.json
    package_json = '''{
  "name": "PROJECT_NAME",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "test": "bun test"
  },
  "dependencies": {
    "@aws-sdk/client-s3": "^3.500.0",
    "duckdb": "^0.10.0"
  },
  "devDependencies": {
    "bun-types": "latest"
  }
}'''.replace("PROJECT_NAME", project_path.name)

    (project_path / "package.json").write_text(package_json)

    # Sample test file
    test_content = '''import { describe, it, expect } from "bun:test";

describe("Agent tests", () => {
  it("should pass basic test", () => {
    expect(true).toBe(true);
  });
});
'''

    (project_path / "test" / "agent.test.ts").parent.mkdir(exist_ok=True)
    (project_path / "test" / "agent.test.ts").write_text(test_content)

    # Sample agent module
    agent_content = '''export class Agent {
  private config: Record<string, any>;

  constructor(config?: Record<string, any>) {
    this.config = config || {};
  }

  run(inputData: string): string {
    return `Processed: ${inputData}`;
  }
}
'''

    (project_path / "src" / "agent.ts").write_text(agent_content)


def create_npm_template(project_path: Path):
    """Create npm/Jest project template."""
    # Create directory structure
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "src").mkdir(exist_ok=True)
    (project_path / "tests").mkdir(exist_ok=True)
    (project_path / ".harness" / "duckdb").mkdir(parents=True, exist_ok=True)

    # package.json
    package_json = '''{
  "name": "PROJECT_NAME",
  "version": "0.1.0",
  "scripts": {
    "test": "jest"
  },
  "dependencies": {
    "@aws-sdk/client-s3": "^3.500.0",
    "duckdb": "^0.10.0"
  },
  "devDependencies": {
    "jest": "^29.0.0",
    "@types/jest": "^29.0.0",
    "ts-jest": "^29.0.0",
    "typescript": "^5.0.0"
  }
}'''.replace("PROJECT_NAME", project_path.name)

    (project_path / "package.json").write_text(package_json)

    # jest.config.js
    jest_config = '''module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/tests'],
};
'''

    (project_path / "jest.config.js").write_text(jest_config)

    # tsconfig.json
    tsconfig = '''{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "esModuleInterop": true,
    "strict": true,
    "skipLibCheck": true
  }
}
'''

    (project_path / "tsconfig.json").write_text(tsconfig)

    # Sample test file
    test_content = '''import { Agent } from '../src/agent';

describe('Agent', () => {
  it('should pass basic test', () => {
    const agent = new Agent();
    expect(agent).toBeDefined();
  });
});
'''

    (project_path / "tests" / "agent.test.ts").write_text(test_content)

    # Sample agent module
    agent_content = '''export class Agent {
  private config: Record<string, any>;

  constructor(config?: Record<string, any>) {
    this.config = config || {};
  }

  run(inputData: string): string {
    return `Processed: ${inputData}`;
  }
}
'''

    (project_path / "src" / "agent.ts").write_text(agent_content)


def generate_sandbox_yaml(project_path: Path, services: list[str]) -> str:
    """Generate sandbox.yaml configuration."""
    yaml_content = f"""# Sandbox configuration for {project_path.name}
# Generated by harness-scaffold

services:
"""

    for service in services:
        if service == "s3":
            yaml_content += """  - name: s3
    type: localstack
    services:
      - s3
"""
        elif service == "sqs":
            yaml_content += """  - name: sqs
    type: localstack
    services:
      - sqs
"""
        elif service == "dynamodb":
            yaml_content += """  - name: dynamodb
    type: localstack
    services:
      - dynamodb
"""
        elif service == "duckdb":
            yaml_content += """  - name: duckdb
    type: duckdb
    path: .harness/duckdb/test.db
"""

    return yaml_content


def generate_docker_compose(project_path: Path, services: list[str]) -> str:
    """Generate docker-compose.yml for LocalStack."""
    localstack_services = [s for s in services if s in ["s3", "sqs", "dynamodb", "lambda", "sns", "sqs"]]

    if not localstack_services:
        return ""

    services_yaml = """version: '3.8'

services:
  localstack:
    image: localstack/localstack:3.5
    ports:
      - "4566:4566"
    environment:
      - SERVICES=""" + ",".join(localstack_services) + """
      - DEBUG=0
      - DOCKER_HOST=unix:///var/run/docker.sock
      - AWS_DEFAULT_REGION=us-east-1
    volumes:
      - localstack_data:/var/lib/localstack
      - /var/run/docker.sock:/var/run/docker.sock
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4566/_localstack/health"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  localstack_data:
"""

    return services_yaml


@app.command("create")
@click.argument("name", type=str)
@click.option("--framework", "-f", type=click.Choice(["pytest", "bun", "npm"]), default="pytest",
              help="Test framework to use")
@click.option("--output-dir", "-o", type=click.Path(exists=True, file_okay=False, dir_okay=True), default=".",
              help="Output directory")
@click.option("--services", "-s", type=str, default="s3,duckdb",
              help="Comma-separated list of sandbox services")
def create_project(name: str, framework: str, output_dir: str, services: str):
    """Create a new agent project with sandbox configuration."""

    output_path = Path(output_dir)
    project_path = output_path / name

    if project_path.exists():
        console_print(style(f"Error: Directory already exists: {project_path}", fg="red"))
        raise SystemExit(1)

    console_print(f"Creating {style(framework, fg='cyan')} project: {style(name, fg='green', bold=True)}")

    # Create project structure
    if framework == "pytest":
        create_pytest_template(project_path)
    elif framework == "bun":
        create_bun_template(project_path)
    elif framework == "npm":
        create_npm_template(project_path)

    # Parse services
    service_list = [s.strip() for s in services.split(",")]

    # Generate sandbox.yaml
    sandbox_yaml = generate_sandbox_yaml(project_path, service_list)
    (project_path / ".harness" / "sandbox.yaml").write_text(sandbox_yaml)

    # Generate docker-compose.yml if LocalStack services needed
    docker_compose = generate_docker_compose(project_path, service_list)
    if docker_compose:
        (project_path / "docker-compose.yml").write_text(docker_compose)

    # Create README
    readme_content = f'''# {name}

Agent project created with harness-scaffold.

## Setup

```bash
# Install dependencies
pip install -e .  # For pytest projects
# or
npm install       # For npm/bun projects

# Start sandbox daemon (run once)
harness-scaffold daemon start

# Run tests
harness-verify verify --project .
```

## Sandbox Services

Configured services: {", ".join(service_list)}

## Commands

```bash
# Run tests
harness-verify verify --project .

# Run with JSON output
harness-verify verify --project . --json

# View sandbox status
harness-scaffold daemon status
```
'''

    (project_path / "README.md").write_text(readme_content)

    console_print(f"[OK] Project created: {project_path}")
    console_print("\nNext steps:")
    console_print(f"  1. cd {project_path}")
    console_print("  2. harness-scaffold daemon start")
    console_print("  3. harness-verify verify --project .")


@app.group()
def daemon():
    """Manage the LocalStack sandbox daemon."""
    pass


@daemon.command("start")
def daemon_start():
    """Start the LocalStack daemon (docker-compose up -d)."""

    # Find docker-compose.yml in current directory or parent
    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        # Search in parent directories
        for parent in Path.cwd().parents[:3]:
            candidate = parent / "docker-compose.yml"
            if candidate.exists():
                compose_file = candidate
                break

    if not compose_file.exists():
        console_print(style("Error: docker-compose.yml not found", fg="red"))
        console_print("Run harness-scaffold create or add-sandbox first")
        raise SystemExit(1)

    console_print("Starting LocalStack daemon...")

    try:
        result = subprocess.run(
            ["docker-compose", "-f", str(compose_file), "up", "-d"],
            capture_output=True,
            text=True,
            cwd=compose_file.parent
        )

        if result.returncode == 0:
            console_print(style("[OK]", fg="green") + " LocalStack daemon started")
            console_print("\nWaiting for health check...")

            # Wait for LocalStack to be healthy
            manager = SandboxManager(SandboxConfig(services=[]))
            if manager.wait_for_healthy(timeout=60):
                console_print(style("[OK]", fg="green") + " LocalStack is healthy and ready")
            else:
                console_print(style("[WARN]", fg="yellow") + " LocalStack may still be starting up")
        else:
            console_print(style("[FAIL]", fg="red") + f" Failed to start daemon: {result.stderr}")
            raise SystemExit(1)

    except FileNotFoundError:
        console_print(style("Error: docker-compose not found", fg="red"))
        console_print("Install Docker Compose or use Docker Desktop")
        raise SystemExit(1)


@daemon.command("stop")
def daemon_stop():
    """Stop the LocalStack daemon."""

    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        for parent in Path.cwd().parents[:3]:
            candidate = parent / "docker-compose.yml"
            if candidate.exists():
                compose_file = candidate
                break

    if not compose_file.exists():
        console_print(style("Error: docker-compose.yml not found", fg="red"))
        raise SystemExit(1)

    console_print("Stopping LocalStack daemon...")

    try:
        result = subprocess.run(
            ["docker-compose", "-f", str(compose_file), "down"],
            capture_output=True,
            text=True,
            cwd=compose_file.parent
        )

        if result.returncode == 0:
            console_print(style("[OK]", fg="green") + " LocalStack daemon stopped")
        else:
            console_print(style("[FAIL]", fg="red") + f" Failed to stop daemon: {result.stderr}")
            raise SystemExit(1)

    except FileNotFoundError:
        console_print(style("Error: docker-compose not found", fg="red"))
        raise SystemExit(1)


@daemon.command("status")
def daemon_status():
    """Check the LocalStack daemon status."""

    manager = SandboxManager(SandboxConfig(services=[]))

    if manager.is_daemon_healthy():
        console_print(style("[OK]", fg="green") + " LocalStack daemon is healthy")
        console_print("\nEndpoint: http://localhost:4566")

        # Show container status
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=localstack", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                console_print("\n" + result.stdout)
        except Exception:
            pass
    else:
        console_print(style("[FAIL]", fg="red") + " LocalStack daemon is not running")
        console_print("\nStart with: harness-scaffold daemon start")


@daemon.command("reset")
def daemon_reset():
    """Reset LocalStack state (purge buckets, queues) without restart."""

    manager = SandboxManager(SandboxConfig(services=[]))

    if not manager.is_daemon_healthy():
        console_print(style("[FAIL]", fg="red") + " LocalStack daemon is not running")
        console_print("Start with: harness-scaffold daemon start")
        raise SystemExit(1)

    console_print("Resetting LocalStack state...")

    # Reset by deleting all S3 buckets
    try:
        s3 = manager.get_s3_client()
        response = s3.list_buckets()

        for bucket in response.get("Buckets", []):
            bucket_name = bucket["Name"]
            if not bucket_name.startswith("__"):  # Skip internal buckets
                # Delete all objects first
                objects = s3.list_objects_v2(Bucket=bucket_name)
                if "Contents" in objects:
                    keys = [{"Key": obj["Key"]} for obj in objects["Contents"]]
                    s3.delete_objects(Bucket=bucket_name, Delete={"Objects": keys})
                # Delete bucket
                s3.delete_bucket(Bucket=bucket_name)

        console_print(style("[OK]", fg="green") + " S3 buckets purged")

    except Exception as e:
        console_print(style("[WARN]", fg="yellow") + f" Could not reset S3: {e}")

    console_print(style("[OK]", fg="green") + " LocalStack state reset complete")


@app.command("add-sandbox")
@click.argument("project-path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--services", "-s", type=str, default="s3,duckdb",
              help="Comma-separated list of services")
def add_sandbox(project_path: str, services: str):
    """Add sandbox configuration to an existing project."""

    path = Path(project_path)
    service_list = [s.strip() for s in services.split(",")]

    # Create .harness directory
    harness_dir = path / ".harness" / "duckdb"
    harness_dir.mkdir(parents=True, exist_ok=True)

    # Generate sandbox.yaml
    sandbox_yaml = generate_sandbox_yaml(path, service_list)
    (path / ".harness" / "sandbox.yaml").write_text(sandbox_yaml)

    # Generate docker-compose.yml if needed
    docker_compose = generate_docker_compose(path, service_list)
    if docker_compose:
        (path / "docker-compose.yml").write_text(docker_compose)

    console_print(style("[OK]", fg="green") + f" Added sandbox to: {path}")
    console_print(f"\nConfigured services: {', '.join(service_list)}")
    console_print("\nNext steps:")
    console_print(f"  1. cd {path}")
    console_print("  2. harness-scaffold daemon start")


if __name__ == "__main__":
    app()
