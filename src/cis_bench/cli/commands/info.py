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
@click.argument("filenames", nargs=-1, required=True)
@click.option("--output-dir", default="./benchmarks", help="Directory containing benchmarks")
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "csv", "yaml"]),
    default="table",
    help="Output format (default: table)",
)
def info(filenames, output_dir, output_format):
    """Show detailed information about downloaded benchmark(s).

    \b
    Examples:
        cis-bench info benchmark.json
        cis-bench info benchmark1.json benchmark2.json
        cis-bench info benchmarks/*.json
    """
    had_errors = False

    # Process each filename
    for filename in filenames:
        # Find file
        if os.path.exists(filename):
            filepath = filename
        else:
            filepath = os.path.join(output_dir, filename)

        if not os.path.exists(filepath):
            console.print(f"[red]Error: File not found: {filepath}[/red]")
            had_errors = True
            continue

        try:
            # Load benchmark
            benchmark = Benchmark.from_json_file(filepath)

            # Count compliance mappings
            cis_v8 = sum(
                1 for r in benchmark.recommendations for c in r.cis_controls if c.version == 8
            )
            cis_v7 = sum(
                1 for r in benchmark.recommendations for c in r.cis_controls if c.version == 7
            )
            mitre_count = sum(1 for r in benchmark.recommendations if r.mitre_mapping)
            nist_count = sum(1 for r in benchmark.recommendations if r.nist_controls)
            artifacts = sum(len(r.artifacts) for r in benchmark.recommendations)

            # Create structured data (includes all extended metadata)
            info_data = {
                "title": benchmark.title,
                "version": benchmark.version,
                "benchmark_id": benchmark.benchmark_id,
                "url": benchmark.url,
                # Extended metadata
                "published_date": benchmark.published_date,
                "release_type": benchmark.release_type,
                "contributors": ", ".join(benchmark.contributors)
                if benchmark.contributors
                else None,
                "parent_benchmark_title": benchmark.parent_benchmark_title,
                "parent_benchmark_url": str(benchmark.parent_benchmark_url)
                if benchmark.parent_benchmark_url
                else None,
                "cpe_ids": ", ".join([a.cpe_id for a in benchmark.assets])
                if benchmark.assets
                else None,
                "milestone": benchmark.milestone_name,
                # System metadata
                "downloaded_at": benchmark.downloaded_at.isoformat(),
                "scraper_version": benchmark.scraper_version,
                "total_recommendations": benchmark.total_recommendations,
                # Compliance mappings
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
                continue  # Skip table display for non-table formats

            # Display summary (table format) - include extended metadata
            console.print()

            # Build panel content dynamically
            panel_lines = [
                f"[bold]{benchmark.title}[/bold]",
                f"Version: {benchmark.version}",
                f"Benchmark ID: {benchmark.benchmark_id}",
            ]

            if benchmark.published_date:
                panel_lines.append(f"Published: {benchmark.published_date}")
            if benchmark.release_type:
                panel_lines.append(f"Release Type: {benchmark.release_type}")
            if benchmark.parent_benchmark_title:
                panel_lines.append(f"Forked From: {benchmark.parent_benchmark_title}")
            if benchmark.assets:
                cpe_summary = f"{len(benchmark.assets)} CPE ID(s)"
                panel_lines.append(f"Assets: {cpe_summary}")
            if benchmark.contributors:
                contrib_summary = f"{len(benchmark.contributors)} contributor(s)"
                panel_lines.append(f"Contributors: {contrib_summary}")

            panel_lines.append(
                f"Downloaded: {benchmark.downloaded_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            panel_lines.append(f"Scraper Version: {benchmark.scraper_version}")

            console.print(
                Panel.fit(
                    "\n".join(panel_lines),
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
                profiles = f" [{', '.join(rec.profiles)}]" if rec.profiles else ""
                console.print(f"  [cyan]{rec.ref}[/cyan]{profiles}")
                console.print(f"    {rec.title}")

            if benchmark.total_recommendations > 5:
                console.print(f"\n  ... and {benchmark.total_recommendations - 5} more")

            console.print()

            # Separator if multiple files
            if len(filenames) > 1:
                console.print("\n" + "=" * 80 + "\n")

        except Exception as e:
            console.print(f"[red]Error processing {filepath}: {e}[/red]")
            if output_format == "table":
                import traceback

                traceback.print_exc()
            had_errors = True
            continue

    # Exit with error code if any file failed
    if had_errors:
        sys.exit(1)
