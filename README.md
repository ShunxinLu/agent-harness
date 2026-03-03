# Zero-Trust Agent Harness

A comprehensive test harness for AI agent development with multi-framework support, sandbox isolation, tracing, and MCP server integration for Claude Code.

## Features

- **Multi-Framework Support**: pytest, pyspark, bun, npm, maven, gradle, sbt, cargo, go
- **MCP Server**: Direct integration with Claude Code for autonomous testing
- **Sandbox Isolation**: LocalStack + DuckDB for AWS/local database testing
- **Execution Tracing**: DuckDB-backed trace storage with SQL query support
- **Result Caching**: Persistent test result storage with trend analysis
- **Project Scaffolding**: Generate new projects with pre-configured test setups

## Installation

```bash
cd harness
pip install -e .
```

### For Development

```bash
pip install -e ".[dev]"
```

### For Schema Migrations

```bash
pip install -e ".[migrations]"
```

### For OpenTelemetry Spans (Optional)

```bash
pip install -e ".[observability]"
```

### For Integration Tests (Optional)

```bash
pip install -e ".[integration]"
```

### Harness Self-Validation

Run the harness repository checks before merging changes:

```bash
python3 -m compileall src tests
python3 -m pytest -q
python3 scripts/lint_docs.py
```

Run integration tests when container runtime is available:

```bash
python3 -m pytest -q tests/integration -m integration
```

## Quick Start

### Run tests (auto-detect projects)

```bash
harness-verify verify
```

By default, project scanning starts from the current working directory.

### Run with JSON output (for Claude Code)

```bash
harness-verify verify --json
```

### Run specific project

```bash
harness-verify verify --project path/to/project
```

### Run with explicit data mode (safe default)

```bash
harness-verify verify --project path/to/project --data-mode mock
```

### Run only previously failed tests

```bash
harness-verify verify --last-failed
```

### Apply database schema migrations

```bash
harness-verify db migrate
```

### Enable OpenTelemetry spans (optional)

```bash
export HARNESS_OTEL_ENABLED=1
export HARNESS_OTEL_EXPORTER=console  # or: otlp
harness-verify verify --project .
```

### Select policy backend (optional)

```bash
export HARNESS_POLICY_BACKEND=local   # default
# or:
export HARNESS_POLICY_BACKEND=opa
export HARNESS_OPA_URL=http://localhost:8181/v1/data/harness/allow
```

### Run evals with explicit provider

```bash
harness-verify eval run --project . --provider local
```

## CLI Commands

### harness-verify

| Command | Description |
|---------|-------------|
| `verify` | Run tests with optimized output |
| `init-project` | Generate `.harness` long-running workflow artifacts |
| `onboard` | Bootstrap `.harness` artifacts and run baseline verification |
| `resume-check` | Validate startup bearings and optional smoke check |
| `list` | List all detectable test projects |
| `detect` | Detect test framework for a path |
| `feature next` | Select next pending feature from feature ledger |
| `feature update` | Update feature pass/fail status with evidence |
| `contract validate` | Validate `.harness/task-contract.yaml` schema |
| `eval run` | Evaluate manifest artifacts for policy/contract/test compliance |
| `db migrate` | Apply Alembic migrations for harness persistence schema |
| `cache status` | Show cache statistics |
| `cache trend <project>` | Show test trend over time |
| `cache clear` | Clear test result cache |
| `trace view <run-id>` | View trace events |
| `trace export <run-id>` | Export traces as JSON |
| `trace compare <id1> <id2>` | Compare two trace runs |
| `trace list` | List recent trace runs |
| `trace analyze` | Analyze error patterns |

### harness-scaffold

| Command | Description |
|---------|-------------|
| `create <name>` | Create a new project with test scaffolding |
| `add-sandbox <path>` | Add sandbox configuration to existing project |
| `daemon start` | Start LocalStack daemon (docker-compose up -d) |
| `daemon stop` | Stop LocalStack daemon |
| `daemon status` | Check LocalStack health |
| `daemon reset` | Purge S3 buckets without restart |

### harness-mcp

Run the MCP server for Claude Code integration:

```bash
harness-mcp
```

## Supported Frameworks

| Framework | Detection Files | Test Command |
|-----------|-----------------|--------------|
| pytest | `pytest.ini`, `conftest.py`, `test_*.py` | `pytest tests/ -v --json-report` |
| pyspark | `spark*.py`, `*_spark.py` | `pytest --spark-home=find` |
| bun | `bunfig.toml`, `*.test.ts` | `bun test` |
| npm | `package.json` with test script | `npm test` |
| maven | `pom.xml` | `mvn test` |
| gradle | `build.gradle` | `gradle test` |
| sbt | `build.sbt` | `sbt test` |
| cargo | `Cargo.toml` | `cargo test` |
| go | `go.mod` | `go test ./...` |

## Examples

### Create a new project with sandbox

```bash
# Create pytest project with S3 and DuckDB sandbox
harness-scaffold create my-agent --framework pytest --services s3,duckdb

cd my-agent

# Start LocalStack daemon (one-time setup)
harness-scaffold daemon start

# Run tests
harness-verify verify --project .
```

### View test trends

```bash
# Show last 10 runs for a project
harness-verify cache trend my-agent --limit 10
```

### Debug with traces

```bash
# Run with tracing enabled
harness-verify verify --project . --trace

# View trace events
harness-verify trace view <run-id>

# Export for analysis
harness-verify trace export <run-id> -o traces.json
```

### Analyze error patterns

```bash
# Find recurring error patterns
harness-verify trace analyze --pattern "connection" --min-count 3
```

## MCP Server Integration

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "harness": {
      "command": "harness-mcp"
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `run_tests` | Run tests for any project |
| `initialize_session` | Collect resume context and optional smoke-check output |
| `list_projects` | List projects in a directory |
| `detect_framework` | Detect framework for a path |
| `get_next_feature` | Select the next pending feature from feature ledger |
| `update_feature_status` | Update feature pass/fail with evidence checks |
| `get_cache_status` | Get cache statistics |
| `get_cache_trend` | Get test trend over time |
| `get_last_failed` | Get recently failed tests |
| `list_traces` | List recent trace runs |
| `get_trace` | Get trace events for a run |
| `analyze_errors` | Analyze error patterns |
| `clear_cache` | Clear the test cache |

`run_tests` accepts:
- `project_path`
- `json_output`
- `last_failed` (pytest/pyspark only)
- `data_mode` (`mock`, `metadata`, `human-contract`; default `mock`)

`run_tests` returns:
- `session_run_id`
- `project_run_id`
- `policy_decisions`

## Safety Defaults

- Safe-by-default data mode is `mock`.
- In `mock` mode, direct real-AWS fallback is blocked by default.
- To explicitly allow real AWS clients in sandbox helpers, set:

```bash
export HARNESS_ALLOW_REAL_AWS=1
```

Use this override only when intentionally running outside safe-local mode.

## Project Structure

```
harness/
├── src/harness/
│   ├── __init__.py          # Package init with lazy exports
│   ├── verify.py            # Main CLI (Click)
│   ├── scaffold.py          # Project scaffolding CLI
│   ├── config.py            # Framework detection (10 frameworks)
│   ├── cache.py             # DuckDB-backed result cache
│   ├── tracing.py           # Trace decorator and store
│   ├── trace_viewer.py      # Trace CLI and analysis
│   ├── mcp_server.py        # MCP server for Claude Code
│   ├── runners/
│   │   ├── __init__.py
│   │   ├── pytest_runner.py  # Pytest executor
│   │   ├── bun_runner.py     # Bun executor
│   │   ├── npm_runner.py     # npm executor
│   │   └── generic_runner.py # Maven/Gradle/SBT/Cargo/Go
│   ├── sandbox/
│   │   └── __init__.py       # LocalStack + DuckDB management
│   └── output/
│       └── compressor.py     # Stack trace compression
├── pyproject.toml
└── README.md
```

## Architecture

Detailed architecture and OSS replacement decisions:
- `docs/harness-architecture-design.md`

```
┌─────────────────────────────────────────────────────────────┐
│                    harness-verify CLI                        │
├─────────────────────────────────────────────────────────────┤
│  detect  │  list  │  verify  │  trace  │  cache  │  scaffold│
└────┬─────────┬─────────┬──────────┬─────────┬─────────┬──────┘
     │         │         │          │         │         │
     ▼         ▼         ▼          ▼         ▼         ▼
┌─────────────────────────────────────────────────────────────┐
│                      Core Modules                            │
├──────────────┬──────────────┬──────────────┬────────────────┤
│   config.py  │   runners/   │   output/    │   sandbox/     │
│  (detection) │ (execution)  │ (compression)│  (isolation)   │
├──────────────┼──────────────┼──────────────┼────────────────┤
│   tracing.py │   cache.py   │  templates/  │                │
│  (debugging) │ (performance)│ (scaffolding)│                │
└──────────────┴──────────────┴──────────────┴────────────────┘
     │              │              │
     ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                   External Services                          │
│    LocalStack (Docker)  │  DuckDB  │  pytest  │  bun/npm   │
└─────────────────────────────────────────────────────────────┘
```

## Data Storage

Test results and traces are stored in:

- **Windows**: `~/.harness/data/harness.duckdb`
- **Linux/Mac**: `~/.harness/data/harness.duckdb`

The DuckDB database enables complex SQL queries across test runs:

```sql
-- Correlate test failures with agent traces
SELECT t.test_name, tr.tool_name, tr.error_type
FROM test_results t
JOIN traces tr ON t.run_id = tr.run_id
WHERE t.status = 'failed'
  AND tr.timestamp > NOW() - INTERVAL '24 hours'
```

## License

MIT
