"""View command - interactively browse a benchmark."""

import sys

import click
from rich.console import Console
from rich.table import Table

from cis_bench.cli.commands.utils import load_benchmark, output_with_pager

console = Console()


@click.command(name="view")
@click.argument("benchmark")
@click.option(
    "--profile",
    "-p",
    help="Filter recommendations by profile (e.g., 'Level 1', 'Level 2')",
)
@click.option(
    "--status",
    "-s",
    type=click.Choice(["automated", "manual", "all"]),
    default="all",
    help="Filter by assessment status (default: all)",
)
@click.option(
    "--interactive/--no-interactive",
    "-i/-I",
    default=None,
    help="Interactive TUI mode (auto-detects terminal by default)",
)
@click.pass_context
def view_cmd(ctx, benchmark, profile, status, interactive):
    """Browse a benchmark's recommendations interactively.

    Accepts benchmark IDs (from downloaded benchmarks) or file paths.
    Automatically fetches benchmarks from CIS WorkBench if not cached locally.

    \b
    Examples:
        cis-bench view 23598                    # Interactive TUI
        cis-bench view 23598 -I                 # Table output
        cis-bench view ubuntu.json              # View from file
        cis-bench view 23598 --profile "Level 1"
        cis-bench view 23598 --status automated

    \b
    Interactive Mode Keys:
        ↑/↓ or j/k   Navigate recommendations
        Tab          Switch between list and detail panes
        Page Up/Down Fast scroll in detail pane
        f            Toggle fullscreen detail
        s            Save report
        q or Esc     Quit
    """
    offline = ctx.obj.get("offline", False) if ctx.obj else False

    # Load benchmark
    try:
        data = load_benchmark(benchmark, offline=offline)
    except Exception as e:
        console.print(f"[red]Error loading benchmark:[/red] {e}")
        raise click.Abort() from e

    # Filter recommendations
    recommendations = data.get("recommendations", [])

    if profile:
        profile_lower = profile.lower()
        recommendations = [
            r
            for r in recommendations
            if any(profile_lower in p.lower() for p in r.get("profiles", []))
        ]

    if status != "all":
        recommendations = [
            r for r in recommendations if r.get("assessment_status", "").lower() == status.lower()
        ]

    if not recommendations:
        console.print("[yellow]No recommendations match the filters.[/yellow]")
        return

    # Determine interactive mode
    use_interactive = interactive if interactive is not None else sys.stdout.isatty()

    if use_interactive:
        from cis_bench.cli.commands.view_tui import run_interactive_view

        run_interactive_view(data, recommendations, offline=offline)
    else:
        output_with_pager(_output_table, data, recommendations)


def _output_table(data: dict, recommendations: list, _console: Console | None = None):
    """Output recommendations as a rich table."""
    out = _console or console

    out.print()
    out.rule(f"[bold]{data.get('title', 'Benchmark')}[/bold]")
    out.print(
        f"[dim]Version: {data.get('version', 'unknown')} | "
        f"{len(recommendations)} recommendations[/dim]"
    )
    out.print()

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Ref", no_wrap=True)
    table.add_column("Title", ratio=3)
    table.add_column("Profiles", ratio=1)
    table.add_column("Status", no_wrap=True)

    for rec in recommendations:
        profiles = ", ".join(rec.get("profiles", []))[:25]
        if len(", ".join(rec.get("profiles", []))) > 25:
            profiles = profiles[:22] + "..."

        status_text = rec.get("assessment_status", "")
        if status_text.lower() == "automated":
            status_display = "[green]Auto[/green]"
        elif status_text.lower() == "manual":
            status_display = "[yellow]Manual[/yellow]"
        else:
            status_display = status_text[:8]

        table.add_row(
            rec.get("ref", ""),
            rec.get("title", "")[:80] + ("..." if len(rec.get("title", "")) > 80 else ""),
            profiles,
            status_display,
        )

    out.print(table)
