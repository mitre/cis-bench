"""Diff browser TUI components.

This module provides the interactive diff browser:
- DiffApp: Main application for viewing benchmark diffs
- DiffDetailView: Detail view for change information
- run_interactive_diff: Entry point function
"""

from cis_bench.cli.commands.tui.diff.app import DiffApp, run_interactive_diff
from cis_bench.cli.commands.tui.diff.detail import DiffDetailView

__all__ = [
    "DiffApp",
    "DiffDetailView",
    "run_interactive_diff",
]
