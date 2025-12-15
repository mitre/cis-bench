"""Catalog management commands for CIS Benchmark CLI."""

import logging

import click
from rich.console import Console
from rich.table import Table

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.downloader import CatalogDownloader
from cis_bench.catalog.scraper import CatalogScraper
from cis_bench.catalog.search import CatalogSearch
from cis_bench.cli.helpers.output import output_data
from cis_bench.config import Config
from cis_bench.exceptions import AuthenticationError
from cis_bench.fetcher.auth import AuthManager
from cis_bench.fetcher.workbench import WorkbenchScraper

console = Console()
logger = logging.getLogger(__name__)


def get_catalog_db() -> CatalogDatabase:
    """Get catalog database instance (environment-aware)."""
    Config.ensure_directories()
    return CatalogDatabase(Config.get_catalog_db_path())


@click.group()
def catalog():
    """Manage CIS benchmark catalog.

    The catalog feature allows you to browse, search, and download benchmarks
    from the CIS WorkBench without knowing the exact URL.

    \b
    Example workflow:
        cis-bench catalog refresh              # Build catalog (one-time, ~10 min)
        cis-bench catalog search "ubuntu 20"   # Find benchmarks
        cis-bench catalog download 23598       # Download by ID
    """
    pass


@catalog.command()
@click.option("--browser", default="chrome", help="Browser for cookie extraction")
@click.option("--max-pages", type=int, help="Limit pages to scrape (for testing)")
@click.option("--rate-limit", default=2.0, type=float, help="Seconds between requests")
def refresh(browser, max_pages, rate_limit):
    """Refresh catalog from CIS WorkBench (scrape all pages).

    This builds or updates the complete catalog by scraping all benchmark
    listing pages from CIS WorkBench. Takes approximately 10 minutes for
    full catalog (~68 pages).

    \b
    Examples:
        cis-bench catalog refresh
        cis-bench catalog refresh --max-pages 5  # Test with 5 pages
        cis-bench catalog refresh --rate-limit 1  # Faster (less polite)
    """
    try:
        # Get database
        db = get_catalog_db()
        db.initialize_schema()

        # Proactive auth check - use saved session or prompt for login
        verify_ssl = Config.get_verify_ssl()
        session = AuthManager.get_or_create_session(browser=browser, verify_ssl=verify_ssl)

        # Validate session before attempting scrape
        console.print("[cyan]Validating session...[/cyan]")
        if not AuthManager.validate_session(session, verify_ssl=verify_ssl):
            console.print("[red]✗[/red] Session invalid or expired")
            console.print("[yellow]Please run: cis-bench auth login --browser chrome[/yellow]")
            raise click.Abort()
        console.print("[green]✓[/green] Session valid\n")

        # Create scraper
        scraper = CatalogScraper(db, session)

        # Test connection
        console.print("[cyan]Testing connection...[/cyan]")
        scraper.test_connection()
        console.print("[green]✓[/green] Connected to CIS WorkBench\n")

        # Scrape catalog
        pages_msg = f"{max_pages} pages" if max_pages else "all pages"
        console.print(f"[cyan]Scraping catalog ({pages_msg})...[/cyan]")

        stats = scraper.scrape_full_catalog(max_pages=max_pages, rate_limit_seconds=rate_limit)

        # Show results
        console.print("\n[green]✓[/green] Catalog refresh complete!")
        console.print(f"  Benchmarks: [yellow]{stats['total_benchmarks']}[/yellow]")
        console.print(f"  Pages: [yellow]{stats['pages_scraped']}[/yellow]")

        if stats["failed_pages"]:
            console.print(
                f"  Failed pages: [red]{len(stats['failed_pages'])}[/red] - {stats['failed_pages']}"
            )

        # Show database stats
        db_stats = db.get_catalog_stats()
        console.print("\n[cyan]Catalog statistics:[/cyan]")
        console.print(f"  Total benchmarks: {db_stats['total_benchmarks']}")
        console.print(f"  Platforms: {db_stats['platforms']}")
        console.print(f"  Communities: {db_stats['communities']}")

    except AuthenticationError as e:
        console.print("[red]✗ Authentication required[/red]")
        console.print(f"[yellow]{e}[/yellow]")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]✗ Catalog refresh failed: {e}[/red]")
        raise click.Abort() from e


@catalog.command()
@click.option("--browser", default="chrome", help="Browser for cookie extraction")
def update(browser):
    """Quick catalog update (scrape page 1 only).

    Faster than full refresh - only checks the first page for new/updated
    benchmarks. Takes ~30 seconds.

    \b
    Example:
        cis-bench catalog update
    """
    try:
        db = get_catalog_db()

        if not db.db_path.exists():
            console.print(
                "[yellow]Catalog not initialized. Run 'cis-bench catalog refresh' first.[/yellow]"
            )
            raise click.Abort()

        session = AuthManager.load_cookies_from_browser(browser)
        scraper = CatalogScraper(db, session)

        console.print("[cyan]Updating catalog (page 1)...[/cyan]")

        stats = scraper.scrape_page_one_update(rate_limit_seconds=1)

        console.print("[green]✓[/green] Catalog updated!")
        console.print(f"  New benchmarks: [yellow]{stats['new_count']}[/yellow]")
        console.print(f"  Updated: [yellow]{stats['updated_count']}[/yellow]")

    except Exception as e:
        console.print(f"[red]✗ Update failed: {e}[/red]")
        raise click.Abort() from e


@catalog.command()
@click.argument("query", required=False)
@click.option("--platform", help="Filter by platform")
@click.option("--status", default="Published", help="Filter by status")
@click.option("--latest", is_flag=True, help="Latest versions only")
@click.option("--limit", type=int, help="Max results (default: 1000)")
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "csv", "yaml"]),
    default="table",
    help="Output format",
)
def search(query, platform, status, latest, limit, output_format):
    """Search catalog for benchmarks.

    \b
    Examples:
        cis-bench catalog search "ubuntu 20"
        cis-bench catalog search "linux" --platform "Operating System"
        cis-bench catalog search --latest
    """
    try:
        db = get_catalog_db()

        if not db.db_path.exists():
            console.print(
                "[yellow]Catalog not found. Run 'cis-bench catalog refresh' first.[/yellow]"
            )
            raise click.Abort()

        search_obj = CatalogSearch(db)

        # Use Config default if limit not provided
        if limit is None:
            limit = Config.get_search_default_limit()

        results = search_obj.search(
            query=query or "", platform=platform, status=status, latest_only=latest, limit=limit
        )

        if not results:
            if output_format != "table":
                output_data([], output_format)
            else:
                console.print(f"[yellow]No benchmarks found matching: {query}[/yellow]")
            return

        # Output in requested format
        if output_format != "table":
            csv_fields = [
                "benchmark_id",
                "title",
                "version",
                "status",
                "platform",
                "community",
                "url",
            ]
            output_data(results, output_format, csv_fields=csv_fields)

        # Human-friendly display
        console.print(f"\n[cyan]Found {len(results)} benchmarks:[/cyan]\n")

        for r in results:
            formatted = search_obj.format_result_for_display(r)
            console.print(formatted)
            console.print()  # Blank line

    except Exception as e:
        console.print(f"[red]✗ Search failed: {e}[/red]")
        raise click.Abort() from e


@catalog.command(name="list")
@click.option("--platform", help="Filter by platform")
@click.option("--latest", is_flag=True, help="Latest versions only")
@click.option("--limit", default=50, type=int, help="Max results")
def list_cmd(platform, latest, limit):
    """List benchmarks in catalog.

    \b
    Examples:
        cis-bench catalog list
        cis-bench catalog list --platform "Operating System" --latest
    """
    try:
        db = get_catalog_db()

        if not db.db_path.exists():
            console.print(
                "[yellow]Catalog not found. Run 'cis-bench catalog refresh' first.[/yellow]"
            )
            raise click.Abort()

        search_obj = CatalogSearch(db)

        if platform:
            results = search_obj.list_by_platform(platform, latest_only=latest)
        else:
            results = search_obj.list_all_published(limit=limit)

        if not results:
            console.print("[yellow]No benchmarks found.[/yellow]")
            return

        console.print(f"\n[cyan]{len(results)} benchmarks:[/cyan]\n")

        for r in results[:limit]:
            formatted = search_obj.format_result_for_display(r)
            console.print(formatted)
            console.print()

    except Exception as e:
        console.print(f"[red]✗ List failed: {e}[/red]")
        raise click.Abort() from e


@catalog.command()
@click.argument("benchmark_id")
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format",
)
def info(benchmark_id, output_format):
    """Show detailed information about a benchmark.

    \b
    Example:
        cis-bench catalog info 23598
    """
    try:
        db = get_catalog_db()

        if not db.db_path.exists():
            console.print(
                "[yellow]Catalog not found. Run 'cis-bench catalog refresh' first.[/yellow]"
            )
            raise click.Abort()

        bench = db.get_benchmark(benchmark_id)

        if not bench:
            console.print(f"[red]Benchmark {benchmark_id} not found in catalog.[/red]")
            raise click.Abort()

        # Output in requested format
        if output_format != "table":
            output_data(bench, output_format)

        # Display detailed info (table format)
        console.print(f"\n[bold]{bench['title']}[/bold]")

        if bench.get("version"):
            console.print(f"Version: {bench['version']}")

        console.print(f"ID: {bench['benchmark_id']}")
        console.print(f"Status: {bench['status']}")

        if bench.get("platform"):
            console.print(f"Platform: {bench['platform']}")

        if bench.get("community"):
            console.print(f"Community: {bench['community']}")

        if bench.get("owner"):
            console.print(f"Owner: {bench['owner']}")

        if bench.get("published_date"):
            console.print(f"Published: {bench['published_date']}")

        console.print(f"\nURL: {bench['url']}")

        if bench.get("description"):
            console.print(f"\n[dim]{bench['description'][:200]}...[/dim]")

        console.print(f"\n[cyan]Download:[/cyan] cis-bench catalog download {benchmark_id}")

    except Exception as e:
        console.print(f"[red]✗ Info failed: {e}[/red]")
        raise click.Abort() from e


@catalog.command()
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "csv", "yaml"]),
    default="table",
    help="Output format",
)
def platforms(output_format):
    """List all platforms with benchmark counts.

    \b
    Example:
        cis-bench catalog platforms
    """
    try:
        db = get_catalog_db()

        if not db.db_path.exists():
            console.print(
                "[yellow]Catalog not found. Run 'cis-bench catalog refresh' first.[/yellow]"
            )
            raise click.Abort()

        platforms = db.list_platforms()

        if not platforms:
            if output_format != "table":
                output_data([], output_format)
            else:
                console.print("[yellow]No platforms found.[/yellow]")
            return

        # Output in requested format
        if output_format != "table":
            csv_fields = ["name", "count"]
            output_data(platforms, output_format, csv_fields=csv_fields)

        # Create table for human display
        table = Table(title="Platforms")
        table.add_column("Platform", style="cyan")
        table.add_column("Benchmarks", justify="right", style="yellow")

        for p in platforms:
            table.add_row(p["name"], str(p["count"]))

        console.print()
        console.print(table)

    except Exception as e:
        console.print(f"[red]✗ Platforms list failed: {e}[/red]")
        raise click.Abort() from e


@catalog.command()
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format",
)
def stats(output_format):
    """Show catalog statistics.

    \b
    Example:
        cis-bench catalog stats
    """
    try:
        db = get_catalog_db()

        if not db.db_path.exists():
            console.print(
                "[yellow]Catalog not found. Run 'cis-bench catalog refresh' first.[/yellow]"
            )
            raise click.Abort()

        stats = db.get_catalog_stats()
        last_scrape = db.get_metadata("last_full_scrape")

        # Add last_scrape to stats
        stats["last_full_scrape"] = last_scrape

        # Output in requested format
        if output_format != "table":
            output_data(stats, output_format)

        # Human display
        console.print("\n[bold]Catalog Statistics[/bold]\n")
        console.print(f"Total benchmarks: [yellow]{stats['total_benchmarks']}[/yellow]")
        console.print(f"Published: [yellow]{stats['published_benchmarks']}[/yellow]")
        console.print(f"Downloaded: [yellow]{stats['downloaded_benchmarks']}[/yellow]")
        console.print(f"Platforms: [yellow]{stats['platforms']}[/yellow]")
        console.print(f"Communities: [yellow]{stats['communities']}[/yellow]")

        if last_scrape:
            console.print(f"\nLast catalog refresh: [dim]{last_scrape}[/dim]")

    except Exception as e:
        console.print(f"[red]✗ Stats failed: {e}[/red]")
        raise click.Abort() from e


@catalog.command()
@click.argument("benchmark_id_or_name")
@click.option("--browser", default="chrome", help="Browser for cookie extraction")
@click.option("--force", is_flag=True, help="Force re-download even if current")
@click.option("--interactive", is_flag=True, help="Interactive selection if multiple matches")
def download(benchmark_id_or_name, browser, force, interactive):
    """Download benchmark from catalog.

    Can download by ID or by name (fuzzy search).

    \b
    Examples:
        cis-bench catalog download 23598
        cis-bench catalog download "ubuntu 20.04" --interactive
    """
    try:
        db = get_catalog_db()

        if not db.db_path.exists():
            console.print(
                "[yellow]Catalog not found. Run 'cis-bench catalog refresh' first.[/yellow]"
            )
            raise click.Abort()

        # Get authenticated session
        session = AuthManager.load_cookies_from_browser(browser)

        # Create downloader
        scraper = WorkbenchScraper(session)
        downloader = CatalogDownloader(db, scraper)

        # Determine if ID or name
        if benchmark_id_or_name.isdigit():
            # Download by ID
            console.print(f"[cyan]Downloading benchmark {benchmark_id_or_name}...[/cyan]")
            result = downloader.download_by_id(benchmark_id_or_name, force=force)
        else:
            # Download by name
            console.print(f"[cyan]Searching for: {benchmark_id_or_name}[/cyan]")
            result = downloader.download_by_name(
                benchmark_id_or_name, latest=True, interactive=interactive
            )

        # Show result
        if result["status"] == "already_current":
            console.print(f"[green]✓[/green] {result['message']}")
        elif result["status"] == "unchanged":
            console.print(f"[green]✓[/green] {result['message']}")
        else:
            console.print(f"[green]✓[/green] Downloaded benchmark {result['benchmark_id']}")
            console.print(f"  Recommendations: {result['recommendation_count']}")
            console.print(f"  Size: {result['file_size'] / 1024:.1f} KB")

    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]✗ Download failed: {e}[/red]")
        logger.error(f"Download error: {e}", exc_info=True)
        raise click.Abort() from e


@catalog.command(name="check-updates")
def check_updates():
    """Check downloaded benchmarks for available updates.

    \b
    Example:
        cis-bench catalog check-updates
    """
    try:
        db = get_catalog_db()

        if not db.db_path.exists():
            console.print(
                "[yellow]Catalog not found. Run 'cis-bench catalog refresh' first.[/yellow]"
            )
            raise click.Abort()

        updates = db.check_updates_available()

        if not updates:
            console.print("[green]✓[/green] All downloaded benchmarks are up-to-date!")
            return

        console.print(f"\n[yellow]Updates available for {len(updates)} benchmarks:[/yellow]\n")

        for u in updates:
            console.print(f"  [{u['benchmark_id']}] {u['title']} {u.get('version', '')}")
            console.print(f"      Downloaded: {u['downloaded_at']}")
            console.print(f"      Latest: {u['last_revision_date']}")
            console.print()

        console.print("[cyan]Use 'cis-bench catalog download <id> --force' to update.[/cyan]")

    except Exception as e:
        console.print(f"[red]✗ Check updates failed: {e}[/red]")
        raise click.Abort() from e
