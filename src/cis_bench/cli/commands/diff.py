"""Diff command: compare two versions of a benchmark."""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cis_bench.catalog.versions import version_sort_key
from cis_bench.cli.helpers.errors import DOWNLOAD_ERRORS, cache_failure, report_download_error
from cis_bench.cli.helpers.services import settings_from, workbench_scraper, workbench_session
from cis_bench.utils.workbench_urls import is_benchmark_id, resolve_benchmark_reference

if TYPE_CHECKING:
    from cis_bench.catalog.database import CatalogDatabase
    from cis_bench.config import Settings
    from cis_bench.fetcher.workbench import WorkbenchScraper

console = Console()
# Downloading, progress and errors go to stderr: stdout carries the comparison (JSON, Markdown).
err_console = Console(stderr=True)

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

    Each argument is a catalog ID or a benchmark JSON file. An ID that is not downloaded
    yet is downloaded from CIS WorkBench into the cache first, as get does.

    \b
    Examples:
        cis-bench diff 22605 23598                    # Two downloaded benchmarks
        cis-bench diff old.json new.json              # Two files
        cis-bench diff 22605 23598 --format markdown  # Markdown document
        cis-bench diff 22605 23598 --format json      # JSON for scripts
        cis-bench diff 22605 23598 --verbose          # Changed fields per recommendation

    \b
    Change types:
        ✚ Added       - Ref only in the newer version
        ✖ Removed     - Ref only in the older version
        ⟳ Modified    - Same ref, different content
        ≈ Reformatted - Same ref, only whitespace in some fields changed
        ↷ Renumbered  - A removed ref and an added ref with near-identical titles
    """
    loader = _BenchmarkLoader(settings_from(ctx))
    old_data = loader.load(old_benchmark)
    new_data = loader.load(new_benchmark)

    comparison = compare_benchmarks(old_data, new_data)

    if output_format == "json":
        _output_json(comparison)
    elif output_format == "markdown":
        _output_markdown(comparison)
    elif output_format == "summary":
        _output_summary(comparison)
    else:
        _output_table(comparison, verbose)


class _BenchmarkLoader:
    """Reads the benchmarks of one diff run, downloading a catalog benchmark that is not
    cached; it logs in at most once."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._scraper: WorkbenchScraper | None = None

    def load(self, identifier: str) -> dict:
        """A benchmark as a dict: digits are a catalog ID (the cached copy, downloaded into
        the cache first when missing), anything else a file.

        Raises:
            click.ClickException: No catalog, an ID the catalog does not list, a failed cache
                write, or a file that is missing, unreadable or not a benchmark.
        """
        if not is_benchmark_id(identifier):
            return self._load_file(identifier)

        from cis_bench.catalog.database import CatalogDatabase

        benchmark_id = identifier.strip()
        if not self.settings.catalog_db_path.exists():
            raise click.ClickException(
                f"Benchmark {benchmark_id} is not downloaded, and there is no catalog to "
                "download it from. Build the catalog first:\n  cis-bench catalog refresh"
            )
        db = CatalogDatabase(self.settings.catalog_db_path)
        downloaded = db.get_downloaded(benchmark_id)
        if downloaded is None:
            self._download(db, benchmark_id)
            downloaded = db.get_downloaded(benchmark_id)
        if downloaded is None:
            raise click.ClickException(f"Benchmark {benchmark_id} was downloaded but not cached")
        return _parse_benchmark(downloaded["content_json"], f"benchmark {benchmark_id}")

    def _download(self, db: CatalogDatabase, benchmark_id: str) -> None:
        """Download a catalog benchmark into the cache, as download and get do."""
        from sqlalchemy.exc import SQLAlchemyError

        from cis_bench.catalog.downloader import CatalogDownloader
        from cis_bench.cli.helpers.download_helper import download_with_progress

        if db.get_benchmark(benchmark_id) is None:
            raise click.ClickException(
                f"Benchmark {benchmark_id} is not in catalog. Check the ID, or refresh the "
                "catalog:\n  cis-bench catalog refresh"
            )
        _, url = resolve_benchmark_reference(benchmark_id, base_url=self.settings.workbench_url)

        try:
            scraper = self._workbench(needs=f"download benchmark {benchmark_id}")
            err_console.print(
                f"[cyan]Benchmark {benchmark_id} is not downloaded; "
                "downloading it from CIS WorkBench...[/cyan]"
            )
            benchmark = download_with_progress(scraper, url, prefix=" ", console=err_console)
        except DOWNLOAD_ERRORS as error:
            report_download_error(err_console, error)
            sys.exit(1)

        try:
            CatalogDownloader(db).cache(benchmark_id, benchmark)
        except (SQLAlchemyError, OSError) as error:
            raise click.ClickException(cache_failure(benchmark_id, error)) from error
        err_console.print(f"[green]✓[/green] Downloaded and cached: {escape(benchmark.title)}")

    def _workbench(self, *, needs: str) -> WorkbenchScraper:
        """The WorkBench scraper for this run, logging in the first time it is needed.

        Raises:
            OfflineError: Offline mode is on.
        """
        if self._scraper is None:
            session = workbench_session(self.settings, needs=needs)
            self._scraper = workbench_scraper(self.settings, session)
        return self._scraper

    @staticmethod
    def _load_file(identifier: str) -> dict:
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
        return _parse_benchmark(text, identifier)


def _parse_benchmark(text: str, source: str) -> dict:
    """The benchmark as the Benchmark model reads it, as a dict.

    Both sides of a comparison go through the model, so a copy saved in an older form
    (profiles as one joined text, for example) compares equal to the same content saved now.
    """
    from pydantic import ValidationError

    from cis_bench.models.benchmark import Benchmark

    try:
        benchmark = Benchmark.model_validate_json(text)
    except ValidationError as error:
        raise click.ClickException(f"{source} is not a benchmark JSON file: {error}") from error
    return benchmark.model_dump(mode="json")


def _ref_key(ref: str) -> tuple:
    """Order refs numerically (1.1.2 before 1.1.10), then as text."""
    return (version_sort_key(ref), ref)


def _whitespace_folded(value: Any) -> Any:
    """value with every run of whitespace in its text folded to one space and the ends
    trimmed, so two values equal here differ only in whitespace."""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return [_whitespace_folded(item) for item in value]
    if isinstance(value, dict):
        return {key: _whitespace_folded(item) for key, item in value.items()}
    return value


def _changed_fields(old_rec: dict, new_rec: dict) -> tuple[Any, list[str]]:
    """DeepDiff of two recommendations and the top-level fields it names, ignoring list
    order and the WorkBench URLs and artifact IDs every release changes."""
    from deepdiff import DeepDiff

    diff = DeepDiff(
        old_rec,
        new_rec,
        ignore_order=True,
        exclude_paths=_WORKBENCH_IDENTIFIER_PATHS,
        exclude_regex_paths=_WORKBENCH_IDENTIFIER_REGEX_PATHS,
    )
    return diff, sorted(str(key) for key in diff.affected_root_keys) if diff else []


def compare_benchmarks(old: dict, new: dict) -> dict:
    """Compare two benchmarks recommendation by recommendation.

    Recommendations are matched by ref and compared with DeepDiff, ignoring list order and
    the WorkBench URLs and artifact IDs every release changes. A field whose text differs
    only in whitespace is reformatted, never a modification: a recommendation whose only
    changes are such fields is listed as reformatted. A removed ref and an added ref whose
    titles are at least RENUMBER_SIMILARITY alike are reported as one renumbered
    recommendation.
    """
    old_recs = {r["ref"]: r for r in old.get("recommendations", [])}
    new_recs = {r["ref"]: r for r in new.get("recommendations", [])}

    modified = []
    reformatted = []
    unchanged = []
    for ref in sorted(old_recs.keys() & new_recs.keys(), key=_ref_key):
        old_rec, new_rec = old_recs[ref], new_recs[ref]
        diff, changed = _changed_fields(old_rec, new_rec)
        _, content_changed = _changed_fields(
            _whitespace_folded(old_rec), _whitespace_folded(new_rec)
        )
        whitespace_only = [field for field in changed if field not in content_changed]
        title = new_rec.get("title", "")
        if content_changed:
            modified.append(
                {
                    "ref": ref,
                    "title": title,
                    "old_title": old_rec.get("title", ""),
                    "fields_changed": content_changed,
                    "reformatted_fields": whitespace_only,
                    "diff": json.loads(diff.to_json()),
                }
            )
        elif whitespace_only:
            reformatted.append({"ref": ref, "title": title, "fields": whitespace_only})
        else:
            unchanged.append({"ref": ref, "title": title})

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

    scraper_versions = {"old": old.get("scraper_version"), "new": new.get("scraper_version")}
    return {
        "old_version": old.get("version", "unknown"),
        "new_version": new.get("version", "unknown"),
        "benchmark_title": new.get("title", old.get("title", "Unknown")),
        "scraper_versions": scraper_versions,
        "scraper_versions_differ": scraper_versions["old"] != scraper_versions["new"],
        "summary": {
            "added": len(remaining_added),
            "removed": len(remaining_removed),
            "modified": len(modified),
            "reformatted": len(reformatted),
            "unchanged": len(unchanged),
            "renumbered": len(renumbered),
        },
        "changes": {
            "added": [{"ref": r, "title": new_recs[r].get("title", "")} for r in remaining_added],
            "removed": [
                {"ref": r, "title": old_recs[r].get("title", "")} for r in remaining_removed
            ],
            "modified": modified,
            "reformatted": reformatted,
            "unchanged": unchanged,
            "renumbered": renumbered,
        },
    }


def _scraper_notice(comparison: dict) -> str | None:
    """The line saying the two copies were made by different scraper versions, if they were."""
    if not comparison["scraper_versions_differ"]:
        return None
    versions = comparison["scraper_versions"]
    return (
        f"These copies were made by different scraper versions ({versions['old']} → "
        f"{versions['new']}); formatting differences may come from cis-bench, not WorkBench."
    )


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
        f"| Reformatted | {summary['reformatted']} |",
        f"| Unchanged   | {summary['unchanged']} |",
        f"| Renumbered  | {summary['renumbered']} |",
        "",
    ]
    notice = _scraper_notice(comparison)
    if notice:
        lines[4:4] = [f"> {notice}", ""]

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
            "Reformatted Recommendations",
            ["Ref", "Title", "Fields"],
            [{**r, "fields": ", ".join(r["fields"])} for r in changes["reformatted"]],
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
        f"[blue]≈ {summary['reformatted']} reformatted[/blue]  "
        f"[cyan]↷ {summary['renumbered']} renumbered[/cyan]"
    )
    console.print()
    console.print(f"Total: {total} recommendations ({summary['unchanged']} unchanged)")
    notice = _scraper_notice(comparison)
    if notice:
        console.print(f"\n[dim]{escape(notice)}[/dim]")


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
    notice = _scraper_notice(comparison)
    if notice:
        out.print(f"[dim]{escape(notice)}[/dim]")
    out.print()

    out.print("[bold]Summary:[/bold]")
    out.print(
        f"  [green]✚ Added:[/green]      {summary['added']} recommendations\n"
        f"  [red]✖ Removed:[/red]    {summary['removed']} recommendations\n"
        f"  [yellow]⟳ Modified:[/yellow]   {summary['modified']} recommendations\n"
        f"  [blue]≈ Reformatted:[/blue] {summary['reformatted']} recommendations\n"
        f"  [dim]═ Unchanged:[/dim] {summary['unchanged']} recommendations\n"
        f"  [cyan]↷ Renumbered:[/cyan] {summary['renumbered']} recommendations"
    )
    out.print()

    if not any([changes["added"], changes["removed"], changes["modified"], changes["renumbered"]]):
        if changes["reformatted"]:
            hint = "" if verbose else " --verbose lists them."
            out.print(
                f"[dim]No content changes; {len(changes['reformatted'])} recommendations "
                f"reformatted (whitespace only).{hint}[/dim]"
            )
            if verbose:
                _print_reformatted(out, changes["reformatted"])
        else:
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
            for field in item["reformatted_fields"]:
                out.print(f"  • {escape(field)} (whitespace only)")
    if verbose and changes["reformatted"]:
        _print_reformatted(out, changes["reformatted"])


def _print_reformatted(out: Console, reformatted: list[dict]) -> None:
    """List the recommendations whose only changes are whitespace, with those fields."""
    out.print()
    out.print("[bold]Reformatted (whitespace only):[/bold]")
    for item in reformatted:
        out.print(f"\n[blue]≈ REFORMATTED: {escape(item['ref'])}[/blue] - {escape(item['title'])}")
        for field in item["fields"]:
            out.print(f"  • {escape(field)} (whitespace only)")
