"""List command for CIS Benchmark CLI.

"Downloaded" means in the cache (catalog.db); the files in the benchmarks folder are exports,
which the user may move, rename or delete, and are listed separately.
"""

import logging
import os

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cis_bench.catalog.database import CatalogDatabase, deserialize_benchmark_json
from cis_bench.cli.helpers.output import display_time, output_data
from cis_bench.cli.helpers.services import settings_from

console = Console()
logger = logging.getLogger(__name__)

CSV_FIELDS = [
    "benchmark_id",
    "title",
    "version",
    "recommendations",
    "cis_v8",
    "mitre",
    "nist",
    "downloaded_at",
    "error",
]


@click.command(name="list")
@click.option(
    "--output-dir",
    help="Folder whose exported files to list (default: <data dir>/benchmarks)",
)
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "csv", "yaml"]),
    default="table",
    help="Output format (default: table; csv holds the downloaded benchmarks only)",
)
def list_benchmarks(output_dir, output_format):
    """List downloaded benchmarks, and the exported files in the benchmarks folder.

    A benchmark is downloaded when it is in the cache, where download and get put it;
    the files the exports wrote are listed separately and stay yours to move or delete.

    \b
    Example:
        cis-bench list
        cis-bench list --output-dir ./my_benchmarks
    """
    settings = settings_from()
    if output_dir is None:
        output_dir = settings.benchmarks_dir

    downloaded = _downloaded_benchmarks(settings.catalog_db_path)
    exported = {"folder": str(output_dir), "files": _exported_files(output_dir)}

    if output_format != "table":
        # Structured output carries the instant in ISO 8601 with its offset
        structured = [
            {**item, "downloaded_at": item["downloaded_at"].isoformat()} for item in downloaded
        ]
        if output_format == "csv":
            output_data(structured, output_format, csv_fields=CSV_FIELDS)
        else:
            output_data({"downloaded": structured, "exported_files": exported}, output_format)
        return

    if downloaded:
        console.print(_downloaded_table(downloaded))
    else:
        console.print("No benchmarks are downloaded.")
        console.print("[dim]Download one first:[/dim]")
        console.print("  cis-bench download <ID>")

    console.print()
    # Paths and file names are printed whole, never folded to the terminal width
    console.print(
        f"[cyan]Exported files in {escape(exported['folder'])} ({len(exported['files'])}):[/cyan]",
        soft_wrap=True,
    )
    if exported["files"]:
        for name in exported["files"]:
            console.print(f"  {escape(name)}", soft_wrap=True)
    else:
        console.print("  none")


def _downloaded_benchmarks(catalog_db_path) -> list[dict]:
    """The cached benchmarks with their compliance counts and download time, in ID order.

    One cached copy is read at a time. A copy that cannot be read is listed with an
    error instead of stopping the list; the title of a benchmark the catalog does not
    list comes from the copy itself.
    """
    if not catalog_db_path.exists():
        return []
    db = CatalogDatabase(catalog_db_path)
    rows = []
    for row in db.list_downloaded():
        item = {
            "benchmark_id": row["benchmark_id"],
            "title": row["title"],
            "version": row["version"],
            "downloaded_at": row["downloaded_at"],
        }
        try:
            cached = db.get_downloaded(row["benchmark_id"])
            benchmark = deserialize_benchmark_json(cached["content_json"] if cached else "")
        except Exception as error:
            logger.debug(f"Cached copy of {row['benchmark_id']} cannot be read", exc_info=True)
            item["error"] = f"unreadable cached copy: {error}".splitlines()[0]
        else:
            item.update(
                title=item["title"] or benchmark.title,
                recommendations=benchmark.total_recommendations,
                cis_v8=sum(
                    1 for r in benchmark.recommendations for c in r.cis_controls if c.version == 8
                ),
                mitre=sum(1 for r in benchmark.recommendations if r.mitre_mapping),
                nist=sum(len(r.nist_controls) for r in benchmark.recommendations),
            )
        rows.append(item)
    return rows


def _exported_files(folder) -> list[str]:
    """The files in the exports folder, by name; an absent folder has none."""
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if os.path.isfile(os.path.join(folder, name)))


def _downloaded_table(downloaded: list[dict]) -> Table:
    table = Table(title=f"Downloaded benchmarks ({len(downloaded)})")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", overflow="fold")
    table.add_column("Version", style="green", no_wrap=True)
    table.add_column("Recs", justify="right", style="yellow")
    table.add_column("CIS v8", justify="right")
    table.add_column("MITRE", justify="right")
    table.add_column("NIST", justify="right")
    table.add_column("Downloaded")
    for item in downloaded:
        if "error" in item:
            table.add_row(
                escape(item["benchmark_id"]),
                f"[red]{escape(item['error'])}[/red]",
                escape(item["version"] or ""),
                "?",
                "?",
                "?",
                "?",
                display_time(item["downloaded_at"]),
            )
            continue
        table.add_row(
            escape(item["benchmark_id"]),
            escape(item["title"]),
            escape(item["version"] or ""),
            str(item["recommendations"]),
            str(item["cis_v8"]) if item["cis_v8"] > 0 else "-",
            str(item["mitre"]) if item["mitre"] > 0 else "-",
            str(item["nist"]) if item["nist"] > 0 else "-",
            display_time(item["downloaded_at"]),
        )
    return table
