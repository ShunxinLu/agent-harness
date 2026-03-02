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
import shutil
from pathlib import Path
from typing import Optional

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
    console_print(f"\nNext steps:")
    console_print(f"  1. cd {project_path}")
    console_print(f"  2. harness-scaffold daemon start")
    console_print(f"  3. harness-verify verify --project .")


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
    console_print(f"  2. harness-scaffold daemon start")


if __name__ == "__main__":
    app()
