"""Browse command - interactive TUI for catalog exploration."""

import sys

import click
from rich.console import Console

from cis_bench.config import Config

console = Console()


@click.command(name="browse")
@click.option("--platform", help="Filter by specific platform (e.g., ubuntu, aws)")
@click.option(
    "--platform-type", help="Filter by platform category (cloud, os, database, container)"
)
@click.option("--status", default="Published", help="Filter by status (Published, Archived, Draft)")
@click.option("--latest", is_flag=True, help="Show only latest version of each benchmark")
@click.option("--query", "-q", help="Initial search query to filter results")
@click.option(
    "--limit", type=int, help="Maximum benchmarks to load (default: from config, typically 1000)"
)
@click.pass_context
def browse_cmd(ctx, platform, platform_type, status, latest, query, limit):
    """Browse CIS benchmarks interactively in a TUI.

    Opens an interactive terminal browser to explore the catalog.
    Supports search, filtering, multi-select, and keyboard navigation.

    \b
    Keyboard Shortcuts:
        /           Search/filter benchmarks
        Space       Toggle selection (for batch operations)
        g           Jump to benchmark ID
        ?           Show help with all keybindings
        Tab         Switch between list and detail panes
        j/k         Navigate up/down
        f           Toggle fullscreen detail view
        q/Esc       Quit

    \b
    Examples:
        cis-bench browse                              # Browse all benchmarks
        cis-bench browse --platform-type cloud        # Only cloud benchmarks
        cis-bench browse --latest                     # Only latest versions
        cis-bench browse -q "ubuntu"                  # Start with search

    \b
    First time usage:
        cis-bench catalog refresh    # Build catalog first (~2 min)
        cis-bench browse             # Then browse
    """
    # Check if offline mode
    offline = ctx.obj.get("offline", False) if ctx.obj else False

    # Use Config defaults if not provided
    if limit is None:
        limit = Config.get_search_default_limit()

    # Check if catalog database exists
    catalog_db_path = Config.get_catalog_db_path()

    if not catalog_db_path.exists():
        console.print("[yellow]⚠ Local catalog not found[/yellow]\n")
        console.print("The browse command needs a local catalog database.")
        console.print("This is a one-time setup.\n")
        console.print("[cyan]To build the catalog:[/cyan]")
        console.print("  cis-bench catalog refresh --browser chrome\n")
        sys.exit(1)

    # Load catalog and get benchmarks
    try:
        from cis_bench.catalog.database import CatalogDatabase
        from cis_bench.catalog.search import CatalogSearch

        db = CatalogDatabase(catalog_db_path)
        search = CatalogSearch(db)

        # Build filters
        filters = {}
        if platform:
            filters["platform"] = platform
        if platform_type:
            filters["platform_type"] = platform_type
        if status:
            filters["status"] = status
        if latest:
            filters["latest_only"] = True

        # Get benchmarks
        benchmarks = search.search(query or "", limit=limit, **filters)

        if not benchmarks:
            console.print("[yellow]No benchmarks found matching your filters[/yellow]")
            if platform or status or latest:
                console.print("\n[dim]Try removing some filters to see more results[/dim]")
            sys.exit(0)

        # Launch TUI
        from cis_bench.cli.commands.catalog_tui import run_catalog_browser

        run_catalog_browser(benchmarks, offline=offline)

    except Exception as e:
        console.print(f"[red]✗ Failed to browse catalog: {e}[/red]")
        sys.exit(1)
