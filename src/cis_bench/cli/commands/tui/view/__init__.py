"""View browser TUI components.

This module provides the interactive benchmark viewer:
- ViewApp: Main application for viewing benchmark recommendations
- ViewDetailView: Detail view for recommendation content
- run_interactive_view: Entry point function
"""

from cis_bench.cli.commands.tui.view.app import ViewApp, run_interactive_view
from cis_bench.cli.commands.tui.view.detail import ViewDetailView

__all__ = [
    "ViewApp",
    "ViewDetailView",
    "run_interactive_view",
]
