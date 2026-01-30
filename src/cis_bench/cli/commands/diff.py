"""Diff command - compare benchmark versions."""

import difflib
import json
import sys

import click
from deepdiff import DeepDiff
from rich.console import Console
from rich.table import Table

from cis_bench.cli.commands.utils import load_benchmark, output_with_pager

console = Console()


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
    help="Show detailed field-level changes",
)
@click.option(
    "--interactive/--no-interactive",
    "-i/-I",
    default=None,
    help="Interactive TUI mode (auto-detects terminal by default)",
)
@click.pass_context
def diff_cmd(ctx, old_benchmark, new_benchmark, output_format, verbose, interactive):
    """Compare two benchmark versions to see what changed.

    Accepts benchmark IDs (from downloaded benchmarks) or file paths.
    Automatically fetches benchmarks from CIS WorkBench if not cached locally
    (unless --offline mode is enabled).

    \b
    Examples:
        cis-bench diff 23598 24001                    # Compare by ID (auto-fetch)
        cis-bench diff old.json new.json              # Compare files
        cis-bench diff 23598 24001 -i                 # Interactive TUI mode
        cis-bench diff 23598 24001 --format markdown  # Markdown output
        cis-bench diff 23598 24001 --format json      # JSON output
        cis-bench diff 23598 24001 --verbose          # Show field details
        cis-bench --offline diff 23598 24001          # Use cached only

    \b
    Change Types Detected:
        ✚ Added      - New recommendations in the newer version
        ✖ Removed    - Recommendations deleted in the newer version
        ⟳ Modified   - Same ref, but content changed
        ? Renumbered - Similar content, different ref (>85% title match)
    """
    # Check if offline mode
    offline = ctx.obj.get("offline", False) if ctx.obj else False

    # Load benchmarks
    try:
        old_data = load_benchmark(old_benchmark, offline=offline)
        new_data = load_benchmark(new_benchmark, offline=offline)
    except Exception as e:
        console.print(f"[red]Error loading benchmarks:[/red] {e}")
        raise click.Abort() from e

    # Compare benchmarks
    comparison = compare_benchmarks(old_data, new_data)

    # Determine if we should use interactive mode
    # Auto-detect: use interactive if stdout is a TTY (terminal)
    use_interactive = interactive if interactive is not None else sys.stdout.isatty()

    # Output based on format
    if use_interactive:
        from cis_bench.cli.commands.tui.diff import run_interactive_diff

        run_interactive_diff(comparison, old_data, new_data, offline=offline)
    elif output_format == "json":
        # JSON output goes direct (no pager, for piping)
        _output_json(comparison)
    elif output_format == "markdown":
        output_with_pager(_output_markdown, comparison)
    elif output_format == "summary":
        _output_summary(comparison)  # Summary is short, no pager needed
    else:
        output_with_pager(_output_table, comparison, verbose)


def compare_benchmarks(old: dict, new: dict) -> dict:
    """Compare two benchmarks and return structured diff.

    Uses DeepDiff for structural comparison with recommendation
    matching by ref ID.
    """
    old_recs = {r["ref"]: r for r in old.get("recommendations", [])}
    new_recs = {r["ref"]: r for r in new.get("recommendations", [])}

    old_refs = set(old_recs.keys())
    new_refs = set(new_recs.keys())

    # Detect added and removed
    added_refs = new_refs - old_refs
    removed_refs = old_refs - new_refs
    common_refs = old_refs & new_refs

    # Detect modifications in common recommendations
    modified = []
    unchanged = []
    for ref in common_refs:
        old_rec = old_recs[ref]
        new_rec = new_recs[ref]

        # Compare with DeepDiff, excluding fields that always change
        diff = DeepDiff(
            old_rec,
            new_rec,
            ignore_order=True,
            exclude_paths=["root['url']"],  # URLs may change
        )

        if diff:
            # Find which fields changed
            changed_fields = _extract_changed_fields(diff)
            modified.append(
                {
                    "ref": ref,
                    "title": new_rec.get("title", ""),
                    "old_title": old_rec.get("title", ""),
                    "fields_changed": changed_fields,
                    "diff": diff.to_dict(),
                }
            )
        else:
            unchanged.append({"ref": ref, "title": new_rec.get("title", "")})

    # Detect renumbered (removed + added with similar titles)
    renumbered = []
    remaining_removed = list(removed_refs)
    remaining_added = list(added_refs)

    for old_ref in list(remaining_removed):
        old_title = old_recs[old_ref].get("title", "")
        for new_ref in list(remaining_added):
            new_title = new_recs[new_ref].get("title", "")
            similarity = difflib.SequenceMatcher(None, old_title, new_title).ratio()
            if similarity >= 0.85:
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

    # Build result
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
            "added": [
                {"ref": r, "title": new_recs[r].get("title", "")} for r in sorted(remaining_added)
            ],
            "removed": [
                {"ref": r, "title": old_recs[r].get("title", "")} for r in sorted(remaining_removed)
            ],
            "modified": sorted(modified, key=lambda x: x["ref"]),
            "unchanged": sorted(unchanged, key=lambda x: x["ref"]),
            "renumbered": renumbered,
        },
    }


def _extract_changed_fields(diff: DeepDiff) -> list[str]:
    """Extract field names from DeepDiff result."""
    fields = set()
    for change_type in [
        "values_changed",
        "type_changes",
        "iterable_item_added",
        "iterable_item_removed",
        "dictionary_item_added",
        "dictionary_item_removed",
    ]:
        if change_type in diff:
            for path in diff[change_type]:
                # Extract field name from path like "root['title']"
                if "['title']" in path:
                    fields.add("title")
                elif "['description']" in path:
                    fields.add("description")
                elif "['rationale']" in path:
                    fields.add("rationale")
                elif "['audit']" in path:
                    fields.add("audit")
                elif "['remediation']" in path:
                    fields.add("remediation")
                elif "['profiles']" in path:
                    fields.add("profiles")
                elif "['nist_controls']" in path:
                    fields.add("nist_controls")
                elif "['cis_controls']" in path:
                    fields.add("cis_controls")
                elif "['assessment_status']" in path:
                    fields.add("assessment_status")
    return sorted(fields)


def _output_json(comparison: dict):
    """Output comparison as JSON."""
    # Remove unchanged from JSON output to reduce size
    output = {**comparison}
    output["changes"] = {k: v for k, v in comparison["changes"].items() if k != "unchanged"}
    console.print(json.dumps(output, indent=2))


def _output_markdown(comparison: dict, _console: Console | None = None):
    """Output comparison as Markdown."""
    out = _console or console
    summary = comparison["summary"]
    changes = comparison["changes"]

    lines = [
        "# Benchmark Comparison",
        "",
        f"**{comparison['benchmark_title']}**: {comparison['old_version']} → {comparison['new_version']}",
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

    if changes["added"]:
        lines.extend(
            [
                "## Added Recommendations",
                "",
                "| Ref | Title |",
                "|-----|-------|",
            ]
        )
        for item in changes["added"]:
            lines.append(f"| {item['ref']} | {item['title']} |")
        lines.append("")

    if changes["removed"]:
        lines.extend(
            [
                "## Removed Recommendations",
                "",
                "| Ref | Title |",
                "|-----|-------|",
            ]
        )
        for item in changes["removed"]:
            lines.append(f"| {item['ref']} | {item['title']} |")
        lines.append("")

    if changes["modified"]:
        lines.extend(
            [
                "## Modified Recommendations",
                "",
                "| Ref | Title | Changed Fields |",
                "|-----|-------|----------------|",
            ]
        )
        for item in changes["modified"]:
            fields = ", ".join(item["fields_changed"])
            lines.append(f"| {item['ref']} | {item['title']} | {fields} |")
        lines.append("")

    if changes["renumbered"]:
        lines.extend(
            [
                "## Renumbered Recommendations",
                "",
                "| Old Ref | New Ref | Title |",
                "|---------|---------|-------|",
            ]
        )
        for item in changes["renumbered"]:
            lines.append(f"| {item['old_ref']} | {item['new_ref']} | {item['title']} |")
        lines.append("")

    out.print("\n".join(lines))


def _output_summary(comparison: dict):
    """Output brief summary only."""
    summary = comparison["summary"]
    total = sum(summary.values())

    console.print(f"Benchmark: {comparison['benchmark_title']}")
    console.print(f"Version:   {comparison['old_version']} → {comparison['new_version']}")
    console.print()
    console.print(
        f"  [green]✚ {summary['added']} added[/green]  "
        f"[red]✖ {summary['removed']} removed[/red]  "
        f"[yellow]⟳ {summary['modified']} modified[/yellow]  "
        f"[cyan]? {summary['renumbered']} renumbered[/cyan]"
    )
    console.print()
    console.print(f"Total: {total} recommendations ({summary['unchanged']} unchanged)")


def _output_table(comparison: dict, verbose: bool = False, _console: Console | None = None):
    """Output comparison as rich table."""
    out = _console or console
    summary = comparison["summary"]
    changes = comparison["changes"]

    # Header
    out.print()
    out.rule(f"[bold]Benchmark Comparison: {comparison['benchmark_title']}[/bold]")
    out.print(f"[dim]{comparison['old_version']} → {comparison['new_version']}[/dim]")
    out.print()

    # Summary
    out.print("[bold]Summary:[/bold]")
    out.print(
        f"  [green]✚ Added:[/green]      {summary['added']} recommendations\n"
        f"  [red]✖ Removed:[/red]    {summary['removed']} recommendations\n"
        f"  [yellow]⟳ Modified:[/yellow]   {summary['modified']} recommendations\n"
        f"  [dim]═ Unchanged:[/dim] {summary['unchanged']} recommendations\n"
        f"  [cyan]? Renumbered:[/cyan] {summary['renumbered']} recommendations"
    )
    out.print()

    # Changes table
    if any([changes["added"], changes["removed"], changes["modified"], changes["renumbered"]]):
        table = Table(show_header=True, header_style="bold cyan", expand=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Ref", no_wrap=True)
        table.add_column("Title", ratio=3)  # Takes most space, wraps if needed
        table.add_column("Changes", ratio=1)

        for item in changes["added"]:
            table.add_row(
                "[green]✚ Added[/green]",
                item["ref"],
                item["title"],
                "New recommendation",
            )

        for item in changes["removed"]:
            table.add_row(
                "[red]✖ Removed[/red]",
                item["ref"],
                item["title"],
                "No longer present",
            )

        for item in changes["modified"]:
            # Show first 3 fields, then "+N more" if there are more
            fields = item["fields_changed"]
            if len(fields) <= 3:
                changes_text = ", ".join(fields)
            else:
                changes_text = ", ".join(fields[:3]) + f" +{len(fields) - 3} more"
            table.add_row(
                "[yellow]⟳ Modified[/yellow]",
                item["ref"],
                item["title"],
                changes_text,
            )

        for item in changes["renumbered"]:
            table.add_row(
                "[cyan]↷ Renumbered[/cyan]",
                f"{item['old_ref']} → {item['new_ref']}",
                item["title"],
                f"{item['similarity']}% match",
            )

        out.print(table)

        # Verbose details
        if verbose and changes["modified"]:
            out.print()
            out.print("[bold]Detailed Changes:[/bold]")
            for item in changes["modified"]:
                out.print(f"\n[yellow]⟳ MODIFIED: {item['ref']}[/yellow] - {item['title']}")
                for field in item["fields_changed"]:
                    out.print(f"  • {field} changed")
    else:
        out.print("[dim]No changes detected between versions.[/dim]")
