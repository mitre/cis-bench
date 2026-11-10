"""Cache commands: what cis-bench can do without CIS WorkBench.

The cache is catalog.db (the catalog and the downloaded benchmarks) and the saved session.
Nothing here contacts WorkBench, so every command works in offline mode.
"""

import logging
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cis_bench.cli.helpers.output import display_time, output_data
from cis_bench.cli.helpers.services import settings_from

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def cache():
    """What is available without CIS WorkBench (offline)."""


@cache.command()
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format (default: table)",
)
def status(output_format):
    """Show the catalog, the downloaded benchmarks and the saved session.

    Everything shown is read from this machine; nothing is sent to WorkBench. The
    session time is when it was saved: login saves it right after confirming it works.

    \b
    Example:
        cis-bench cache status
        cis-bench cache status --output-format json
    """
    settings = settings_from()
    report = {
        **_catalog_and_downloads(settings.catalog_db_path),
        "session": _session(settings.session_file_path),
    }

    if output_format != "table":
        output_data(report, output_format)
        return

    _print_catalog(report["catalog"])
    console.print()
    _print_downloaded(report["downloaded"])
    console.print()
    _print_session(report["session"])


def _catalog_and_downloads(catalog_db_path: Path) -> dict:
    """The catalog's facts and the downloaded benchmarks, both kept in catalog.db.

    An absent catalog.db holds neither and is not created. A downloaded benchmark the
    catalog does not list takes its title from the cached copy, as list shows it.
    """
    catalog: dict = {
        "present": False,
        "benchmarks": 0,
        "last_full_refresh": None,
        "last_update": None,
    }
    if not catalog_db_path.exists():
        return {"catalog": catalog, "downloaded": []}

    from cis_bench.catalog.database import CatalogDatabase, deserialize_benchmark_json

    with closing(CatalogDatabase(catalog_db_path)) as db:
        count = db.get_catalog_stats()["total_benchmarks"]
        catalog.update(
            present=count > 0,
            benchmarks=count,
            last_full_refresh=db.get_metadata("last_full_scrape"),
            last_update=db.get_metadata("last_update_scrape"),
        )
        downloaded = []
        for row in db.list_downloaded():
            item = {
                "benchmark_id": row["benchmark_id"],
                "title": row["title"],
                "version": row["version"],
                "downloaded_at": row["downloaded_at"].isoformat(),
            }
            if item["title"] is None:
                try:
                    cached = db.get_downloaded(row["benchmark_id"])
                    item["title"] = deserialize_benchmark_json(
                        cached["content_json"] if cached else ""
                    ).title
                except Exception:
                    logger.debug(
                        f"Cached copy of {row['benchmark_id']} cannot be read", exc_info=True
                    )
            downloaded.append(item)
    return {"catalog": catalog, "downloaded": downloaded}


def _session(session_file: Path) -> dict:
    """Whether a session is saved, and when the file was written."""
    if not session_file.exists():
        return {"present": False, "file": str(session_file), "saved_at": None}
    saved_at = datetime.fromtimestamp(session_file.stat().st_mtime, tz=UTC)
    return {"present": True, "file": str(session_file), "saved_at": saved_at.isoformat()}


def _when(value: str | None) -> str:
    return display_time(datetime.fromisoformat(value)) if value else "never"


def _print_catalog(catalog: dict) -> None:
    if not catalog["present"]:
        console.print("Catalog: none")
        console.print("[dim]Build it with:[/dim]")
        console.print("  cis-bench catalog refresh")
        return
    console.print(f"Catalog: {catalog['benchmarks']} benchmarks")
    console.print(f"  Last full refresh: {_when(catalog['last_full_refresh'])}")
    console.print(f"  Last update: {_when(catalog['last_update'])}")


def _print_downloaded(downloaded: list[dict]) -> None:
    if not downloaded:
        console.print("Downloaded benchmarks: none")
        console.print("[dim]Download one with:[/dim]")
        console.print("  cis-bench download <ID>")
        return
    table = Table(title=f"Downloaded benchmarks ({len(downloaded)})")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", overflow="fold")
    table.add_column("Version", style="green", no_wrap=True)
    table.add_column("Downloaded")
    for item in downloaded:
        title = (
            escape(item["title"])
            if item["title"] is not None
            else "[red]unreadable cached copy[/red]"
        )
        table.add_row(
            escape(item["benchmark_id"]),
            title,
            escape(item["version"] or ""),
            display_time(datetime.fromisoformat(item["downloaded_at"])),
        )
    console.print(table)


def _print_session(session: dict) -> None:
    if not session["present"]:
        console.print("Session: none")
        console.print("[dim]Log in with:[/dim]")
        console.print("  cis-bench auth login --browser chrome")
        return
    console.print(f"Session: saved {display_time(datetime.fromisoformat(session['saved_at']))}")
    # The path is printed whole, never folded to the terminal width
    console.print(f"[dim]  {escape(session['file'])}[/dim]", soft_wrap=True)
