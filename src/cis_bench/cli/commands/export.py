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


def _load_benchmark_from_db(identifier, catalog_db_path):
    """Load a benchmark from the catalog database by ID.

    Args:
        identifier: Benchmark ID (numeric string)
        catalog_db_path: Path to catalog database

    Returns:
        tuple: (Benchmark, benchmark_id) or (None, error_message)
    """
    from cis_bench.catalog.database import CatalogDatabase

    db = CatalogDatabase(catalog_db_path)
    downloaded = db.get_downloaded(identifier)

    if not downloaded:
        return None, f"Benchmark {identifier} not downloaded"

    benchmark_data = json.loads(downloaded["content_json"])
    benchmark = Benchmark(**benchmark_data)
    return benchmark, identifier


def _load_benchmark_from_file(identifier, input_dir):
    """Load a benchmark from a JSON file.

    Args:
        identifier: File path
        input_dir: Directory to search for file

    Returns:
        tuple: (Benchmark, None) or (None, error_message)
    """
    # Find input file
    if os.path.exists(identifier):
        input_file = identifier
    else:
        input_file = os.path.join(input_dir, identifier)

    if not os.path.exists(input_file):
        return None, f"File not found: {input_file}"

    benchmark = Benchmark.from_json_file(input_file)
    return benchmark, None


def _export_single_benchmark(
    identifier,
    export_format,
    style,
    output_file,
    output_dir,
    input_dir,
    prefix="",
):
    """Export a single benchmark.

    Args:
        identifier: Benchmark ID or file path
        export_format: Export format (yaml, csv, xccdf, etc.)
        style: XCCDF style (disa, cis)
        output_file: Explicit output file path (for single exports)
        output_dir: Output directory (for batch exports)
        input_dir: Input directory for file paths
        prefix: Progress prefix (e.g., "[1/3]")

    Returns:
        tuple: (success: bool, output_path: str or None)
    """
    benchmark = None
    benchmark_id_for_filename = None

    # Check if identifier is a benchmark ID (numeric)
    if identifier.isdigit():
        logger.info(f"Loading benchmark {identifier} from database")

        catalog_db_path = Config.get_catalog_db_path()

        if not catalog_db_path.exists():
            console.print(f"{prefix} [red]Error: Catalog database not found[/red]")
            console.print(
                "[yellow]Hint: Run 'cis-bench catalog refresh' to build the catalog[/yellow]"
            )
            return False, None

        try:
            benchmark, result = _load_benchmark_from_db(identifier, catalog_db_path)
            if benchmark is None:
                console.print(f"{prefix} [red]Error: {result}[/red]")
                console.print(
                    f"[yellow]Hint: Run 'cis-bench download {identifier}' to download it first[/yellow]"
                )
                return False, None

            benchmark_id_for_filename = result
            console.print(f"{prefix} [green]✓[/green] Loaded from cache: {benchmark.title}")

        except Exception as e:
            logger.error(f"Failed to load benchmark from database: {e}", exc_info=True)
            console.print(f"{prefix} [red]Error loading from database: {e}[/red]")
            return False, None

    else:
        # Treat as file path
        logger.info(f"Loading benchmark from file: {identifier}")

        try:
            benchmark, error = _load_benchmark_from_file(identifier, input_dir)
            if benchmark is None:
                console.print(f"{prefix} [red]Error: {error}[/red]")
                return False, None

            console.print(f"{prefix} [green]✓[/green] Loaded: {benchmark.title}")

        except Exception as e:
            logger.error(f"Failed to load benchmark: {e}", exc_info=True)
            console.print(f"{prefix} [red]Error loading benchmark: {e}[/red]")
            return False, None

    # Determine exporter parameters
    exporter_kwargs = {}
    if export_format in ["xccdf", "xml"]:
        exporter_kwargs["style"] = style

    # Determine output filename
    actual_output_file = output_file
    if not actual_output_file:
        # Generate filename
        if benchmark_id_for_filename:
            base = f"benchmark_{benchmark_id_for_filename}"
        else:
            base = os.path.splitext(os.path.basename(identifier))[0]

        exporter = ExporterFactory.create(export_format, **exporter_kwargs)
        ext = exporter.get_file_extension()

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            actual_output_file = os.path.join(output_dir, f"{base}.{ext}")
        else:
            actual_output_file = f"{base}.{ext}"

    # Export
    try:
        exporter = ExporterFactory.create(export_format, **exporter_kwargs)
        exporter.export(benchmark, actual_output_file)

        file_size = os.path.getsize(actual_output_file) / 1024
        logger.info(f"Export successful: {actual_output_file} ({file_size:.1f} KB)")

        console.print(
            f"{prefix} [green]✓[/green] Exported {len(benchmark.recommendations)} "
            f"recommendations to [bold]{actual_output_file}[/bold]"
        )
        console.print(f"      Format: [cyan]{exporter.format_name()}[/cyan]")
        console.print(f"      Size: [yellow]{file_size:.1f} KB[/yellow]")

        return True, actual_output_file

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        console.print(f"{prefix} [red]✗ Export failed: {e}[/red]")
        return False, None


@click.command(name="export")
@click.argument("identifiers", nargs=-1, required=True)
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
    "--output",
    "-o",
    "output_file",
    help="Output file (only valid for single benchmark export)",
)
@click.option(
    "--output-dir",
    "output_dir",
    help="Output directory for exported files (creates if not exists)",
)
@click.option(
    "--input-dir",
    default="./benchmarks",
    help="Input directory where benchmark JSON files are stored",
)
def export_cmd(identifiers, export_format, style, output_file, output_dir, input_dir):
    """Export benchmarks to different formats.

    IDENTIFIERS can be one or more of:
    - Benchmark IDs (e.g., 23598) - loads from catalog database
    - File paths (e.g., benchmark.json) - loads from file

    \b
    Examples:
        # Single benchmark export
        cis-bench export 23598 --format xccdf --style cis
        cis-bench export benchmark.json --format yaml

        # Batch export multiple benchmarks
        cis-bench export 23598 22605 18208 --format yaml
        cis-bench export 23598 22605 --format xccdf --style disa

        # Export to specific directory
        cis-bench export 23598 22605 --format xccdf --output-dir ./stig_exports
    """
    logger.debug(
        f"Export command called: identifiers={identifiers}, format={export_format}, style={style}"
    )

    # Validate: --output only valid for single identifier
    if output_file and len(identifiers) > 1:
        console.print("[red]Error: --output cannot be used with multiple identifiers[/red]")
        console.print("[yellow]Hint: Use --output-dir for batch exports[/yellow]")
        sys.exit(1)

    total = len(identifiers)
    success_count = 0
    failed_count = 0
    exported_files = []

    # Process each identifier
    for idx, identifier in enumerate(identifiers, 1):
        prefix = f"[{idx}/{total}]" if total > 1 else ""

        success, output_path = _export_single_benchmark(
            identifier=identifier,
            export_format=export_format,
            style=style,
            output_file=output_file if total == 1 else None,
            output_dir=output_dir,
            input_dir=input_dir,
            prefix=prefix,
        )

        if success:
            success_count += 1
            if output_path:
                exported_files.append(output_path)
        else:
            failed_count += 1

        # Add spacing between benchmarks in batch mode
        if total > 1 and idx < total:
            console.print()

    # Show summary for batch exports
    if total > 1:
        console.print()
        if failed_count == 0:
            console.print(
                f"[bold green]Export complete![/bold green] {success_count} benchmarks exported."
            )
        else:
            console.print(
                f"[bold yellow]Export complete with errors.[/bold yellow] "
                f"{success_count} succeeded, {failed_count} failed."
            )

    # Show XCCDF note for single successful export
    if total == 1 and success_count == 1 and export_format in ["xccdf", "xml"]:
        console.print()
        console.print("[dim]Note: XCCDF output validates against NIST XCCDF 1.2 schema[/dim]")
        console.print("[dim]Compatible with OpenSCAP, SCC, and other SCAP tools[/dim]")

    # Exit with error if all failed
    if success_count == 0:
        sys.exit(1)
