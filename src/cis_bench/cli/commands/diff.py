"""Diff command: compare two versions of a benchmark."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cis_bench.catalog.versions import version_sort_key
from cis_bench.cli.helpers.services import settings_from
from cis_bench.utils.workbench_urls import is_benchmark_id

if TYPE_CHECKING:
    from cis_bench.config import Settings

console = Console()

# Titles at least this similar (difflib ratio) pair a removed ref with an added one.
RENUMBER_SIMILARITY = 0.85

# WorkBench gives every release new URLs and artifact IDs, so they are not content.
_WORKBENCH_IDENTIFIER_PATHS = ["root['url']", "root['parent']['url']"]
_WORKBENCH_IDENTIFIER_REGEX_PATHS = [r"^root\['artifacts'\]\[\d+\]\['id'\]$"]


@click.command(name="diff")
@click.argument("old_benchmark")
@click.argument("new_benchmark")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "json", "markdown", "summary"]),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="List the changed fields of each modified recommendation under the table",
)
@click.pass_context
def diff_cmd(ctx, old_benchmark, new_benchmark, output_format, verbose):
    """Compare two versions of a benchmark to see what changed.

    Each argument is the ID of a downloaded benchmark or a benchmark JSON file.

    \b
    Examples:
        cis-bench diff 22605 23598                    # Two downloaded benchmarks
        cis-bench diff old.json new.json              # Two files
        cis-bench diff 22605 23598 --format markdown  # Markdown document
        cis-bench diff 22605 23598 --format json      # JSON for scripts
        cis-bench diff 22605 23598 --verbose          # Changed fields per recommendation

    \b
    Change types:
        ✚ Added      - Ref only in the newer version
        ✖ Removed    - Ref only in the older version
        ⟳ Modified   - Same ref, different content
        ↷ Renumbered - A removed ref and an added ref with near-identical titles
    """
    settings = settings_from(ctx)
    old_data = _load_benchmark(old_benchmark, settings)
    new_data = _load_benchmark(new_benchmark, settings)

    comparison = compare_benchmarks(old_data, new_data)

    if output_format == "json":
        _output_json(comparison)
    elif output_format == "markdown":
        _output_markdown(comparison)
    elif output_format == "summary":
        _output_summary(comparison)
    else:
        _output_table(comparison, verbose)


def _load_benchmark(identifier: str, settings: Settings) -> dict:
    """A benchmark as a dict: digits are a downloaded benchmark's ID, anything else a file.

    Raises:
        click.ClickException: The ID is not downloaded, or the file is missing, unreadable
            or not a benchmark.
    """
    if is_benchmark_id(identifier):
        benchmark_id = identifier.strip()
        downloaded = None
        if settings.catalog_db_path.exists():
            from cis_bench.catalog.database import CatalogDatabase

            downloaded = CatalogDatabase(settings.catalog_db_path).get_downloaded(benchmark_id)
        if downloaded is None:
            raise click.ClickException(
                f"Benchmark {benchmark_id} is not downloaded. Download it first:\n"
                f"  cis-bench download {benchmark_id}"
            )
        text, source = downloaded["content_json"], f"benchmark {benchmark_id}"
    else:
        path = Path(identifier)
        if not path.is_file():
            raise click.ClickException(f"No benchmark file {identifier}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise click.ClickException(
                f"{identifier} is not a benchmark JSON file: {error}"
            ) from error
        except OSError as error:
            raise click.ClickException(f"{identifier} could not be read: {error}") from error
        source = identifier

    return _parse_benchmark(text, source)


def _parse_benchmark(text: str, source: str) -> dict:
    """The benchmark JSON as a dict, after checking it against the Benchmark model."""
    from pydantic import ValidationError

    from cis_bench.models.benchmark import Benchmark

    try:
        data = json.loads(text)
        Benchmark.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as error:
        raise click.ClickException(f"{source} is not a benchmark JSON file: {error}") from error
    benchmark: dict = data
    return benchmark


def _ref_key(ref: str) -> tuple:
    """Order refs numerically (1.1.2 before 1.1.10), then as text."""
    return (version_sort_key(ref), ref)


def compare_benchmarks(old: dict, new: dict) -> dict:
    """Compare two benchmarks recommendation by recommendation.

    Recommendations are matched by ref and compared with DeepDiff, ignoring list order and
    the WorkBench URLs and artifact IDs every release changes. A removed ref and an added ref whose titles are at least
    RENUMBER_SIMILARITY alike are reported as one renumbered recommendation.
    """
    from deepdiff import DeepDiff

    old_recs = {r["ref"]: r for r in old.get("recommendations", [])}
    new_recs = {r["ref"]: r for r in new.get("recommendations", [])}

    modified = []
    unchanged = []
    for ref in sorted(old_recs.keys() & new_recs.keys(), key=_ref_key):
        old_rec, new_rec = old_recs[ref], new_recs[ref]
        diff = DeepDiff(
            old_rec,
            new_rec,
            ignore_order=True,
            exclude_paths=_WORKBENCH_IDENTIFIER_PATHS,
            exclude_regex_paths=_WORKBENCH_IDENTIFIER_REGEX_PATHS,
        )
        if diff:
            modified.append(
                {
                    "ref": ref,
                    "title": new_rec.get("title", ""),
                    "old_title": old_rec.get("title", ""),
                    "fields_changed": sorted(str(key) for key in diff.affected_root_keys),
                    "diff": json.loads(diff.to_json()),
                }
            )
        else:
            unchanged.append({"ref": ref, "title": new_rec.get("title", "")})

    remaining_removed = sorted(old_recs.keys() - new_recs.keys(), key=_ref_key)
    remaining_added = sorted(new_recs.keys() - old_recs.keys(), key=_ref_key)
    renumbered = []
    for old_ref in list(remaining_removed):
        old_title = old_recs[old_ref].get("title", "")
        for new_ref in remaining_added:
            new_title = new_recs[new_ref].get("title", "")
            similarity = difflib.SequenceMatcher(None, old_title, new_title).ratio()
            if similarity >= RENUMBER_SIMILARITY:
                renumbered.append(
                    {
                        "old_ref": old_ref,
                        "new_ref": new_ref,
                        "title": new_title,
                        "similarity": round(similarity * 100, 1),
                    }
                )
                remaining_removed.remove(old_ref)
                remaining_added.remove(new_ref)
                break

    return {
        "old_version": old.get("version", "unknown"),
        "new_version": new.get("version", "unknown"),
        "benchmark_title": new.get("title", old.get("title", "Unknown")),
        "summary": {
            "added": len(remaining_added),
            "removed": len(remaining_removed),
            "modified": len(modified),
            "unchanged": len(unchanged),
            "renumbered": len(renumbered),
        },
        "changes": {
            "added": [{"ref": r, "title": new_recs[r].get("title", "")} for r in remaining_added],
            "removed": [
                {"ref": r, "title": old_recs[r].get("title", "")} for r in remaining_removed
            ],
            "modified": modified,
            "unchanged": unchanged,
            "renumbered": renumbered,
        },
    }


def _output_json(comparison: dict) -> None:
    """Print the comparison as JSON, without the unchanged recommendations."""
    output: dict[str, Any] = {**comparison}
    output["changes"] = {k: v for k, v in comparison["changes"].items() if k != "unchanged"}
    click.echo(json.dumps(output, indent=2, ensure_ascii=False))


def _md_cell(value: str) -> str:
    """Text for one Markdown table cell: pipes escaped, line breaks as spaces."""
    return " ".join(str(value).split()).replace("|", "\\|")


def _output_markdown(comparison: dict) -> None:
    """Print the comparison as a Markdown document."""
    summary = comparison["summary"]
    changes = comparison["changes"]

    lines = [
        "# Benchmark Comparison",
        "",
        f"**{comparison['benchmark_title']}**: "
        f"{comparison['old_version']} → {comparison['new_version']}",
        "",
        "## Summary",
        "",
        "| Change Type | Count |",
        "|-------------|-------|",
        f"| Added       | {summary['added']} |",
        f"| Removed     | {summary['removed']} |",
        f"| Modified    | {summary['modified']} |",
        f"| Unchanged   | {summary['unchanged']} |",
        f"| Renumbered  | {summary['renumbered']} |",
        "",
    ]

    sections = [
        ("Added Recommendations", ["Ref", "Title"], changes["added"], ("ref", "title")),
        ("Removed Recommendations", ["Ref", "Title"], changes["removed"], ("ref", "title")),
        (
            "Modified Recommendations",
            ["Ref", "Title", "Changed Fields"],
            [{**m, "fields": ", ".join(m["fields_changed"])} for m in changes["modified"]],
            ("ref", "title", "fields"),
        ),
        (
            "Renumbered Recommendations",
            ["Old Ref", "New Ref", "Title"],
            changes["renumbered"],
            ("old_ref", "new_ref", "title"),
        ),
    ]
    for heading, columns, items, keys in sections:
        if not items:
            continue
        lines.extend(
            [
                f"## {heading}",
                "",
                "| " + " | ".join(columns) + " |",
                "|" + "|".join("-" * (len(c) + 2) for c in columns) + "|",
            ]
        )
        lines.extend("| " + " | ".join(_md_cell(item[k]) for k in keys) + " |" for item in items)
        lines.append("")

    click.echo("\n".join(lines))


def _output_summary(comparison: dict) -> None:
    """Print the counts only."""
    summary = comparison["summary"]
    total = sum(summary.values())

    console.print(f"Benchmark: {escape(comparison['benchmark_title'])}")
    console.print(
        f"Version:   {escape(comparison['old_version'])} → {escape(comparison['new_version'])}"
    )
    console.print()
    console.print(
        f"  [green]✚ {summary['added']} added[/green]  "
        f"[red]✖ {summary['removed']} removed[/red]  "
        f"[yellow]⟳ {summary['modified']} modified[/yellow]  "
        f"[cyan]↷ {summary['renumbered']} renumbered[/cyan]"
    )
    console.print()
    console.print(f"Total: {total} recommendations ({summary['unchanged']} unchanged)")


def _output_table(comparison: dict, verbose: bool = False, _console: Console | None = None) -> None:
    """Print the comparison as a summary and a table of changes."""
    out = _console or console
    summary = comparison["summary"]
    changes = comparison["changes"]

    out.print()
    out.rule(f"[bold]Benchmark Comparison: {escape(comparison['benchmark_title'])}[/bold]")
    out.print(
        f"[dim]{escape(comparison['old_version'])} → {escape(comparison['new_version'])}[/dim]"
    )
    out.print()

    out.print("[bold]Summary:[/bold]")
    out.print(
        f"  [green]✚ Added:[/green]      {summary['added']} recommendations\n"
        f"  [red]✖ Removed:[/red]    {summary['removed']} recommendations\n"
        f"  [yellow]⟳ Modified:[/yellow]   {summary['modified']} recommendations\n"
        f"  [dim]═ Unchanged:[/dim] {summary['unchanged']} recommendations\n"
        f"  [cyan]↷ Renumbered:[/cyan] {summary['renumbered']} recommendations"
    )
    out.print()

    if not any([changes["added"], changes["removed"], changes["modified"], changes["renumbered"]]):
        out.print("[dim]No changes detected between versions.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Ref", no_wrap=True)
    table.add_column("Title", ratio=3)
    table.add_column("Changes", ratio=1)

    for item in changes["added"]:
        table.add_row("[green]✚ Added[/green]", escape(item["ref"]), escape(item["title"]), "New")
    for item in changes["removed"]:
        table.add_row(
            "[red]✖ Removed[/red]",
            escape(item["ref"]),
            escape(item["title"]),
            "No longer present",
        )
    for item in changes["modified"]:
        fields = item["fields_changed"]
        changes_text = ", ".join(fields[:3])
        if len(fields) > 3:
            changes_text += f" +{len(fields) - 3} more"
        table.add_row(
            "[yellow]⟳ Modified[/yellow]",
            escape(item["ref"]),
            escape(item["title"]),
            escape(changes_text),
        )
    for item in changes["renumbered"]:
        table.add_row(
            "[cyan]↷ Renumbered[/cyan]",
            escape(f"{item['old_ref']} → {item['new_ref']}"),
            escape(item["title"]),
            f"{item['similarity']}% match",
        )
    out.print(table)

    if verbose and changes["modified"]:
        out.print()
        out.print("[bold]Detailed Changes:[/bold]")
        for item in changes["modified"]:
            out.print(
                f"\n[yellow]⟳ MODIFIED: {escape(item['ref'])}[/yellow] - {escape(item['title'])}"
            )
            for field in item["fields_changed"]:
                out.print(f"  • {escape(field)} changed")
