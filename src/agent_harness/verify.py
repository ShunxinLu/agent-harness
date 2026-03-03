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
import uuid
from pathlib import Path
from typing import Optional

import click

from .config import detect_project, scan_projects, ProjectConfig
from .output import TestRunResult, format_summary
from .runners import get_runner
from .cache import get_default_cache
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


def run_tests(config: ProjectConfig, trace_enabled: bool = False, extra_args: Optional[list[str]] = None) -> TestRunResult:
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

    # Pass extra args to runner if provided (e.g., specific test names for --last-failed)
    if extra_args:
        result = runner.run(extra_args=extra_args)
    else:
        result = runner.run()
    return result


@app.command("verify")
@click.option("--project", "-p", type=click.Path(exists=True, file_okay=False, dir_okay=True), default=None,
              help="Path to specific project to test")
@click.option("--all", "run_all", is_flag=True, help="Scan and run all projects in the base directory")
@click.option("--base-dir", "-b", type=str, default="", help="Base directory to scan for projects")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
@click.option("--last-failed", "-lf", is_flag=True, help="Run only previously failed tests")
@click.option("--trace", "-t", "enable_trace", is_flag=True, help="Enable tracing for this run")
def verify(project, run_all, base_dir, as_json, last_failed, enable_trace):
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
        scan_dir = Path(base_dir) if base_dir else Path.home() / "projects"
        projects_to_run = scan_projects(scan_dir)

        if not projects_to_run:
            console_print(style("No testable projects found", fg="yellow"))
            raise SystemExit(0)

    else:
        scan_dir = Path(base_dir) if base_dir else Path.cwd()
        projects_to_run = scan_projects(scan_dir)

        if not projects_to_run:
            default_dir = Path.home() / "projects"
            if default_dir.exists():
                projects_to_run = scan_projects(default_dir)

    if not projects_to_run:
        console_print(style("No testable projects found. Use --project to specify a project.", fg="red"))
        raise SystemExit(1)

    # Get cache for caching results and --last-failed functionality
    cache = get_default_cache()

    # Run tests for each project
    all_results = []
    run_id = str(uuid.uuid4())

    for proj_config in projects_to_run:
        # Modify command for --last-failed
        extra_args = None
        if last_failed:
            failed_tests = cache.get_last_failed(proj_config.name)
            if failed_tests and proj_config.framework == "pytest":
                extra_args = failed_tests
                console_print(f"Running {len(failed_tests)} failed test(s)...")

        result = run_tests(proj_config, enable_trace, extra_args=extra_args)
        all_results.append(result)

        # Cache the results
        duration_ms = 0  # Could calculate from result
        cache.store_run(
            project=proj_config.name,
            run_id=run_id,
            results=[r.model_dump() for r in result.results] if result.results else [],
            duration_ms=duration_ms,
        )

    # Close cache connection
    cache.close()

    # Output results
    if as_json:
        output = {
            "projects": [r.model_dump(mode="json") for r in all_results],
            "total_projects": len(all_results),
            "total_passed": sum(r.passed for r in all_results),
            "total_failed": sum(r.failed for r in all_results),
            "run_id": run_id,
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

    scan_dir = Path(base_dir) if base_dir else Path.home() / "projects"

    if not scan_dir.exists():
        console_print(f"[red]Directory not found: {scan_dir}[/red]")
        raise SystemExit(1)

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
        raise SystemExit(1)

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
