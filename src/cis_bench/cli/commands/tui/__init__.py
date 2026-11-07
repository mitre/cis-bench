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
    SCREEN_BINDINGS,
    BaseBrowserApp,
    BaseBrowserScreen,
    DetailView,
    html_to_markdown,
    natural_sort_key,
)
from cis_bench.cli.commands.tui.widgets import (
    HelpScreen,
    JumpDialog,
    LoadingModal,
    SaveDialog,
    SearchInput,
)

__all__ = [
    # Base
    "BaseBrowserApp",
    "BaseBrowserScreen",
    "COMMON_BINDINGS",
    "COMMON_CSS",
    "SCREEN_BINDINGS",
    "DetailView",
    "html_to_markdown",
    "natural_sort_key",
    # Widgets
    "HelpScreen",
    "JumpDialog",
    "LoadingModal",
    "SaveDialog",
    "SearchInput",
]
