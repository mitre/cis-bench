"""Download command for CIS Benchmark CLI."""

import logging
import os
import re
import sys

import click
from rich.console import Console

from cis_bench.config import Config
from cis_bench.exporters import ExporterFactory
from cis_bench.fetcher.auth import AuthManager
from cis_bench.fetcher.workbench import WorkbenchScraper

console = Console()
logger = logging.getLogger(__name__)


@click.command(name="download")
@click.argument("benchmark_ids", nargs=-1, required=False)
@click.option(
    "--file",
    "-f",
    "urls_file",
    type=click.Path(exists=True),
    help="File containing benchmark URLs or IDs (one per line)",
)
@click.option(
    "--output-dir", "-o", default="./benchmarks", help="Output directory for downloaded benchmarks"
)
@click.option(
    "--format",
    "-fmt",
    "export_formats",
    multiple=True,
    type=click.Choice(["json", "yaml", "csv", "markdown", "xccdf"]),
    default=["json"],
    help="Export formats (can specify multiple)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose (DEBUG level) logging")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging (same as --verbose)")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode (warnings and errors only)")
@click.option("--force", is_flag=True, help="Force re-download even if already cached in database")
def download(
    benchmark_ids,
    urls_file,
    output_dir,
    export_formats,
    verbose,
    debug,
    quiet,
    force,
):
    """Download CIS benchmarks by ID or URL.

    Uses saved session from 'cis-bench auth login'.

    \b
    Examples:
        # First, authenticate (one time)
        cis-bench auth login --browser chrome

        # Then download
        cis-bench download 23598
        cis-bench download 23598 22605 --format json --format xccdf
        cis-bench download --file urls.txt
    """
    # Configure logging if flags provided (overrides global)
    if verbose or debug or quiet:
        from cis_bench.utils.logging_config import LoggingConfig

        LoggingConfig.setup_from_flags(quiet=quiet, verbose=(verbose or debug))

    logger.debug(f"Starting download command: output_dir={output_dir}, formats={export_formats}")

    # Get authenticated session (uses saved session only)
    try:
        logger.debug("Getting authenticated session")
        with console.status("[bold green]Authenticating..."):
            session = AuthManager.get_or_create_session()

        console.print("[green]✓[/green] Authenticated successfully\n")
        logger.debug("Authentication successful")

    except ValueError:
        # No saved session
        console.print("\n[bold red]Authentication Required[/bold red]\n")
        console.print("[bold cyan]Please log in first:[/bold cyan]")
        console.print("  cis-bench auth login --browser chrome")
        console.print("\n[dim]This saves your session for future commands.[/dim]")
        console.print(
            "\n[dim]Windows users: If Chrome fails, try Firefox or --cookies option.[/dim]"
        )
        sys.exit(1)
    except Exception as e:
        logger.error(f"Authentication failed: {e}", exc_info=True)
        console.print("\n[bold red]Authentication Failed[/bold red]\n")
        console.print(f"[yellow]Error: {e}[/yellow]\n")
        console.print("[bold cyan]Your session may have expired. To refresh:[/bold cyan]")
        console.print("  cis-bench auth login --browser chrome")
        sys.exit(1)

    # Create scraper
    scraper = WorkbenchScraper(session)

    # Collect URLs to download
    urls = []

    if urls_file:
        # Read from file
        with open(urls_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if line.startswith("http"):
                        urls.append(line)
                    else:
                        urls.append(f"https://workbench.cisecurity.org/benchmarks/{line}")

    elif benchmark_ids:
        # Convert IDs or URLs to full URLs
        for item in benchmark_ids:
            if item.startswith("http"):
                urls.append(item)
            else:
                urls.append(f"https://workbench.cisecurity.org/benchmarks/{item}")
    else:
        console.print("[red]Error: Must specify benchmark IDs or --file[/red]")
        sys.exit(1)

    if not urls:
        console.print("[red]Error: No benchmarks to download[/red]")
        sys.exit(1)

    # Download benchmarks
    logger.debug(f"Starting download of {len(urls)} benchmark(s)")
    console.print(f"[bold]Downloading {len(urls)} benchmark(s)...[/bold]\n")

    for idx, url in enumerate(urls, 1):
        prefix = f"[{idx}/{len(urls)}]"
        logger.debug(f"Processing benchmark {idx}/{len(urls)}: {url}")

        # Extract benchmark ID from URL
        benchmark_id = url.split("/")[-1]

        # Check if already cached (unless --force)
        if not force:
            catalog_db_path = Config.get_catalog_db_path()
            if catalog_db_path.exists():
                try:
                    from cis_bench.catalog.database import CatalogDatabase

                    db = CatalogDatabase(catalog_db_path)
                    existing = db.get_downloaded(benchmark_id)

                    if existing:
                        console.print(
                            f"{prefix} [yellow]Benchmark {benchmark_id} already cached[/yellow]"
                        )
                        console.print(f"      Downloaded: {existing['downloaded_at']}")
                        console.print(f"      Recommendations: {existing['recommendation_count']}")
                        console.print("\n[dim]Use --force to re-download[/dim]\n")
                        logger.debug(f"Skipping {benchmark_id} - already cached")
                        continue

                except Exception as e:
                    logger.debug(f"Cache check failed: {e}, will download anyway")

        try:
            # Download with progress bar (using helper)
            from cis_bench.cli.helpers.download_helper import download_with_progress

            console.print(f"{prefix} [cyan]Starting download...[/cyan]")

            benchmark = download_with_progress(scraper, url, prefix=prefix)

            logger.debug(f"Successfully downloaded benchmark: {benchmark.title}")
            console.print(f"{prefix} [green]✓[/green] Downloaded: [bold]{benchmark.title}[/bold]")
            console.print(f"      Recommendations: {benchmark.total_recommendations}")
            console.print(
                f"      CIS Controls: {sum(len(r.cis_controls) for r in benchmark.recommendations)}"
            )
            console.print(
                f"      MITRE Mappings: {sum(1 for r in benchmark.recommendations if r.mitre_mapping)}"
            )
            console.print(
                f"      NIST Controls: {sum(len(r.nist_controls) for r in benchmark.recommendations)}"
            )

            # Save to catalog database if it exists
            catalog_db_path = Config.get_catalog_db_path()
            if catalog_db_path.exists():
                try:
                    import hashlib

                    from cis_bench.catalog.database import CatalogDatabase

                    # Prepare data for database
                    content_json = benchmark.model_dump_json()
                    content_hash = hashlib.sha256(content_json.encode()).hexdigest()
                    recommendation_count = len(benchmark.recommendations)

                    db = CatalogDatabase(catalog_db_path)
                    db.save_downloaded(
                        benchmark_id=benchmark_id,
                        content_json=content_json,
                        content_hash=content_hash,
                        recommendation_count=recommendation_count,
                    )
                    logger.debug(f"Saved benchmark {benchmark_id} to catalog database")
                    console.print(f"      [green]✓[/green] Cached in database (ID: {benchmark_id})")
                except Exception as e:
                    logger.warning(f"Failed to save to catalog database: {e}", exc_info=True)
                    console.print(f"      [yellow]⚠[/yellow] Could not cache in database: {e}")

            # Export to requested formats
            for fmt in export_formats:
                try:
                    logger.debug(f"Exporting to format: {fmt}")
                    exporter = ExporterFactory.create(fmt)
                    ext = exporter.get_file_extension()

                    # Create safe filename
                    safe_title = re.sub(r"[^\w\s-]", "", benchmark.title).strip()
                    safe_title = re.sub(r"[-\s]+", "_", safe_title).lower()
                    output_file = os.path.join(output_dir, f"{safe_title}.{ext}")

                    # Ensure output directory exists
                    os.makedirs(output_dir, exist_ok=True)

                    # Export
                    exporter.export(benchmark, output_file)

                    file_size = os.path.getsize(output_file) / 1024
                    logger.debug(f"Exported {fmt} format: {output_file} ({file_size:.1f} KB)")
                    console.print(
                        f"      [green]✓[/green] Exported {exporter.format_name()}: {output_file} ({file_size:.1f} KB)"
                    )

                except Exception as e:
                    logger.error(f"Export failed for format {fmt}: {e}", exc_info=True)
                    console.print(f"      [red]✗[/red] {fmt} export failed: {e}")

            console.print()

        except Exception as e:
            logger.error(f"Benchmark download failed: {e}", exc_info=True)
            console.print(f"{prefix} [red]✗ Error:[/red] {e}\n")
            import traceback

            traceback.print_exc()
            continue

    logger.debug("Download command completed")
    console.print("[bold green]Download complete![/bold green]")
