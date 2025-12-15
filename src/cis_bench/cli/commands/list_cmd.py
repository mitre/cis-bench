"""List command for CIS Benchmark CLI."""

import os

import click
from rich.console import Console
from rich.table import Table

from cis_bench.cli.helpers.output import output_data
from cis_bench.models.benchmark import Benchmark

console = Console()


@click.command(name="list")
@click.option(
    "--output-dir", default="./benchmarks", help="Directory containing downloaded benchmarks"
)
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "csv", "yaml"]),
    default="table",
    help="Output format (default: table)",
)
def list_benchmarks(output_dir, output_format):
    """List downloaded benchmarks with details.

    \b
    Example:
        cis-bench list
        cis-bench list --output-dir ./my_benchmarks
    """
    if not os.path.exists(output_dir):
        if output_format == "table":
            console.print(f"[yellow]Directory not found: {output_dir}[/yellow]")
        else:
            output_data([], output_format)
        return

    json_files = [f for f in os.listdir(output_dir) if f.endswith(".json")]

    if not json_files:
        if output_format == "table":
            console.print(f"[yellow]No benchmarks found in {output_dir}[/yellow]")
        else:
            output_data([], output_format)
        return

    # Collect benchmark data
    benchmarks_data = []

    for filename in sorted(json_files):
        filepath = os.path.join(output_dir, filename)

        try:
            benchmark = Benchmark.from_json_file(filepath)

            cis_v8 = sum(
                1 for r in benchmark.recommendations for c in r.cis_controls if c.version == 8
            )
            mitre_count = sum(1 for r in benchmark.recommendations if r.mitre_mapping)
            nist_count = sum(len(r.nist_controls) for r in benchmark.recommendations)

            benchmarks_data.append(
                {
                    "title": benchmark.title,
                    "version": benchmark.version,
                    "recommendations": benchmark.total_recommendations,
                    "cis_v8": cis_v8,
                    "mitre": mitre_count,
                    "nist": nist_count,
                    "file": filename,
                }
            )
        except Exception:
            benchmarks_data.append({"file": filename, "error": "Failed to load"})

    # Output in requested format
    if output_format != "table":
        csv_fields = ["title", "version", "recommendations", "cis_v8", "mitre", "nist", "file"]
        output_data(benchmarks_data, output_format, csv_fields=csv_fields)

    # Create table for human display
    def show_table(console, data):
        table = Table(title=f"Downloaded Benchmarks ({len(data)} total)")
        table.add_column("Title", style="cyan", no_wrap=False)
        table.add_column("Version", style="green")
        table.add_column("Recs", justify="right", style="yellow")
        table.add_column("CIS v8", justify="right")
        table.add_column("MITRE", justify="right")
        table.add_column("NIST", justify="right")

        for item in data:
            if "error" in item:
                table.add_row(item["file"], "?", "?", "?", "?", "[red]Error[/red]")
            else:
                table.add_row(
                    item["title"],
                    item["version"],
                    str(item["recommendations"]),
                    str(item["cis_v8"]) if item["cis_v8"] > 0 else "-",
                    str(item["mitre"]) if item["mitre"] > 0 else "-",
                    str(item["nist"]) if item["nist"] > 0 else "-",
                )

        console.print(table)

    # Output in requested format
    csv_fields = ["title", "version", "recommendations", "cis_v8", "mitre", "nist", "file"]
    output_data(benchmarks_data, output_format, show_table, csv_fields)
