"""Cache management commands."""

import click
from rich.console import Console
from rich.table import Table

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.config import Config

console = Console()


@click.group()
def cache():
    """Manage local cache (catalog and benchmarks)."""
    pass


@cache.command()
@click.pass_context
def status(ctx):
    """Show status of cached data.

    Displays what's available for offline use:
    - Catalog entries (searchable benchmarks)
    - Downloaded benchmarks (exportable)
    """
    table = Table(title="Cache Status", show_header=True)
    table.add_column("Item", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")

    # Check catalog
    catalog_path = Config.get_catalog_db_path()
    if catalog_path.exists():
        try:
            db = CatalogDatabase(catalog_path)
            count = db.count_benchmarks()
            table.add_row(
                "Catalog",
                "✓ Available",
                f"{count} benchmarks indexed",
            )
        except Exception as e:
            table.add_row("Catalog", "✗ Error", str(e))
    else:
        table.add_row(
            "Catalog",
            "✗ Not found",
            "Run 'cis-bench catalog refresh' to build",
        )

    # Check downloaded benchmarks
    benchmarks_dir = Config.get_benchmarks_dir()
    if benchmarks_dir.exists():
        json_files = list(benchmarks_dir.glob("*.json"))
        if json_files:
            table.add_row(
                "Downloaded Benchmarks",
                "✓ Available",
                f"{len(json_files)} benchmarks cached",
            )
        else:
            table.add_row(
                "Downloaded Benchmarks",
                "○ Empty",
                "Use 'cis-bench download <id>' to fetch",
            )
    else:
        table.add_row(
            "Downloaded Benchmarks",
            "○ Not initialized",
            "Directory will be created on first download",
        )

    console.print(table)

    # Show what works offline
    console.print("\n[bold]Offline-capable commands:[/bold]")
    console.print("  • search - Search catalog (if built)")
    console.print("  • list - List downloaded benchmarks")
    console.print("  • export - Export downloaded benchmarks")
    console.print("  • info - Show benchmark details")
    console.print("  • cache status - This command")

    console.print("\n[bold]Network-required commands:[/bold]")
    console.print("  • auth login - Authenticate with CIS WorkBench")
    console.print("  • catalog refresh - Update catalog from WorkBench")
    console.print("  • download - Fetch benchmark from WorkBench")
    console.print("  • get - Combined search/download/export")
