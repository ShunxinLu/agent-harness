# Harness Diff Analysis: `codex/harness-phase6-rollout` vs `origin/main`

Last updated: 2026-03-02

## Snapshot

- Analysis date: 2026-03-02 (America/Los_Angeles)
- Current branch: `codex/harness-phase6-rollout` at `92b4ba26b721ceb1fda919bf3e0f9e206235b3ee`
- Main branch tip compared: `origin/main` at `30064e140da3108b82ab718de9e2a99b97c758cf`
- Merge base: `042c66a6a36a5a6c28eeb9e3aedfa7bbf24c6636`
- Divergence:
  - `origin/main` only: 3 commits
  - `codex/harness-phase6-rollout` only: 7 commits

## Executive Summary

Both branches evolved from the initial harness in different directions:

1. `origin/main` optimized for package naming/agent-legibility scaffolding:
   - Renamed package from `harness` to `agent_harness`
   - Added `harness-lint` and `harness-cleanup` commands
   - Added scaffold generators for `AGENTS.md`, `CLAUDE.md`, Copilot instructions, `tach.toml`, and capabilities manifest
2. `codex/harness-phase6-rollout` expanded runtime capabilities significantly:
   - Added policy engine (local + OPA backend), task contracts, manifest/eval workflow, session management, OTEL hooks, Alembic/SQLAlchemy migration path, npm runner, CI, docs, and broad tests

The correct consolidation path is not a simple cherry-pick. It should be a controlled integration with package convergence plus feature union.

## Commit-Level Divergence

### `origin/main` only

- `4c06a8f` Refactor: Rename package from `harness` to `agent-harness`
- `cc1054b` Phase 6: Universal Harness Engineering (lint/cleanup + agent instruction scaffolding)
- `30064e1` Phase 6: docs/ knowledge system and execution plan templates

### `codex/harness-phase6-rollout` only

- `7ad8589` Phase-0 hardening and safe data-mode defaults
- `ee17238` A03 optional OpenTelemetry spans
- `7d15dbc` A04 pluggable policy backends (OPA adapter)
- `b51886a` A05 eval provider abstraction and adapters
- `8a03b27` A06 testcontainers integration lane + CI job
- `c96f0ef` A07 service architecture package + phase6 docs
- `92b4ba2` remaining hardening/migration updates

## Scope and Scale

- Current branch unique delta (`origin/main...HEAD`):
  - 67 files changed
  - 7289 insertions, 269 deletions
- Main branch unique delta (`HEAD...origin/main`):
  - 21 files changed
  - 1481 insertions, 56 deletions

This indicates Phase6 branch is the larger functional superset, while `origin/main` carries critical structural and tooling deltas that should not be dropped.

## Architectural Differences by Area

## 1) Package and Distribution Strategy

### `origin/main`

- Python package path: `src/agent_harness`
- Project name in `pyproject.toml`: `agent-harness`
- Entry points target `agent_harness.*`

### `codex/harness-phase6-rollout`

- Python package path: `src/harness`
- Project name in `pyproject.toml`: `harness`
- Entry points target `harness.*`

### Consolidation implication

This is the highest-conflict area. If unresolved, imports/scripts/packaging will drift or break.

## 2) CLI and MCP Surface

### `origin/main` strengths

- Adds `harness-lint` and `harness-cleanup` CLIs
- MCP exposes `lint_check` and `cleanup_run`

### `codex/harness-phase6-rollout` strengths

- Extends `harness-verify` with:
  - `init-project`, `onboard`, `resume-check`
  - `feature next`, `feature update`
  - `contract validate`
  - `eval run`
  - `db migrate`
- MCP adds:
  - `initialize_session`
  - `get_next_feature`
  - `update_feature_status`
  - policy + contract + manifest aware `run_tests`

### Conflict

- `origin/main` has lint/cleanup MCP tools absent in Phase6 branch
- Phase6 has session/feature tools absent in `origin/main`
- These should be combined, not chosen as either/or

## 3) Runtime Hardening and Data Safety

### `codex/harness-phase6-rollout` improvements

- `sandbox.get_s3_client()` is safe-by-default:
  - refuses implicit real AWS unless `HARNESS_ALLOW_REAL_AWS=1`
- Policy checks enforce data mode and project boundaries
- Task-contract validation gate (optional strict mode)
- Separate session and project run IDs with manifest evidence

### `origin/main`

- Falls back to direct `boto3.client("s3")` when sandbox missing
- No policy or contract enforcement path

### Consolidation decision

Keep Phase6 safety defaults; do not regress to implicit real AWS fallback.

## 4) Persistence and Trace Layer

### `codex/harness-phase6-rollout` improvements

- Adds `parent_run_id` support in run history
- Adds repository abstraction (`DuckDBRepository`)
- Parameterized trace/cache SQL queries (lower injection risk)
- Adds execution status in test result model (`ok/timeout/tool_missing/runner_error`)
- Adds Alembic + SQLAlchemy migration path and schema models

### `origin/main`

- Simpler direct-connection implementation
- Some string-formatted SQL usage in tracing/trace viewer paths

### Consolidation decision

Keep Phase6 persistence model and migration path.

## 5) Scaffolding and Agent Legibility

### `origin/main` strengths

Scaffold includes generation of:

- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `tach.toml`
- `.harness/capabilities.json`
- docs structure and execution plan templates

### `codex/harness-phase6-rollout`

- Scaffold focuses on runtime project setup and sandbox templates
- Does not include the full legibility template set from `origin/main`
- Adds repository-level docs (`docs/`) and doc lint script

### Consolidation decision

Merge `origin/main` legibility templates into Phase6 scaffold behavior.

## 6) Test and CI Maturity

### `codex/harness-phase6-rollout`

- Adds CI workflow `.github/workflows/harness-ci.yml`
- Adds 19 test files and broad coverage across new features

### `origin/main`

- No equivalent test suite additions in divergence window

### Consolidation decision

Keep Phase6 tests/CI as baseline and extend for merged lint/cleanup + package migration.

## File-Level Merge Hotspots

Highest-risk files where both branches diverged semantically:

- `README.md`
- `pyproject.toml`
- `src/*/mcp_server.py`
- `src/*/verify.py`
- `src/*/scaffold.py`
- `src/*/tracing.py`
- `src/*/cache.py`
- `src/*/runners/generic_runner.py`
- `src/*/sandbox/__init__.py`
- `.claude/settings.local.json`

Expected conflict classes:

1. Namespace/path conflicts (`harness` vs `agent_harness`)
2. Tool-surface conflicts (MCP methods)
3. Dependency-set conflicts (`lint/cleanup/frontend/data` vs `migrations/observability/integration`)
4. Behavior regression risk (safety defaults and run identity model)

## Recommended Consolidation Strategy

## Phase 1: Create a dedicated integration branch

1. Branch from current Phase6 tip:
   - `git switch -c codex/consolidate-main-harness`
2. Merge `origin/main` into this integration branch.
3. Resolve only structural conflicts first (do not refactor behavior in the same step).

## Phase 2: Converge on package namespace with compatibility shim

Recommended canonical namespace: `agent_harness` (matches `origin/main` rename intent).

Plan:

1. Move canonical source to `src/agent_harness`.
2. Keep a compatibility shim package `src/harness` for one transition cycle.
3. Update all internal imports to canonical namespace.
4. Keep CLI command names stable (`harness-verify`, `harness-scaffold`, `harness-mcp`, `harness-lint`, `harness-cleanup`).

Why this is the right approach:

- Avoids perpetual divergence with upstream `main`
- Preserves current users/scripts via shim
- Enables staged deprecation instead of hard break

## Phase 3: Feature union (not replacement)

From Phase6 branch, preserve:

- policy/contracts/manifest/session/evals/db/observability/test/CI stack
- safe-by-default sandbox behavior
- session/project run identity model

From `origin/main`, preserve and port:

- `lint.py`, `cleanup.py`
- MCP `lint_check`, `cleanup_run`
- scaffold generation for AGENTS/CLAUDE/Copilot/tach/capabilities/docs skeleton
- related dependency extras and local permissions updates

## Phase 4: Lock behavior with tests

Add/extend tests covering:

1. Namespace compatibility (`import harness.*` and `import agent_harness.*`)
2. MCP tool registry includes both:
   - session/feature tools
   - lint/cleanup tools
3. Sandbox safety (no implicit real AWS in mock mode)
4. Verify run IDs:
   - one session run ID
   - per-project run IDs
   - parent linkage persisted
5. Scaffold output includes both runtime files and legibility templates

## Phase 5: Validation loop before merge

Recommended validation gates:

1. `python3 -m compileall src tests scripts`
2. `python3 -m pytest -q`
3. `python3 scripts/lint_docs.py`
4. `python3 -m pytest -q tests/integration -m integration` (when container runtime is available)
5. CLI smoke:
   - `harness-verify --help`
   - `harness-scaffold --help`
   - `harness-mcp --help`
   - `harness-lint --help`
   - `harness-cleanup --help`

## Practical Merge Order (Low-Risk Sequence)

1. Namespace and `pyproject.toml` reconciliation
2. Core runtime (`verify`, `mcp_server`, `cache`, `tracing`, `sandbox`)
3. Main-only lint/cleanup/scaffold legibility features
4. Docs + README harmonization
5. Final validation matrix

## Decision Checklist Before Implementation

- Confirm canonical package name: `agent_harness` with `harness` shim
- Confirm MCP tool contract should include both feature-session tools and lint/cleanup tools
- Confirm default project scan root policy (`cwd` recommended)
- Confirm deprecation window for old import path (`harness.*`)

## Final Recommendation

Use a **feature-union consolidation** centered on the Phase6 runtime and safety model, while importing `origin/main`’s package rename direction and legibility/lint-cleanup tooling.

This yields the most complete harness with the least long-term maintenance risk:

1. No loss of Phase6 functionality and tests
2. No loss of `origin/main` legibility and maintenance tooling
3. Single converged architecture instead of two competing implementations
