"""Get command - unified search + download + export workflow."""

import logging
import sys

import click
import questionary
from rich.console import Console

from cis_bench.config import Config
from cis_bench.exporters import ExporterFactory
from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter
from cis_bench.fetcher.auth import AuthManager
from cis_bench.fetcher.workbench import WorkbenchScraper

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
@click.option(
    "--browser",
    "-b",
    type=click.Choice(["chrome", "firefox", "edge", "safari"]),
    help="Browser for authentication (only needed if no saved session)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose (DEBUG level) logging")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging (same as --verbose)")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode (warnings and errors only)")
@click.option(
    "--non-interactive", is_flag=True, help="Disable interactive prompts (show table instead)"
)
def get_cmd(query, export_format, style, output, browser, verbose, debug, quiet, non_interactive):
    """Search, download, and export benchmark in one command.

    This is the easiest way to get a CIS benchmark. It combines search,
    download, and export into a single command.

    \b
    Examples:
        cis-bench get "ubuntu 20.04" --format xccdf --style cis
        cis-bench get "aws" --format yaml
        cis-bench get "docker" --format markdown

    \b
    Requirements:
        Must have catalog initialized first:
        cis-bench catalog refresh --browser chrome
    """
    # Configure logging if flags provided
    if verbose or debug or quiet:
        from cis_bench.utils.logging_config import LoggingConfig

        LoggingConfig.setup_from_flags(quiet=quiet, verbose=(verbose or debug))

    logger.debug(f"Get command: query='{query}', format={export_format}, style={style}")

    # Step 1: Check catalog exists
    catalog_db_path = Config.get_catalog_db_path()

    if not catalog_db_path.exists():
        console.print("[bold red]Catalog not found[/bold red]\n")
        console.print("The 'get' command requires a catalog database to search.\n")
        console.print("[bold cyan]First, initialize the catalog:[/bold cyan]")
        console.print("  cis-bench catalog refresh --browser chrome")
        console.print("\n[dim]This is a one-time setup (~10 minutes)[/dim]\n")
        console.print("[cyan]After initialization, you can use:[/cyan]")
        console.print(f'  cis-bench get "{query}" --format {export_format}')
        sys.exit(1)

    # Step 2: Search catalog
    try:
        from cis_bench.catalog.database import CatalogDatabase
        from cis_bench.catalog.search import CatalogSearch

        logger.debug(f"Searching catalog for: {query}")
        console.print(f"[cyan]Searching for:[/cyan] {query}\n")

        db = CatalogDatabase(catalog_db_path)
        search = CatalogSearch(db)

        # Search with Published filter by default
        results = search.search(query, status="Published", latest_only=True, limit=50)

        if not results:
            console.print("[yellow]No results found[/yellow]\n")
            console.print("[dim]Try a different search term or check:[/dim]")
            console.print("  cis-bench search --help")
            sys.exit(1)

        logger.debug(f"Found {len(results)} results")

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        console.print(f"[red]✗ Search failed: {e}[/red]")
        sys.exit(1)

    # Step 3: Select benchmark
    if len(results) == 1:
        selected = results[0]
        console.print(f"[green]✓[/green] Found: {selected['title']}\n")
    else:
        # Multiple results
        console.print(f"[yellow]Found {len(results)} benchmarks matching '{query}'[/yellow]\n")

        from rich.table import Table

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="yellow", width=8)
        table.add_column("Title", style="white", width=90)
        table.add_column("Version", style="cyan", width=12)
        table.add_column("Status", style="green", width=12)

        for r in results:
            title = r["title"]
            if len(title) > 87:
                title = title[:84] + "..."

            table.add_row(
                str(r["benchmark_id"]),
                title,
                r.get("version", "N/A"),
                r.get("status", "N/A"),
            )

        console.print(table)

        # Interactive selection (if not disabled)
        if not non_interactive:
            console.print()
            try:
                choices = [
                    f"{r['benchmark_id']}: {r['title']} ({r.get('version', 'N/A')})"
                    for r in results
                ]

                answer = questionary.select("Select benchmark:", choices=choices).ask()

                if not answer:
                    console.print("\n[yellow]Cancelled[/yellow]")
                    sys.exit(0)

                # Extract ID from answer
                selected_id = answer.split(":")[0]
                selected = next(r for r in results if str(r["benchmark_id"]) == selected_id)

                console.print(f"\n[green]✓[/green] Selected: {selected['title']}\n")

            except Exception as e:
                logger.warning(f"Interactive selection failed: {e}")
                # Fall through to non-interactive mode
                non_interactive = True

        # Non-interactive mode - show instructions
        if non_interactive:
            console.print("\n[bold cyan]Multiple matches found. Please:[/bold cyan]")
            console.print('  1. Be more specific: [bold]cis-bench get "almalinux 9"[/bold]')
            console.print(
                "  2. Or use ID directly: [bold]cis-bench download <ID> --format xccdf[/bold]"
            )
            console.print(
                "\n[dim]Example: cis-bench download 23598 --format xccdf --style cis[/dim]"
            )
            sys.exit(0)

    benchmark_id = str(selected["benchmark_id"])
    logger.debug(f"Selected benchmark ID: {benchmark_id}")

    # Step 4: Check if already downloaded
    existing = db.get_downloaded(benchmark_id)

    if existing:
        console.print(
            f"[green]✓[/green] Benchmark already cached (downloaded {existing['downloaded_at']})\n"
        )
        logger.debug(f"Using cached benchmark {benchmark_id}")
    else:
        # Step 5: Download benchmark
        console.print("[cyan]Downloading benchmark...[/cyan]\n")

        try:
            # Get authenticated session
            logger.debug("Getting authenticated session for download")
            verify_ssl = Config.get_verify_ssl()
            session = AuthManager.get_or_create_session(browser=browser, verify_ssl=verify_ssl)

            # Download with progress bar
            import hashlib

            from cis_bench.cli.helpers.download_helper import download_with_progress
            from cis_bench.models.benchmark import Benchmark

            scraper = WorkbenchScraper(session)
            benchmark_url = f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}"

            benchmark = download_with_progress(scraper, benchmark_url, prefix="  ")

            console.print(f"[green]✓[/green] Downloaded: {benchmark.title}")
            console.print(f"  Recommendations: {benchmark.total_recommendations}\n")

            # Save to database
            content_json = benchmark.model_dump_json()
            content_hash = hashlib.sha256(content_json.encode()).hexdigest()
            recommendation_count = len(benchmark.recommendations)

            db.save_downloaded(
                benchmark_id=benchmark_id,
                content_json=content_json,
                content_hash=content_hash,
                recommendation_count=recommendation_count,
            )

            logger.debug(f"Saved benchmark {benchmark_id} to database")

        except ValueError as e:
            console.print("\n[bold red]Authentication Required[/bold red]\n")
            console.print(f"[yellow]{e}[/yellow]\n")
            console.print("[cyan]Please log in first:[/cyan]")
            console.print("  cis-bench auth login --browser chrome\n")
            console.print("[dim]Or provide --browser flag:[/dim]")
            console.print(f'  cis-bench get "{query}" --browser chrome --format {export_format}')
            sys.exit(1)
        except Exception as e:
            logger.error(f"Download failed: {e}", exc_info=True)
            console.print(f"[red]✗ Download failed: {e}[/red]")
            sys.exit(1)

    # Step 6: Export to requested format
    try:
        import json

        from cis_bench.models.benchmark import Benchmark

        console.print(f"[cyan]Exporting to {export_format}...[/cyan]")

        # Load from database
        downloaded = db.get_downloaded(benchmark_id)
        benchmark_data = json.loads(downloaded["content_json"])
        benchmark = Benchmark(**benchmark_data)

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
        console.print(f"  Output: [bold]{output}[/bold]")
        console.print(f"  Size: {file_size:.1f} KB")

        logger.debug(f"Export complete: {output}")

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        console.print(f"[red]✗ Export failed: {e}[/red]")
        sys.exit(1)
