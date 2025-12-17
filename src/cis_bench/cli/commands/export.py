"""Export command for CIS Benchmark CLI."""

import json
import logging
import os
import sys

import click
from rich.console import Console

from cis_bench.config import Config
from cis_bench.exporters import ExporterFactory
from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter
from cis_bench.models.benchmark import Benchmark

console = Console()
logger = logging.getLogger(__name__)


def get_available_xccdf_styles():
    """Get available XCCDF styles for CLI validation."""
    return XCCDFExporter._get_available_styles()


class DynamicStyleChoice(click.Choice):
    """Dynamic choice that loads available styles at runtime."""

    def __init__(self):
        # Load choices dynamically
        super().__init__(get_available_xccdf_styles())


@click.command(name="export")
@click.argument("identifier")
@click.option(
    "--format",
    "-f",
    "export_format",
    type=click.Choice(["yaml", "csv", "markdown", "md", "xccdf", "xml"]),
    default="yaml",
    help="Export format",
)
@click.option(
    "--style",
    type=DynamicStyleChoice(),
    default="disa",
    help="XCCDF export style (only used with --format xccdf)",
)
@click.option(
    "--output", "-o", "output_file", help="Output file (default: input filename with new extension)"
)
@click.option(
    "--input-dir", default="./benchmarks", help="Input directory where benchmark JSON is stored"
)
def export_cmd(identifier, export_format, style, output_file, input_dir):
    """Export benchmark to different formats.

    IDENTIFIER can be either:
    - Benchmark ID (e.g., 23598) - loads from catalog database
    - File path (e.g., benchmark.json) - loads from file

    \b
    Examples:
        cis-bench export 23598 --format xccdf --style cis
        cis-bench export benchmark.json --format yaml
        cis-bench export benchmark.json --format xccdf -o output.xml
        cis-bench export benchmark.json --format csv
    """
    logger.debug(
        f"Export command called: identifier={identifier}, format={export_format}, style={style}"
    )

    benchmark = None
    benchmark_id_for_filename = None

    # Check if identifier is a benchmark ID (numeric)
    if identifier.isdigit():
        logger.info(
            f"Identifier is numeric, attempting to load from catalog database: {identifier}"
        )

        # Try to load from catalog database
        catalog_db_path = Config.get_catalog_db_path()

        if not catalog_db_path.exists():
            logger.error("Catalog database not found")
            console.print(f"[red]Error: Catalog database not found at {catalog_db_path}[/red]")
            console.print(
                "[yellow]Hint: Run 'cis-bench catalog refresh' to build the catalog[/yellow]"
            )
            sys.exit(1)

        try:
            from cis_bench.catalog.database import CatalogDatabase

            db = CatalogDatabase(catalog_db_path)
            downloaded = db.get_downloaded(identifier)

            if not downloaded:
                logger.error(f"Benchmark {identifier} not found in database")
                console.print(f"[red]Error: Benchmark {identifier} not downloaded[/red]")
                console.print(
                    f"[yellow]Hint: Run 'cis-bench download {identifier}' to download it first[/yellow]"
                )
                sys.exit(1)

            # Load benchmark from JSON stored in database
            logger.info(f"Loading benchmark {identifier} from database")
            with console.status("[bold green]Loading benchmark from cache..."):
                benchmark_data = json.loads(downloaded["content_json"])
                benchmark = Benchmark(**benchmark_data)

            benchmark_id_for_filename = identifier
            logger.info(
                f"Loaded benchmark from DB: {benchmark.title} ({len(benchmark.recommendations)} recommendations)"
            )
            console.print(f"[green]✓[/green] Loaded from cache: {benchmark.title}")

        except Exception as e:
            logger.error(f"Failed to load benchmark from database: {e}", exc_info=True)
            console.print(f"[red]Error loading from database: {e}[/red]")
            sys.exit(1)

    else:
        # Treat as file path
        logger.info(f"Identifier is file path, attempting to load from file: {identifier}")

        # Find input file
        if os.path.exists(identifier):
            input_file = identifier
            logger.debug(f"Found input file at: {input_file}")
        else:
            input_file = os.path.join(input_dir, identifier)
            logger.debug(f"Searching for file in input_dir: {input_file}")

        if not os.path.exists(input_file):
            logger.error(f"Input file not found: {input_file}")
            console.print(f"[red]Error: File not found: {input_file}[/red]")
            sys.exit(1)

        # Load benchmark
        try:
            logger.info(f"Loading benchmark from {input_file}")
            with console.status("[bold green]Loading benchmark..."):
                benchmark = Benchmark.from_json_file(input_file)

            logger.info(
                f"Loaded benchmark: {benchmark.title} ({len(benchmark.recommendations)} recommendations)"
            )
            console.print(f"[green]✓[/green] Loaded: {benchmark.title}")

        except Exception as e:
            logger.error(f"Failed to load benchmark: {e}", exc_info=True)
            console.print(f"[red]Error loading benchmark: {e}[/red]")
            sys.exit(1)

    # Determine exporter and parameters
    exporter_format = export_format
    exporter_kwargs = {}

    # For XCCDF, pass style as parameter to exporter
    if export_format in ["xccdf", "xml"]:
        exporter_kwargs["style"] = style
        logger.debug(f"XCCDF export with style={style}")

    # Determine output filename
    if not output_file:
        # Use benchmark ID for filename if loaded from database, otherwise use input filename
        if benchmark_id_for_filename:
            base = f"benchmark_{benchmark_id_for_filename}"
        else:
            base = os.path.splitext(os.path.basename(identifier))[0]

        exporter = ExporterFactory.create(exporter_format, **exporter_kwargs)
        ext = exporter.get_file_extension()
        output_file = f"{base}.{ext}"
        logger.debug(f"Generated output filename: {output_file}")

    # Export
    try:
        logger.info(f"Starting export to {exporter_format} format")
        with console.status(f"[bold green]Exporting to {export_format}..."):
            exporter = ExporterFactory.create(exporter_format, **exporter_kwargs)
            exporter.export(benchmark, output_file)

        file_size = os.path.getsize(output_file) / 1024
        logger.info(f"Export successful: {output_file} ({file_size:.1f} KB)")

        console.print(
            f"[green]✓[/green] Exported {len(benchmark.recommendations)} recommendations to [bold]{output_file}[/bold]"
        )
        console.print(f"  Format: [cyan]{exporter.format_name()}[/cyan]")
        console.print(f"  Size: [yellow]{file_size:.1f} KB[/yellow]")

        # Special message for XCCDF
        if export_format in ["xccdf", "xml"]:
            console.print()
            console.print("[dim]Note: XCCDF output validates against NIST XCCDF 1.2 schema[/dim]")
            console.print("[dim]Compatible with OpenSCAP, SCC, and other SCAP tools[/dim]")

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        console.print(f"[red]✗ Export failed: {e}[/red]")
        import traceback

        traceback.print_exc()
        sys.exit(1)
