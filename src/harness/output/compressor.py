"""
Output optimization - Stack trace compression and JSON formatting.
"""

import re
from typing import Optional
from pydantic import BaseModel


class CompressedError(BaseModel):
    """A compressed error representation."""
    error_type: str
    message: str
    location: Optional[str] = None  # file:line
    context: list[str] = []  # Relevant code context
    category: str = "unknown"  # assertion, import, timeout, etc.

    class Config:
        arbitrary_types_allowed = True


class TestResult(BaseModel):
    """Result of a single test."""
    name: str
    status: str  # passed, failed, skipped, error
    duration: float = 0.0
    error: Optional[CompressedError] = None
    output: str = ""

    class Config:
        arbitrary_types_allowed = True


class TestRunResult(BaseModel):
    """Result of a test run."""
    project: str
    framework: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    results: list[TestResult] = []
    summary: str = ""

    class Config:
        arbitrary_types_allowed = True


def categorize_error(error_message: str) -> str:
    """Categorize an error based on its content."""

    error_lower = error_message.lower()

    if "assert" in error_lower:
        return "assertion"
    elif "import" in error_lower or "module not found" in error_lower:
        return "import"
    elif "timeout" in error_lower:
        return "timeout"
    elif "attributeerror" in error_lower:
        return "attribute"
    elif "typeerror" in error_lower:
        return "type"
    elif "keyerror" in error_lower or "indexerror" in error_lower:
        return "lookup"
    elif "file" in error_lower and "not found" in error_lower:
        return "file_not_found"
    elif "connection" in error_lower or "refused" in error_lower:
        return "connection"
    elif "permission" in error_lower or "denied" in error_lower:
        return "permission"
    elif "syntax" in error_lower:
        return "syntax"
    elif "null" in error_lower or "none" in error_lower:
        return "null_reference"

    return "unknown"


def compress_stack_trace(trace: str, max_frames: int = 5) -> str:
    """
    Compress a stack trace to only show relevant frames.

    - Removes internal pytest/Python frames
    - Keeps user code frames
    - Limits total frames shown
    """

    if not trace:
        return ""

    lines = trace.split("\n")
    compressed = []
    user_frames = 0
    skipped = 0

    # Patterns to filter out
    skip_patterns = [
        r".*site-packages.*",
        r".*lib/python.*",
        r".*pycharm.*",
        r".*venv.*",
        r".*__pycache__.*",
        r"^  File \"<.*",
        r".*typing\.py.*",
        r".*functools\.py.*",
        r".*asyncio.*",
        r"^Traceback.*",
        r"^\w+Error:",  # We'll add the final error separately
    ]

    for line in lines:
        should_skip = any(re.match(pattern, line) for pattern in skip_patterns)

        if should_skip:
            skipped += 1
            continue

        # Keep user code frames (limited)
        if "File \"" in line and user_frames < max_frames:
            compressed.append(line)
            user_frames += 1
        elif "File \"" in line and user_frames >= max_frames:
            skipped += 1
        else:
            # Keep assertion lines and context
            if line.strip() and not line.strip().startswith("^"):
                compressed.append(line)

    # Add summary of skipped frames
    if skipped > 0:
        compressed.insert(-1 if len(compressed) > 1 else 0,
                         f"\n[... {skipped} internal frames skipped ...]\n")

    return "\n".join(compressed)


def extract_error_info(trace: str) -> CompressedError:
    """Extract structured error information from a stack trace."""

    # Find the error type and message (last line usually)
    error_match = re.search(r"(\w+Error):\s*(.+?)(?:\n|$)", trace)

    if error_match:
        error_type = error_match.group(1)
        message = error_match.group(2).strip()
    else:
        error_type = "UnknownError"
        message = trace.split("\n")[-1] if trace else "Unknown error"

    # Find file location
    location_match = re.search(r'File "([^"]+)", line (\d+)', trace)
    location = None
    if location_match:
        file_path = location_match.group(1)
        line_num = location_match.group(2)
        # Use just the relative path
        location = f"{file_path}:{line_num}"

    context = []
    # Extract code context if available
    context_match = re.findall(r"^\s*(?:>>>|E\s+|AssertionError:|>\s+)(.+)$", trace, re.MULTILINE)
    if context_match:
        context = context_match[:3]  # Limit context lines

    return CompressedError(
        error_type=error_type,
        message=message[:500],  # Limit message length
        location=location,
        context=context,
        category=categorize_error(trace),
    )


def format_result_json(result: TestRunResult, compact: bool = True) -> str:
    """Format test results as JSON."""

    import json

    output = result.model_dump(mode="json")

    if compact:
        # Remove empty fields and compress errors
        for r in output.get("results", []):
            if r.get("output") == "":
                r.pop("output", None)
            if r.get("error") and compact:
                # Error is already compressed at extraction time
                pass

    return json.dumps(output, indent=2)


def format_summary(result: TestRunResult) -> str:
    """Format a human-readable summary."""

    # Status indicators (ASCII only for Windows compatibility)
    if result.failed == 0 and result.errors == 0:
        status_icon = "[PASS]"
        status_text = "PASSED"
    else:
        status_icon = "[FAIL]"
        status_text = "FAILED"

    output = []
    output.append(f"\n{result.project} ({result.framework})")
    output.append(f"Status: {status_icon} {status_text}")
    output.append(
        f"Total: {result.total} | "
        f"Passed: {result.passed} | "
        f"Failed: {result.failed} | "
        f"Skipped: {result.skipped} | "
        f"Errors: {result.errors}"
    )
    output.append(f"Duration: {result.duration:.2f}s")

    # Show failures
    failures = [r for r in result.results if r.status in ("failed", "error") and r.error]

    if failures:
        output.append("\nFailures:")
        for failure in failures:
            output.append(f"  - {failure.name}")
            if failure.error:
                output.append(f"    Location: {failure.error.location or 'Unknown'}")
                output.append(f"    Error: {failure.error.error_type}: {failure.error.message[:100]}")
                if failure.error.context:
                    for ctx in failure.error.context:
                        output.append(f"    > {ctx}")
            output.append("")

    print("\n".join(output))

    return status_text
