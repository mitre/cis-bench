"""`cis-bench remove`: delete downloaded benchmarks from the local cache."""

import sys

import click
from rich.console import Console
from rich.markup import escape

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.config import Config
from cis_bench.exceptions import ConfigurationError
from cis_bench.utils.workbench_urls import resolve_benchmark_reference

console = Console()


@click.command(name="remove")
@click.argument("references", nargs=-1, required=True)
@click.option("--yes", "-y", is_flag=True, help="Remove without asking for confirmation")
def remove_cmd(references: tuple[str, ...], yes: bool) -> None:
    """Remove downloaded benchmarks from the local cache.

    REFERENCES are benchmark IDs or URLs, as accepted by `download`. The cached copy that
    `download`, `get` and `export <ID>` use is deleted; the benchmark stays in the catalog,
    so search still finds it and it can be downloaded again. Exported files such as
    ./benchmarks/*.json are not touched. To replace a bad copy instead, run
    `cis-bench download <ID> --force`.

    \b
    Examples:
        cis-bench remove 23598
        cis-bench remove 23598 22605 --yes
    """
    # Validate every reference before touching the database, so a typo removes nothing.
    try:
        benchmark_ids = list(dict.fromkeys(resolve_benchmark_reference(r)[0] for r in references))
    except ConfigurationError as e:
        console.print(
            f"\n[bold red]Configuration Error[/bold red]\n[yellow]{escape(str(e))}[/yellow]"
        )
        sys.exit(1)
    except ValueError as e:
        console.print(f"[red]✗ {escape(str(e))}[/red]")
        sys.exit(1)

    catalog_db_path = Config.get_catalog_db_path()
    if not catalog_db_path.exists():
        console.print(
            f"[yellow]No catalog database at {catalog_db_path}; nothing is downloaded.[/yellow]"
        )
        sys.exit(1)
    db = CatalogDatabase(catalog_db_path)

    to_remove: list[str] = []
    not_downloaded: list[str] = []
    for benchmark_id in benchmark_ids:
        downloaded = db.get_downloaded(benchmark_id)
        if downloaded is None:
            not_downloaded.append(benchmark_id)
            continue
        to_remove.append(benchmark_id)
        catalog_row = db.get_benchmark(benchmark_id) or {}
        title = catalog_row.get("title") or "(not in catalog)"
        version = downloaded.get("version") or catalog_row.get("version") or "?"
        downloaded_at = downloaded.get("downloaded_at")
        when = downloaded_at.strftime("%Y-%m-%d") if downloaded_at else "?"
        console.print(
            f"  [{benchmark_id}] {escape(str(title))} {escape(str(version))} (downloaded {when})"
        )

    for benchmark_id in not_downloaded:
        console.print(f"[yellow]  [{benchmark_id}] not downloaded; nothing to remove[/yellow]")

    if to_remove:
        if not yes:
            click.confirm(
                f"Remove {len(to_remove)} cached benchmark(s)?", default=False, abort=True
            )
        for benchmark_id in to_remove:
            db.delete_downloaded(benchmark_id)
            console.print(f"[green]✓[/green] Removed {benchmark_id} from the local cache")
        console.print(
            "\n[dim]Exported files in your output directory (./benchmarks by default) were "
            "not touched. To replace a bad copy instead of removing it, run:[/dim]"
        )
        console.print(f"  cis-bench download {to_remove[0]} --force", soft_wrap=True)

    sys.exit(1 if not_downloaded else 0)
