"""Info command for CIS Benchmark CLI."""

import logging
import os
import sys
from contextlib import closing

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from cis_bench.catalog.database import CatalogDatabase, deserialize_benchmark_json
from cis_bench.cli.helpers.output import display_time, output_data
from cis_bench.cli.helpers.services import settings_from
from cis_bench.models.benchmark import Benchmark
from cis_bench.utils.workbench_urls import is_benchmark_id

console = Console()
logger = logging.getLogger(__name__)


@click.command()
@click.argument("benchmark")
@click.option(
    "--output-dir",
    help="Folder a file name is looked for in (default: <data dir>/benchmarks)",
)
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "csv", "yaml"]),
    default="table",
    help="Output format (default: table)",
)
def info(benchmark, output_dir, output_format):
    """Show detailed information about a downloaded benchmark.

    BENCHMARK is a catalog ID (the downloaded copy in the cache) or the path or name of
    an exported JSON file.

    \b
    Example:
        cis-bench info 23598
        cis-bench info cis_almalinux_os_8_benchmark_v400.json
    """
    settings = settings_from()
    if output_dir is None:
        output_dir = settings.benchmarks_dir

    if is_benchmark_id(benchmark):
        filepath = None
    else:
        # A path as given, or a file name in the exports folder
        filepath = benchmark if os.path.exists(benchmark) else os.path.join(output_dir, benchmark)
        if not os.path.exists(filepath):
            console.print(f"[red]Error: File not found: {escape(str(filepath))}[/red]")
            sys.exit(1)

    try:
        if filepath is None:
            benchmark = _cached_benchmark(settings.catalog_db_path, benchmark.strip())
        else:
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
            "source": "file" if filepath else "cache",
            "file": filepath,
        }

        # Output in requested format (non-table)
        if output_format != "table":
            output_data(info_data, output_format)

        # Display summary (table format)
        console.print()
        console.print(
            Panel.fit(
                f"[bold]{escape(benchmark.title)}[/bold]\n"
                f"Version: {escape(benchmark.version)}\n"
                f"Benchmark ID: {escape(benchmark.benchmark_id)}\n"
                f"Downloaded: {display_time(benchmark.downloaded_at)}\n"
                f"Scraper Version: {escape(benchmark.scraper_version)}\n"
                f"Source: {'file ' + escape(str(filepath)) if filepath else 'cache'}",
                title="Benchmark Information",
                border_style="cyan",
            )
        )

        # Statistics table
        table = Table(title="Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="yellow")

        table.add_row("Total Recommendations", str(benchmark.total_recommendations))
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
            profiles = " " + escape(f"[{', '.join(rec.profiles)}]") if rec.profiles else ""
            console.print(f"  [cyan]{escape(rec.ref)}[/cyan]{profiles}")
            console.print(f"    {escape(rec.title)}")

        if benchmark.total_recommendations > 5:
            console.print(f"\n  ... and {benchmark.total_recommendations - 5} more")

        console.print()

    except Exception as e:
        logger.debug("Could not show benchmark info", exc_info=True)
        console.print(f"[red]Error: {escape(str(e))}[/red]")
        sys.exit(1)


def _cached_benchmark(catalog_db_path, benchmark_id: str) -> Benchmark:
    """The downloaded copy of a benchmark from the cache; exit 1 when it is not downloaded."""
    downloaded = None
    if catalog_db_path.exists():
        with closing(CatalogDatabase(catalog_db_path)) as db:
            downloaded = db.get_downloaded(benchmark_id)
    if downloaded is None:
        console.print(f"[yellow]Benchmark {escape(benchmark_id)} is not downloaded[/yellow]")
        console.print("[dim]Download it first:[/dim]")
        console.print(f"  cis-bench download {escape(benchmark_id)}")
        sys.exit(1)
    return deserialize_benchmark_json(downloaded["content_json"])
