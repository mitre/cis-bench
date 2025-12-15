"""Output formatting helpers for CLI commands.

Provides consistent output formatting for human-friendly and JSON/CSV/YAML outputs.
"""

import csv
import json
import sys
from io import StringIO
from typing import Any

import yaml
from rich.console import Console

console = Console()


def output_json(data: Any) -> None:
    """Output data as JSON to stdout.

    Args:
        data: Data to serialize as JSON (dict, list, etc.)

    Note:
        Uses default=str to handle dates and other non-JSON types
    """
    print(json.dumps(data, indent=2, default=str))
    sys.exit(0)


def output_csv(data: list[dict], fields: list[str] = None) -> None:
    """Output data as CSV to stdout.

    Args:
        data: List of dictionaries
        fields: Optional field names (defaults to keys from first row)
    """
    if not data:
        sys.exit(0)

    # Auto-detect fields from first row if not provided
    if fields is None:
        fields = list(data[0].keys())

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data)

    print(output.getvalue())
    sys.exit(0)


def output_yaml(data: Any) -> None:
    """Output data as YAML to stdout.

    Args:
        data: Data to serialize as YAML
    """
    print(yaml.dump(data, default_flow_style=False, sort_keys=False))
    sys.exit(0)


def output_data(
    data: Any, format: str = "table", human_formatter_func=None, csv_fields: list[str] = None
) -> None:
    """Output data in specified format.

    Args:
        data: Data to output
        format: Output format (table, json, csv, yaml)
        human_formatter_func: Function to display table (gets console and data)
        csv_fields: Optional CSV field order

    Example:
        def show_table(console, data):
            # ... build and show Rich table
            pass

        output_data(results, format, show_table)
    """
    if format == "json":
        output_json(data)
    elif format == "csv":
        output_csv(data, csv_fields)
    elif format == "yaml":
        output_yaml(data)
    elif format == "table" and human_formatter_func:
        human_formatter_func(console, data)
    else:
        # Fallback
        console.print(data)


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
