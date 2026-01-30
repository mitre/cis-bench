"""Catalog browser TUI application."""

import logging

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static

from cis_bench.cli.commands.tui.base import BaseBrowserApp
from cis_bench.cli.commands.tui.catalog.actions import CATALOG_CSS, ActionMenu
from cis_bench.cli.commands.tui.catalog.detail import CatalogDetailView
from cis_bench.cli.commands.tui.widgets import SearchInput

logger = logging.getLogger(__name__)


class CatalogBrowserApp(BaseBrowserApp):
    """Interactive TUI for browsing the CIS benchmark catalog."""

    CSS = CATALOG_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
        Binding("question_mark", "show_help", "Help", show=True),
        Binding("slash", "start_search", "Search", show=True),
        Binding("g", "jump_to_ref", "Go to ID", show=True),
        Binding("c", "copy_to_clipboard", "Copy", show=True),
        Binding("tab", "toggle_focus", "Switch Pane", show=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("f", "toggle_fullscreen", "Fullscreen", show=True),
        Binding("r", "reverse_sort", "Reverse", show=True),
        # Selection
        Binding("space", "toggle_select", "Select", show=True),
        # Actions
        Binding("enter", "open_actions", "Actions", show=True),
    ]

    def __init__(self, benchmarks: list[dict], offline: bool = False, **kwargs):
        """Initialize the catalog browser.

        Args:
            benchmarks: List of benchmark dictionaries from catalog search.
            offline: Whether running in offline mode.
        """
        super().__init__(**kwargs)
        self._benchmarks = benchmarks
        self._all_benchmarks = benchmarks.copy()
        self.offline = offline
        self._sort_reverse = False
        self._selected_indices: set[int] = set()
        self._downloaded_ids: set[str] = set()
        self._load_downloaded_ids()

    def _load_downloaded_ids(self) -> None:
        """Load set of downloaded benchmark IDs from database."""
        try:
            from cis_bench.catalog.database import CatalogDatabase
            from cis_bench.config import Config

            db_path = Config.get_catalog_db_path()
            if db_path.exists():
                db = CatalogDatabase(db_path)
                # Get downloaded benchmark IDs from the downloaded_benchmarks table
                downloaded = db.get_catalog_stats()
                if downloaded.get("downloaded_benchmarks", 0) > 0:
                    # TODO: Query actual downloaded IDs when ep9.7 implements this
                    pass
        except Exception as e:
            # Downloaded status is optional enhancement - log and continue
            logger.debug(f"Could not load downloaded IDs: {e}")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._build_summary(), id="summary")
        yield Horizontal(
            Container(
                DataTable(id="changes-table"),
                id="list-container",
            ),
            VerticalScroll(
                CatalogDetailView(id="detail-view"),
                id="detail-container",
            ),
            id="main-container",
        )
        yield Container(
            SearchInput(),
            Static("", id="search-count"),
            id="search-container",
        )
        yield Footer()

    def on_resize(self, event) -> None:
        """Handle terminal resize for responsive layout."""
        self._update_layout_for_size(event.size.width)

    def _update_layout_for_size(self, width: int) -> None:
        """Update layout based on terminal width.

        Args:
            width: Terminal width in characters.
        """
        try:
            list_container = self.query_one("#list-container")
            detail_container = self.query_one("#detail-container")

            if width < 80:
                # Narrow: hide detail pane, list takes full width
                detail_container.styles.display = "none"
                list_container.styles.width = "100%"
            else:
                # Wide: show both panes
                detail_container.styles.display = "block"
                list_container.styles.width = "45%"
                detail_container.styles.width = "55%"
        except Exception:
            # May fail during initial compose before widgets exist
            logger.debug("Layout update skipped - widgets not ready")

    def _build_summary(self) -> Text:
        """Build summary text showing catalog stats."""
        text = Text()
        if self.offline:
            text.append("[OFFLINE] ", style="bold yellow")
        text.append("CIS Benchmark Catalog  ", style="bold")
        text.append(f"{len(self._benchmarks)} benchmarks", style="dim")
        if self._selected_indices:
            text.append(f"  ({len(self._selected_indices)} selected)", style="cyan")
        return text

    def _update_summary(self) -> None:
        """Update the summary display."""
        summary = self.query_one("#summary", Static)
        summary.update(self._build_summary())

    def on_mount(self) -> None:
        """Set up the table when app mounts."""
        table = self.query_one("#changes-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Columns: Selection checkbox, ID, Title (with version), Platform
        table.add_columns("", "ID", "Title", "Platform")

        self._populate_table()

        # Show first item details if available
        if self._benchmarks:
            self._show_detail(0)

        # Focus the table initially
        table.focus()

    def _populate_table(self) -> None:
        """Populate the table with benchmark data."""
        table = self.query_one("#changes-table", DataTable)

        for idx, benchmark in enumerate(self._benchmarks):
            # Selection checkbox
            is_selected = idx in self._selected_indices
            checkbox = Text("●", style="cyan bold") if is_selected else Text("○", style="dim")

            # Build title with version inline
            title = benchmark.get("title", "Unknown")
            version = benchmark.get("version", "")

            # Add star for latest, combine title+version
            if benchmark.get("is_latest"):
                title = f"★ {title}"
            if version:
                title = f"{title} {version}"

            # Platform (truncated for narrow screens)
            platform = (benchmark.get("platform") or "")[:15]

            table.add_row(
                checkbox,
                benchmark.get("benchmark_id", ""),
                self._truncate(title, 55),
                platform,
            )

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail view when row selection changes."""
        if event.cursor_row is not None and event.cursor_row < len(self._benchmarks):
            self._show_detail(event.cursor_row)

    def _show_detail(self, index: int) -> None:
        """Show detail for the selected benchmark."""
        if index < 0 or index >= len(self._benchmarks):
            return

        benchmark = self._benchmarks[index]
        detail_view = self.query_one("#detail-view", CatalogDetailView)
        detail_view.update_content(benchmark)

    def action_toggle_select(self) -> None:
        """Toggle selection on the current row."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row in self._selected_indices:
            self._selected_indices.remove(current_row)
        else:
            self._selected_indices.add(current_row)

        # Rebuild table to show updated checkboxes
        self._rebuild_table_preserve_cursor()
        self._update_summary()

    def _rebuild_table_preserve_cursor(self) -> None:
        """Rebuild table preserving cursor position."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row
        table.clear()
        self._populate_table()
        if current_row is not None and current_row < len(self._benchmarks):
            table.move_cursor(row=current_row)

    def action_open_actions(self) -> None:
        """Open the actions menu for the current benchmark."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row is None or current_row >= len(self._benchmarks):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._benchmarks[current_row]
        benchmark_id = str(benchmark.get("benchmark_id", ""))
        is_downloaded = benchmark_id in self._downloaded_ids

        self.push_screen(
            ActionMenu(benchmark, is_downloaded=is_downloaded),
            self._handle_action,
        )

    def _handle_action(self, result: tuple | None) -> None:
        """Handle the result from the action menu."""
        if result is None:
            return

        action, benchmark = result
        benchmark_id = benchmark.get("benchmark_id", "")

        if action == "download":
            self.notify(
                f"Download {benchmark_id}: Use 'cis-bench download {benchmark_id}'",
                severity="information",
            )
        elif action == "view":
            self.notify(
                f"View {benchmark_id}: Use 'cis-bench view {benchmark_id}'",
                severity="information",
            )
        elif action == "diff":
            self.notify(
                f"Diff: Select another version to compare with {benchmark_id}",
                severity="information",
            )
        elif action == "export":
            self.notify(
                f"Export {benchmark_id}: Use 'cis-bench export {benchmark_id}'",
                severity="information",
            )

    def get_selected_items(self) -> list[dict]:
        """Get the selected benchmarks.

        Returns:
            List of benchmark dictionaries for selected items.
        """
        return [
            self._benchmarks[idx]
            for idx in sorted(self._selected_indices)
            if idx < len(self._benchmarks)
        ]

    def action_reverse_sort(self) -> None:
        """Toggle sort order (asc/desc)."""
        self._sort_reverse = not self._sort_reverse
        self._rebuild_table()
        direction = "descending" if self._sort_reverse else "ascending"
        self.notify(f"Sort: {direction}", title="Sort Order")

    def _rebuild_table(self) -> None:
        """Rebuild the table with current sort order."""
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._selected_indices.clear()  # Clear selections on rebuild

        # Sort by published date
        self._benchmarks = sorted(
            self._benchmarks,
            key=lambda x: x.get("published_date", "") or "",
            reverse=not self._sort_reverse,  # Default is newest first
        )

        self._populate_table()
        self._update_summary()

        if self._benchmarks:
            self._show_detail(0)

    def _apply_search_filter(self, query: str) -> None:
        """Filter the table based on search query."""
        query = query.lower().strip()
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._benchmarks = []
        self._selected_indices.clear()  # Clear selections on filter

        for benchmark in self._all_benchmarks:
            # Check if query matches ID, title, platform, or description
            # Handle None values safely with `or ""`
            benchmark_id = str(benchmark.get("benchmark_id", ""))
            title = (benchmark.get("title") or "").lower()
            platform = (benchmark.get("platform") or "").lower()
            description = (benchmark.get("description") or "").lower()
            version = (benchmark.get("version") or "").lower()

            if query and not any(
                [
                    query in benchmark_id.lower(),
                    query in title,
                    query in platform,
                    query in description,
                    query in version,
                ]
            ):
                continue

            self._benchmarks.append(benchmark)

        self._populate_table()
        self._update_summary()

        # Update search count
        search_count = self.query_one("#search-count", Static)
        if query:
            search_count.update(f"{len(self._benchmarks)}/{len(self._all_benchmarks)}")
        else:
            search_count.update("")

        if self._benchmarks:
            self._show_detail(0)


def run_catalog_browser(benchmarks: list[dict], offline: bool = False) -> None:
    """Run the catalog browser TUI.

    Args:
        benchmarks: List of benchmark dictionaries from catalog search.
        offline: Whether running in offline mode (shows indicator).
    """
    app = CatalogBrowserApp(benchmarks=benchmarks, offline=offline)
    app.title = "CIS Benchmark Catalog"
    app.run()
