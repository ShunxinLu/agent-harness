"""
Harness Verify - Unified test runner with optimized JSON output.

Usage:
    harness-verify verify                  # Auto-detect and run tests
    harness-verify verify --project <path> # Run specific project
    harness-verify verify --all            # Run all projects in directory
    harness-verify verify --json           # Output as JSON
    harness-verify verify --last-failed    # Run only previously failed tests
"""

import json
import os
import sys
import uuid
import time
from pathlib import Path
from typing import Optional

import click

from .config import detect_project, scan_projects, ProjectConfig
from .output import TestRunResult, format_result_json, format_summary
from .runners import get_runner
from .cache import HarnessCache, get_default_cache
from .tracing import Tracer, create_trace_store
from .trace_viewer import trace
from .session_manager import get_next_feature, update_feature_status, collect_resume_context
from .policy import PolicyEngine
from .contracts import load_task_contract
from .manifest import write_project_run_manifest
from .evals import evaluate_session
from .db import build_db_url, run_migrations
from .observability import set_span_attributes, start_span


@click.group()
@click.version_option(version="0.1.0")
def app():
    """Unified test runner with optimized JSON output for Claude Code."""
    pass


def console_print(text: str):
    """Simple print function."""
    click.echo(text)


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
    else:
        code = None

    result = text
    if code:
        result = f"\033[{code}m{result}\033[0m"
    if bold:
        result = f"\033[1m{result}\033[0m"
    return result


def _write_project_file(path: Path, content: str, force: bool) -> str:
    """Write a file with optional overwrite behavior."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existed_before = path.exists()

    if existed_before and not force:
        return "skipped"

    path.write_text(content)
    return "overwritten" if existed_before else "created"


def _init_script_template() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[harness] startup bearings"
pwd
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || echo "[harness] warning: not a git repository"
git log --oneline -n 5 || true

if [ -f ".harness/progress.md" ]; then
  echo "[harness] recent progress (tail)"
  tail -n 40 .harness/progress.md || true
fi

echo "[harness] smoke check in mock mode"
harness-verify verify --project . --json --data-mode mock || true
echo "[harness] init complete"
"""


def _feature_list_template() -> str:
    return json.dumps(
        {
            "version": 1,
            "features": [
                {
                    "id": "FEAT-001",
                    "category": "bootstrap",
                    "description": "Establish initial harness workflow for this repository",
                    "priority": "high",
                    "steps": [
                        "Run baseline verify in mock mode",
                        "Define first implementation feature and acceptance criteria",
                    ],
                    "passes": False,
                    "last_verified_at": None,
                    "evidence": [],
                }
            ],
        },
        indent=2,
    ) + "\n"


def _progress_template() -> str:
    return """# Harness Progress Log

## Session
- Date:
- Actor:
- Active feature:

## Completed
- 

## Blockers
- 

## Next step
- 

## Validation refs
- session_run_id:
- project_run_ids:
"""


def _task_contract_template() -> str:
    return """version: 1
goal: ""
constraints:
  - "Stay within FilesInScope unless explicitly approved"
files_in_scope:
  - ""
acceptance_criteria:
  - ""
validation_steps:
  - "harness-verify verify --project . --json --data-mode mock"
"""


def _data_contract_template() -> str:
    return """version: 1
data_mode_default: mock
entities: []
approval_required_for:
  - "new source entity"
  - "constraint relaxation"
"""


def _project_config_template(config: ProjectConfig) -> str:
    command_lines = "\n".join(f"  - {part}" for part in config.command)
    return (
        "version: 1\n"
        f"project_name: {config.name}\n"
        f"framework: {config.framework}\n"
        f"test_dir: {config.test_dir}\n"
        "command:\n"
        f"{command_lines}\n"
    )


def _initialize_project_artifacts(project_root: Path, force: bool) -> dict:
    """Create or update baseline .harness artifacts for long-running workflows."""
    harness_dir = project_root / ".harness"
    harness_dir.mkdir(parents=True, exist_ok=True)

    files = {
        harness_dir / "init.sh": _init_script_template(),
        harness_dir / "feature_list.json": _feature_list_template(),
        harness_dir / "progress.md": _progress_template(),
        harness_dir / "task-contract.yaml": _task_contract_template(),
        harness_dir / "data-contract.yaml": _data_contract_template(),
    }

    summary = {"created": [], "overwritten": [], "skipped": []}
    for path_obj, content in files.items():
        status = _write_project_file(path_obj, content, force=force)
        summary[status].append(str(path_obj))

    init_script = harness_dir / "init.sh"
    init_script.chmod(init_script.stat().st_mode | 0o111)
    return summary


def run_tests(
    config: ProjectConfig,
    trace_enabled: bool = False,
    extra_args: Optional[list[str]] = None,
    tracer: Optional[Tracer] = None,
    session_run_id: Optional[str] = None,
    project_run_id: Optional[str] = None,
) -> TestRunResult:
    """Run tests for a project."""
    with start_span(
        "harness.verify.project_run",
        {
            "harness.project": config.name,
            "harness.framework": config.framework,
            "harness.path": str(config.path),
            "harness.trace_enabled": trace_enabled,
            "harness.extra_args_count": len(extra_args or []),
            "harness.session_run_id": session_run_id,
            "harness.project_run_id": project_run_id,
        },
    ) as span:
        runner = get_runner(config)
        if not runner:
            set_span_attributes(
                span,
                {
                    "harness.execution_status": "runner_error",
                    "harness.error_message": f"No runner for framework {config.framework}",
                },
            )
            return TestRunResult(
                project=config.name,
                framework=config.framework,
                summary=f"No runner available for framework: {config.framework}",
                execution_status="runner_error",
            )

        console_print(f"\nRunning tests: {config.name} ({config.framework})")
        console_print(f"Path: {config.path}")

        if trace_enabled:
            console_print("Tracing: enabled")
        if tracer:
            tracer.log(
                "verify.project.start",
                event_type="verify.project.start",
                project=config.name,
                framework=config.framework,
                path=str(config.path),
                extra_args=extra_args or [],
            )

        if extra_args and config.framework in ("pytest", "pyspark", "bun", "npm"):
            result = runner.run(extra_args=extra_args)
        else:
            result = runner.run()

        if tracer:
            tracer.log(
                "verify.project.complete",
                event_type="verify.project.complete",
                project=config.name,
                framework=config.framework,
                total=result.total,
                passed=result.passed,
                failed=result.failed,
                skipped=result.skipped,
                errors=result.errors,
                duration=result.duration,
            )

        set_span_attributes(
            span,
            {
                "harness.execution_status": result.execution_status,
                "harness.total_tests": result.total,
                "harness.failed_tests": result.failed,
                "harness.error_tests": result.errors,
                "harness.duration_seconds": result.duration,
            },
        )
        return result


@app.command("verify")
@click.option("--project", "-p", type=click.Path(exists=True, file_okay=False, dir_okay=True), default=None,
              help="Path to specific project to test")
@click.option("--all", "run_all", is_flag=True, help="Scan and run all projects in the base directory")
@click.option("--base-dir", "-b", type=str, default="", help="Base directory to scan for projects")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
@click.option("--last-failed", "-lf", is_flag=True, help="Run only previously failed tests")
@click.option("--trace", "-t", "enable_trace", is_flag=True, help="Enable tracing for this run")
@click.option(
    "--data-mode",
    type=click.Choice(["mock", "metadata", "human-contract"]),
    default="mock",
    show_default=True,
    help="Data access mode for this run",
)
def verify(project, run_all, base_dir, as_json, last_failed, enable_trace, data_mode):
    """Run tests and output optimized results."""

    # Determine what to run
    projects_to_run = []

    if project:
        proj_config = detect_project(Path(project))
        if proj_config:
            projects_to_run.append(proj_config)
        else:
            console_print(f"{style('No test framework detected in: ' + str(project), fg='red')}")
            raise SystemExit(1)

    elif run_all:
        scan_dir = Path(base_dir).expanduser() if base_dir else Path.cwd()
        projects_to_run = scan_projects(scan_dir)

        if not projects_to_run:
            console_print(style("No testable projects found", fg="yellow"))
            raise SystemExit(0)

    else:
        scan_dir = Path(base_dir).expanduser() if base_dir else Path.cwd()
        projects_to_run = scan_projects(scan_dir)

    if not projects_to_run:
        console_print(style("No testable projects found. Use --project to specify a project.", fg="red"))
        raise SystemExit(1)

    session_run_id = str(uuid.uuid4())

    require_task_contract = os.getenv("HARNESS_REQUIRE_TASK_CONTRACT", "").lower() in {"1", "true", "yes"}
    contract_findings = []
    with start_span(
        "harness.verify.contract_validation",
        {
            "harness.session_run_id": session_run_id,
            "harness.project_count": len(projects_to_run),
            "harness.require_task_contract": require_task_contract,
        },
    ) as contract_span:
        for proj_config in projects_to_run:
            try:
                load_task_contract(proj_config.path)
                contract_findings.append(
                    {
                        "project": proj_config.name,
                        "allowed": True,
                        "reason": "Task contract valid",
                    }
                )
            except Exception as exc:
                contract_findings.append(
                    {
                        "project": proj_config.name,
                        "allowed": False,
                        "reason": str(exc),
                    }
                )
        denied_contracts_count = sum(1 for finding in contract_findings if not finding["allowed"])
        set_span_attributes(
            contract_span,
            {
                "harness.contract_denied_count": denied_contracts_count,
                "harness.contract_allowed_count": len(contract_findings) - denied_contracts_count,
            },
        )

    denied_contracts = [finding for finding in contract_findings if not finding["allowed"]]
    contract_findings_by_project = {finding["project"]: finding for finding in contract_findings}
    if denied_contracts and require_task_contract:
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "error": "task_contract_validation_failed",
                        "contract_findings": contract_findings,
                    },
                    indent=2,
                )
            )
        else:
            console_print(style("Run blocked: task contract validation failed", fg="red", bold=True))
            for finding in denied_contracts:
                console_print(f"  - {finding['project']}: {finding['reason']}")
        raise SystemExit(1)

    if denied_contracts and not require_task_contract:
        console_print(style("Warning: missing/invalid task contract(s). Set HARNESS_REQUIRE_TASK_CONTRACT=1 to enforce.", fg="yellow"))
        for finding in denied_contracts:
            console_print(f"  - {finding['project']}: {finding['reason']}")

    # Get cache for caching results and --last-failed functionality
    cache = get_default_cache()
    trace_store = create_trace_store() if enable_trace else None

    # Run tests for each project
    all_results = []
    project_run_records = []
    tracer = Tracer(run_id=session_run_id, store=trace_store) if trace_store else None
    with start_span(
        "harness.verify.policy_evaluation",
        {
            "harness.session_run_id": session_run_id,
            "harness.project_count": len(projects_to_run),
            "harness.data_mode": data_mode,
        },
    ) as policy_span:
        policy_engine = PolicyEngine()
        policy_result = policy_engine.evaluate_verify_request(projects_to_run, data_mode)
        policy_decisions_payload = [decision.model_dump(mode="json") for decision in policy_result.decisions]
        denied_count = sum(1 for decision in policy_result.decisions if not decision.allowed)
        set_span_attributes(
            policy_span,
            {
                "harness.policy_allowed": policy_result.allowed,
                "harness.policy_decision_count": len(policy_result.decisions),
                "harness.policy_denied_count": denied_count,
            },
        )

    if tracer:
        tracer.log(
            "verify.run.start",
            event_type="verify.run.start",
            run_id=session_run_id,
            project_count=len(projects_to_run),
            last_failed=last_failed,
            data_mode=data_mode,
        )
        for finding in contract_findings:
            tracer.log(
                "contract.validation",
                event_type="contract.validation",
                project=finding["project"],
                allowed=finding["allowed"],
                reason=finding["reason"],
            )
        for decision in policy_result.decisions:
            tracer.log(
                "policy.decision",
                event_type="policy.decision",
                action=decision.action,
                allowed=decision.allowed,
                reason=decision.reason,
                metadata=decision.metadata,
            )

    if not policy_result.allowed:
        denied = [decision for decision in policy_result.decisions if not decision.allowed]
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "error": "policy_denied",
                        "session_run_id": session_run_id,
                        "policy_decisions": policy_decisions_payload,
                    },
                    indent=2,
                )
            )
        else:
            console_print(style("Run blocked by policy", fg="red", bold=True))
            for decision in denied:
                console_print(f"  - {decision.action}: {decision.reason}")
        cache.close()
        if trace_store:
            trace_store.close()
        raise SystemExit(1)

    previous_data_mode = os.environ.get("HARNESS_DATA_MODE")
    os.environ["HARNESS_DATA_MODE"] = data_mode

    try:
        for proj_config in projects_to_run:
            extra_args = None
            project_run_id = str(uuid.uuid4())

            # Modify command for --last-failed
            if last_failed:
                if proj_config.framework in ("pytest", "pyspark"):
                    failed_tests = cache.get_last_failed(proj_config.name)
                    if failed_tests:
                        extra_args = failed_tests
                        console_print(f"Running {len(failed_tests)} failed test(s)...")
                    else:
                        console_print("No previously failed tests found; running full suite.")
                else:
                    console_print(
                        f"--last-failed is only supported for pytest/pyspark. "
                        f"Running full suite for framework: {proj_config.framework}"
                    )

            result = run_tests(
                proj_config,
                enable_trace,
                extra_args=extra_args,
                tracer=tracer,
                session_run_id=session_run_id,
                project_run_id=project_run_id,
            )
            all_results.append(result)

            # Cache the results
            duration_ms = 0  # Could calculate from result
            cache.store_run(
                project=proj_config.name,
                run_id=project_run_id,
                results=[r.model_dump() for r in result.results] if result.results else [],
                duration_ms=duration_ms,
                parent_run_id=session_run_id,
            )

            manifest_path = write_project_run_manifest(
                project_config=proj_config,
                session_run_id=session_run_id,
                project_run_id=project_run_id,
                data_mode=data_mode,
                last_failed_requested=last_failed,
                last_failed_applied=bool(extra_args),
                policy_decisions=policy_decisions_payload,
                result=result,
                contract_finding=contract_findings_by_project.get(proj_config.name),
            )

            project_run_records.append(
                {
                    "project": proj_config.name,
                    "project_run_id": project_run_id,
                    "result": result,
                    "manifest_path": str(manifest_path),
                }
            )

        if tracer:
            tracer.log(
                "verify.run.complete",
                event_type="verify.run.complete",
                run_id=session_run_id,
                total_projects=len(all_results),
                total_tests=sum(r.total for r in all_results),
                total_failed=sum(r.failed for r in all_results),
                data_mode=data_mode,
            )
    finally:
        if previous_data_mode is None:
            os.environ.pop("HARNESS_DATA_MODE", None)
        else:
            os.environ["HARNESS_DATA_MODE"] = previous_data_mode
        cache.close()
        if trace_store:
            trace_store.close()

    # Output results
    execution_failures = sum(1 for r in all_results if r.execution_status != "ok")

    if as_json:
        project_outputs = []
        for item in project_run_records:
            project_output = item["result"].model_dump(mode="json")
            project_output["project_run_id"] = item["project_run_id"]
            project_output["session_run_id"] = session_run_id
            project_output["manifest_path"] = item["manifest_path"]
            project_outputs.append(project_output)

        output = {
            "projects": project_outputs,
            "total_projects": len(all_results),
            "total_passed": sum(r.passed for r in all_results),
            "total_failed": sum(r.failed for r in all_results),
            "execution_failures": execution_failures,
            "run_id": session_run_id,
            "session_run_id": session_run_id,
            "data_mode": data_mode,
        }
        click.echo(json.dumps(output, indent=2))
    else:
        # Print summaries
        for result in all_results:
            format_summary(result)

        total_tests = sum(r.total for r in all_results)
        total_passed = sum(r.passed for r in all_results)
        total_failed = sum(r.failed for r in all_results)

        console_print("\n" + "=" * 60)
        console_print("Overall Summary")
        console_print(
            f"Projects: {len(all_results)} | Tests: {total_tests} | Passed: {total_passed} | "
            f"Failed: {total_failed} | Execution failures: {execution_failures}"
        )
        console_print(f"Session Run ID: {session_run_id}")
        for item in project_run_records:
            console_print(f"  - {item['project']}: {item['project_run_id']}")
            console_print(f"    manifest: {item['manifest_path']}")

        if total_failed > 0 or execution_failures > 0:
            raise SystemExit(1)


@app.command("list")
@click.option("--base-dir", "-b", type=str, default="", help="Base directory to scan")
def list_projects(base_dir):
    """List all detectable test projects in a directory."""

    scan_dir = Path(base_dir).expanduser() if base_dir else Path.cwd()

    if not scan_dir.exists():
        console_print(f"[red]Directory not found: {scan_dir}[/red]")
        raise click.Exit(1)

    projects = scan_projects(scan_dir)

    if not projects:
        console_print("[yellow]No testable projects found[/yellow]")
        return

    # Simple table output
    click.echo(f"\n{'Name':<30} {'Framework':<15} {'Path':<50} {'Test Dir':<30}")
    click.echo("-" * 125)
    for proj in projects:
        path_str = str(proj.path.relative_to(scan_dir) if proj.path.is_relative_to(scan_dir) else proj.path)
        test_dir_str = str(proj.test_dir.relative_to(proj.path) if proj.test_dir else "N/A")
        click.echo(f"{proj.name:<30} {proj.framework:<15} {path_str:<50} {test_dir_str:<30}")


@app.command()
@click.argument("path", type=str, default=".")
def detect(path):
    """Detect test framework for a specific path."""

    path_obj = Path(path)

    if not path_obj.exists():
        console_print(style(f"Path not found: {path}", fg="red"))
        raise click.Exit(1)

    config = detect_project(path_obj)

    if config:
        console_print(style(f"Detected: {config.framework}", fg="green"))
        console_print(f"  Project: {config.name}")
        console_print(f"  Test directory: {config.test_dir}")
        console_print(f"  Command: {' '.join(config.command)}")
    else:
        console_print(style(f"No test framework detected in: {path}", fg="yellow"))
        console_print("  Supported: pytest, pyspark, bun, npm, maven, gradle, sbt, cargo, go")


@app.group()
def feature():
    """Feature ledger operations for long-running sessions."""
    pass


@feature.command("next")
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root containing .harness/feature_list.json",
)
@click.option("--json", "as_json", is_flag=True, help="Output selected feature as JSON")
def feature_next(project: str, as_json: bool):
    """Select the next pending feature from the ledger."""
    project_root = Path(project).expanduser().resolve()
    try:
        next_feature = get_next_feature(project_root)
    except FileNotFoundError as exc:
        console_print(style(str(exc), fg="red"))
        raise click.Exit(1)
    except ValueError as exc:
        console_print(style(f"Invalid feature ledger: {exc}", fg="red"))
        raise click.Exit(1)

    if not next_feature:
        console_print(style("All features are currently marked as passed.", fg="green"))
        return

    if as_json:
        click.echo(json.dumps(next_feature.model_dump(mode="json"), indent=2))
        return

    console_print(style("Next feature:", bold=True))
    console_print(f"  ID: {next_feature.id}")
    console_print(f"  Priority: {next_feature.priority}")
    console_print(f"  Category: {next_feature.category}")
    console_print(f"  Description: {next_feature.description}")
    if next_feature.steps:
        console_print("  Steps:")
        for step in next_feature.steps:
            console_print(f"    - {step}")


@feature.command("update")
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root containing .harness/feature_list.json",
)
@click.option("--feature-id", required=True, help="Feature ID to update")
@click.option("--pass/--fail", "passes", default=False, help="Set pass or fail status")
@click.option("--evidence", multiple=True, help="Evidence references (run IDs, manifest paths, eval links)")
@click.option("--json", "as_json", is_flag=True, help="Output updated feature as JSON")
def feature_update(project: str, feature_id: str, passes: bool, evidence: tuple[str, ...], as_json: bool):
    """Update feature pass/fail status with evidence enforcement."""
    project_root = Path(project).expanduser().resolve()
    try:
        updated = update_feature_status(
            project_root=project_root,
            feature_id=feature_id,
            passes=passes,
            evidence=list(evidence),
        )
    except FileNotFoundError as exc:
        console_print(style(str(exc), fg="red"))
        raise click.Exit(1)
    except ValueError as exc:
        console_print(style(str(exc), fg="red"))
        raise click.Exit(1)

    if as_json:
        click.echo(json.dumps(updated.model_dump(mode="json"), indent=2))
        return

    console_print(style("Feature updated", fg="green", bold=True))
    console_print(f"  ID: {updated.id}")
    console_print(f"  Passes: {updated.passes}")
    console_print(f"  Last verified at: {updated.last_verified_at or 'N/A'}")
    console_print(f"  Evidence count: {len(updated.evidence)}")


@app.command("init-project")
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Repository root where .harness artifacts should be created",
)
@click.option("--force", is_flag=True, help="Overwrite existing harness artifacts")
def init_project(project: str, force: bool):
    """Initialize long-running harness artifacts for a repository."""
    project_root = Path(project).expanduser().resolve()
    harness_dir = project_root / ".harness"
    summary = _initialize_project_artifacts(project_root=project_root, force=force)

    console_print(style("Harness project initialization complete", fg="green", bold=True))
    console_print(f"Project: {project_root}")
    for bucket in ("created", "overwritten", "skipped"):
        entries = summary[bucket]
        console_print(f"{bucket.title()}: {len(entries)}")
        for entry in entries:
            console_print(f"  - {entry}")

    console_print("\nNext steps:")
    console_print(f"  1. Review {harness_dir / 'task-contract.yaml'} and {harness_dir / 'data-contract.yaml'}")
    console_print(f"  2. Run {harness_dir / 'init.sh'}")
    console_print("  3. Start feature work with harness-verify verify --project . --json --data-mode mock")


@app.command("onboard")
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root to onboard",
)
@click.option("--force", is_flag=True, help="Overwrite existing .harness files")
@click.option("--run-baseline/--no-run-baseline", default=True, help="Run baseline verify after scaffold generation")
def onboard(project: str, force: bool, run_baseline: bool):
    """Onboard a repository with harness artifacts and baseline verification."""
    project_root = Path(project).expanduser().resolve()
    summary = _initialize_project_artifacts(project_root=project_root, force=force)

    config = detect_project(project_root)
    if not config:
        console_print(style(f"Could not detect a supported framework in {project_root}", fg="red"))
        raise click.Exit(1)

    project_yaml_path = project_root / ".harness" / "project.yaml"
    project_yaml_status = _write_project_file(project_yaml_path, _project_config_template(config), force=force)

    console_print(style("Harness onboarding initialized", fg="green", bold=True))
    console_print(f"Project: {project_root}")
    console_print(f"Detected framework: {config.framework}")
    console_print(f"Project config file: {project_yaml_path} ({project_yaml_status})")
    for bucket in ("created", "overwritten", "skipped"):
        console_print(f"{bucket.title()}: {len(summary[bucket])}")

    if run_baseline:
        console_print("\nRunning baseline verification...")
        result = run_tests(config, trace_enabled=False, extra_args=None, tracer=None)
        format_summary(result)
        if result.execution_status != "ok" or result.failed > 0 or result.errors > 0:
            raise click.Exit(1)

    console_print(style("Onboarding complete", fg="green"))


@app.command("resume-check")
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root to inspect for resume artifacts",
)
@click.option("--run-smoke/--no-run-smoke", default=False, help="Execute .harness/init.sh as part of resume check")
@click.option("--json", "as_json", is_flag=True, help="Output resume context as JSON")
def resume_check(project: str, run_smoke: bool, as_json: bool):
    """Validate startup bearings and show context for long-running session resume."""
    project_root = Path(project).expanduser().resolve()
    with start_span(
        "harness.verify.resume_check",
        {
            "harness.project": str(project_root),
            "harness.run_smoke_check": run_smoke,
        },
    ) as span:
        context = collect_resume_context(project_root=project_root, run_smoke_check=run_smoke)
        set_span_attributes(
            span,
            {
                "harness.has_required_artifacts": context["has_required_artifacts"],
                "harness.missing_artifacts_count": len(context["missing_artifacts"]),
                "harness.smoke_exit_code": context["smoke_check"]["exit_code"],
            },
        )

    if as_json:
        click.echo(json.dumps(context, indent=2))
    else:
        console_print(style("Resume Check", bold=True))
        console_print(f"Project: {context['project_root']}")
        console_print(f"Required artifacts present: {context['has_required_artifacts']}")
        if context["missing_artifacts"]:
            console_print(style("Missing artifacts:", fg="red"))
            for artifact in context["missing_artifacts"]:
                console_print(f"  - {artifact}")

        if context["next_feature"]:
            console_print(style("Next feature:", fg="green"))
            console_print(f"  - {context['next_feature']['id']}: {context['next_feature']['description']}")
        else:
            console_print("Next feature: none")

        if context["progress_tail"]:
            console_print(style("Progress tail:", fg="blue"))
            for line in context["progress_tail"][-10:]:
                console_print(f"  {line}")

        smoke = context["smoke_check"]
        if smoke["requested"]:
            console_print(f"Smoke check executed: {smoke['executed']} (exit_code={smoke['exit_code']})")
            for line in smoke["output_tail"][-8:]:
                console_print(f"  {line}")

    if not context["has_required_artifacts"]:
        raise click.Exit(1)
    if context["smoke_check"]["requested"] and context["smoke_check"]["exit_code"] not in (0, None):
        raise click.Exit(1)


@app.group()
def contract():
    """Task contract validation operations."""
    pass


@contract.command("validate")
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root containing .harness/task-contract.yaml",
)
@click.option("--json", "as_json", is_flag=True, help="Output validation result as JSON")
def contract_validate(project: str, as_json: bool):
    """Validate the task contract schema for a project."""
    project_root = Path(project).expanduser().resolve()

    try:
        contract_obj = load_task_contract(project_root)
        output = {
            "valid": True,
            "project": str(project_root),
            "task_contract": contract_obj.model_dump(mode="json"),
        }
        if as_json:
            click.echo(json.dumps(output, indent=2))
        else:
            console_print(style("Task contract is valid", fg="green", bold=True))
            console_print(f"Project: {project_root}")
    except Exception as exc:
        output = {"valid": False, "project": str(project_root), "error": str(exc)}
        if as_json:
            click.echo(json.dumps(output, indent=2))
        else:
            console_print(style(f"Task contract is invalid: {exc}", fg="red"))
        raise click.Exit(1)


@app.group(name="eval")
def eval_group():
    """Run harness eval checks from persisted manifests."""
    pass


@eval_group.command("run")
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root containing .harness/runs manifests",
)
@click.option("--session-run-id", type=str, default=None, help="Specific session run ID to evaluate")
@click.option(
    "--provider",
    type=click.Choice(["local", "promptfoo", "openai-evals"]),
    default="local",
    show_default=True,
    help="Eval provider backend",
)
@click.option("--json", "as_json", is_flag=True, help="Output eval report as JSON")
def eval_run(project: str, session_run_id: Optional[str], provider: str, as_json: bool):
    """Evaluate run manifests for safety and reliability checks."""
    project_root = Path(project).expanduser().resolve()
    report = evaluate_session(project_root=project_root, session_run_id=session_run_id, provider=provider)

    if as_json:
        click.echo(json.dumps(report, indent=2))
    else:
        if report.get("error"):
            console_print(style(f"Eval error: {report['error']}", fg="red"))
        else:
            console_print(style("Eval Report", bold=True))
            console_print(f"Provider: {report.get('provider')}")
            console_print(f"Session Run ID: {report['session_run_id']}")
            console_print(
                f"Manifests: {report['passed_manifests']}/{report['total_manifests']} passed"
            )
            if report["findings"]:
                console_print(style("Findings:", fg="red"))
                for finding in report["findings"]:
                    console_print(
                        f"  - [{finding['rule']}] {finding['project']}: {finding['message']} "
                        f"({finding['manifest_path']})"
                    )
            else:
                console_print(style("No eval findings.", fg="green"))

    if not report.get("passed", False):
        raise click.Exit(1)


@app.group()
def db():
    """Database schema and migration operations."""
    pass


@db.command("migrate")
@click.option("--db-path", type=click.Path(), default=None, help="Path to harness DuckDB file")
@click.option("--db-url", type=str, default=None, help="Explicit SQLAlchemy URL override")
@click.option("--revision", type=str, default="head", show_default=True, help="Target Alembic revision")
def db_migrate(db_path: Optional[str], db_url: Optional[str], revision: str):
    """Apply Alembic migrations to harness persistence tables."""
    effective_db_url = db_url or build_db_url(db_path)

    try:
        run_migrations(revision=revision, db_url=effective_db_url, db_path=db_path)
    except Exception as exc:
        console_print(style(f"Database migration failed: {exc}", fg="red"))
        raise click.Exit(1)

    console_print(style("Database migration complete", fg="green", bold=True))
    console_print(f"Revision: {revision}")
    console_print(f"URL: {effective_db_url}")


@app.group()
def cache():
    """Manage test result cache."""
    pass


@cache.command("status")
def cache_status():
    """Show cache statistics."""
    c = get_default_cache()
    stats = c.get_stats()

    console_print(f"\n{style('Cache Statistics:', bold=True)}")
    console_print(f"  Total runs: {stats.total_runs}")
    console_print(f"  Total tests: {stats.total_tests}")
    console_print(f"  Projects: {', '.join(stats.projects) if stats.projects else 'None'}")

    if stats.oldest_run:
        console_print(f"  Oldest run: {stats.oldest_run.strftime('%Y-%m-%d %H:%M:%S')}")
    if stats.newest_run:
        console_print(f"  Newest run: {stats.newest_run.strftime('%Y-%m-%d %H:%M:%S')}")

    c.close()


@cache.command("clear")
@click.option("--project", "-p", type=str, default=None, help="Clear cache for specific project only")
def cache_clear(project):
    """Clear the test result cache."""
    c = get_default_cache()
    c.clear(project=project)
    c.close()

    if project:
        console_print(style("[OK]", fg="green") + f" Cache cleared for project: {project}")
    else:
        console_print(style("[OK]", fg="green") + " Cache cleared")


@cache.command("trend")
@click.argument("project", type=str)
@click.option("--limit", "-l", type=int, default=10, help="Number of runs to show")
def cache_trend(project, limit):
    """Show test trend over time for a project."""
    c = get_default_cache()
    trend = c.get_trend(project, limit)

    if not trend:
        console_print(style(f"No cache data found for project: {project}", fg="yellow"))
        c.close()
        return

    console_print(f"\n{style('Test Trend:', bold=True)} {project}")
    console_print(f"{'Run ID':<36} {'Total':<8} {'Passed':<8} {'Failed':<8} {'Timestamp':<20}")
    console_print("-" * 85)

    for run in reversed(trend):  # Show oldest first for trend
        timestamp = run["timestamp"][:19] if run["timestamp"] else "N/A"
        passed_str = style(str(run["passed"]), fg="green")
        failed_str = style(str(run["failed"]), fg="red") if run["failed"] > 0 else str(run["failed"])
        console_print(f"{run['run_id']:<36} {run['total']:<8} {passed_str:<8} {failed_str:<8} {timestamp:<20}")

    c.close()


# Add trace commands
app.add_command(trace)


if __name__ == "__main__":
    app()
