"""Backwards compatibility - imports from new modular location.

This file re-exports from cis_bench.cli.commands.tui for
backwards compatibility with existing code.

New code should import from cis_bench.cli.commands.tui directly.
"""

from cis_bench.cli.commands.tui import (
    COMMON_BINDINGS,
    COMMON_CSS,
    BaseBrowserApp,
    DetailView,
    HelpScreen,
    JumpDialog,
    SaveDialog,
    SearchInput,
    html_to_markdown,
    natural_sort_key,
)

__all__ = [
    "BaseBrowserApp",
    "COMMON_BINDINGS",
    "COMMON_CSS",
    "DetailView",
    "HelpScreen",
    "JumpDialog",
    "SaveDialog",
    "SearchInput",
    "html_to_markdown",
    "natural_sort_key",
]
