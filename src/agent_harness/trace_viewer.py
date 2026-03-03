"""
Harness Trace Viewer - CLI for viewing and analyzing agent traces.

Commands:
    harness-verify trace view <run-id>     # View trace in terminal
    harness-verify trace export <run-id>   # Export as JSON
    harness-verify trace compare <id1> <id2> # Compare two runs
    harness-verify trace list              # List recent runs
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from .tracing import TraceStore


def style(text: str, fg: str = None, bold: bool = False) -> str:
    """Add ANSI style to text."""
    colors = {
        "green": "32",
        "red": "31",
        "yellow": "33",
        "blue": "34",
        "cyan": "36",
        "magenta": "35",
    }

    result = text
    if fg and fg in colors:
        result = f"\033[{colors[fg]}m{result}\033[0m"
    if bold:
        result = f"\033[1m{result}\033[0m"
    return result


def console_print(text: str):
    """Simple print function."""
    click.echo(text)


def format_db_timestamp(value) -> str:
    """Format timestamp values from DuckDB rows for terminal display."""
    if value is None:
        return "N/A"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, str):
        return value[:19]
    return str(value)[:19]


def get_trace_store() -> TraceStore:
    """Get trace store from default location."""
    # Check for harness data directory
    data_dir = Path.home() / ".harness" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "harness.duckdb"
    return TraceStore(str(db_path))


@click.group()
def trace():
    """View and analyze agent execution traces."""
    pass


@trace.command("view")
@click.argument("run-id", type=str)
@click.option("--limit", "-l", type=int, default=50, help="Max events to show")
@click.option("--errors-only", "-e", is_flag=True, help="Show only error events")
def view_trace(run_id: str, limit: int, errors_only: bool):
    """View trace events for a specific run."""

    store = get_trace_store()
    events = store.get_by_run(run_id)

    if not events:
        console_print(style(f"No traces found for run: {run_id}", fg="yellow"))
        return

    # Filter if needed
    if errors_only:
        events = [e for e in events if e.status == "error"]

    console_print(f"\n{style('Trace:', bold=True)} {run_id}")
    console_print(f"{style('Events:', bold=True)} {len(events)}\n")

    # Group events by type for summary
    event_types = {}
    for event in events:
        event_types[event.event_type] = event_types.get(event.event_type, 0) + 1

    console_print(style("Event Summary:", bold=True))
    for event_type, count in sorted(event_types.items(), key=lambda x: -x[1]):
        console_print(f"  {event_type}: {count}")

    console_print(f"\n{style('Timeline:', bold=True)}")
    console_print("-" * 80)

    # Show events
    for event in events[:limit]:
        status_icon = "[OK]" if event.status == "ok" else "[FAIL]" if event.status == "error" else "[...]"
        status_color = "green" if event.status == "ok" else "red" if event.status == "error" else "yellow"

        time_str = event.timestamp.strftime("%H:%M:%S.%f")[:-3]

        line = f"{time_str} {style(status_icon, fg=status_color)} [{event.event_type}] {event.name}"

        if event.duration_ms:
            line += f" ({event.duration_ms:.1f}ms)"

        console_print(line)

        # Show error message if present
        if event.error_message:
            console_print(f"         {style('Error:', fg='red')} {event.error_message}")

        # Show payload summary
        if event.payload:
            payload_str = json.dumps(event.payload, default=str)[:100]
            if len(payload_str) > 100:
                payload_str += "..."
            console_print(f"         {style('Data:', fg='cyan')} {payload_str}")

    if len(events) > limit:
        console_print(f"\n... and {len(events) - limit} more events")


@trace.command("export")
@click.argument("run-id", type=str)
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path")
def export_trace(run_id: str, output: Optional[str]):
    """Export trace events as JSON."""

    store = get_trace_store()
    events = store.get_by_run(run_id)

    if not events:
        console_print(style(f"No traces found for run: {run_id}", fg="yellow"))
        return

    # Serialize events
    data = []
    for event in events:
        data.append({
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

    json_output = json.dumps(data, indent=2)

    if output:
        output_path = Path(output)
        output_path.write_text(json_output)
        console_print(style("[OK]", fg="green") + f" Exported {len(data)} events to: {output_path}")
    else:
        console_print(json_output)


@trace.command("compare")
@click.argument("run-id-1", type=str)
@click.argument("run-id-2", type=str)
def compare_traces(run_id_1: str, run_id_2: str):
    """Compare two trace runs."""

    store = get_trace_store()
    events_1 = store.get_by_run(run_id_1)
    events_2 = store.get_by_run(run_id_2)

    if not events_1:
        console_print(style(f"No traces found for run: {run_id_1}", fg="yellow"))
        return
    if not events_2:
        console_print(style(f"No traces found for run: {run_id_2}", fg="yellow"))
        return

    # Calculate stats
    def calc_stats(events):
        total = len(events)
        errors = sum(1 for e in events if e.status == "error")
        durations = [e.duration_ms for e in events if e.duration_ms]
        total_duration = sum(durations)
        avg_duration = total_duration / len(durations) if durations else 0
        return {
            "total": total,
            "errors": errors,
            "total_duration": total_duration,
            "avg_duration": avg_duration,
        }

    stats_1 = calc_stats(events_1)
    stats_2 = calc_stats(events_2)

    console_print(f"\n{style('Comparison:', bold=True)}")
    console_print(f"{'':<15} {style('Run 1', fg='cyan'):<15} {style('Run 2', fg='magenta'):<15} {'Diff':<15}")
    console_print("-" * 60)

    console_print(f"Run ID:         {run_id_1[:14]:<15} {run_id_2[:14]:<15}")
    console_print(f"Events:         {stats_1['total']:<15} {stats_2['total']:<15} {stats_2['total'] - stats_1['total']:+d}")
    console_print(f"Errors:         {stats_1['errors']:<15} {stats_2['errors']:<15} {stats_2['errors'] - stats_1['errors']:+d}")
    console_print(f"Total Duration: {stats_1['total_duration']:.1f}ms{'':<8} {stats_2['total_duration']:.1f}ms{'':<8} {stats_2['total_duration'] - stats_1['total_duration']:+.1f}ms")
    console_print(f"Avg Duration:   {stats_1['avg_duration']:.1f}ms{'':<8} {stats_2['avg_duration']:.1f}ms{'':<8} {stats_2['avg_duration'] - stats_1['avg_duration']:+.1f}ms")

    # Compare event types
    types_1 = set(e.event_type for e in events_1)
    types_2 = set(e.event_type for e in events_2)

    new_types = types_2 - types_1
    removed_types = types_1 - types_2

    if new_types:
        console_print(f"\n{style('New event types in Run 2:', fg='green')}")
        for t in new_types:
            console_print(f"  + {t}")

    if removed_types:
        console_print(f"\n{style('Removed event types from Run 1:', fg='yellow')}")
        for t in removed_types:
            console_print(f"  - {t}")


@trace.command("list")
@click.option("--limit", "-l", type=int, default=20, help="Max runs to show")
def list_traces(limit: int):
    """List recent trace runs."""

    store = get_trace_store()

    # Query for distinct run_ids with counts
    results = store.query(
        """
            SELECT run_id, COUNT(*) as event_count,
                   MIN(timestamp) as start_time,
                   MAX(timestamp) as end_time,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count
            FROM traces
            GROUP BY run_id
            ORDER BY start_time DESC
            LIMIT ?
        """,
        (limit,),
    )

    if not results:
        console_print(style("No traces found.", fg="yellow"))
        return

    console_print(f"\n{style('Recent Trace Runs:', bold=True)}")
    console_print(f"{'Run ID':<36} {'Events':<8} {'Errors':<8} {'Start Time':<20}")
    console_print("-" * 75)

    for row in results:
        run_id = row["run_id"]
        events = row["event_count"]
        errors = row["error_count"]
        start_time = format_db_timestamp(row.get("start_time"))

        error_str = style(str(errors), fg="red") if errors > 0 else str(errors)
        console_print(f"{run_id:<36} {events:<8} {error_str:<8} {start_time:<20}")


@trace.command("analyze")
@click.option("--pattern", "-p", type=str, default="", help="Error pattern to search for")
@click.option("--min-count", "-m", type=int, default=3, help="Minimum occurrence count")
def analyze_traces(pattern: str, min_count: int):
    """Analyze error patterns across traces."""

    store = get_trace_store()

    if pattern:
        results = store.analyze_patterns(pattern, min_count)

        if not results:
            console_print(style(f"No patterns found matching: {pattern}", fg="yellow"))
            return

        console_print(f"\n{style('Error Pattern Analysis:', bold=True)}")
        console_print(f"Pattern: {pattern}")
        console_print(f"{'Tool/Source':<30} {'Count':<10}")
        console_print("-" * 40)

        for row in results:
            tool_name = row.get("tool_name", "unknown")
            count = row.get("failure_count", 0)
            console_print(f"{tool_name:<30} {count:<10}")
    else:
        # Show general error summary
        results = store.query("""
            SELECT event_type, name, error_message, COUNT(*) as count
            FROM traces
            WHERE status = 'error'
            GROUP BY event_type, name, error_message
            ORDER BY count DESC
            LIMIT 20
        """)

        if not results:
            console_print(style("No errors found in traces.", fg="green"))
            return

        console_print(f"\n{style('Top Errors:', bold=True)}")
        console_print(f"{'Count':<8} {'Event Type':<20} {'Name':<20}")
        console_print("-" * 50)

        for row in results:
            console_print(f"{row['count']:<8} {row['event_type']:<20} {row['name']:<20}")
            if row['error_message']:
                msg = row['error_message'][:60] + "..." if len(row['error_message']) > 60 else row['error_message']
                console_print(f"         {style(msg, fg='yellow')}")


# Add trace commands to the main verify app
def register_trace_commands(app):
    """Register trace commands with the main app."""
    app.add_command(trace)
