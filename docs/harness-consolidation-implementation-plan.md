# Harness Consolidation Implementation Plan

Last updated: 2026-03-03

## Document Purpose

Define an executable plan to consolidate:

- `codex/harness-phase6-rollout` (runtime hardening, policy/evals/observability/migrations/tests/CI)
- `origin/main` (package rename, lint/cleanup tooling, agent-legibility scaffold templates)

into one canonical harness implementation without regressing safety, traceability, or developer ergonomics.

## Program Task Contract

### Goal

Ship a single consolidated harness that combines the strongest capabilities from both branches and becomes the only supported implementation path.

### Constraints

- Preserve current Phase6 runtime safety and governance behavior.
- Adopt `agent_harness` canonical namespace to align with `origin/main`.
- Maintain backward compatibility for existing `harness.*` imports during transition.
- Keep CLI command names stable (`harness-verify`, `harness-scaffold`, `harness-mcp`, `harness-lint`, `harness-cleanup`).
- Keep changes reviewable by splitting into sequenced PRs with explicit validation gates.

### Files in Scope

- Packaging and entrypoints: `pyproject.toml`
- Core runtime: `src/harness/*` and future `src/agent_harness/*`
- MCP/CLI surface: `src/*/verify.py`, `src/*/mcp_server.py`, `src/*/scaffold.py`
- Tooling: `src/*/lint.py`, `src/*/cleanup.py`
- Persistence/trace/safety: cache/tracing/sandbox/policy/contracts/evals/db/observability modules
- Tests and CI: `tests/**`, `.github/workflows/harness-ci.yml`
- Documentation: `README.md`, `docs/**`

### Acceptance Criteria

- One canonical package (`agent_harness`) builds and runs.
- Compatibility shim keeps `harness.*` imports functional for one transition cycle.
- Consolidated MCP toolset includes both:
  - runtime governance/session tools
  - lint/cleanup tools
- Safe-by-default AWS behavior remains enforced in mock mode.
- Full test/CI/doc lint pass on consolidated branch.

### Validation Steps

1. `python3 -m compileall src tests scripts`
2. `python3 -m pytest -q`
3. `python3 scripts/lint_docs.py`
4. `python3 -m pytest -q tests/integration -m integration` (if container runtime available)
5. CLI smoke:
   - `harness-verify --help`
   - `harness-scaffold --help`
   - `harness-mcp --help`
   - `harness-lint --help`
   - `harness-cleanup --help`

## Consolidated Target State

## Keep from `codex/harness-phase6-rollout`

- Policy engine and backends (`local`, `opa`)
- Task contract validation
- Session + project run identity, manifests, feature ledger, resume context
- Eval provider abstraction and runner
- Safe-by-default sandbox behavior (no implicit real AWS fallback)
- Repository abstraction and parameterized persistence paths
- Alembic/SQLAlchemy migration scaffolding
- Optional OpenTelemetry spans
- Expanded tests and CI coverage

## Keep from `origin/main`

- Canonical package naming direction: `agent_harness`
- `harness-lint` and `harness-cleanup` commands
- MCP lint/cleanup tools
- Scaffold-generated agent-legibility files:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `.github/copilot-instructions.md`
  - `tach.toml`
  - `.harness/capabilities.json`
  - docs and execution-plan skeletons

## Closer-to-Recommended Patterns (OpenAI/Anthropic)

- Strongly keep: explicit guardrails, policy checks, eval loops, structured outputs, safety defaults.
- Also keep: clear project instruction scaffolds and mechanical lint/cleanup automation.
- Avoid regressions to implicit cloud access and ambiguous run identity.

## Detailed Implementation Plan

## Phase 0: Preflight and Branching

### Goal

Prepare a clean integration lane and baseline measurements.

### Steps

1. Create integration branch from Phase6 tip:
   - `git switch codex/harness-phase6-rollout`
   - `git switch -c codex/consolidate-main-harness`
2. Capture baseline:
   - current test pass/fail
   - CLI help outputs
   - MCP tool list snapshot
3. Merge `origin/main` into integration branch and stop at conflicts.

### Acceptance Criteria

- Integration branch exists.
- Conflict set is visible and documented.
- Baseline snapshots are recorded in PR description.

### Validation

- `git status --short --branch`
- `git log --oneline --left-right origin/main...HEAD`

## Phase 1: Package Namespace Convergence

### Goal

Adopt `agent_harness` canonical namespace while preserving compatibility.

### Steps

1. Set canonical package path to `src/agent_harness`.
2. Add compatibility shim package at `src/harness`:
   - re-export canonical modules for backward import compatibility.
3. Update `pyproject.toml`:
   - project name to `agent-harness`
   - wheel package list to canonical path
   - retain full extras from both branches (`migrations`, `observability`, `integration`, `lint`, `cleanup`, plus existing dev extras)
4. Ensure CLI entrypoints resolve to canonical modules.
5. Add deprecation note for `harness.*` import path in README/docs.

### Files in Scope

- `pyproject.toml`
- `src/agent_harness/**`
- `src/harness/**` (compatibility layer)
- `README.md`

### Acceptance Criteria

- `import agent_harness` and `import harness` both work.
- Installed scripts still run with unchanged command names.

### Validation

- `python3 -c "import agent_harness, harness; print('ok')"`
- CLI smoke checks

## Phase 2: Core Runtime Merge (No Behavior Regression)

### Goal

Preserve Phase6 runtime behavior as the source of truth.

### Steps

1. Keep Phase6 versions for:
   - `verify.py`
   - `cache.py`
   - `tracing.py`
   - `sandbox/__init__.py`
   - `manifest.py`
   - `session_manager.py`
   - `policy*`
   - `contracts.py`
   - `evals/*`
   - `db/*`
   - `observability/*`
2. Resolve merge conflicts explicitly in these files in favor of:
   - safe defaults
   - session/project run ID model
   - parameterized queries/repository usage
3. Keep npm runner separation (`npm_runner.py`) and explicit runner dispatch.

### Acceptance Criteria

- No regression in policy/contract enforcement behavior.
- No regression to implicit AWS fallback behavior.
- Existing Phase6 test suite remains green.

### Validation

- full unit test run
- targeted tests:
  - run identity
  - sql safety
  - policy engine
  - task contract
  - eval runner

## Phase 3: Tooling Union (Lint/Cleanup + MCP Surface)

### Goal

Combine both branches' operational tooling into a single interface contract.

### Steps

1. Port `lint.py` and `cleanup.py` into canonical package.
2. Wire CLI entrypoints:
   - `harness-lint`
   - `harness-cleanup`
3. Extend consolidated MCP server with lint/cleanup handlers while keeping Phase6 session/feature handlers.
4. Define stable MCP tool catalog:
   - `run_tests`
   - `initialize_session`
   - `list_projects`
   - `detect_framework`
   - `get_next_feature`
   - `update_feature_status`
   - `get_cache_status`
   - `get_cache_trend`
   - `get_last_failed`
   - `list_traces`
   - `get_trace`
   - `analyze_errors`
   - `clear_cache`
   - `lint_check`
   - `cleanup_run`

### Acceptance Criteria

- MCP advertises and executes complete unified toolset.
- Lint/cleanup commands run and return structured outputs.

### Validation

- MCP tool list smoke test
- `harness-lint check --format json`
- `harness-cleanup run --dry-run --format json`

## Phase 4: Scaffold Union (Developer + Agent Legibility)

### Goal

Merge scaffold outputs so new projects get both runtime harness setup and multi-agent legibility artifacts.

### Steps

1. Integrate `origin/main` scaffold generators into consolidated scaffold flow.
2. Ensure generated project includes:
   - runtime test scaffolding + sandbox templates
   - AGENTS/CLAUDE/Copilot instructions
   - `tach.toml`
   - capabilities manifest
   - docs/execution plan skeletons
3. Ensure generated files use UTF-8 and platform-safe paths.

### Acceptance Criteria

- Scaffold output contains full union of required artifacts.
- Generated project is immediately runnable and agent-readable.

### Validation

- Create fresh temp scaffold project
- Assert expected files exist
- Run verify/lint/cleanup from generated project

## Phase 5: Tests, CI, and Contract Locks

### Goal

Lock merged behavior with automated checks to prevent branch drift recurrence.

### Steps

1. Add compatibility tests:
   - import namespace dual support
2. Add MCP catalog contract test for unified tool set.
3. Add scaffold output contract test for required generated files.
4. Keep and run existing Phase6 tests.
5. Keep CI workflow and ensure it installs all needed extras.

### Acceptance Criteria

- CI green with merged code path.
- Regression tests cover all prior conflict classes.

### Validation

- local test matrix and CI run

## Phase 6: Docs, Migration Notes, and Rollout

### Goal

Publish one authoritative workflow for developers.

### Steps

1. Update README:
   - canonical package/install instructions
   - unified CLI/MCP surface
   - safe defaults and optional overrides
2. Update docs index to include this consolidation plan and final architecture note.
3. Add migration note:
   - `harness.*` imports deprecated timeline
   - what changed for MCP clients

### Acceptance Criteria

- Documentation reflects only consolidated behavior.
- Teams can migrate without oral knowledge transfer.

### Validation

- `python3 scripts/lint_docs.py`

## PR Slicing Plan

Create sequential PRs to keep risk manageable.

1. PR-1: Integration branch + namespace convergence + shim
2. PR-2: Runtime conflict resolution (keep Phase6 behavior)
3. PR-3: Lint/Cleanup commands + MCP tooling union
4. PR-4: Scaffold union + generator tests
5. PR-5: Docs and migration notes
6. PR-6: Final hardening, full CI proof, and merge

Each PR must include:

- exact files changed
- acceptance criteria
- validation command outputs summary

## Risk Register and Mitigation

## Risk 1: Namespace breakage

- Mitigation: compatibility shim + import tests + release note.

## Risk 2: MCP client incompatibility

- Mitigation: additive tool catalog, avoid renaming existing tool contracts.

## Risk 3: Safety regression

- Mitigation: explicit tests for mock mode and AWS guard behavior.

## Risk 4: Overlarge merge conflicts

- Mitigation: isolate by workstream and resolve in scoped PRs.

## Risk 5: Developer friction from new rules

- Mitigation: keep defaults simple, make strictness opt-in where possible, provide clear error messages.

## Rollback Strategy

If a consolidation PR regresses runtime behavior:

1. Revert only the offending PR (not the entire integration series).
2. Keep previously validated PRs.
3. Re-run full validation matrix.
4. Re-land with additional tests for the escaped regression.

## Developer Workflow Impact (Post-Consolidation)

## Improvements

- One package and one mental model.
- Better default safety for local/agent runs.
- Better forensic traceability (session + project IDs + manifests).
- Standardized maintenance loops (`harness-lint`, `harness-cleanup`).
- Better bootstrap quality for AI-assisted development via scaffold templates.

## Tradeoffs

- Slightly higher initial setup complexity due to richer feature set.
- More explicit policy/contract checks can block runs until corrected.

## Net Effect

Higher reliability and reproducibility with acceptable overhead, especially for teams running autonomous or semi-autonomous coding agents.

## Exit Checklist (Definition of Done)

- Canonical package is `agent_harness` and compatibility shim exists.
- Unified MCP tool list and CLI commands are functional.
- Safe-by-default sandbox behavior is unchanged from Phase6.
- Consolidated scaffold generates runtime + legibility artifacts.
- Test matrix and CI pass.
- README/docs/migration notes updated.
