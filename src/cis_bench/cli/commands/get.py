"""Get command - unified search + download + export workflow."""

import logging
import sys
from typing import TYPE_CHECKING

import click
import questionary
from rich.console import Console
from rich.markup import escape

from cis_bench.cli.helpers.errors import report_expired_session, report_unreachable
from cis_bench.cli.helpers.output import benchmark_table, display_time
from cis_bench.cli.helpers.services import auth_manager, settings_from, workbench_scraper
from cis_bench.exceptions import (
    AuthenticationError,
    FetchError,
    NoSavedSessionError,
    TLSVerificationError,
)
from cis_bench.exporters import ExporterFactory
from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter
from cis_bench.utils.workbench_urls import is_benchmark_id, resolve_benchmark_reference

if TYPE_CHECKING:
    from cis_bench.catalog.search import CatalogSearch
    from cis_bench.config import Settings

console = Console()
logger = logging.getLogger(__name__)


def get_available_xccdf_styles():
    """Get available XCCDF styles for CLI validation."""
    return XCCDFExporter._get_available_styles()


class DynamicStyleChoice(click.Choice):
    """Dynamic choice that loads available styles at runtime."""

    def __init__(self):
        super().__init__(get_available_xccdf_styles())


@click.command(name="get")
@click.argument("query")
@click.option(
    "--format",
    "-f",
    "export_format",
    type=click.Choice(["yaml", "csv", "markdown", "md", "xccdf", "xml", "json"]),
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
    help="Output file path (default: auto-generated)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose (DEBUG level) logging")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging (same as --verbose)")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode (warnings and errors only)")
@click.option(
    "--non-interactive",
    is_flag=True,
    help="No menu: when several benchmarks match, take the best match",
)
@click.option(
    "--force", is_flag=True, help="Download again and replace the cached copy, if there is one"
)
def get_cmd(query, export_format, style, output, verbose, debug, quiet, non_interactive, force):
    """Search, download, and export benchmark in one command.

    This is the easiest way to get a CIS benchmark. It combines search,
    download, and export into a single command. QUERY is search words or a
    catalog ID. When several benchmarks match, a menu offers them, best match
    first; with --non-interactive the best match is taken.

    \b
    Examples:
        cis-bench get "ubuntu 20.04" --format xccdf --style cis
        cis-bench get "kubernetes v2.0.1" --format xccdf
        cis-bench get 23598 --format xccdf
        cis-bench get 23598 --force --format xccdf
        cis-bench get "aws" --format yaml
        cis-bench get "docker" --format markdown

    \b
    Requirements:
        1. Authenticate: cis-bench auth login --browser chrome
        2. Build catalog: cis-bench catalog refresh
    """
    # Configure logging if flags provided
    if verbose or debug or quiet:
        from cis_bench.utils.logging_config import LoggingConfig

        LoggingConfig.setup_from_flags(quiet=quiet, verbose=(verbose or debug))

    logger.debug(f"Get command: query='{query}', format={export_format}, style={style}")

    settings = settings_from()

    # Step 1: Check catalog exists
    catalog_db_path = settings.catalog_db_path

    if not catalog_db_path.exists():
        console.print("[bold red]Catalog not found[/bold red]\n")
        console.print("The 'get' command requires a catalog database to search.\n")
        console.print("[bold cyan]First, initialize the catalog:[/bold cyan]")
        console.print("  cis-bench catalog refresh --browser chrome")
        console.print("\n[dim]This is a one-time setup (under a minute)[/dim]\n")
        console.print("[cyan]After initialization, you can use:[/cyan]")
        console.print(f'  cis-bench get "{escape(query)}" --format {export_format}')
        sys.exit(1)

    # Step 2: Find the benchmark: by its catalog ID, or by searching the catalog
    try:
        from cis_bench.catalog.database import CatalogDatabase
        from cis_bench.catalog.search import CatalogSearch

        db = CatalogDatabase(catalog_db_path)
        search = CatalogSearch(db)

        if is_benchmark_id(query):
            selected = _benchmark_with_id(search, query.strip())
        else:
            selected = _benchmark_matching(search, query, settings, non_interactive)
    except Exception as e:
        logger.debug("Search failed", exc_info=True)
        console.print(f"[red]✗ Search failed: {escape(str(e))}[/red]")
        sys.exit(1)

    benchmark_id = str(selected["benchmark_id"])
    logger.debug(f"Selected benchmark ID: {benchmark_id}")

    # Step 3: Use the cached copy, unless there is none or --force says to replace it
    existing = None if force else db.get_downloaded(benchmark_id)

    if existing:
        console.print(
            "[green]✓[/green] Benchmark already cached "
            f"(downloaded {display_time(existing['downloaded_at'])})\n"
        )
        logger.debug(f"Using cached benchmark {benchmark_id}")
    else:
        # Step 4: Download benchmark
        console.print("[cyan]Downloading benchmark...[/cyan]\n")

        try:
            # The catalog row's ID becomes a canonical WorkBench URL on the configured origin
            _, benchmark_url = resolve_benchmark_reference(
                str(benchmark_id), base_url=settings.workbench_url
            )
        except ValueError as e:
            console.print(f"[red]✗ {escape(str(e))}[/red]")
            sys.exit(1)

        try:
            # Get authenticated session (uses saved session only)
            logger.debug("Getting authenticated session for download")
            session = auth_manager(settings).get_or_create_session()

            # Download with progress bar
            from cis_bench.catalog.database import serialize_benchmark_json
            from cis_bench.cli.helpers.download_helper import download_with_progress

            scraper = workbench_scraper(settings, session)

            benchmark = download_with_progress(scraper, benchmark_url, prefix="  ")

            console.print(f"[green]✓[/green] Downloaded: {escape(benchmark.title)}")
            console.print(f"  Recommendations: {benchmark.total_recommendations}\n")

            # Save to database
            content_json, content_hash = serialize_benchmark_json(benchmark)
            recommendation_count = len(benchmark.recommendations)

            db.save_downloaded(
                version=benchmark.version,
                benchmark_id=benchmark_id,
                content_json=content_json,
                content_hash=content_hash,
                recommendation_count=recommendation_count,
                downloaded_at=benchmark.downloaded_at,
            )

            logger.debug(f"Saved benchmark {benchmark_id} to database")

        except NoSavedSessionError:
            console.print("\n[bold red]Authentication Required[/bold red]\n")
            console.print("[cyan]Please log in first:[/cyan]")
            console.print("  cis-bench auth login --browser chrome")
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
        except FetchError as e:
            report_unreachable(console, e)
            sys.exit(1)
        except Exception as e:
            logger.debug("Download failed", exc_info=True)
            console.print(f"[red]✗ Download failed: {escape(str(e))}[/red]")
            sys.exit(1)

    # Step 5: Export to requested format
    try:
        from cis_bench.catalog.database import deserialize_benchmark_json

        console.print(f"[cyan]Exporting to {export_format}...[/cyan]")

        # Load from database
        downloaded = db.get_downloaded(benchmark_id)
        if not downloaded:
            raise ValueError(f"Benchmark {benchmark_id} not found in catalog cache")
        benchmark = deserialize_benchmark_json(downloaded["content_json"])

        # Create exporter
        exporter_kwargs = {}
        if export_format in ["xccdf", "xml"]:
            exporter_kwargs["style"] = style

        exporter = ExporterFactory.create(export_format, **exporter_kwargs)

        # Determine output filename
        if not output:
            base = f"benchmark_{benchmark_id}"
            ext = exporter.get_file_extension()
            output = f"{base}.{ext}"

        # Export
        exporter.export(benchmark, output)

        import os

        file_size = os.path.getsize(output) / 1024

        console.print("\n[bold green]✓ Success![/bold green]")
        console.print(f"  Format: {exporter.format_name()}")
        console.print(f"  Output: [bold]{escape(str(output))}[/bold]")
        console.print(f"  Size: {file_size:.1f} KB")

        logger.debug(f"Export complete: {output}")

    except Exception as e:
        logger.debug("Export failed", exc_info=True)
        console.print(f"[red]✗ Export failed: {escape(str(e))}[/red]")
        sys.exit(1)


def _benchmark_with_id(search: "CatalogSearch", benchmark_id: str) -> dict:
    """The catalog row with this ID, whatever its status or age; exit 1 when there is none."""
    found = search.find_by_id(benchmark_id)
    if found is None:
        console.print(f"[yellow]No benchmark with ID {benchmark_id} in the catalog[/yellow]\n")
        console.print("[dim]If it is new on WorkBench, update the catalog first:[/dim]")
        console.print("  cis-bench catalog refresh")
        sys.exit(1)
    console.print(f"[green]✓[/green] Found: {escape(found['title'])} {escape(found['version'])}\n")
    return found


def _benchmark_matching(
    search: "CatalogSearch", query: str, settings: "Settings", non_interactive: bool
) -> dict:
    """The benchmark a word query means: the only match, the best-ranked match, or the one
    chosen from a menu. Exit 1 when nothing matches or the menu is left without a choice."""
    console.print(f"[cyan]Searching for:[/cyan] {escape(query)}\n")
    logger.debug(f"Searching catalog for: {query}")

    # Published benchmarks: the latest release of each, and any release the query names
    # by its version. CIS_BENCH_SEARCH_LIMIT caps the candidates; they come best match first.
    limit = settings.search_limit
    results = search.search(
        query, status="Published", latest_only=True, named_releases=True, limit=limit
    )
    # A list shorter than the limit is complete; only a full one may have been cut off.
    total = len(results)
    if len(results) >= limit:
        total = search.count(query, status="Published", latest_only=True, named_releases=True)

    if not results:
        console.print("[yellow]No results found[/yellow]\n")
        console.print("[dim]Try a different search term or check:[/dim]")
        console.print("  cis-bench search --help")
        sys.exit(1)

    logger.debug(f"Found {len(results)} results")

    if len(results) == 1:
        selected = results[0]
        console.print(f"[green]✓[/green] Found: {escape(str(selected['title']))}\n")
        return selected

    if non_interactive:
        return _best_match(results, total, query)

    cut_off = f" (showing the first {len(results)})" if total > len(results) else ""
    console.print(
        f"[yellow]Found {total} benchmarks matching '{escape(query)}'{cut_off}[/yellow]\n"
    )

    console.print(benchmark_table(results, title_width=settings.table_title_width))
    console.print()
    choices = [f"{r['benchmark_id']}: {r['title']} ({r.get('version', 'N/A')})" for r in results]
    try:
        answer = questionary.select("Select benchmark:", choices=choices).ask()
    except Exception as e:
        # No usable terminal for a menu (a pipe, a CI job): the best match, as without one
        logger.warning(f"Interactive selection failed: {e}")
        return _best_match(results, total, query)
    if not answer:
        # Nothing was exported; a script must not take this for success
        console.print("\n[yellow]Cancelled[/yellow]")
        sys.exit(1)

    selected_id = answer.split(":")[0]
    selected = next(r for r in results if str(r["benchmark_id"]) == selected_id)
    console.print(f"\n[green]✓[/green] Selected: {escape(str(selected['title']))}\n")
    return selected


def _best_match(results: list[dict], total: int, query: str) -> dict:
    """The best-ranked match, saying how many others there were and how to see them."""
    selected = results[0]
    others = total - 1
    console.print(
        f"[green]✓[/green] Chose: {escape(str(selected['title']))} "
        f"{escape(str(selected.get('version', '')))}"
    )
    console.print(
        f"  {others} other benchmark{'s' if others != 1 else ''} matched. To see them all:"
    )
    console.print(f'    cis-bench search "{escape(query)}"\n')
    return selected
