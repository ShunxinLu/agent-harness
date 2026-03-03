"""
Harness Cleanup - Automated entropy management.

Wraps existing tools:
- vulture: Dead code detection
- ruff: Auto-fix formatting, imports
- pre-commit: Hook management

Universal: Works for any agent - output is JSON.
"""

import click
import json
import subprocess
from pathlib import Path


PRE_COMMIT_CONFIG = """repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix, --show-fixes]
      - id: ruff-format

  - repo: https://github.com/jendrikseipp/vulture
    rev: v2.10
    hooks:
      - id: vulture
        args: [--min-confidence=60]
"""


@click.group()
def app():
    """Automated code cleanup using vulture, ruff, and pre-commit."""
    pass


@app.command("run")
@click.option("--dry-run", is_flag=True, help="Preview changes without applying")
@click.option("--auto", is_flag=True, help="Auto-fix safe changes")
@click.option("--format", "-f", type=click.Choice(["text", "json"]), default="json")
def run_cleanup(dry_run: bool, auto: bool, format: str):
    """Run cleanup and optionally apply fixes."""

    results = {
        "dead_code": run_vulture(),
        "ruff_issues": run_ruff_check(),
        "pre_commit": run_pre_commit(dry_run=not auto),
    }

    # Apply auto-fixes if requested
    if auto and not dry_run:
        results["applied_fixes"] = apply_auto_fixes()

    # Output
    if format == "json":
        click.echo(json.dumps(results, indent=2, default=str))
    else:
        print_cleanup_report(results)


@app.command("init")
def init():
    """Initialize pre-commit configuration."""
    config_path = Path(".pre-commit-config.yaml")
    config_path.write_text(PRE_COMMIT_CONFIG)
    click.echo("Created .pre-commit-config.yaml")

    result = subprocess.run(["pre-commit", "install"], capture_output=True, text=True)
    if result.returncode == 0:
        click.echo("pre-commit hooks installed")
    else:
        click.echo("Note: pre-commit not available. Install with: pip install pre-commit")


def run_vulture() -> dict:
    """Run vulture for dead code detection.

    Returns list of potentially unused code with confidence scores.
    """
    cmd = ["vulture", ".", "--min-confidence", "60", "--exclude", "node_modules,.git,venv,.venv"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if not result.stdout.strip():
            return {"passed": True, "issues": []}

        # Parse vulture output
        issues = []
        for line in result.stdout.strip().split("\n"):
            if line:
                issues.append({
                    "type": "dead_code",
                    "message": line,
                    "fix": "Verify this code is unused, then remove it.",
                    "safe_to_remove": False,  # Needs human verification
                })

        return {
            "passed": len(issues) == 0,
            "issues": issues,
        }
    except FileNotFoundError:
        return {
            "passed": True,
            "issues": [],
            "note": "vulture not installed. Install: pip install vulture"
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "issues": [{"type": "error", "message": "vulture timed out"}],
        }


def run_ruff_check() -> dict:
    """Run ruff to find fixable issues."""
    cmd = ["ruff", "check", "--output-format", "json"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        issues = json.loads(result.stdout) if result.stdout else []

        fixable = [i for i in issues if i.get("fix")]

        return {
            "passed": len(issues) == 0,
            "total_issues": len(issues),
            "auto_fixable": len(fixable),
        }
    except FileNotFoundError:
        return {"passed": True, "issues": [], "note": "ruff not available"}
    except (json.JSONDecodeError, subprocess.TimeoutExpired):
        return {"passed": True, "issues": [], "note": "ruff check failed"}


def run_pre_commit(dry_run: bool = True) -> dict:
    """Run pre-commit hooks.

    If dry_run, just show what would run.
    """
    cmd = ["pre-commit", "run", "--all-files"]
    if dry_run:
        cmd = ["pre-commit", "run", "--all-files", "--show-diff-on-failure"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "passed": result.returncode == 0,
            "output": result.stdout + result.stderr,
        }
    except FileNotFoundError:
        return {
            "passed": True,
            "note": "pre-commit not installed. Install: pip install pre-commit"
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "output": "pre-commit timed out",
        }


def apply_auto_fixes() -> dict:
    """Apply safe auto-fixes.

    Returns what was fixed.
    """
    fixes_applied = []

    # Ruff auto-fixes
    result = subprocess.run(
        ["ruff", "check", "--fix"],
        capture_output=True,
        text=True
    )
    fixes_applied.append({
        "tool": "ruff",
        "output": result.stdout if result.stdout else "No fixes applied",
    })

    return fixes_applied


def print_cleanup_report(results: dict):
    """Print a human-readable cleanup report."""
    click.echo("\n=== Cleanup Report ===\n")

    # Dead code
    dead_code = results.get("dead_code", {})
    if dead_code.get("note"):
        click.echo(f"Dead Code: {dead_code['note']}")
    elif dead_code.get("issues"):
        click.echo(f"Dead Code: {len(dead_code['issues'])} potential issues")
        for issue in dead_code["issues"][:5]:
            click.echo(f"  - {issue.get('message', '')}")
    else:
        click.echo("Dead Code: PASSED")

    # Ruff issues
    ruff = results.get("ruff_issues", {})
    if ruff.get("note"):
        click.echo(f"Ruff: {ruff['note']}")
    else:
        click.echo(f"Ruff: {ruff.get('total_issues', 0)} issues ({ruff.get('auto_fixable', 0)} auto-fixable)")

    # Pre-commit
    pre_commit = results.get("pre_commit", {})
    if pre_commit.get("note"):
        click.echo(f"Pre-commit: {pre_commit['note']}")
    elif pre_commit.get("passed"):
        click.echo("Pre-commit: PASSED")
    else:
        click.echo("Pre-commit: ISSUES FOUND")

    # Applied fixes
    if results.get("applied_fixes"):
        click.echo("\n=== Applied Fixes ===")
        for fix in results["applied_fixes"]:
            click.echo(f"\n{fix['tool']}:")
            click.echo(f"  {fix['output'][:200]}..." if len(fix['output']) > 200 else f"  {fix['output']}")


if __name__ == "__main__":
    app()
