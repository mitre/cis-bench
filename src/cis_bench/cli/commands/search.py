"""Search command for CIS Benchmark CLI (catalog-aware)."""

import logging
import sys

import click
from rich.console import Console
from rich.markup import escape

from cis_bench.cli.helpers.output import benchmark_table, output_data, showing_line
from cis_bench.cli.helpers.services import settings_from

console = Console()
logger = logging.getLogger(__name__)


@click.command(name="search")
@click.argument("query", required=False)
@click.option("--platform", help="Filter by specific platform (e.g., ubuntu, aws, oracle-database)")
@click.option(
    "--platform-type", help="Filter by platform category (e.g., cloud, os, database, container)"
)
@click.option(
    "--status",
    default="Published",
    help="Filter by status (Published, Accepted, Draft, Archived, Rejected, Final Update, Withdrawn, or all)",
)
@click.option("--latest", is_flag=True, help="Show only latest version of each benchmark")
@click.option(
    "--limit", type=int, help="Maximum results to show (default: CIS_BENCH_SEARCH_LIMIT, 100)"
)
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "csv", "yaml"]),
    default="table",
    help="Output format (default: table)",
)
def search_cmd(query, platform, platform_type, status, latest, limit, output_format):
    """Search for CIS benchmarks (uses catalog if available).

    Searches the local catalog database if it exists, otherwise provides
    instructions for building the catalog. Multi-word queries match all terms
    (boolean keywords like AND, OR, and NOT are treated as literal search words).
    A version in the query (v2.1.0, 2.1) picks the release.

    \b
    Examples:
        # Basic search
        cis-bench search "ubuntu 20.04"
        cis-bench search "oracle cloud"
        cis-bench search "kubernetes v2.1.0"

    \b
        # Filter by platform category
        cis-bench search --platform-type cloud
        cis-bench search --platform-type database

    \b
        # Filter by specific platform
        cis-bench search --platform aws
        cis-bench search oracle --platform-type cloud

    \b
        # Scripting with JSON
        cis-bench search "ubuntu" --latest --output-format json | jq
        cis-bench search --platform-type cloud --output-format csv

    \b
    First time usage:
        cis-bench catalog refresh  # Build catalog (one-time, under a minute)
        cis-bench search "ubuntu"  # Then search
    """
    logger.debug(f"Search command: query={query}, platform={platform}, status={status}")

    settings = settings_from()
    if limit is None:
        limit = settings.search_limit

    # Check if catalog database exists
    catalog_db_path = settings.catalog_db_path

    if not catalog_db_path.exists():
        console.print("[yellow]⚠ Local catalog not found[/yellow]\n")
        console.print("The search command needs a local catalog database.")
        console.print("This is a one-time setup that takes under a minute.\n")
        console.print("[cyan]To build the catalog:[/cyan]")
        console.print("  cis-bench catalog refresh --browser chrome\n")
        console.print(
            "[dim]After building the catalog, you can search offline and it's much faster![/dim]"
        )
        sys.exit(1)

    # Load catalog database and search
    try:
        from cis_bench.catalog.database import CatalogDatabase, normalize_status_filter
        from cis_bench.catalog.search import CatalogSearch

        logger.debug(f"Loading catalog from {catalog_db_path}")
        db = CatalogDatabase(catalog_db_path)
        search = CatalogSearch(db)

        # Build filters; the database normalizes the status value (None/blank/'all' -> unfiltered)
        filters: dict[str, object] = {"status": status}
        if platform:
            filters["platform"] = platform
        if platform_type:
            filters["platform_type"] = platform_type
        if latest:
            filters["latest_only"] = True

        # Execute search
        if query:
            logger.debug(f"Searching for: {query}")
            if output_format == "table":
                console.print(f"[cyan]Searching for:[/cyan] {escape(str(query))}\n")
            results = search.search(query, limit=limit, **filters)
        else:
            logger.debug("Listing all benchmarks")
            if output_format == "table":
                console.print("[cyan]Listing benchmarks...[/cyan]\n")
            # Use search with empty query instead of list_all
            results = search.search("", limit=limit, **filters)

        if not results:
            if output_format == "table":
                console.print("[yellow]No results found[/yellow]")
                # Only suggest loosening filters when one is actually narrowing the results
                status_narrows = normalize_status_filter(status) is not None
                if platform or platform_type or status_narrows or latest:
                    console.print("\n[dim]Try removing some filters to see more results[/dim]")
            else:
                output_data([], output_format)
            sys.exit(0)

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

        # Display results (human-friendly table)
        console.print(f"[green]Found {len(results)} benchmark(s)[/green]\n")

        console.print(benchmark_table(results, title_width=settings.table_title_width))

        # Show usage hints
        # A list shorter than the limit is complete; only a full one may have been cut off.
        total = search.count(query or "", **filters) if len(results) >= limit else len(results)
        console.print(f"\n[dim]{showing_line(len(results), total)}[/dim]")
        console.print("\n[cyan]Next steps:[/cyan]")
        console.print("  cis-bench download <ID>                     # Download a benchmark")
        console.print("  cis-bench catalog info <ID>                 # Show detailed info")
        console.print(
            '  cis-bench get "<query>" --format xccdf        # Search + download + export in one step'
        )

    except Exception as e:
        logger.debug("Search failed", exc_info=True)
        console.print(f"[red]✗ Search failed: {escape(str(e))}[/red]")
        sys.exit(1)
