"""Download command for CIS Benchmark CLI."""

from __future__ import annotations

import logging
import os
import re
import sys
from contextlib import closing
from gettext import ngettext
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.markup import escape

from cis_bench.cli.helpers.errors import (
    DOWNLOAD_ERRORS,
    cache_failure,
    report_download_error,
    report_expired_session,
)
from cis_bench.cli.helpers.offline import OfflineError
from cis_bench.cli.helpers.output import display_time
from cis_bench.cli.helpers.services import settings_from, workbench_scraper, workbench_session
from cis_bench.config import Settings
from cis_bench.exceptions import AuthenticationError
from cis_bench.exporters import ExporterFactory
from cis_bench.utils.workbench_urls import resolve_benchmark_reference

if TYPE_CHECKING:
    from cis_bench.fetcher.workbench import WorkbenchScraper

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


def _open_workbench(settings: Settings, benchmark_id: str) -> WorkbenchScraper:
    """Log in to WorkBench for the first benchmark that must be fetched.

    A failed login ends the run (every later download would fail the same way).

    Raises:
        OfflineError: Offline mode is on; the caller fails this benchmark and goes on.
    """
    try:
        logger.debug("Getting authenticated session")
        with console.status("[bold green]Authenticating..."):
            session = workbench_session(settings, needs=f"download benchmark {benchmark_id}")
    except OfflineError:
        raise
    except DOWNLOAD_ERRORS as e:
        report_download_error(console, e)
        sys.exit(1)
    except Exception as e:
        logger.debug("Authentication failed", exc_info=True)
        report_expired_session(console, e)
        sys.exit(1)
    console.print("[green]✓[/green] Authenticated successfully\n")
    logger.debug("Authentication successful")
    return workbench_scraper(settings, session)


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

    \b
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

    # The session is opened at the first benchmark that is not cached, so cached ones need
    # no login (and work offline).
    scraper: WorkbenchScraper | None = None

    # Download benchmarks
    downloading = ngettext(
        "Downloading {count} benchmark...", "Downloading {count} benchmarks...", len(targets)
    ).format(count=len(targets))
    logger.debug(downloading)
    console.print(f"[bold]{downloading}[/bold]\n")

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

                    with closing(CatalogDatabase(catalog_db_path)) as db:
                        existing = db.get_downloaded(benchmark_id)

                    if existing:
                        console.print(
                            f"{prefix} [yellow]Benchmark {benchmark_id} already cached[/yellow]"
                        )
                        console.print(
                            f"      Downloaded: {display_time(existing['downloaded_at'])}"
                        )
                        console.print(f"      Recommendations: {existing['recommendation_count']}")
                        console.print("\n[dim]Use --force to re-download[/dim]\n")
                        logger.debug(f"Skipping {benchmark_id} - already cached")
                        continue

                except Exception as e:
                    logger.debug(f"Cache check failed: {e}, will download anyway")

        if scraper is None:
            try:
                scraper = _open_workbench(settings, benchmark_id)
            except OfflineError as e:
                console.print(f"{prefix} [red]✗[/red] {escape(e.format_message())}\n")
                failed.append(benchmark_id)
                continue

        try:
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

            # Into the cache when there is one (catalog.db). A failed cache write fails this
            # benchmark, but the download is kept: the exports below are still written.
            catalog_db_path = settings.catalog_db_path
            if catalog_db_path.exists():
                from sqlalchemy.exc import SQLAlchemyError

                from cis_bench.catalog.database import CatalogDatabase
                from cis_bench.catalog.downloader import CatalogDownloader

                try:
                    with closing(CatalogDatabase(catalog_db_path)) as db:
                        CatalogDownloader(db).cache(benchmark_id, benchmark)
                    console.print(f"      [green]✓[/green] Cached in database (ID: {benchmark_id})")
                except (SQLAlchemyError, OSError) as e:
                    logger.debug("Failed to cache the benchmark", exc_info=True)
                    console.print(f"      [red]✗[/red] {escape(cache_failure(benchmark_id, e))}")
                    failed.append(benchmark_id)

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
            "[bold red]Download finished with errors:[/bold red] "
            + ngettext(
                "{failed} of {total} benchmark failed ({ids}).",
                "{failed} of {total} benchmarks failed ({ids}).",
                len(targets),
            ).format(failed=len(failed), total=len(targets), ids=", ".join(failed))
        )
        sys.exit(1)
    console.print("[bold green]Download complete![/bold green]")
