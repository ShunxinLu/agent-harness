# Harness Implementation Task Sequence

Last updated: 2026-03-03

This is the execution sequence for `docs/harness-team-implementation-plan-v2.md`.

## Sequencing rules

1. Complete tasks in order unless a task is explicitly parallelizable.
2. Every task must have:
   - code changes
   - automated checks (unit/integration where possible)
   - updated docs if behavior changed
3. Do not start the next task until current task acceptance criteria are met or explicitly deferred.

## Task list

## Phase 0 - Runtime hardening

### T01 - Run identity and persistence model
Status: `completed`

Goal:
1. Prevent multi-project run collisions.
2. Preserve one top-level session run ID while storing unique per-project run IDs.

Scope:
1. `src/harness/cache.py`
2. `src/harness/verify.py`
3. `src/harness/mcp_server.py` (alignment for run metadata consistency)

Deliverables:
1. `run_history` supports `parent_run_id`.
2. `verify` uses `session_run_id` + `project_run_id`.
3. Cache rows and traces remain linkable.

Acceptance criteria:
1. Multi-project verify run no longer violates primary-key constraints.
2. Trend/last-failed queries still work.
3. CLI JSON output includes session-level run ID and per-project run IDs.

Validation:
1. Unit test for multi-project store behavior.
2. Unit test for last-failed query against project-level run IDs.

### T02 - SQL safety and filter correctness
Status: `completed`

Goal:
1. Remove SQL interpolation in operational paths.
2. Fix malformed optional `WHERE/AND` query construction.

Scope:
1. `src/harness/cache.py`
2. `src/harness/tracing.py`
3. `src/harness/mcp_server.py`
4. `src/harness/trace_viewer.py` (if needed for list/view queries)

Acceptance criteria:
1. Query paths are parameterized.
2. No malformed `FROM ... AND ...` when optional filters are absent.
3. Query behavior unchanged for expected inputs.

Validation:
1. Unit tests for optional filter combinations.
2. Fuzz tests for pattern/run IDs in trace search paths.

### T03 - Trace timestamp decoding reliability
Status: `completed`

Goal:
1. Make trace row decoding robust across DB driver return types.

Scope:
1. `src/harness/tracing.py`
2. `src/harness/trace_viewer.py`

Acceptance criteria:
1. Timestamp parsing handles `datetime` and string values.
2. Trace list/view/compare render correctly.

Validation:
1. Unit tests for both timestamp representations.

### T04 - Exit semantics and machine-safe output
Status: `completed`

Goal:
1. Ensure CLI exits non-zero on runner/tool failures, not just test assertion failures.
2. Remove side-effect printing from output helpers used by MCP.

Scope:
1. `src/harness/output/compressor.py`
2. `src/harness/verify.py`
3. `src/harness/mcp_server.py`
4. `src/harness/runners/*`

Acceptance criteria:
1. `verify` fails on timeout/tool-missing/runner errors.
2. MCP responses remain protocol-clean in all output modes.

Validation:
1. Unit tests for timeout/tool-missing code paths.
2. MCP unit test to assert no unsolicited stdout noise.

### T05 - Baseline test harness for this repository
Status: `deferred (env-blocked)`

Goal:
1. Add initial repo tests for P0 behavior and a repeatable local test command.

Scope:
1. `tests/` (new)
2. `pyproject.toml` (dev tooling additions if needed)
3. `README.md` (developer validation instructions)

Acceptance criteria:
1. Core cache/trace/verify modules have regression coverage for T01-T04.
2. `pytest -q` works as the baseline local validation command.

Validation:
1. `python3 -m compileall src`
2. `pytest -q`

Deferral note:
1. Local environment currently cannot install test dependencies from network, so `pytest` execution is blocked.
2. Task implementation work is done (tests added + README validation loop), but final runtime validation is pending when dependency install is available.

## Phase 1 - Long-running session workflow

### T06 - `init-project` command and artifact templates
Status: `completed`

Goal:
1. Generate required session artifacts for harness-driven long-running work.

Scope:
1. `src/harness/verify.py` (or new command module)
2. `src/harness/scaffold.py` (shared templates if appropriate)
3. `.harness/*` template generation logic

Acceptance criteria:
1. Command creates `.harness/init.sh`, `feature_list.json`, `progress.md`, task/data contract templates.
2. Command is idempotent with safe overwrite flags.

### T07 - Feature ledger schema + enforcement
Status: `completed`

Goal:
1. Enforce one-feature-at-a-time progression with explicit status and evidence.

Scope:
1. `src/harness/contracts.py` (new)
2. `src/harness/session_manager.py` (new)
3. `src/harness/mcp_server.py` (feature tools)

Acceptance criteria:
1. Feature status cannot move to pass without verification refs.
2. Non-status fields are protected during coding sessions unless explicitly unlocked.

### T08 - Resume/bearings workflow
Status: `completed`

Goal:
1. Ensure session start and restart are artifact-driven.

Scope:
1. `src/harness/session_manager.py`
2. `src/harness/verify.py` (`resume-check` command)
3. `src/harness/mcp_server.py` (`initialize_session`)

Acceptance criteria:
1. Resume check validates progress, feature state, and smoke check execution.

## Phase 2 - Policy and contracts

### T09 - Runtime policy engine
Status: `completed`

Goal:
1. Enforce command/path/network/data-mode boundaries with auditable decisions.

Scope:
1. `src/harness/policy.py` (new)
2. `src/harness/verify.py`
3. `src/harness/mcp_server.py`
4. `src/harness/tracing.py` (policy events)

### T10 - Task/data contract validation
Status: `completed`

Goal:
1. Enforce contract completeness before execution.

Scope:
1. `src/harness/contracts.py`
2. CLI/MCP preflight checks

## Phase 3 - Legibility and verification discipline

### T11 - Run manifest implementation
Status: `completed`

Goal:
1. Persist full run metadata and links to tests/evals/policy outcomes.

Scope:
1. `src/harness/manifest.py` (new)
2. `src/harness/verify.py`
3. `src/harness/mcp_server.py`

### T12 - Docs lifecycle linting
Status: `completed`

Goal:
1. Enforce docs index hygiene and stale-plan checks.

Scope:
1. `scripts/` doc lint utility (new)
2. `README.md` and `docs/` structure updates
3. CI integration hooks

## Phase 4 - Evals and CI gates

### T13 - Eval runner and graders
Status: `completed`

Goal:
1. Add mechanical grading for safety/reliability/session-discipline rules.

Scope:
1. `src/harness/evals/` (new)
2. `src/harness/verify.py` (`eval run`)

### T14 - CI required checks
Status: `completed`

Goal:
1. Block merges when core harness checks fail.

Scope:
1. `.github/workflows/` (new)
2. test/lint/eval commands

## Phase 5 - Pilot readiness

### T15 - Onboarding command and pilot runbook
Status: `completed`

Goal:
1. Make new repo onboarding repeatable with one harness command.

Scope:
1. `src/harness/verify.py` (`onboard`)
2. `docs/` onboarding guide updates

## Phase 6 - Architecture modernization and OSS adoption

### A01 - Persistence repository abstraction
Status: `completed`

Goal:
1. Isolate direct DB access behind a repository layer.

Scope:
1. `src/harness/cache.py`
2. `src/harness/tracing.py`
3. `src/harness/repository.py` (new)

Acceptance criteria:
1. Cache/trace call sites use repository interfaces for CRUD/query paths.
2. Existing CLI/MCP behavior remains unchanged.

Validation:
1. Unit tests for repository behavior parity.
2. `python3 -m compileall src tests scripts`

### A02 - SQLAlchemy + Alembic baseline
Status: `completed`

Goal:
1. Replace ad-hoc schema evolution with explicit migrations and typed models.

Scope:
1. `src/harness/db/models.py` (new)
2. `alembic/` (new)
3. Migration bootstrap wiring in runtime.

Acceptance criteria:
1. Existing schema represented as SQLAlchemy models.
2. Alembic baseline migration can initialize current schema.
3. Legacy DuckDB data paths still function.

Validation:
1. Migration smoke tests in CI.
2. Schema compatibility tests.

### A03 - OpenTelemetry instrumentation wrapper
Status: `completed`

Goal:
1. Add standard tracing spans and correlation IDs while preserving local trace viewer usage.

Scope:
1. `src/harness/tracing.py`
2. `src/harness/verify.py`
3. `src/harness/mcp_server.py`
4. `src/harness/observability/` (new)

Acceptance criteria:
1. Verify/MCP/session operations emit OTel spans.
2. Span context includes `session_run_id` and `project_run_id`.
3. Feature flag allows local-only mode without OTLP export.

Validation:
1. Unit tests for span emission hooks.
2. End-to-end trace correlation test.

### A04 - Policy backend interface + OPA adapter
Status: `completed`

Goal:
1. Support policy-as-code backend without rewriting harness policy call sites.

Scope:
1. `src/harness/policy.py`
2. `src/harness/policy_backends/` (new)
3. Runtime config for backend selection.

Acceptance criteria:
1. Existing behavior preserved with local backend default.
2. OPA backend can evaluate equivalent allow/deny rules.
3. Denials are normalized into existing policy decision schema.

Validation:
1. Contract tests across local vs OPA backends.
2. Policy regression tests for deny/allow matrix.

### A05 - Eval provider abstraction + external adapters
Status: `completed`

Goal:
1. Keep deterministic harness evals while enabling external model/agent eval systems.

Scope:
1. `src/harness/evals/runner.py`
2. `src/harness/evals/providers/` (new)

Acceptance criteria:
1. Default local deterministic grader remains active.
2. Promptfoo/OpenAI-evals adapters can ingest manifest data and return normalized scores.
3. Provider selection is explicit and auditable in manifest.

Validation:
1. Provider contract tests.
2. Manifest schema tests for eval output normalization.

### A06 - Testcontainers integration lane
Status: `completed`

Goal:
1. Replace manual dependency orchestration for integration tests with reproducible containers.

Scope:
1. `tests/integration/` setup (new)
2. CI workflow integration-test job
3. Local developer docs updates

Acceptance criteria:
1. Integration tests can stand up required services deterministically.
2. Existing local fast tests stay available without containers.

Validation:
1. CI integration lane green on supported runners.
2. Local smoke invocation documented and tested.

### A07 - Service mode architecture package
Status: `completed`

Goal:
1. Define implementation-ready API and worker architecture for multi-user operation.

Scope:
1. `docs/harness-service-architecture.md` (new)
2. API contract draft and workflow/state diagrams

Acceptance criteria:
1. Control-plane and worker responsibilities are fully specified.
2. Auth, policy, orchestration, artifact, and observability boundaries are explicit.
3. Migration dependencies from local mode are documented.

Validation:
1. Architecture review checklist.
2. Sign-off from harness maintainers.
