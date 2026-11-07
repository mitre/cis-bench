"""Launch the main tabbed TUI interface."""

import click

from cis_bench.cli.helpers.services import settings_from


@click.command(name="tui")
@click.pass_context
def main_tui(ctx):
    """Launch the unified tabbed TUI interface.

    \b
    Tabs:
        Catalog    - Browse benchmarks, view details, actions (v/d/e/o)
        Operations - Bulk download, export, catalog refresh
        Settings   - Auth status, preferences, about

    \b
    Navigation:
        Arrow keys - Navigate within tab
        Tab        - Switch focus (table/detail pane)
        q          - Quit
        ?          - Help

    \b
    Example:
        cis-bench tui
    """
    from cis_bench.cli.commands.tui.main_app import MainTUIApp

    app = MainTUIApp(settings=settings_from(ctx))
    app.run()
