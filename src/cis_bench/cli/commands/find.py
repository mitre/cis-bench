"""Find command - search within benchmark recommendations."""

import logging

import click
from rich.console import Console
from rich.table import Table

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.cli.helpers.output import output_data
from cis_bench.config import Config

console = Console()
logger = logging.getLogger(__name__)


@click.command(name="find")
@click.argument("query")
@click.option(
    "--benchmark",
    "-b",
    "benchmark_id",
    help="Filter results to specific benchmark ID",
)
@click.option(
    "--profile",
    "-p",
    help="Filter by profile level (e.g., 'Level 1', 'Level 2')",
)
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=50,
    help="Maximum results to return (default: 50)",
)
@click.pass_context
def find_cmd(ctx, query, benchmark_id, profile, output_format, limit):
    """Search within downloaded benchmark recommendations.

    Searches recommendation titles, descriptions, audit procedures,
    remediation steps, and control mappings (NIST, CIS Controls).

    \b
    Examples:
        cis-bench find "SSH"                    # Find SSH-related rules
        cis-bench find "firewall" --profile "Level 1"
        cis-bench find "AC-7" --output-format json
        cis-bench find "SELinux" -b 12345       # Search in specific benchmark

    \b
    Searches these fields:
        - Recommendation title
        - Description
        - Rationale
        - Audit procedure
        - Remediation steps
        - NIST control mappings
        - CIS Controls mappings

    \b
    Note: Only searches downloaded benchmarks. Use 'cis-bench download'
    to fetch benchmarks first.
    """
    # Get database
    db_path = Config.get_catalog_db_path()

    if not db_path.exists():
        console.print("[yellow]No catalog database found.[/yellow]")
        console.print("Run 'cis-bench catalog refresh' to build the catalog.")
        return

    try:
        db = CatalogDatabase(db_path)
        results = db.search_recommendations(
            query=query,
            benchmark_id=benchmark_id,
            profile=profile,
            limit=limit,
        )

        if not results:
            console.print(f"[yellow]No recommendations found matching '{query}'[/yellow]")
            console.print("\nTip: Make sure you have downloaded benchmarks first:")
            console.print("  cis-bench download <benchmark_id>")
            return

        # Format output
        if output_format == "json":
            output_data(results, "json")
        elif output_format == "csv":
            output_data(results, "csv")
        else:
            _display_results_table(results, query)

    except Exception as e:
        logger.exception("Error searching recommendations")
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort() from e


def _display_results_table(results: list[dict], query: str):
    """Display search results in a rich table."""
    table = Table(
        title=f"Recommendations matching '{query}'",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Benchmark", style="dim", width=15)
    table.add_column("Ref", style="cyan", width=8)
    table.add_column("Title", width=50)
    table.add_column("Profile", style="dim", width=15)

    for result in results:
        table.add_row(
            result.get("benchmark_id", ""),
            result.get("ref", ""),
            result.get("title", ""),
            ", ".join(result.get("profiles", []))[:15],
        )

    console.print(table)
    console.print(f"\n[dim]Found {len(results)} matching recommendations[/dim]")
