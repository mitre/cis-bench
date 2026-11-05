"""Download command for CIS Benchmark CLI."""

import logging
import os
import re
import sys

import click
from rich.console import Console
from rich.markup import escape

from cis_bench.cli.helpers.errors import report_expired_session
from cis_bench.cli.helpers.services import auth_manager, settings_from, workbench_scraper
from cis_bench.exceptions import (
    AuthenticationError,
    NoSavedSessionError,
    TLSVerificationError,
)
from cis_bench.exporters import ExporterFactory
from cis_bench.utils.workbench_urls import resolve_benchmark_reference

console = Console()
logger = logging.getLogger(__name__)


def _collect_targets(
    benchmark_ids: tuple[str, ...], urls_file: str | None, base_url: str
) -> list[tuple[str, str]]:
    """Turn CLI arguments or an input file into validated (benchmark_id, canonical_url) pairs.

    Blank lines and ``#`` comments in the file are skipped. The first invalid reference
    aborts the whole run with its location, so nothing is downloaded from a bad list.
    """
    if urls_file:
        targets = []
        with open(urls_file) as f:
            for line_no, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    targets.append(resolve_benchmark_reference(line, base_url=base_url))
                except ValueError as e:
                    raise ValueError(f"line {line_no} of {urls_file}: {e}") from e
        return targets
    if benchmark_ids:
        return [resolve_benchmark_reference(item, base_url=base_url) for item in benchmark_ids]
    console.print("[red]Error: Must specify benchmark IDs or --file[/red]")
    sys.exit(1)


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
    "--output-dir",
    "-o",
    help="Output directory for downloaded benchmarks (default: <data dir>/benchmarks)",
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

    # Resolve and validate every benchmark reference before touching the network, so a bad
    # ID, an off-origin URL or a cleartext URL can never be sent with the session cookies.
    settings = settings_from()
    if output_dir is None:
        output_dir = settings.benchmarks_dir
    try:
        targets = _collect_targets(benchmark_ids, urls_file, settings.workbench_url)
    except ValueError as e:
        console.print(f"[red]✗ {escape(str(e))}[/red]")
        sys.exit(1)

    if not targets:
        console.print("[red]Error: No benchmarks to download[/red]")
        sys.exit(1)

    # Get authenticated session (uses saved session only)
    try:
        logger.debug("Getting authenticated session")
        with console.status("[bold green]Authenticating..."):
            session = auth_manager(settings).get_or_create_session()

        console.print("[green]✓[/green] Authenticated successfully\n")
        logger.debug("Authentication successful")

    except NoSavedSessionError:
        console.print("\n[bold red]Authentication Required[/bold red]\n")
        console.print("[bold cyan]Please log in first:[/bold cyan]")
        console.print("  cis-bench auth login --browser chrome")
        console.print("\n[dim]This saves your session for future commands.[/dim]")
        console.print(
            "\n[dim]Windows users: If Chrome fails, try Firefox or --cookies option.[/dim]"
        )
        sys.exit(1)
    except TLSVerificationError as e:
        # The server could not be trusted; the message carries the remediation.
        console.print(f"\n[red]✗ {escape(str(e))}[/red]")
        sys.exit(1)
    except AuthenticationError as e:
        report_expired_session(console, e)
        sys.exit(1)
    except Exception as e:
        logger.debug("Authentication failed", exc_info=True)
        console.print("\n[bold red]Authentication Failed[/bold red]\n")
        console.print(f"[yellow]Error: {escape(str(e))}[/yellow]\n")
        console.print("[bold cyan]Your session may have expired. To refresh:[/bold cyan]")
        console.print("  cis-bench auth login --browser chrome")
        sys.exit(1)

    # Create scraper
    scraper = workbench_scraper(settings, session)

    # Download benchmarks
    logger.debug(f"Starting download of {len(targets)} benchmark(s)")
    console.print(f"[bold]Downloading {len(targets)} benchmark(s)...[/bold]\n")

    failed: list[str] = []
    for idx, (benchmark_id, url) in enumerate(targets, 1):
        prefix = f"[{idx}/{len(targets)}]"
        logger.debug(f"Processing benchmark {idx}/{len(targets)}: {url}")

        # Check if already cached (unless --force)
        if not force:
            catalog_db_path = settings.catalog_db_path
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
            console.print(
                f"{prefix} [green]✓[/green] Downloaded: [bold]{escape(benchmark.title)}[/bold]"
            )
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
            catalog_db_path = settings.catalog_db_path
            if catalog_db_path.exists():
                try:
                    from cis_bench.catalog.database import (
                        CatalogDatabase,
                        serialize_benchmark_json,
                    )

                    # Prepare data for database
                    content_json, content_hash = serialize_benchmark_json(benchmark)
                    recommendation_count = len(benchmark.recommendations)

                    db = CatalogDatabase(catalog_db_path)
                    db.save_downloaded(
                        version=benchmark.version,
                        benchmark_id=benchmark_id,
                        content_json=content_json,
                        content_hash=content_hash,
                        recommendation_count=recommendation_count,
                    )
                    logger.debug(f"Saved benchmark {benchmark_id} to catalog database")
                    console.print(f"      [green]✓[/green] Cached in database (ID: {benchmark_id})")
                except Exception as e:
                    logger.debug("Failed to save to catalog database", exc_info=True)
                    console.print(
                        f"      [yellow]⚠[/yellow] Could not cache in database: {escape(str(e))}"
                    )

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
                        f"      [green]✓[/green] Exported {exporter.format_name()}: {escape(output_file)} ({file_size:.1f} KB)"
                    )

                except Exception as e:
                    logger.debug(f"Export failed for format {fmt}", exc_info=True)
                    console.print(f"      [red]✗[/red] {fmt} export failed: {escape(str(e))}")
                    if benchmark_id not in failed:
                        failed.append(benchmark_id)

            console.print()

        except AuthenticationError as e:
            # Every further request would get the login page too: stop, do not try the rest.
            logger.debug(f"Session expired while downloading {url}: {e}")
            report_expired_session(console, e)
            sys.exit(1)
        except Exception as e:
            logger.debug(f"Benchmark download failed: {url}", exc_info=True)
            console.print(f"{prefix} [red]✗ Error:[/red] {escape(str(e))}\n")
            failed.append(benchmark_id)
            continue

    logger.debug("Download command completed")
    if failed:
        console.print(
            f"[bold red]Download finished with errors:[/bold red] {len(failed)} of "
            f"{len(targets)} benchmark(s) failed ({', '.join(failed)})."
        )
        sys.exit(1)
    console.print("[bold green]Download complete![/bold green]")
