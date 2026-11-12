"""Catalog management commands for CIS Benchmark CLI."""

from __future__ import annotations

import logging
import math
from contextlib import closing
from datetime import datetime
from gettext import ngettext
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.search import CatalogSearch
from cis_bench.cli.helpers.errors import report_unreachable
from cis_bench.cli.helpers.output import display_time, output_data, showing_line
from cis_bench.cli.helpers.services import (
    catalog_scraper,
    settings_from,
    workbench_scraper,
    workbench_session,
)
from cis_bench.exceptions import AuthenticationError, FetchError
from cis_bench.utils.workbench_urls import is_benchmark_id

if TYPE_CHECKING:
    from cis_bench.fetcher.workbench import WorkbenchScraper

console = Console()
logger = logging.getLogger(__name__)


BROWSER_HELP = "Browser to read cookies from (default: the CIS_BENCH_BROWSER setting)"


def _validate_rate_limit(
    _ctx: click.Context, _param: click.Parameter, value: float | None
) -> float | None:
    """Click callback: refuse a gap between requests that is not a finite number above zero,
    or so small that the request rate it stands for (1 / gap) is not a finite number."""
    if value is None:
        return None
    if not math.isfinite(value) or value <= 0:
        raise click.BadParameter(f"must be a finite number of seconds greater than 0, got {value}")
    if not math.isfinite(1 / value):
        raise click.BadParameter(f"is too small to be a gap between requests, got {value}")
    return value


def get_catalog_db() -> CatalogDatabase:
    """The catalog database in the data folder, creating the folder if needed."""
    settings = settings_from()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return CatalogDatabase(settings.catalog_db_path)


def require_catalog_db(
    missing_message: str = "Catalog not found. Run 'cis-bench catalog refresh' first.",
) -> CatalogDatabase:
    """Return an existing catalog database or abort with a user-facing prompt."""
    db = get_catalog_db()
    if not db.db_path.exists():
        db.close()
        console.print(f"[yellow]{missing_message}[/yellow]")
        raise click.Abort()
    return db


@click.group()
def catalog():
    """Manage CIS benchmark catalog.

    The catalog feature allows you to browse, search, and download benchmarks
    from the CIS WorkBench without knowing the exact URL.

    \b
    Example workflow:
        cis-bench catalog refresh              # Build catalog (one-time, under a minute)
        cis-bench catalog search "ubuntu 20"   # Find benchmarks
        cis-bench catalog download 23598       # Download by ID
    """
    pass


@catalog.command()
@click.option("--browser", help=BROWSER_HELP)
@click.option("--max-pages", type=int, help="Limit pages to scrape (for testing)")
@click.option(
    "--rate-limit",
    default=None,
    type=float,
    callback=_validate_rate_limit,
    metavar="SECONDS",
    help=(
        "Seconds between requests to WorkBench for this run "
        "(default: 1 / the CIS_BENCH_REQUESTS_PER_SECOND setting)"
    ),
)
def refresh(browser, max_pages, rate_limit):
    """Refresh catalog from CIS WorkBench (scrape all pages).

    This builds or updates the complete catalog by scraping all benchmark
    listing pages from CIS WorkBench (about 80 pages, about 1,500 benchmarks).
    Pages are fetched in parallel, paced by the CIS_BENCH_* request settings; a
    full refresh takes under a minute with the defaults.

    \b
    Examples:
        cis-bench catalog refresh
        cis-bench catalog refresh --max-pages 5  # Test with 5 pages
        cis-bench catalog refresh --rate-limit 1  # One request per second (gentler)
    """
    try:
        # The session comes first: nothing is created (not even catalog.db) for a run that
        # cannot log in or is offline. The session helper validates the saved or freshly
        # extracted session and raises AuthenticationError when WorkBench accepts neither.
        settings = settings_from()
        with console.status("[cyan]Validating session...[/cyan]"):
            # Pace every request of this run at the requested gap, from the session check on;
            # the scraper's worker threads share the session's adapter, so they all follow it.
            session = workbench_session(
                settings,
                needs="read the catalog",
                browser=browser or settings.browser,
                requests_per_second=None if rate_limit is None else 1 / rate_limit,
            )
        console.print("[green]✓[/green] Session valid\n")

        with closing(get_catalog_db()) as db:
            db.initialize_schema()

            # Create scraper
            scraper = catalog_scraper(settings, db, session)

            # Scrape catalog
            pages_msg = (
                ngettext("{count} page", "{count} pages", max_pages).format(count=max_pages)
                if max_pages
                else "all pages"
            )
            console.print(f"[cyan]Scraping catalog ({pages_msg})...[/cyan]")

            stats = scraper.scrape_full_catalog(max_pages=max_pages)

            # Show results
            console.print("\n[green]✓[/green] Catalog refresh complete!")
            console.print(f"  Benchmarks: [yellow]{stats['total_benchmarks']}[/yellow]")
            console.print(f"  Pages: [yellow]{stats['pages_scraped']}[/yellow]")
            if stats["withdrawn"] is None:
                console.print("  Withdrawn: not checked (the refresh was not complete)")
            else:
                console.print(f"  Withdrawn: [yellow]{stats['withdrawn']}[/yellow]")

            if stats["failed_pages"]:
                console.print(
                    f"  Failed pages: [red]{len(stats['failed_pages'])}[/red] - {stats['failed_pages']}"
                )

            # Show database stats
            db_stats = db.get_catalog_stats()
            console.print("\n[cyan]Catalog statistics:[/cyan]")
            console.print(
                f"  Total benchmarks: {db_stats['total_benchmarks']} "
                f"(of which withdrawn: {db_stats['withdrawn_benchmarks']})"
            )
            console.print(f"  Platforms: {db_stats['platforms']}")
            console.print(f"  Communities: {db_stats['communities']}")

    except (click.Abort, click.ClickException):
        raise  # Click reports its own errors (offline mode refuses with one)
    except FetchError as e:
        report_unreachable(console, e)
        raise click.Abort() from e
    except AuthenticationError as e:
        console.print("[red]✗ Authentication required[/red]")
        console.print(f"[yellow]{escape(str(e))}[/yellow]")
        console.print("[yellow]Please run: cis-bench auth login --browser chrome[/yellow]")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]✗ Catalog refresh failed: {escape(str(e))}[/red]")
        raise click.Abort() from e


@catalog.command()
@click.option("--browser", help=BROWSER_HELP)
def update(browser):
    """Quick catalog update (scrape page 1 only).

    Faster than full refresh - only checks the first page for new/updated
    benchmarks. Takes a few seconds.

    \b
    Example:
        cis-bench catalog update
    """
    try:
        with closing(
            require_catalog_db(
                missing_message="Catalog not initialized. Run 'cis-bench catalog refresh' first."
            )
        ) as db:
            db.initialize_schema()

            settings = settings_from()
            session = workbench_session(
                settings, needs="read the catalog", browser=browser or settings.browser
            )
            scraper = catalog_scraper(settings, db, session)

            console.print("[cyan]Updating catalog (page 1)...[/cyan]")

            stats = scraper.scrape_page_one_update()

            console.print("[green]✓[/green] Catalog updated!")
            console.print(f"  New benchmarks: [yellow]{stats['new_count']}[/yellow]")
            console.print(f"  Updated: [yellow]{stats['updated_count']}[/yellow]")

    except (click.Abort, click.ClickException):
        raise  # Click reports its own errors (offline mode refuses with one)
    except FetchError as e:
        report_unreachable(console, e)
        raise click.Abort() from e
    except AuthenticationError as e:
        console.print("[red]✗ Authentication required[/red]")
        console.print(f"[yellow]{escape(str(e))}[/yellow]")
        console.print("[yellow]Please run: cis-bench auth login --browser chrome[/yellow]")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]✗ Update failed: {escape(str(e))}[/red]")
        raise click.Abort() from e


_STATUS_HELP = (
    "Filter by status (Published, Accepted, Draft, Archived, Rejected, Final Update, "
    "Withdrawn, or all)"
)


@catalog.command()
@click.argument("query", required=False)
@click.option("--platform", help="Filter by platform")
@click.option("--status", default="Published", help=_STATUS_HELP)
@click.option("--latest", is_flag=True, help="Latest versions only")
@click.option("--limit", type=int, help="Max results (default: CIS_BENCH_SEARCH_LIMIT, 100)")
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
        with closing(require_catalog_db()) as db:
            search_obj = CatalogSearch(db)

            if limit is None:
                limit = settings_from().search_limit

            results = search_obj.search(
                query=query or "",
                platform=platform,
                status=status,
                latest_only=latest,
                limit=limit,
            )

            if not results:
                if output_format != "table":
                    output_data([], output_format)
                else:
                    console.print(
                        f"[yellow]No benchmarks found matching: {escape(str(query))}[/yellow]"
                    )
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
            found = ngettext(
                "Found {count} benchmark:", "Found {count} benchmarks:", len(results)
            ).format(count=len(results))
            console.print(f"\n[cyan]{found}[/cyan]\n")

            for r in results:
                formatted = search_obj.format_result_for_display(r)
                console.print(escape(formatted))
                console.print()  # Blank line

            # A list shorter than the limit is complete; only a full one may have been cut off.
            total = (
                search_obj.count(
                    query=query or "", platform=platform, status=status, latest_only=latest
                )
                if len(results) >= limit
                else len(results)
            )
            console.print(f"[dim]{showing_line(len(results), total)}[/dim]")

    except (click.Abort, click.ClickException):
        raise  # Click reports its own errors (offline mode refuses with one)
    except Exception as e:
        console.print(f"[red]✗ Search failed: {escape(str(e))}[/red]")
        raise click.Abort() from e


@catalog.command(name="list")
@click.option("--platform", help="Filter by platform")
@click.option("--status", default="Published", help=_STATUS_HELP)
@click.option("--latest", is_flag=True, help="Latest versions only")
@click.option("--limit", type=int, help="Max results (default: CIS_BENCH_SEARCH_LIMIT, 100)")
def list_cmd(platform, status, latest, limit):
    """List benchmarks in catalog.

    \b
    Examples:
        cis-bench catalog list
        cis-bench catalog list --platform "Operating System" --latest
        cis-bench catalog list --status Withdrawn
    """
    try:
        with closing(require_catalog_db()) as db:
            search_obj = CatalogSearch(db)
            if limit is None:
                limit = settings_from().search_limit

            filters = {"platform": platform, "status": status, "latest_only": latest}
            results = search_obj.search(query="", limit=limit, **filters)

            if not results:
                console.print("[yellow]No benchmarks found.[/yellow]")
                return

            listed = ngettext("{count} benchmark:", "{count} benchmarks:", len(results)).format(
                count=len(results)
            )
            console.print(f"\n[cyan]{listed}[/cyan]\n")

            for r in results:
                formatted = search_obj.format_result_for_display(r)
                console.print(escape(formatted))
                console.print()

            total = search_obj.count(**filters) if len(results) >= limit else len(results)
            console.print(f"[dim]{showing_line(len(results), total)}[/dim]")

    except (click.Abort, click.ClickException):
        raise  # Click reports its own errors (offline mode refuses with one)
    except Exception as e:
        console.print(f"[red]✗ List failed: {escape(str(e))}[/red]")
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
        with closing(require_catalog_db()) as db:
            bench = db.get_benchmark(benchmark_id)

            if not bench:
                console.print(
                    f"[red]Benchmark {escape(str(benchmark_id))} not found in catalog.[/red]"
                )
                raise click.Abort()

            # Output in requested format
            if output_format != "table":
                output_data(bench, output_format)

            # Display detailed info (table format)
            console.print(f"\n[bold]{escape(str(bench['title']))}[/bold]")

            if bench.get("version"):
                console.print(f"Version: {escape(str(bench['version']))}")

            console.print(f"ID: {escape(str(bench['benchmark_id']))}")
            console.print(f"Status: {escape(str(bench['status']))}")

            if bench.get("platform"):
                console.print(f"Platform: {escape(str(bench['platform']))}")

            if bench.get("community"):
                console.print(f"Community: {escape(str(bench['community']))}")

            if bench.get("owner"):
                console.print(f"Owner: {escape(str(bench['owner']))}")

            if bench.get("published_date"):
                console.print(f"Published: {escape(str(bench['published_date']))}")

            console.print(f"\nURL: {escape(str(bench['url']))}")

            if bench.get("description"):
                console.print(f"\n[dim]{escape(bench['description'][:200])}...[/dim]")

            console.print(
                f"\n[cyan]Download:[/cyan] cis-bench catalog download {escape(str(benchmark_id))}"
            )

    except (click.Abort, click.ClickException):
        raise  # Click reports its own errors (offline mode refuses with one)
    except Exception as e:
        console.print(f"[red]✗ Info failed: {escape(str(e))}[/red]")
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
        with closing(require_catalog_db()) as db:
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
                table.add_row(escape(str(p["name"])), str(p["count"]))

            console.print()
            console.print(table)

    except (click.Abort, click.ClickException):
        raise  # Click reports its own errors (offline mode refuses with one)
    except Exception as e:
        console.print(f"[red]✗ Platforms list failed: {escape(str(e))}[/red]")
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
        with closing(require_catalog_db()) as db:
            catalog_stats = db.get_catalog_stats()
            last_scrape = db.get_metadata("last_full_scrape")

            stats_payload: dict[str, int | str | None] = {
                **catalog_stats,
                "last_full_scrape": last_scrape,
            }

            # Output in requested format
            if output_format != "table":
                output_data(stats_payload, output_format)

            # Human display
            console.print("\n[bold]Catalog Statistics[/bold]\n")
            console.print(f"Total benchmarks: [yellow]{catalog_stats['total_benchmarks']}[/yellow]")
            console.print(f"Published: [yellow]{catalog_stats['published_benchmarks']}[/yellow]")
            console.print(f"Withdrawn: [yellow]{catalog_stats['withdrawn_benchmarks']}[/yellow]")
            console.print(f"Downloaded: [yellow]{catalog_stats['downloaded_benchmarks']}[/yellow]")
            console.print(f"Platforms: [yellow]{catalog_stats['platforms']}[/yellow]")
            console.print(f"Communities: [yellow]{catalog_stats['communities']}[/yellow]")

            if last_scrape:
                console.print(
                    f"\nLast catalog refresh: [dim]{display_time(datetime.fromisoformat(last_scrape))}[/dim]"
                )

    except (click.Abort, click.ClickException):
        raise  # Click reports its own errors (offline mode refuses with one)
    except Exception as e:
        console.print(f"[red]✗ Stats failed: {escape(str(e))}[/red]")
        raise click.Abort() from e


@catalog.command()
@click.argument("benchmark_id_or_name")
@click.option("--browser", help=BROWSER_HELP)
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
        with closing(require_catalog_db()) as db:
            from cis_bench.catalog.downloader import CatalogDownloader

            settings = settings_from()

            def connect() -> WorkbenchScraper:
                # Logs in (saved session, else the browser's cookies) only when a download is
                # needed: an up-to-date copy is reported without contacting WorkBench.
                session = workbench_session(
                    settings, needs="download a benchmark", browser=browser or settings.browser
                )
                return workbench_scraper(settings, session)

            downloader = CatalogDownloader(db, connect)

            # Determine if ID or name
            if is_benchmark_id(benchmark_id_or_name):
                # Download by ID
                benchmark_id = benchmark_id_or_name.strip()
                console.print(f"[cyan]Downloading benchmark {escape(benchmark_id)}...[/cyan]")
                result = downloader.download_by_id(benchmark_id, force=force)
            else:
                # Download by name
                console.print(f"[cyan]Searching for: {escape(str(benchmark_id_or_name))}[/cyan]")
                result = downloader.download_by_name(
                    benchmark_id_or_name, latest=True, interactive=interactive, force=force
                )

            # Show result
            if result["status"] == "already_current":
                console.print(f"[green]✓[/green] {escape(str(result['message']))}")
            elif result["status"] == "unchanged":
                console.print(f"[green]✓[/green] {escape(str(result['message']))}")
            else:
                console.print(
                    f"[green]✓[/green] Downloaded benchmark {escape(str(result['benchmark_id']))}"
                )
                console.print(f"  Recommendations: {result['recommendation_count']}")
                console.print(f"  Size: {result['file_size'] / 1024:.1f} KB")

    except (click.Abort, click.ClickException):
        raise  # Click reports its own errors (offline mode refuses with one)
    except FetchError as e:
        report_unreachable(console, e)
        raise click.Abort() from e
    except AuthenticationError as e:
        console.print("[red]✗ Authentication required[/red]")
        console.print(f"[yellow]{escape(str(e))}[/yellow]")
        console.print("[yellow]Please run: cis-bench auth login --browser chrome[/yellow]")
        raise click.Abort() from e
    except ValueError as e:
        console.print(f"[red]✗ {escape(str(e))}[/red]")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]✗ Download failed: {escape(str(e))}[/red]")
        logger.debug("Download error", exc_info=True)
        raise click.Abort() from e


@catalog.command(name="check-updates")
@click.option(
    "--offline",
    is_flag=True,
    help="Compare versions only; do not fetch publication dates from WorkBench",
)
def check_updates(offline):
    """Check downloaded benchmarks for available updates.

    Compares each downloaded benchmark's version with the catalog, and (unless
    --offline) fetches its WorkBench page to see whether it was published again
    after you downloaded it.

    \b
    Example:
        cis-bench catalog check-updates
        cis-bench catalog check-updates --offline
    """
    try:
        with closing(require_catalog_db()) as db:
            if not db.list_downloaded_benchmark_ids():
                console.print("No benchmarks are downloaded, so there is nothing to check.")
                console.print("[dim]Download one first:[/dim]")
                console.print("  cis-bench download <ID>")
                return

            # Its own --offline, or offline mode, compares versions only.
            settings = settings_from()
            if not (offline or settings.offline):
                session = workbench_session(settings, needs="read publication dates")
                console.print("[cyan]Checking WorkBench publication dates...[/cyan]")
                refreshed = catalog_scraper(settings, db, session).refresh_downloaded_pages()
                checked = ngettext(
                    "Checked {count} downloaded benchmark",
                    "Checked {count} downloaded benchmarks",
                    refreshed,
                ).format(count=refreshed)
                console.print(f"[green]✓[/green] {checked}\n")

            updates = db.check_updates_available()

            if not updates:
                console.print("[green]✓[/green] All downloaded benchmarks are up-to-date!")
                return

            available = ngettext(
                "Updates available for {count} benchmark:",
                "Updates available for {count} benchmarks:",
                len(updates),
            ).format(count=len(updates))
            console.print(f"\n[yellow]{available}[/yellow]\n")

            for u in updates:
                console.print(f"  [{u['benchmark_id']}] {escape(str(u['title']))}")
                if u["reason"] == "newer version in catalog":
                    console.print(
                        f"      Version: {escape(str(u['downloaded_version'] or '?'))} -> {escape(str(u['catalog_version']))}"
                    )
                else:
                    console.print(f"      WorkBench published {escape(str(u['published_date']))}")
                console.print(f"      Downloaded: {display_time(u['downloaded_at'])}")
                console.print()

            console.print(
                "[cyan]Use 'cis-bench catalog download <id>' to download the update.[/cyan]"
            )

    except (click.Abort, click.ClickException):
        raise  # Click reports its own errors (offline mode refuses with one)
    except FetchError as e:
        report_unreachable(console, e)
        raise click.Abort() from e
    except AuthenticationError as e:
        console.print("[red]✗ Authentication required[/red]")
        console.print(f"[yellow]{escape(str(e))}[/yellow]")
        console.print(
            "[yellow]Please run: cis-bench auth login --browser chrome, or use --offline[/yellow]"
        )
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]✗ Check updates failed: {escape(str(e))}[/red]")
        raise click.Abort() from e
