"""find: search the text of the downloaded benchmarks' recommendations.

find reads the recommendation index in catalog.db, which holds exactly the downloaded
benchmarks. Nothing is sent to CIS WorkBench, so find works in offline mode.
"""

import logging
from contextlib import closing
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cis_bench.cli.helpers.output import output_data, showing_line
from cis_bench.cli.helpers.services import settings_from

console = Console()
# Messages that go with json or yaml output: stdout carries only the data.
notes = Console(stderr=True)
logger = logging.getLogger(__name__)


@click.command(name="find")
@click.argument("query")
@click.option(
    "--benchmark",
    "benchmark_id",
    metavar="ID",
    help="Search only this downloaded benchmark",
)
@click.option(
    "--profile",
    help="Keep recommendations of a profile whose name holds these words side by side "
    '("Level 2" keeps "Level 2 - Server" and "Level 2 - Workstation")',
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    help="Maximum results to show (default: CIS_BENCH_SEARCH_LIMIT, 100)",
)
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format (default: table)",
)
def find_cmd(query, benchmark_id, profile, limit, output_format):
    """Search the recommendations of the downloaded benchmarks.

    Every word of QUERY must be found, as the start of a word, in a recommendation's
    title, description, rationale, audit or remediation. Punctuation and words such as
    AND, OR and NOT are search words, not operators. Best match first.

    Only downloaded benchmarks are searched; the search command searches the catalog.
    Nothing is sent to CIS WorkBench, so find works offline.

    \b
    Examples:
        cis-bench find ssh
        cis-bench find "/etc/shadow permissions"
        cis-bench find firewall --profile "Level 1"
        cis-bench find auditd --benchmark 23598 --output-format json
    """
    settings = settings_from()
    if limit is None:
        limit = settings.search_limit
    structured = output_format != "table"

    found, downloaded = _search(settings.catalog_db_path, query, benchmark_id, profile)

    if not found:
        if not downloaded:
            _note(
                structured,
                "No benchmarks are downloaded, so there is nothing to search.",
                "[dim]Download one with:[/dim]",
                "  cis-bench download <ID>",
            )
        elif benchmark_id is not None and benchmark_id not in downloaded:
            _note(
                structured,
                f"Benchmark {escape(benchmark_id)} is not downloaded.",
                "[dim]Download it with:[/dim]",
                f"  cis-bench download {escape(benchmark_id)}",
            )
        elif not structured:
            console.print(f"[yellow]No downloaded recommendation matches {escape(query)}[/yellow]")
            if benchmark_id is not None or profile is not None:
                console.print(
                    "[dim]Try again without --benchmark or --profile to search every "
                    "downloaded benchmark.[/dim]"
                )
        if structured:
            output_data([], output_format)
        return

    shown = found[:limit]
    if structured:
        output_data(shown, output_format)
        return

    table = Table(
        title=f"Recommendations matching {escape(query)}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Benchmark", style="yellow", no_wrap=True)
    table.add_column("Ref", style="cyan", no_wrap=True)
    table.add_column("Title", overflow="fold", max_width=settings.table_title_width)
    table.add_column("Found in", style="dim")
    for result in shown:
        table.add_row(
            escape(result["benchmark_id"]),
            escape(result["ref"]),
            escape(result["title"]),
            ", ".join(result["matched_fields"]),
        )
    console.print(table)
    console.print(f"\n[dim]{showing_line(len(shown), len(found))}[/dim]")


def _search(
    catalog_db_path: Path, query: str, benchmark_id: str | None, profile: str | None
) -> tuple[list[dict], list[str]]:
    """Every hit, best first, and, when there is none, the downloaded benchmarks' IDs.

    Every hit is read in one search so the count shown beside a limited list is exact. The
    downloaded IDs are read only to say why nothing was found. An absent catalog.db holds
    nothing and is not created.

    Raises:
        click.ClickException: catalog.db exists but cannot be read (corrupt, locked).
    """
    if not catalog_db_path.exists():
        return [], []

    from sqlalchemy.exc import DatabaseError

    from cis_bench.catalog.database import CatalogDatabase

    try:
        with closing(CatalogDatabase(catalog_db_path)) as db:
            found = db.search_recommendations(
                query, benchmark_id=benchmark_id, profile=profile, limit=None
            )
            downloaded = [] if found else db.list_downloaded_benchmark_ids()
    except DatabaseError as error:
        raise click.ClickException(
            f"{catalog_db_path} cannot be read: {str(error).splitlines()[0]}"
        ) from error
    return found, downloaded


def _note(structured: bool, *lines: str) -> None:
    """Lines that explain an empty result: with the table on stdout, beside json or yaml on
    stderr."""
    for line in lines:
        (notes if structured else console).print(line)
