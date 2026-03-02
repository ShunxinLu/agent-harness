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
import sys
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .config import detect_project, detect_framework, scan_projects, ProjectConfig
from .cache import HarnessCache, get_default_cache
from .tracing import TraceStore, get_default_store
from .runners.generic_runner import get_runner
from .output import format_summary


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
                        "description": "Base directory to scan (default: c:/Users/lushu/projects)"
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
        elif name == "list_projects":
            return await handle_list_projects(arguments)
        elif name == "detect_framework":
            return await handle_detect_framework(arguments)
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

    if not project_path.exists():
        return [TextContent(type="text", text=f"Project path not found: {project_path}")]

    # Detect project
    config = detect_project(project_path)
    if not config:
        framework = detect_framework(project_path)
        if framework:
            return [TextContent(type="text", text=f"Detected {framework} but could not configure project")]
        return [TextContent(type="text", text=f"No test framework detected in: {project_path}")]

    # Get cache for last_failed
    cache = None
    if last_failed:
        cache = get_default_cache()
        failed_tests = cache.get_last_failed(config.name)
        if failed_tests and config.framework == "pytest":
            # Note: Would need to modify runner to support specific test names
            pass

    # Run tests
    runner = get_runner(config)
    if not runner:
        return [TextContent(type="text", text=f"No runner available for framework: {config.framework}")]

    result = runner.run()

    # Store in cache
    if cache:
        cache.store_run(
            project=config.name,
            run_id=str(hash(str(project_path))),
            results=[r.model_dump() for r in result.results] if result.results else [],
        )
        cache.close()
    else:
        # Still cache the result
        cache = get_default_cache()
        cache.store_run(
            project=config.name,
            run_id=str(hash(str(project_path))),
            results=[r.model_dump() for r in result.results] if result.results else [],
        )
        cache.close()

    if json_output:
        return [TextContent(type="text", text=json.dumps(result.model_dump(), indent=2, default=str))]
    else:
        return [TextContent(type="text", text=format_summary(result))]


async def handle_list_projects(arguments: dict) -> list[TextContent]:
    """List all detectable projects."""
    base_dir = arguments.get("base_dir", "c:/Users/lushu/projects")
    scan_dir = Path(base_dir)

    if not scan_dir.exists():
        return [TextContent(type="text", text=f"Directory not found: {base_dir}")]

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


async def handle_get_cache_status(arguments: dict) -> list[TextContent]:
    """Get cache statistics."""
    cache = get_default_cache()
    stats = cache.get_stats()
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

    cache = get_default_cache()
    trend = cache.get_trend(project, limit)
    cache.close()

    if not trend:
        return [TextContent(type="text", text=f"No cache data found for project: {project}")]

    return [TextContent(type="text", text=json.dumps(trend, indent=2))]


async def handle_get_last_failed(arguments: dict) -> list[TextContent]:
    """Get last failed tests for a project."""
    project = arguments["project"]

    cache = get_default_cache()
    failed = cache.get_last_failed(project)
    cache.close()

    return [TextContent(type="text", text=json.dumps({"failed_tests": failed}, indent=2))]


async def handle_list_traces(arguments: dict) -> list[TextContent]:
    """List recent traces."""
    limit = arguments.get("limit", 20)

    store = get_default_store()
    results = store.query(f"""
        SELECT run_id, COUNT(*) as event_count,
               MIN(timestamp) as start_time,
               SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count
        FROM traces
        GROUP BY run_id
        ORDER BY start_time DESC
        LIMIT {limit}
    """)
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

    store = get_default_store()
    events = store.get_by_run(run_id)

    if errors_only:
        events = [e for e in events if e.status == "error"]

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

    store = get_default_store()

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

    store.close()

    return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]


async def handle_clear_cache(arguments: dict) -> list[TextContent]:
    """Clear the cache."""
    project = arguments.get("project")

    cache = get_default_cache()
    cache.clear(project=project)
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
