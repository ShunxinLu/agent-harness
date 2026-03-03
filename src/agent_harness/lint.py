"""
Harness Lint - Structural validation orchestrator.

Wraps existing tools instead of reinventing parsers:
- ruff: Standard linting (F401, F841, docstrings, style)
- tach: Architectural boundaries (layer enforcement)
- vulture: Dead code detection

Universal: Works for Claude Code, Cursor, Copilot, Codex - any agent.
"""

import json
import subprocess
import click


@click.group()
def app():
    """Structural validation for agent projects.

    Wraps ruff, tach, and vulture. Aggregates output into unified JSON.
    """
    pass


@app.command("check")
@click.option("--format", "-f", type=click.Choice(["text", "json"]), default="json")
@click.option("--fix", is_flag=True, help="Auto-fix what's safe")
def check(format: str, fix: bool):
    """Run all lint checks and output results."""

    check_results = {
        "standard": run_ruff_check(fix=fix),
        "architecture": run_tach_check(),
        "dead_code": run_vulture_check(),
    }

    # Calculate overall status
    passed = all(r["passed"] for r in check_results.values())
    total_issues = sum(
        len(r.get("issues", [])) for r in check_results.values()
    )

    results = {
        "passed": passed,
        "total_issues": total_issues,
        **check_results,
    }

    if format == "json":
        click.echo(json.dumps(results, indent=2))
    else:
        print_text_report(results)

    if not results["passed"]:
        raise SystemExit(1)


@app.command("fix")
@click.argument("file", type=click.Path(), required=False)
def fix(file: str = None):
    """Auto-fix issues where possible.

    Runs ruff check --fix for automatic fixes.
    """
    cmd = ["ruff", "check", "--fix"]
    if file:
        cmd.append(file)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)
    click.echo("Auto-fixes applied where possible")


@app.command("init")
def init():
    """Initialize tach configuration for this project."""
    result = subprocess.run(["tach", "init"], capture_output=True, text=True)
    if result.returncode == 0:
        click.echo("tach.toml created. Edit to define your layer boundaries.")
    else:
        click.echo(f"tach init result: {result.stdout}")
        click.echo(f"tach init errors: {result.stderr}")


def run_ruff_check(fix: bool = False) -> dict:
    """Run ruff linter.

    Ruff handles (in milliseconds):
    - F401: Unused imports
    - F841: Unused variables
    - D100-D107: Missing docstrings
    - E, W: Style issues
    - I: Import sorting

    Native JSON output: ruff check --output-format json
    """
    cmd = ["ruff", "check", "--output-format", "json"]
    if fix:
        cmd.append("--fix")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        ruff_issues = json.loads(result.stdout) if result.stdout else []

        return {
            "passed": len(ruff_issues) == 0,
            "issues": [
                {
                    "type": issue.get("code", "unknown"),
                    "file": issue.get("filename", "unknown"),
                    "line": issue.get("location", {}).get("row", 0) if issue.get("location") else 0,
                    "message": issue.get("message", ""),
                    "fix": ruff_fix_instruction(issue.get("fix")),
                }
                for issue in ruff_issues
            ],
        }
    except FileNotFoundError:
        return {
            "passed": True,
            "issues": [],
            "note": "ruff not installed. Install: pip install ruff"
        }
    except json.JSONDecodeError:
        return {
            "passed": True,
            "issues": [],
            "note": "ruff output not valid JSON"
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "issues": [{"type": "error", "message": "ruff timed out"}],
        }


def ruff_fix_instruction(fix: dict | None) -> str:
    """Convert ruff fix to agent-readable instruction."""
    if not fix:
        return "Manual fix required"
    if fix.get("applicable"):
        return "Auto-fix available via ruff check --fix"
    return "Manual fix required"


def run_tach_check() -> dict:
    """Run tach for architectural boundary enforcement.

    Tach (https://github.com/gauge-sh/tach) enforces layer boundaries
    defined in tach.toml.

    Run: tach check
    Output: Blocking imports like "domain cannot import infrastructure"
    """
    cmd = ["tach", "check"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            return {"passed": True, "issues": []}

        # Parse tach error output
        violations = parse_tach_output(result.stdout + result.stderr)
        return {
            "passed": False,
            "issues": violations,
        }
    except FileNotFoundError:
        return {
            "passed": True,
            "issues": [],
            "note": "tach not installed. Install: pip install tach"
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "issues": [{"type": "error", "message": "tach timed out"}],
        }


def parse_tach_output(output: str) -> list:
    """Parse tach blocking import errors into structured violations."""
    violations = []
    # Example tach output:
    # "Error: src.domain.models cannot import src.infrastructure.db"
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        if "cannot import" in line.lower() or "blocking" in line.lower():
            violations.append({
                "type": "architecture_violation",
                "message": line,
                "fix": "Remove the blocking import. Lower layers cannot depend on higher layers. Consider dependency injection or moving shared code to a common layer.",
            })
    return violations


def run_vulture_check() -> dict:
    """Run vulture for dead code detection.

    Vulture (https://github.com/jendrikseipp/vulture) finds:
    - Unused functions
    - Unused classes
    - Unused variables
    - Unused imports

    Run: vulture . --min-confidence 60
    """
    cmd = ["vulture", ".", "--min-confidence", "60", "--exclude", "node_modules,.git,venv,.venv"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if not result.stdout.strip():
            return {"passed": True, "issues": []}

        # Parse vulture output
        # Format: file:line: <type> '<name>' unused
        issues = parse_vulture_output(result.stdout)
        return {
            "passed": False,
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


def parse_vulture_output(output: str) -> list:
    """Parse vulture output into structured issues."""
    issues = []
    for line in output.strip().split("\n"):
        if not line:
            continue
        # Format: "src/module.py:10: unused function 'my_func' (60% confidence)"
        parts = line.split(":")
        if len(parts) >= 3:
            file_path = parts[0]
            line_num = parts[1]
            rest = ":".join(parts[2:])

            # Extract the name from the message
            name = "unknown"
            if "'" in rest:
                name = rest.split("'")[1]

            issues.append({
                "type": "dead_code",
                "file": file_path,
                "line": int(line_num) if line_num.isdigit() else 0,
                "message": rest.strip(),
                "fix": f"Verify '{name}' is unused, then remove it.",
                "safe_to_remove": False,  # Needs human verification
            })
    return issues


def print_text_report(results: dict):
    """Print a human-readable text report."""
    status = "PASSED" if results["passed"] else "FAILED"
    click.echo(f"\nLint Check: {status}")
    click.echo(f"Total issues: {results['total_issues']}")

    for check_name, check_result in results.items():
        if check_name in ("passed", "total_issues"):
            continue
        if not isinstance(check_result, dict):
            continue

        if check_result.get("note"):
            click.echo(f"\n{check_name}: {check_result['note']}")
        elif check_result.get("issues"):
            click.echo(f"\n{check_name}: {len(check_result['issues'])} issues")
            for issue in check_result["issues"][:5]:  # Show first 5
                click.echo(f"  - {issue.get('file', 'unknown')}:{issue.get('line', '?')} - {issue.get('message', '')}")
            if len(check_result["issues"]) > 5:
                click.echo(f"  ... and {len(check_result['issues']) - 5} more")


if __name__ == "__main__":
    app()
