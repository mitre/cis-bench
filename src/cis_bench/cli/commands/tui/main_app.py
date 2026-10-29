"""Main tabbed TUI application for cis-bench.

Unified interface with 3-tab architecture:
- Catalog: Browse benchmarks, view details, actions (view/diff/export)
- Operations: Bulk download, bulk export, catalog refresh, cache management
- Settings: Auth status, preferences, about
"""

from dataclasses import dataclass

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    Placeholder,
    Static,
    TabbedContent,
    TabPane,
)

from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane


@dataclass
class TabConfig:
    """Configuration for a tab in the main TUI."""

    id: str  # Tab ID (e.g., "tab-catalog")
    label: str  # Display label (e.g., "Catalog")
    pane_class: type[Static] | None  # Pane widget class, or None for placeholder
    placeholder_text: str = ""  # Text shown when pane_class is None


# Tab configuration - single source of truth
# Order determines display order in the UI
TABS: list[TabConfig] = [
    TabConfig(
        id="tab-catalog",
        label="Catalog",
        pane_class=CatalogTabPane,
    ),
    TabConfig(
        id="tab-operations",
        label="Operations",
        pane_class=None,
        placeholder_text="Operations: Bulk download, export, catalog refresh - Phase 3",
    ),
    TabConfig(
        id="tab-settings",
        label="Settings",
        pane_class=None,
        placeholder_text="Settings: Auth, preferences, about - Phase 4",
    ),
]


def get_tab_labels() -> list[str]:
    """Get list of tab labels for testing."""
    return [tab.label for tab in TABS]


def get_tab_count() -> int:
    """Get number of tabs for testing."""
    return len(TABS)


class MainTUIApp(App):
    """Main tabbed TUI application."""

    TITLE = "CIS Benchmark CLI"
    CSS = """
    TabbedContent {
        height: 100%;
    }

    TabbedContent ContentSwitcher, DataTable, VerticalScroll {
        height: 1fr;
    }

    TabPane {
        padding: 1 2;
    }

    /* Catalog tab layout */
    #catalog-table {
        width: 65%;
    }

    #detail-container {
        width: 35%;
        border-left: solid $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        ("?", "help", "Help"),
    ]

    def compose(self) -> ComposeResult:
        """Create tabbed interface from TABS config."""
        yield Header()

        # Use first tab as initial
        initial_tab = TABS[0].id if TABS else None

        with TabbedContent(initial=initial_tab):
            for tab in TABS:
                with TabPane(tab.label, id=tab.id):
                    if tab.pane_class:
                        yield tab.pane_class()
                    else:
                        # Placeholder for tabs not yet implemented
                        yield Label(tab.placeholder_text)
                        yield Placeholder(f"{tab.label} - Coming soon")

        yield Footer()

    def action_help(self) -> None:
        """Show help screen."""
        # TODO: Implement help screen
        self.notify("Help screen - TBD")

    @on(TabbedContent.TabActivated, "#tab-catalog")
    def on_catalog_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Focus DataTable when catalog tab is activated.

        Required for proper keyboard navigation - tab switching doesn't
        automatically focus child widgets.
        """
        try:
            table = self.query_one("#catalog-table", DataTable)
            table.focus()
        except Exception:  # noqa: BLE001, S110  # nosec B110 - expected: table may not exist yet
            pass
