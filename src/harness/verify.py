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


def run_tests(
    config: ProjectConfig,
    trace_enabled: bool = False,
    extra_args: Optional[list[str]] = None,
    tracer: Optional[Tracer] = None,
) -> TestRunResult:
    """Run tests for a project."""

    runner = get_runner(config)
    if not runner:
        return TestRunResult(
            project=config.name,
            framework=config.framework,
            summary=f"No runner available for framework: {config.framework}",
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

    if data_mode == "mock" and os.getenv("HARNESS_ALLOW_REAL_AWS", "").lower() in {"1", "true", "yes"}:
        console_print(
            style(
                "Refusing run: HARNESS_ALLOW_REAL_AWS is enabled while --data-mode=mock. "
                "Unset HARNESS_ALLOW_REAL_AWS or use a non-mock mode explicitly.",
                fg="red",
            )
        )
        raise SystemExit(1)

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

    # Get cache for caching results and --last-failed functionality
    cache = get_default_cache()
    trace_store = create_trace_store() if enable_trace else None

    # Run tests for each project
    all_results = []
    run_id = str(uuid.uuid4())
    tracer = Tracer(run_id=run_id, store=trace_store) if trace_store else None

    if tracer:
        tracer.log(
            "verify.run.start",
            event_type="verify.run.start",
            run_id=run_id,
            project_count=len(projects_to_run),
            last_failed=last_failed,
            data_mode=data_mode,
        )

    previous_data_mode = os.environ.get("HARNESS_DATA_MODE")
    os.environ["HARNESS_DATA_MODE"] = data_mode

    try:
        for proj_config in projects_to_run:
            extra_args = None

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

            result = run_tests(proj_config, enable_trace, extra_args=extra_args, tracer=tracer)
            all_results.append(result)

            # Cache the results
            duration_ms = 0  # Could calculate from result
            cache.store_run(
                project=proj_config.name,
                run_id=run_id,
                results=[r.model_dump() for r in result.results] if result.results else [],
                duration_ms=duration_ms,
            )

        if tracer:
            tracer.log(
                "verify.run.complete",
                event_type="verify.run.complete",
                run_id=run_id,
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
    if as_json:
        output = {
            "projects": [r.model_dump(mode="json") for r in all_results],
            "total_projects": len(all_results),
            "total_passed": sum(r.passed for r in all_results),
            "total_failed": sum(r.failed for r in all_results),
            "run_id": run_id,
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
        console_print(f"Projects: {len(all_results)} | Tests: {total_tests} | Passed: {total_passed} | Failed: {total_failed}")
        console_print(f"Run ID: {run_id}")

        if total_failed > 0:
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
