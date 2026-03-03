# PR Draft: Consolidate `origin/main` + Phase6 Harness into One Canonical Runtime

Last updated: 2026-03-03

## Title

`merge: consolidate main harness with phase6 runtime hardening, tooling union, and cleanup`

## Goal

Merge the two diverged harness implementations into a single, production-ready baseline that keeps Phase6 runtime governance while retaining main-branch lint/cleanup and scaffold ergonomics.

## Scope

- Base comparison: `origin/main...codex/consolidate-main-harness`
- Commits in this consolidation branch:
  - `e2e7f20` merge: consolidate `origin/main` with phase6 runtime and cleanup
  - `34e8d46` cleanup: align `agent_harness` imports and remove dead code
  - `27c776c` docs: record execution status and final namespace stance

## Summary of What Changed

1. Canonical namespace and packaging
- Standardized on `src/agent_harness` as the only supported runtime package path.
- Updated script entrypoints in `pyproject.toml` to `agent_harness.*` modules.
- Kept consolidated extras (`migrations`, `observability`, `integration`, `lint`, `cleanup`).
- Removed stale `harness.*` monkeypatch import targets in tests.

2. Runtime hardening retained from Phase6
- Policy engine and pluggable backends (`local`, `opa`).
- Task contract validation support.
- Session/project run identity model + per-run manifest generation.
- Eval provider abstraction and runner plumbing.
- Optional observability spans.
- Repository/model-backed persistence with Alembic migration scaffolding.
- Safe-by-default data mode behavior preserved (`mock` default, no implicit real AWS fallback).

3. Tooling union from main + Phase6
- Retained and wired `harness-lint` / `harness-cleanup` CLI commands.
- Unified MCP tool catalog now includes runtime governance/session tools plus lint/cleanup tools:
  - `run_tests`, `initialize_session`, `list_projects`, `detect_framework`
  - `get_next_feature`, `update_feature_status`
  - `get_cache_status`, `get_cache_trend`, `get_last_failed`
  - `list_traces`, `get_trace`, `analyze_errors`, `clear_cache`
  - `lint_check`, `cleanup_run`

4. Docs, CI, and cleanup
- Added consolidation and architecture docs under `docs/`.
- Added harness CI workflow and docs lint script.
- Removed deprecated analysis file: `HARNESS_ANALYSIS.md`.
- Fixed Alembic model import path to canonical package.

## Notable Alignment/Cleanup Decisions

- No compatibility shim was kept for `harness.*` imports.
- Import and monkeypatch targets now align to `agent_harness.*` everywhere in maintained code/tests.
- Telemetry attribute names remain `harness.*` by design (stable signal namespace, not Python import paths).

## Files/Areas to Review First

1. Packaging and entrypoints
- `pyproject.toml`

2. Runtime behavior and safety gates
- `src/agent_harness/verify.py`
- `src/agent_harness/mcp_server.py`
- `src/agent_harness/policy.py`
- `src/agent_harness/policy_backends/*`
- `src/agent_harness/contracts.py`
- `src/agent_harness/manifest.py`

3. Persistence and migrations
- `src/agent_harness/repository.py`
- `src/agent_harness/db/*`
- `alembic/*`

4. Observability and tracing
- `src/agent_harness/observability/*`
- `src/agent_harness/tracing.py`
- `src/agent_harness/trace_viewer.py`

5. Tooling union and tests
- `src/agent_harness/lint.py`
- `src/agent_harness/cleanup.py`
- `tests/test_a03_observability.py`
- `tests/test_a04_policy_backends.py`
- `tests/test_t01_run_identity.py`

## Risk Register

1. Namespace migration breakage for downstream custom tests/scripts
- Risk: external callers still using `harness.*` Python imports may break.
- Mitigation: explicit migration note in docs and import-path consistency cleanup in repo tests.

2. MCP client assumptions about tool catalog
- Risk: clients expecting only the older minimal catalog might need adjustment.
- Mitigation: additive tool union kept existing runtime tools and added lint/cleanup tools without renaming.

3. Governance regressions in future merges
- Risk: policy/contract/run-identity behaviors could drift.
- Mitigation: keep targeted test coverage and add CI checks for import-path consistency + MCP tool catalog contract.

4. Environment-dependent test gaps
- Risk: local full test run can be skipped due missing network/container runtime.
- Mitigation: CI gate remains required for full pytest/integration coverage.

## Validation Evidence

Commands executed on this branch:

1. Static/runtime integrity
- `python3 -m compileall src tests scripts` -> pass
- `python3 scripts/lint_docs.py` -> pass

2. Lint/dead-code cleanup
- `uvx ruff check src tests` -> pass
- `uvx vulture src tests --min-confidence 80` -> pass

3. Full test status
- `uvx pytest ...` in this local sandbox -> blocked (offline PyPI resolution; could not fetch `pytest`)
- Expected final gate: run full `pytest` matrix in CI (and integration lane where container runtime is available)

## Backward Compatibility Notes

- CLI command names remain stable (`harness-verify`, `harness-scaffold`, `harness-mcp`, `harness-lint`, `harness-cleanup`).
- Python import path is now canonicalized to `agent_harness.*` only.
- Persistent DB filename/location semantics remain `.harness/data/harness.duckdb` unless overridden.

## Suggested PR Description (Copy/Paste)

This PR consolidates the diverged harness implementations from `origin/main` and the Phase6 rollout into one canonical runtime.

It keeps Phase6 governance/safety/runtime capabilities (policy backends, contracts, session+project run identity, manifests, eval providers, observability, repository+migrations) and combines them with the main-branch tooling improvements (lint/cleanup commands and MCP tool exposure), under a single namespace: `agent_harness`.

Post-merge cleanup was completed in this branch:
- Removed dead code flagged by lint tools.
- Aligned stale `harness.*` monkeypatch import targets to `agent_harness.*`.
- Updated docs to reflect final consolidation stance (no compatibility shim).

Validation completed:
- `python3 -m compileall src tests scripts`
- `python3 scripts/lint_docs.py`
- `uvx ruff check src tests`
- `uvx vulture src tests --min-confidence 80`

Local full `pytest` was blocked by offline dependency resolution in this environment; CI remains the full validation gate.

## Merge Recommendation

Approve after CI passes full test matrix. This branch is the clean consolidated baseline and removes deprecated split-implementation drift.
