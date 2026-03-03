"""
Harness MCP Server - Enable Claude Code to interact with the test harness.

Provides tools for:
- Running tests on any project type
- Listing available projects
- Querying test results and cache
- Viewing execution traces
- Detecting project frameworks
"""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .config import detect_project, detect_framework, scan_projects, ProjectConfig
from .cache import create_cache
from .tracing import create_trace_store
from .runners.generic_runner import get_runner
from .output import format_summary
from .session_manager import get_next_feature, update_feature_status, collect_resume_context
from .policy import PolicyEngine
from .contracts import load_task_contract
from .manifest import write_project_run_manifest
from .observability import set_span_attributes, start_span


# Create the MCP server
server = Server("harness")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available harness tools."""
    return [
        Tool(
            name="run_tests",
            description="Run tests for a project. Supports pytest, bun, npm, maven, gradle, sbt, cargo, go, pyspark.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project directory"
                    },
                    "json_output": {
                        "type": "boolean",
                        "description": "Return results as JSON (default: true)",
                        "default": True
                    },
                    "last_failed": {
                        "type": "boolean",
                        "description": "Run only previously failed tests",
                        "default": False
                    },
                    "data_mode": {
                        "type": "string",
                        "description": "Data access mode for the run",
                        "enum": ["mock", "metadata", "human-contract"],
                        "default": "mock",
                    }
                },
                "required": ["project_path"]
            }
        ),
        Tool(
            name="initialize_session",
            description="Run startup bearings checks and return resume context from .harness artifacts",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project directory"
                    },
                    "run_smoke_check": {
                        "type": "boolean",
                        "description": "Execute .harness/init.sh during initialization",
                        "default": False
                    }
                },
                "required": ["project_path"]
            }
        ),
        Tool(
            name="list_projects",
            description="List all detectable test projects in a directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "base_dir": {
                        "type": "string",
                        "description": "Base directory to scan (default: current working directory)"
                    }
                }
            }
        ),
        Tool(
            name="detect_framework",
            description="Detect the test framework for a specific project path",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory"
                    }
                },
                "required": ["project_path"]
            }
        ),
        Tool(
            name="get_next_feature",
            description="Get next pending feature from .harness/feature_list.json",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project directory"
                    }
                },
                "required": ["project_path"]
            }
        ),
        Tool(
            name="update_feature_status",
            description="Update feature pass/fail status with evidence requirements",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project directory"
                    },
                    "feature_id": {
                        "type": "string",
                        "description": "Feature ID in .harness/feature_list.json"
                    },
                    "passes": {
                        "type": "boolean",
                        "description": "Whether the feature now passes validation"
                    },
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Evidence references (run IDs, manifest paths, eval links)"
                    }
                },
                "required": ["project_path", "feature_id", "passes"]
            }
        ),
        Tool(
            name="get_cache_status",
            description="Get cache statistics showing test run history",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_cache_trend",
            description="Get test trend over time for a project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "Project name"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of runs to show",
                        "default": 10
                    }
                },
                "required": ["project"]
            }
        ),
        Tool(
            name="get_last_failed",
            description="Get list of tests that failed in the most recent run for a project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "Project name"
                    }
                },
                "required": ["project"]
            }
        ),
        Tool(
            name="list_traces",
            description="List recent trace runs",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum runs to show",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="get_trace",
            description="Get trace events for a specific run ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The run ID to get traces for"
                    },
                    "errors_only": {
                        "type": "boolean",
                        "description": "Return only error events",
                        "default": False
                    }
                },
                "required": ["run_id"]
            }
        ),
        Tool(
            name="analyze_errors",
            description="Analyze error patterns across traces",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Error pattern to search for"
                    },
                    "min_count": {
                        "type": "integer",
                        "description": "Minimum occurrence count",
                        "default": 3
                    }
                }
            }
        ),
        Tool(
            name="clear_cache",
            description="Clear the test result cache",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "Clear cache for specific project only (optional)"
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""

    try:
        if name == "run_tests":
            return await handle_run_tests(arguments)
        elif name == "initialize_session":
            return await handle_initialize_session(arguments)
        elif name == "list_projects":
            return await handle_list_projects(arguments)
        elif name == "detect_framework":
            return await handle_detect_framework(arguments)
        elif name == "get_next_feature":
            return await handle_get_next_feature(arguments)
        elif name == "update_feature_status":
            return await handle_update_feature_status(arguments)
        elif name == "get_cache_status":
            return await handle_get_cache_status(arguments)
        elif name == "get_cache_trend":
            return await handle_get_cache_trend(arguments)
        elif name == "get_last_failed":
            return await handle_get_last_failed(arguments)
        elif name == "list_traces":
            return await handle_list_traces(arguments)
        elif name == "get_trace":
            return await handle_get_trace(arguments)
        elif name == "analyze_errors":
            return await handle_analyze_errors(arguments)
        elif name == "clear_cache":
            return await handle_clear_cache(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_run_tests(arguments: dict) -> list[TextContent]:
    """Run tests for a project."""
    project_path = Path(arguments["project_path"])
    json_output = arguments.get("json_output", True)
    last_failed = arguments.get("last_failed", False)
    data_mode = arguments.get("data_mode", "mock")
    session_run_id = str(uuid.uuid4())
    project_run_id = str(uuid.uuid4())
    with start_span(
        "harness.mcp.preflight",
        {
            "harness.session_run_id": session_run_id,
            "harness.project_run_id": project_run_id,
            "harness.project_path": str(project_path),
            "harness.data_mode": data_mode,
            "harness.last_failed_requested": last_failed,
            "harness.json_output": json_output,
        },
    ) as preflight_span:
        allowed_modes = {"mock", "metadata", "human-contract"}
        if data_mode not in allowed_modes:
            return [TextContent(type="text", text=f"Invalid data_mode: {data_mode}. Allowed: {sorted(allowed_modes)}")]

        if not project_path.exists():
            return [TextContent(type="text", text=f"Project path not found: {project_path}")]

        # Detect project
        config = detect_project(project_path)
        if not config:
            framework = detect_framework(project_path)
            if framework:
                return [TextContent(type="text", text=f"Detected {framework} but could not configure project")]
            return [TextContent(type="text", text=f"No test framework detected in: {project_path}")]

        require_task_contract = os.getenv("HARNESS_REQUIRE_TASK_CONTRACT", "").lower() in {"1", "true", "yes"}
        contract_finding = {"project": config.name, "allowed": True, "reason": "Task contract valid"}
        try:
            load_task_contract(config.path)
        except Exception as exc:
            contract_finding = {"project": config.name, "allowed": False, "reason": str(exc)}
            if require_task_contract:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": "task_contract_validation_failed",
                                "contract_finding": contract_finding,
                            },
                            indent=2,
                        ),
                    )
                ]

        policy_result = PolicyEngine().evaluate_verify_request([config], data_mode)
        policy_decisions_payload = [decision.model_dump(mode="json") for decision in policy_result.decisions]
        denied_count = sum(1 for decision in policy_result.decisions if not decision.allowed)
        set_span_attributes(
            preflight_span,
            {
                "harness.project": config.name,
                "harness.framework": config.framework,
                "harness.contract_allowed": contract_finding["allowed"],
                "harness.policy_allowed": policy_result.allowed,
                "harness.policy_denied_count": denied_count,
            },
        )
        if not policy_result.allowed:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": "policy_denied",
                            "policy_decisions": policy_decisions_payload,
                        },
                        indent=2,
                    ),
                )
            ]

    extra_args = None

    # Get cache info for last_failed
    if last_failed and config.framework in ("pytest", "pyspark"):
        cache = create_cache()
        try:
            failed_tests = cache.get_last_failed(config.name)
            if failed_tests:
                extra_args = failed_tests
        finally:
            cache.close()

    # Run tests
    runner = get_runner(config)
    if not runner:
        return [TextContent(type="text", text=f"No runner available for framework: {config.framework}")]

    with start_span(
        "harness.mcp.project_run",
        {
            "harness.session_run_id": session_run_id,
            "harness.project_run_id": project_run_id,
            "harness.project": config.name,
            "harness.framework": config.framework,
            "harness.data_mode": data_mode,
            "harness.last_failed_applied": bool(extra_args),
        },
    ) as project_span:
        previous_data_mode = os.environ.get("HARNESS_DATA_MODE")
        os.environ["HARNESS_DATA_MODE"] = data_mode
        try:
            if extra_args and config.framework in ("pytest", "pyspark", "bun", "npm"):
                result = runner.run(extra_args=extra_args)
            else:
                result = runner.run()
        finally:
            if previous_data_mode is None:
                os.environ.pop("HARNESS_DATA_MODE", None)
            else:
                os.environ["HARNESS_DATA_MODE"] = previous_data_mode

        set_span_attributes(
            project_span,
            {
                "harness.execution_status": result.execution_status,
                "harness.total_tests": result.total,
                "harness.failed_tests": result.failed,
                "harness.error_tests": result.errors,
                "harness.duration_seconds": result.duration,
            },
        )

    # Store in cache
    cache = create_cache()
    try:
        cache.store_run(
            project=config.name,
            run_id=project_run_id,
            results=[r.model_dump() for r in result.results] if result.results else [],
            parent_run_id=session_run_id,
        )
    finally:
        cache.close()

    manifest_path = write_project_run_manifest(
        project_config=config,
        session_run_id=session_run_id,
        project_run_id=project_run_id,
        data_mode=data_mode,
        last_failed_requested=last_failed,
        last_failed_applied=bool(extra_args),
        policy_decisions=policy_decisions_payload,
        result=result,
        contract_finding=contract_finding,
    )

    if json_output:
        payload = result.model_dump(mode="json")
        payload["run_id"] = session_run_id
        payload["session_run_id"] = session_run_id
        payload["project_run_id"] = project_run_id
        payload["manifest_path"] = str(manifest_path)
        payload["last_failed_applied"] = bool(extra_args)
        payload["data_mode"] = data_mode
        payload["policy_decisions"] = policy_decisions_payload
        payload["contract_finding"] = contract_finding
        return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]

    status = format_summary(result, print_output=False)
    return [
        TextContent(
            type="text",
            text=(
                f"Session Run ID: {session_run_id}\n"
                f"Project Run ID: {project_run_id}\n"
                f"Manifest: {manifest_path}\n"
                f"Status: {status}"
            ),
        )
    ]


async def handle_initialize_session(arguments: dict) -> list[TextContent]:
    """Collect startup bearings and optional smoke-check output."""
    project_path = Path(arguments["project_path"])
    run_smoke_check = bool(arguments.get("run_smoke_check", False))

    if not project_path.exists():
        return [TextContent(type="text", text=f"Project path not found: {project_path}")]

    with start_span(
        "harness.mcp.initialize_session",
        {
            "harness.project_path": str(project_path),
            "harness.run_smoke_check": run_smoke_check,
        },
    ) as span:
        context = collect_resume_context(project_root=project_path, run_smoke_check=run_smoke_check)
        set_span_attributes(
            span,
            {
                "harness.has_required_artifacts": context["has_required_artifacts"],
                "harness.missing_artifacts_count": len(context["missing_artifacts"]),
                "harness.smoke_exit_code": context["smoke_check"]["exit_code"],
            },
        )
    return [TextContent(type="text", text=json.dumps(context, indent=2))]


async def handle_list_projects(arguments: dict) -> list[TextContent]:
    """List all detectable projects."""
    base_dir = arguments.get("base_dir")
    scan_dir = Path(base_dir).expanduser() if base_dir else Path.cwd()

    if not scan_dir.exists():
        return [TextContent(type="text", text=f"Directory not found: {scan_dir}")]

    projects = scan_projects(scan_dir)

    if not projects:
        return [TextContent(type="text", text="No testable projects found")]

    result = []
    for proj in projects:
        result.append({
            "name": proj.name,
            "framework": proj.framework,
            "path": str(proj.path),
            "test_dir": str(proj.test_dir),
        })

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_detect_framework(arguments: dict) -> list[TextContent]:
    """Detect framework for a project."""
    project_path = Path(arguments["project_path"])

    if not project_path.exists():
        return [TextContent(type="text", text=f"Path not found: {project_path}")]

    framework = detect_framework(project_path)

    if not framework:
        return [TextContent(type="text", text="No test framework detected")]

    config = detect_project(project_path)

    result = {
        "framework": framework,
        "project": config.name if config else project_path.name,
        "test_dir": str(config.test_dir) if config else None,
        "command": config.command if config else [],
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_next_feature(arguments: dict) -> list[TextContent]:
    """Get next pending feature from feature ledger."""
    project_path = Path(arguments["project_path"])
    if not project_path.exists():
        return [TextContent(type="text", text=f"Project path not found: {project_path}")]

    try:
        feature = get_next_feature(project_path)
    except (FileNotFoundError, ValueError) as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]

    if feature is None:
        return [TextContent(type="text", text=json.dumps({"next_feature": None, "all_passed": True}, indent=2))]

    return [
        TextContent(
            type="text",
            text=json.dumps({"next_feature": feature.model_dump(mode="json"), "all_passed": False}, indent=2),
        )
    ]


async def handle_update_feature_status(arguments: dict) -> list[TextContent]:
    """Update feature pass/fail status."""
    project_path = Path(arguments["project_path"])
    if not project_path.exists():
        return [TextContent(type="text", text=f"Project path not found: {project_path}")]

    feature_id = arguments["feature_id"]
    passes = bool(arguments["passes"])
    evidence = arguments.get("evidence", [])

    try:
        updated = update_feature_status(
            project_root=project_path,
            feature_id=feature_id,
            passes=passes,
            evidence=evidence,
        )
    except (FileNotFoundError, ValueError) as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]

    return [TextContent(type="text", text=json.dumps(updated.model_dump(mode="json"), indent=2))]


async def handle_get_cache_status(arguments: dict) -> list[TextContent]:
    """Get cache statistics."""
    cache = create_cache()
    try:
        stats = cache.get_stats()
    finally:
        cache.close()

    result = {
        "total_runs": stats.total_runs,
        "total_tests": stats.total_tests,
        "projects": stats.projects,
        "oldest_run": stats.oldest_run.isoformat() if stats.oldest_run else None,
        "newest_run": stats.newest_run.isoformat() if stats.newest_run else None,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_cache_trend(arguments: dict) -> list[TextContent]:
    """Get test trend for a project."""
    project = arguments["project"]
    limit = arguments.get("limit", 10)

    cache = create_cache()
    try:
        trend = cache.get_trend(project, limit)
    finally:
        cache.close()

    if not trend:
        return [TextContent(type="text", text=f"No cache data found for project: {project}")]

    return [TextContent(type="text", text=json.dumps(trend, indent=2))]


async def handle_get_last_failed(arguments: dict) -> list[TextContent]:
    """Get last failed tests for a project."""
    project = arguments["project"]

    cache = create_cache()
    try:
        failed = cache.get_last_failed(project)
    finally:
        cache.close()

    return [TextContent(type="text", text=json.dumps({"failed_tests": failed}, indent=2))]


async def handle_list_traces(arguments: dict) -> list[TextContent]:
    """List recent traces."""
    limit = int(arguments.get("limit", 20))

    store = create_trace_store()
    try:
        results = store.query(
            """
                SELECT run_id, COUNT(*) as event_count,
                       MIN(timestamp) as start_time,
                       SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count
                FROM traces
                GROUP BY run_id
                ORDER BY start_time DESC
                LIMIT ?
            """,
            (limit,),
        )
    finally:
        store.close()

    # Convert to serializable format
    for row in results:
        if row.get("start_time"):
            row["start_time"] = str(row["start_time"])

    return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]


async def handle_get_trace(arguments: dict) -> list[TextContent]:
    """Get trace for a run ID."""
    run_id = arguments["run_id"]
    errors_only = arguments.get("errors_only", False)

    store = create_trace_store()
    try:
        events = store.get_by_run(run_id)
        if errors_only:
            events = [e for e in events if e.status == "error"]
    finally:
        store.close()

    result = []
    for event in events:
        result.append({
            "id": event.id,
            "run_id": event.run_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "name": event.name,
            "payload": event.payload,
            "status": event.status,
            "error_message": event.error_message,
            "duration_ms": event.duration_ms,
        })

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def handle_analyze_errors(arguments: dict) -> list[TextContent]:
    """Analyze error patterns."""
    pattern = arguments.get("pattern", "")
    min_count = arguments.get("min_count", 3)

    store = create_trace_store()
    try:
        if pattern:
            results = store.analyze_patterns(pattern, min_count)
        else:
            results = store.query("""
                SELECT event_type, name, error_message, COUNT(*) as count
                FROM traces
                WHERE status = 'error'
                GROUP BY event_type, name, error_message
                ORDER BY count DESC
                LIMIT 20
            """)
    finally:
        store.close()

    return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]


async def handle_clear_cache(arguments: dict) -> list[TextContent]:
    """Clear the cache."""
    project = arguments.get("project")

    cache = create_cache()
    try:
        cache.clear(project=project)
    finally:
        cache.close()

    if project:
        return [TextContent(type="text", text=f"Cache cleared for project: {project}")]
    else:
        return [TextContent(type="text", text="Cache cleared")]


def main():
    """Run the MCP server."""
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )

    import asyncio
    asyncio.run(run())


if __name__ == "__main__":
    main()
