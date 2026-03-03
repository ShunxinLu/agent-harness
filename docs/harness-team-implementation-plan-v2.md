# Harness Team Implementation Plan v2

Last updated: 2026-03-03

## 1) Goal and scope

### Goal
Deliver a production-ready harness for long-running coding agents that is:
1. Reliable across repeated runs and multi-project execution.
2. Safe by default with mechanical enforcement.
3. Legible to agents through repository-native artifacts and workflows.
4. Measurable via evals, CI gates, and operational KPIs.

### Why this revision
This plan updates the previous implementation plan using:
1. OpenAI harness-engineering patterns for agent-first repos, doc/system legibility, and mechanical enforcement.
2. Anthropic long-running harness patterns for initializer/coding session separation, incremental feature progress, and resume artifacts.
3. Current repository gaps observed in `src/harness/*` and `docs/harness-team-implementation-plan.md`.

### In-scope
1. CLI/MCP runtime correctness and safety.
2. Long-running session primitives (initializer artifacts, progress handoff, one-feature loops).
3. Documentation and plan lifecycle enforcement.
4. Evals and CI merge gating for safety/quality.

### Out-of-scope (for this revision)
1. Full multi-tenant hosted service with complete RBAC in phase 0.
2. Cross-org rollout sequencing details per downstream repo.
3. Replacing existing CI stacks in one phase.

## 2) Baseline gap summary

### Critical correctness and safety gaps
1. Multi-project run collision risk on `run_id` persistence (`run_history` primary key vs shared run ID).
2. SQL query correctness/injection risks in cache/trace query paths.
3. Trace timestamp typing mismatch likely to break trace viewing in some environments.
4. Exit status semantics can report success when runners time out or fail to execute tools.
5. MCP `run_tests` non-JSON path prints to stdout through `format_summary`, unsafe for MCP stdio framing.

### Long-running harness gaps
1. No initializer workflow to create durable project session artifacts.
2. No feature ledger to enforce one-feature-at-a-time progress.
3. No structured progress file + startup bearings protocol.
4. No required pre-feature smoke/E2E check loop.

### System-level enforcement gaps
1. No repository tests for harness internals.
2. No CI workflow that gates merges on tests/lint/evals.
3. No doc structure/freshness lints or recurring doc-gardening workflow.
4. Task contracts and run manifests are planned but not implemented in runtime.

## 3) Design principles for v2

1. Docs as system-of-record: `AGENTS.md` remains a router; detailed behavior lives in versioned docs and executable checks.
2. Mechanical over advisory: every important rule is enforced via code, lints, or CI checks.
3. Incremental progress: one feature per coding session with explicit pass/fail status.
4. Resumeability: every new session can recover state from git + progress + feature files.
5. Safe defaults: mock/no-AWS mode is default and verifiably enforced.
6. Single source of run truth: one run manifest links CLI/MCP, cache, traces, policy events, and eval output.

## 4) Target architecture delta

### New core components
1. `session_manager.py`
   - Session bootstrap, bearings checks, and environment readiness.
2. `manifest.py`
   - Run manifest schema and writer.
3. `policy.py`
   - Command/path/network/data-mode policy decisions with structured events.
4. `contracts.py`
   - Task contract parsing/validation.
5. `evals/`
   - Graders for safety, progress, and output correctness.

### New repository artifacts per project
1. `.harness/init.sh`
2. `.harness/feature_list.json`
3. `.harness/progress.md` (or `.txt`; choose one and enforce)
4. `.harness/task-contract.yaml`
5. `.harness/data-contract.yaml`

### CLI additions
1. `harness-verify init-project`
2. `harness-verify resume-check`
3. `harness-verify work-feature --feature-id <id>`
4. `harness-verify manifest show <run-id>`
5. `harness-verify eval run --run-id <run-id>`

### MCP additions
1. `initialize_session`
2. `get_next_feature`
3. `update_feature_status`
4. `append_progress`
5. `run_smoke_check`
6. `get_run_manifest`
7. `run_evals`

## 5) Phase roadmap

## Phase 0 (Week 1-2): Correctness and safety hardening

### Objective
Fix runtime defects that undermine trust in test, trace, and cache outputs.

### Workstream A: Run identity and persistence correctness
1. Introduce `session_run_id` and `project_run_id`.
2. Keep shared top-level run link, but write per-project rows with unique project run IDs.
3. Add `parent_run_id` to `run_history` for grouping.
4. Ensure all trace events and cache rows link deterministically.

### Workstream B: SQL and typing safety
1. Replace all f-string SQL with parameterized statements.
2. Fix optional `WHERE` clause construction in `cache.get_errors` and `tracing.get_errors`.
3. Normalize timestamp conversions with robust type checks.
4. Add query helper utility for safe clause composition.

### Workstream C: Exit semantics and MCP stdio safety
1. Track `execution_status` in `TestRunResult` (`ok`, `tool_missing`, `timeout`, `runner_error`).
2. Exit non-zero for non-`ok` execution statuses.
3. Replace `print` side effects in output formatters with pure return strings.
4. Keep MCP tool responses strictly machine-readable.

### Workstream D: Baseline automated tests
1. Add unit tests for:
   - run_id persistence behavior
   - SQL clause correctness
   - timestamp decoding
   - exit semantics
   - MCP response framing
2. Add integration test for multi-project run.

### Deliverables
1. Correct run/cache/trace linkage under multi-project load.
2. No dynamic SQL interpolation in operational paths.
3. Deterministic CLI exit codes and clean MCP outputs.
4. Passing test suite for phase-0 defects.

### Exit criteria
1. 200 sequential local verify runs complete without DB/ID collisions.
2. SQL safety tests pass with fuzzed project/run/pattern values.
3. MCP `run_tests` succeeds with `json_output=true|false` without protocol noise.

## Phase 1 (Week 2-4): Long-running session scaffold

### Objective
Introduce durable artifacts and workflow for context-window handoff.

### Workstream A: Initializer flow
1. Add `harness-verify init-project` command to generate:
   - `.harness/init.sh`
   - `.harness/feature_list.json`
   - `.harness/progress.md`
2. Validate generated files against schemas/templates.
3. Commit an initial scaffold summary artifact in manifest.

### Workstream B: Feature ledger model
1. Define `feature_list.json` schema:
   - `id`, `category`, `description`, `priority`, `steps[]`, `passes`, `last_verified_at`.
2. Enforce immutable semantics for non-status fields in coding sessions unless explicitly authorized.
3. Add `get_next_feature` selection logic (highest-priority failing).

### Workstream C: Progress and session resume
1. Enforce startup bearings sequence:
   - check cwd
   - read progress file
   - read recent git history
   - read feature ledger
   - run smoke check via `init.sh`
2. Enforce end-of-session update:
   - append progress notes
   - update feature status only after verification evidence
   - write run manifest

### Deliverables
1. Initializer command and templates.
2. Feature ledger + progress update engine.
3. Resume-check command and MCP equivalent.

### Exit criteria
1. Fresh session can resume project state using only repo artifacts.
2. Feature completion cannot be marked without verification metadata.
3. Smoke check runs before feature work in automated session tests.

## Phase 2 (Week 4-6): Policy and contract enforcement

### Objective
Convert safety rules into enforced runtime policy with auditable decisions.

### Workstream A: Policy engine
1. Add policy evaluator for actions:
   - command execution class
   - file path access
   - network access
   - data mode access
2. Emit policy decision events into trace store.
3. Enforce explicit approval checkpoints for high-risk categories.

### Workstream B: Contract system
1. Implement task-contract schema validation:
   - Goal
   - Constraints
   - FilesInScope
   - AcceptanceCriteria
   - ValidationSteps
2. Require contract for non-trivial runs.
3. Fail early when contracts are missing or invalid.

### Workstream C: Data mode guardrails
1. Keep default `mock`.
2. Block direct AWS SDK/CLI in `mock`.
3. Permit metadata-only endpoints in `metadata` mode.
4. Log all blocked attempts with structured policy context.

### Deliverables
1. `policy.py` and policy events in traces.
2. Contract validator and run-time preflight checks.
3. Data mode compliance checker.

### Exit criteria
1. Unsafe operations are blocked with deterministic error codes.
2. Policy and contract checks are present in every manifest.
3. No direct AWS access paths succeed in `mock` mode tests.

## Phase 3 (Week 6-8): Agent legibility and app-level verification

### Objective
Increase agent throughput while reducing human QA load.

### Workstream A: Repository knowledge and docs lifecycle
1. Split docs into indexed sections:
   - architecture
   - reliability
   - security
   - plans (active/completed)
   - generated references
2. Keep top-level `AGENTS.md` short and routing-only.
3. Add documentation lints for:
   - required index links
   - stale plan markers
   - missing ownership metadata

### Workstream B: App/test observability for agent validation
1. Add optional browser smoke hook in `init.sh` for UI repos.
2. Add structured logs/metrics/traces capture references in manifests.
3. Add per-worktree runtime isolation guidance and checks.

### Workstream C: Feature verification discipline
1. Require verification artifacts before `passes=true`.
2. Add standardized self-check steps:
   - unit/regression tests
   - smoke/E2E checks where applicable
   - negative-path checks for safety constraints

### Deliverables
1. Reorganized docs map and lint rules.
2. Smoke-check/E2E hook templates.
3. Feature completion verifier.

### Exit criteria
1. Doc lint passes on every PR.
2. Feature marked pass without evidence is blocked by evals.
3. Agent session startup and verification steps are reproducible.

## Phase 4 (Week 8-10): Evals and CI merge gates

### Objective
Make harness behavior measurable and regressions block merges.

### Workstream A: Eval runner
1. Add eval suites for:
   - runtime correctness regressions
   - policy compliance
   - long-running session behavior
   - feature status integrity
2. Add grading outputs to run manifest.

### Workstream B: CI integration
1. Add GitHub workflow:
   - unit tests
   - lint/docs checks
   - eval suite
2. Fail PR when critical evals regress.

### Workstream C: Trend reporting
1. Export eval and reliability trends from DuckDB.
2. Add weekly summary job for failed eval categories.

### Deliverables
1. Eval framework and baseline corpus.
2. CI pipeline and required status checks.
3. Trend report artifacts.

### Exit criteria
1. Main branch protected by harness checks.
2. Safety eval failures block merges.
3. Weekly failure taxonomy available for triage.

## Phase 5 (Week 10-12): Pilot onboarding and governance

### Objective
Operationalize the harness for multi-repo pilot teams.

### Workstream A: Onboarding automation
1. Add `onboard` command:
   - detect profile
   - generate `.harness/*` contracts and session artifacts
   - validate baseline test + smoke loop

### Workstream B: Governance model
1. Define policy change process and ownership.
2. Add approval classes and incident response for harness failures.
3. Define SLOs for harness reliability and eval latency.

### Deliverables
1. Pilot onboarding kit and command.
2. Governance handbook section in docs.
3. SLO + incident templates.

### Exit criteria
1. At least 3 pilot repos onboarded with full checks.
2. Each onboarded repo emits manifests/evals on agent runs.
3. Policy exceptions are explicit, reviewed, and auditable.

## 6) Prioritized implementation backlog

## P0 (must complete first)
1. Fix run_id collision model in cache/run history.
2. Parameterize SQL and fix malformed optional-filter queries.
3. Fix timestamp parsing for trace rows and trace list rendering.
4. Introduce execution-status fields and strict exit codes.
5. Remove print side effects from shared output formatter paths.
6. Add unit/integration tests for all P0 fixes.

## P1 (long-running foundations)
1. Implement `init-project` and artifact generation.
2. Implement feature ledger schema + one-feature workflow.
3. Implement resume-check/startup bearings sequence.
4. Implement end-of-session progress and manifest updates.
5. Add smoke check hook via `init.sh`.

## P2 (policy and contracts)
1. Add policy engine and decision events.
2. Add task/data contract validators.
3. Add data-mode enforcement tests.
4. Add approval hooks for risky actions.

## P3 (evals and rollout)
1. Build eval suite and CI gates.
2. Add doc lint + recurring doc-gardening workflow.
3. Add onboarding command and pilot templates.

## 7) Validation strategy

### Local validation loop (per change)
1. `python3 -m compileall src`
2. `pytest -q`
3. `harness-verify verify --project <fixture_repo> --json --data-mode mock`
4. `harness-verify trace list --limit 5`
5. `harness-verify cache status`

### Phase-specific validation
1. Phase 0
   - Multi-project run simulation with unique run linkage assertions.
   - SQL fuzz tests on filter inputs.
2. Phase 1
   - Restart session test: new process can resume using only repo artifacts.
   - Feature ledger mutation checks (status-only update constraints).
3. Phase 2
   - Policy violation replay tests (blocked actions must emit events).
4. Phase 3
   - Feature cannot transition to pass without evidence artifacts.
5. Phase 4
   - CI fail-open check: ensure required checks are truly blocking.

### Release readiness checklist
1. All P0/P1 tests green.
2. Safety evals at 100% pass on baseline corpus.
3. No undocumented policy exceptions.
4. Docs indexes and plans lint clean.

## 8) KPIs and targets

### Reliability
1. Harness internal test pass rate: >= 98%.
2. Multi-project run DB/linkage failures: 0.
3. MCP tool framing errors: 0.

### Safety
1. Mock-mode direct AWS escapes: 0.
2. Policy decision coverage on risky actions: 100%.
3. Contract compliance failures caught pre-run: >= 95% of seeded violations.

### Long-running effectiveness
1. Session resume success without human restatement: >= 90%.
2. Premature project-complete declarations: < 5% of long-run eval cases.
3. Feature status false-positives (marked pass but failing): < 2%.

### Throughput and quality
1. Median time from task start to first passing feature: down 30%.
2. Regression rate after harness-approved merge: < 5%.

## 9) Risks and mitigations

1. Risk: Policy friction slows feature work.
   - Mitigation: policy tiers with explicit, audited temporary exceptions.
2. Risk: Artifact sprawl reduces clarity.
   - Mitigation: strict schemas and linted docs indexes.
3. Risk: E2E hooks become flaky.
   - Mitigation: keep smoke checks minimal, deterministic, and time-bounded.
4. Risk: Eval maintenance cost increases.
   - Mitigation: start with high-value failure classes and expand iteratively.

## 10) Ownership and execution model

### Harness-core ownership (this repo)
1. Runtime correctness and persistence.
2. Session artifacts and workflows.
3. Policy engine and contract validation.
4. Eval runner and CI integration.

### Cross-team dependencies
1. Downstream repos: onboarding and fixture/data-contract authoring.
2. DevEx/CI: required checks standardization.
3. Security/GRC: approval class definitions.

## 11) Immediate next actions (this week)

1. Create implementation tickets for all P0 items with test-first acceptance criteria.
2. Implement run ID model fix plus SQL safety fixes in one hardening PR.
3. Add baseline unit test scaffolding in this repository.
4. Add v1 schemas for `.harness/feature_list.json` and `.harness/task-contract.yaml`.
5. Prototype `init-project` command and generated templates.

## 12) Source mapping

This plan is based on:
1. OpenAI harness-engineering patterns (published 2026-02-11): repository legibility, plans as first-class artifacts, and mechanical doc/CI enforcement.
2. Anthropic long-running harness patterns (published 2025-11-26): initializer/coding split, `init.sh`, feature ledger, progress logs, startup bearings, and incremental one-feature loops.

## 13) Developer workflow examples

These examples show how a developer and coding agent work together while staying inside harness boundaries.

### 13A) One-time project setup (developer)

1. Initialize harness artifacts in repo:
```bash
harness-verify init-project --project <repo_root>
```
2. Commit generated files:
   - `.harness/init.sh`
   - `.harness/feature_list.json`
   - `.harness/progress.md`
   - `.harness/task-contract.yaml` template
   - `.harness/data-contract.yaml` template
3. Register MCP server in agent client:
```json
{
  "mcpServers": {
    "harness": {
      "command": "harness-mcp"
    }
  }
}
```
4. Run baseline preflight:
```bash
harness-verify resume-check --project <repo_root>
harness-verify verify --project <repo_root> --json --data-mode mock
```

### 13B) Standard feature delivery loop (developer + coding agent)

### Scenario
Add feature `FEAT-102` in Python repo and keep all work in `mock` mode.

### Steps
1. Developer creates branch:
```bash
cd <repo_root>
git switch -c codex/feat-102
```
2. Agent starts session with boundaries:
   - call `initialize_session`
   - call `get_next_feature` or select `FEAT-102`
   - call `run_smoke_check`
3. Agent runs baseline tests:
   - call `run_tests` with `data_mode=mock`
4. Agent edits only `FilesInScope` from task contract.
5. Agent reruns tests after each increment:
   - call `run_tests`
6. Agent records progress:
   - call `append_progress` with what changed, why, and what remains
7. Agent requests validation and eval:
```bash
harness-verify eval run --run-id <run_id>
```
8. Agent updates feature status only if all gates pass:
   - call `update_feature_status` with `passes=true` and evidence refs
9. Developer opens PR with artifacts:
   - task contract hash
   - run manifest
   - eval output
   - feature ledger diff

### Boundary guarantees
1. `mock` mode blocks direct AWS access.
2. Out-of-scope file edits fail policy checks.
3. Feature cannot be marked passed without verification evidence.

### 13C) Long-running handoff across sessions

### Scenario
Work spans multiple days and context windows.

### End-of-day session
1. Agent appends concise status to `.harness/progress.md`:
   - completed steps
   - failing tests and blockers
   - next exact step
2. Agent updates `feature_list.json` status for only the active feature.
3. Agent writes run manifest and stores run ID in progress note.

### Next-day session
1. New agent session runs:
```bash
harness-verify resume-check --project <repo_root>
```
2. Agent reads:
   - `.harness/progress.md`
   - `.harness/feature_list.json`
   - latest run manifest
3. Agent executes `init.sh` smoke check.
4. Agent resumes exactly one feature from prior checkpoint.

### Boundary guarantees
1. Session resume is artifact-driven, not memory-driven.
2. Agent cannot skip smoke/baseline checks before status updates.

### 13D) Data/schema uncertainty flow (metadata mode)

### Scenario
Feature is blocked by unknown schema shape.

### Steps
1. Agent starts in `mock` mode and attempts implementation.
2. If blocked by schema uncertainty, switch explicitly to `metadata` mode:
   - call `run_tests` with `data_mode=metadata` only for discovery run
3. Agent calls metadata-only tools:
   - `describe_table`
   - `profile_table`
   - `get_column_stats`
4. Agent updates assumptions in `.harness/data-contract.yaml`.
5. Agent returns to `mock` mode for implementation and tests.

### Boundary guarantees
1. No row-level data access in `metadata` mode.
2. Direct AWS/database access remains blocked unless explicitly approved.
3. Contract drift is visible in manifest/eval output.

### 13E) High-risk change requiring approval

### Scenario
Task requires destructive command or broad filesystem write.

### Steps
1. Agent proposes action and hits policy gate.
2. Harness emits policy event with reason and required approval class.
3. Developer reviews and explicitly approves or denies.
4. If approved, agent executes only approved action scope.
5. Agent reruns tests/evals and logs approval reference in manifest.

### Boundary guarantees
1. Risky operations are deny-by-default.
2. Approvals are explicit, scoped, and auditable.
3. Final run record links code changes, approvals, and validation results.

### 13F) Copy/paste prompts developers can use with coding agents

### Start-session prompt
```text
Use the harness workflow for this repo. Start by running resume-check and smoke checks, then pick one feature from .harness/feature_list.json. Stay within task contract FilesInScope and run in data_mode=mock unless explicitly required otherwise. Update .harness/progress.md and feature status only after passing tests and evals.
```

### Mid-task correction prompt
```text
You are drifting scope. Stop new edits. Re-read task contract and continue only with the current feature. Re-run harness tests and append a brief progress update with next step.
```

### Pre-PR prompt
```text
Before finalizing, run harness evals, produce run manifest references, verify feature status evidence, and summarize what policy boundaries were enforced during this run.
```
