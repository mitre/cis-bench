"""Backwards compatibility - imports from new modular location.

This file re-exports from cis_bench.cli.commands.tui.view for
backwards compatibility with existing code.

New code should import from cis_bench.cli.commands.tui.view directly.
"""

from cis_bench.cli.commands.tui.view import (
    ViewApp,
    ViewDetailView,
    run_interactive_view,
)

__all__ = [
    "ViewApp",
    "ViewDetailView",
    "run_interactive_view",
]
