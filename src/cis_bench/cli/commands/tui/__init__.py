"""TUI components for cis-bench interactive commands.

This package provides modular TUI components:
- tui.base: Base classes (BaseBrowserApp, DetailView, COMMON_CSS)
- tui.widgets: Shared widgets (SearchInput, HelpScreen, JumpDialog, SaveDialog)
- tui.catalog: Catalog browser (CatalogBrowserApp, run_catalog_browser)
"""

# Re-export common components for backwards compatibility
from cis_bench.cli.commands.tui.base import (
    COMMON_BINDINGS,
    COMMON_CSS,
    BaseBrowserApp,
    DetailView,
    html_to_markdown,
    natural_sort_key,
)
from cis_bench.cli.commands.tui.widgets import (
    HelpScreen,
    JumpDialog,
    SaveDialog,
    SearchInput,
)

__all__ = [
    # Base
    "BaseBrowserApp",
    "COMMON_BINDINGS",
    "COMMON_CSS",
    "DetailView",
    "html_to_markdown",
    "natural_sort_key",
    # Widgets
    "HelpScreen",
    "JumpDialog",
    "SaveDialog",
    "SearchInput",
]
