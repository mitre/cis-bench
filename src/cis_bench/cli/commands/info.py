"""Info command for CIS Benchmark CLI."""

import os
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cis_bench.cli.helpers.output import output_data
from cis_bench.models.benchmark import Benchmark

console = Console()


@click.command()
@click.argument("filename")
@click.option("--output-dir", default="./benchmarks", help="Directory containing benchmarks")
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "csv", "yaml"]),
    default="table",
    help="Output format (default: table)",
)
def info(filename, output_dir, output_format):
    """Show detailed information about a downloaded benchmark.

    \b
    Example:
        cis-bench info cis_almalinux_os_8_benchmark_v400.json
    """
    # Find file
    if os.path.exists(filename):
        filepath = filename
    else:
        filepath = os.path.join(output_dir, filename)

    if not os.path.exists(filepath):
        console.print(f"[red]Error: File not found: {filepath}[/red]")
        sys.exit(1)

    try:
        # Load benchmark
        benchmark = Benchmark.from_json_file(filepath)

        # Count compliance mappings
        cis_v8 = sum(1 for r in benchmark.recommendations for c in r.cis_controls if c.version == 8)
        cis_v7 = sum(1 for r in benchmark.recommendations for c in r.cis_controls if c.version == 7)
        mitre_count = sum(1 for r in benchmark.recommendations if r.mitre_mapping)
        nist_count = sum(1 for r in benchmark.recommendations if r.nist_controls)
        artifacts = sum(len(r.artifacts) for r in benchmark.recommendations)

        # Create structured data
        info_data = {
            "title": benchmark.title,
            "version": benchmark.version,
            "benchmark_id": benchmark.benchmark_id,
            "url": benchmark.url,
            "downloaded_at": benchmark.downloaded_at.isoformat(),
            "scraper_version": benchmark.scraper_version,
            "total_recommendations": benchmark.total_recommendations,
            "cis_controls_v8": cis_v8,
            "cis_controls_v7": cis_v7,
            "mitre_mappings": mitre_count,
            "nist_controls": nist_count,
            "total_artifacts": artifacts,
            "file": filepath,
        }

        # Output in requested format (non-table)
        if output_format != "table":
            output_data(info_data, output_format)

        # Display summary (table format)
        console.print()
        console.print(
            Panel.fit(
                f"[bold]{benchmark.title}[/bold]\n"
                f"Version: {benchmark.version}\n"
                f"Benchmark ID: {benchmark.benchmark_id}\n"
                f"Downloaded: {benchmark.downloaded_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Scraper Version: {benchmark.scraper_version}",
                title="Benchmark Information",
                border_style="cyan",
            )
        )

        # Statistics table
        table = Table(title="Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="yellow")

        table.add_row("Total Recommendations", str(benchmark.total_recommendations))

        # Count compliance mappings
        cis_v8 = sum(1 for r in benchmark.recommendations for c in r.cis_controls if c.version == 8)
        cis_v7 = sum(1 for r in benchmark.recommendations for c in r.cis_controls if c.version == 7)
        mitre_count = sum(1 for r in benchmark.recommendations if r.mitre_mapping)
        nist_count = sum(1 for r in benchmark.recommendations if r.nist_controls)
        artifacts = sum(len(r.artifacts) for r in benchmark.recommendations)

        table.add_row("CIS Controls v8", str(cis_v8))
        table.add_row("CIS Controls v7", str(cis_v7))
        table.add_row("MITRE Mappings", str(mitre_count))
        table.add_row("Recommendations with NIST Controls", str(nist_count))
        table.add_row("Total Artifacts", str(artifacts))

        console.print(table)
        console.print()

        # Sample recommendations
        console.print("[bold]Sample Recommendations:[/bold]\n")
        for rec in benchmark.recommendations[:5]:
            profiles = f" [{', '.join(rec.profiles)}]" if rec.profiles else ""
            console.print(f"  [cyan]{rec.ref}[/cyan]{profiles}")
            console.print(f"    {rec.title}")

        if benchmark.total_recommendations > 5:
            console.print(f"\n  ... and {benchmark.total_recommendations - 5} more")

        console.print()

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback

        traceback.print_exc()
        sys.exit(1)
