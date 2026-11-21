"""Output formatting helpers for CLI commands.

Provides consistent output formatting for human-friendly and JSON/CSV/YAML outputs.
"""

import csv
import json
import sys
from datetime import datetime
from gettext import ngettext
from io import StringIO
from typing import Any

import yaml
from rich.console import Console
from rich.markup import escape
from rich.table import Table

console = Console()


def display_time(value: datetime) -> str:
    """A time as a table shows it: in the viewer's zone, named.

    Structured output carries the ISO 8601 form with its offset (``isoformat``); a table
    converts to the local zone of the process (the system's, or ``TZ``). A time that
    carries no zone, such as one written by an earlier version, is shown as it is and
    marked, never guessed into a zone.
    """
    if value.tzinfo is None:
        return f"{value:%Y-%m-%d %H:%M:%S} (zone not recorded)"
    return f"{value.astimezone():%Y-%m-%d %H:%M:%S %Z}"


def output_json(data: Any, exit_code: int = 0) -> None:
    """Output data as JSON to stdout and end the command with exit_code.

    Args:
        data: Data to serialize as JSON (dict, list, etc.)
        exit_code: The command's exit code (1 when the data reports a failure)

    Note:
        Uses default=str to handle dates and other non-JSON types
    """
    print(json.dumps(data, indent=2, default=str))
    sys.exit(exit_code)


def output_csv(data: list[dict], fields: list[str] | None = None, exit_code: int = 0) -> None:
    """Output data as CSV to stdout and end the command with exit_code.

    Args:
        data: List of dictionaries
        fields: Optional field names (defaults to keys from first row)
        exit_code: The command's exit code (1 when the data reports a failure)
    """
    if not data:
        sys.exit(exit_code)

    # Auto-detect fields from first row if not provided
    if fields is None:
        fields = list(data[0].keys())

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data)

    print(output.getvalue())
    sys.exit(exit_code)


def output_yaml(data: Any, exit_code: int = 0) -> None:
    """Output data as YAML to stdout and end the command with exit_code.

    Args:
        data: Data to serialize as YAML
        exit_code: The command's exit code (1 when the data reports a failure)
    """
    print(yaml.dump(data, default_flow_style=False, sort_keys=False))
    sys.exit(exit_code)


def output_data(
    data: Any,
    format: str = "table",
    human_formatter_func=None,
    csv_fields: list[str] | None = None,
    exit_code: int = 0,
) -> None:
    """Output data in specified format.

    Args:
        data: Data to output
        format: Output format (table, json, csv, yaml)
        human_formatter_func: Function to display table (gets console and data)
        csv_fields: Optional CSV field order
        exit_code: Exit code a json, csv or yaml output ends the command with (1 when
            the data reports a failure, as the table output's exit code would)

    Example:
        def show_table(console, data):
            # ... build and show Rich table
            pass

        output_data(results, format, show_table)
    """
    if format == "json":
        output_json(data, exit_code)
    elif format == "csv":
        output_csv(data, csv_fields, exit_code)
    elif format == "yaml":
        output_yaml(data, exit_code)
    elif format == "table" and human_formatter_func:
        human_formatter_func(console, data)
    else:
        # Fallback
        console.print(data)


def benchmark_table(results: list[dict], *, title_width: int) -> Table:
    """Build the ID / Title / Version / Status table that search and get print.

    ID, Version and Status never wrap, so when the terminal is too narrow the
    title wraps first and gives up the width. The title grows no wider than
    title_width (the CLI passes CIS_BENCH_TABLE_TITLE_WIDTH), and a word wider than
    the column folds onto the next line instead of being cut.
    Every cell comes from the catalog and is escaped so Rich prints it as written.
    """
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="yellow", no_wrap=True)
    table.add_column("Title", style="white", overflow="fold", max_width=title_width)
    table.add_column("Version", style="cyan", no_wrap=True)
    table.add_column("Status", style="green", no_wrap=True)

    for result in results:
        table.add_row(
            escape(str(result["benchmark_id"])),
            escape(str(result["title"])),
            escape(str(result.get("version", "N/A"))),
            escape(str(result.get("status", "N/A"))),
        )
    return table


def showing_line(shown: int, total: int) -> str:
    """'Showing N of TOTAL results', with a hint when the limit cut the list short."""
    line = ngettext(
        "Showing {shown} of {total} result", "Showing {shown} of {total} results", total
    ).format(shown=shown, total=total)
    return f"{line}; use --limit to see more" if shown < total else line


def output_results(results: list[dict], output_json_flag: bool, human_formatter_func=None) -> None:
    """Output results in JSON or human-friendly format.

    Args:
        results: List of result dictionaries
        output_json_flag: If True, output as JSON
        human_formatter_func: Function to display results for humans (gets console and results)

    Example:
        def show_table(console, results):
            table = Table()
            # ... build table
            console.print(table)

        output_results(results, output_json, show_table)
    """
    if output_json_flag:
        output_json(results)
    elif human_formatter_func:
        human_formatter_func(console, results)
    else:
        # Default: just print the data
        console.print(results)


def add_json_option(func):
    """Decorator to add --json option to Click commands.

    Usage:
        @click.command()
        @add_json_option
        def my_command(..., output_json):
            results = get_data()
            output_results(results, output_json, display_table)
    """
    import click

    return click.option(
        "--json", "output_json", is_flag=True, help="Output as JSON (for scripting)"
    )(func)
