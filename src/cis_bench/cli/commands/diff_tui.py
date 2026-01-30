"""Backwards compatibility - imports from new modular location.

This file re-exports from cis_bench.cli.commands.tui.diff for
backwards compatibility with existing code.

New code should import from cis_bench.cli.commands.tui.diff directly.
"""

from cis_bench.cli.commands.tui.diff import (
    DiffApp,
    DiffDetailView,
    run_interactive_diff,
)

__all__ = [
    "DiffApp",
    "DiffDetailView",
    "run_interactive_diff",
]
