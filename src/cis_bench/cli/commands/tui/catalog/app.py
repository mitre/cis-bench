"""Catalog browser TUI application."""

import logging

from rich.text import Text
from textual.binding import Binding
from textual.widgets import DataTable, Static

from cis_bench.cli.commands.tui.base import COMMON_BINDINGS, BaseBrowserApp
from cis_bench.cli.commands.tui.catalog.actions import CATALOG_CSS, ActionMenu
from cis_bench.cli.commands.tui.catalog.detail import CatalogDetailView

logger = logging.getLogger(__name__)


class CatalogBrowserApp(BaseBrowserApp):
    """Interactive TUI for browsing the CIS benchmark catalog."""

    CSS = CATALOG_CSS

    # Enable selection tracking
    supports_selection = True

    # Extend COMMON_BINDINGS with catalog-specific bindings
    BINDINGS = COMMON_BINDINGS + [
        # Selection
        Binding("space", "toggle_select", "Select", show=True),
        # Actions menu
        Binding("enter", "open_actions", "Actions", show=True),
        # Direct action shortcuts (skip menu)
        Binding("v", "view_benchmark", "View", show=True),
        Binding("d", "diff_benchmarks", "Diff", show=True),
        Binding("e", "export_benchmark", "Export", show=False),  # Also 's'
        Binding("s", "export_benchmark", "Save/Export", show=False),
    ]

    def __init__(self, benchmarks: list[dict], offline: bool = False, **kwargs):
        """Initialize the catalog browser.

        Args:
            benchmarks: List of benchmark dictionaries from catalog search.
            offline: Whether running in offline mode.
        """
        super().__init__(**kwargs)
        # Standardized naming: _items for visible, _all_items for unfiltered
        self._items = benchmarks
        self._all_items = benchmarks.copy()
        self.offline = offline
        self._downloaded_ids: set[str] = set()
        self._load_downloaded_ids()

    def get_detail_view(self) -> Static:
        """Return the catalog detail view widget."""
        return CatalogDetailView(id="detail-view")

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
        text.append(f"{len(self._items)} benchmarks", style="dim")
        if self._selected_indices:
            text.append(f"  ({len(self._selected_indices)} selected)", style="cyan")
        return text

    def _update_summary(self) -> None:
        """Update the summary display."""
        summary = self.query_one("#summary", Static)
        summary.update(self._build_summary())

    def _get_columns(self) -> list[str]:
        """Return column headers for catalog table."""
        return ["", "ID", "Title", "Platform"]

    def _populate_table(self) -> None:
        """Populate the table with benchmark data."""
        table = self.query_one("#changes-table", DataTable)

        for idx, benchmark in enumerate(self._items):
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

    def _show_detail(self, index: int) -> None:
        """Show detail for the selected benchmark."""
        if index < 0 or index >= len(self._items):
            return

        benchmark = self._items[index]
        detail_view = self.query_one("#detail-view", CatalogDetailView)
        detail_view.update_content(benchmark)

    def _on_selection_changed(self) -> None:
        """Override to rebuild table and update summary on selection change."""
        # Rebuild table to show updated checkboxes
        self._rebuild_table_preserve_cursor()
        self._update_summary()

    def _rebuild_table_preserve_cursor(self) -> None:
        """Rebuild table preserving cursor position."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row
        table.clear()
        self._populate_table()
        if current_row is not None and current_row < len(self._items):
            table.move_cursor(row=current_row)

    def action_open_actions(self) -> None:
        """Open the actions menu for the current benchmark."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row is None or current_row >= len(self._items):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._items[current_row]
        benchmark_id = str(benchmark.get("benchmark_id", ""))
        is_downloaded = benchmark_id in self._downloaded_ids

        self.push_screen(
            ActionMenu(benchmark, is_downloaded=is_downloaded),
            self._handle_action,
        )

    def _handle_action(self, result: tuple | None) -> None:
        """Handle the result from the action menu.

        Exits the app with action info for the runner to handle launching
        the appropriate TUI (ViewApp, DiffApp, etc.).
        """
        if result is None:
            return

        action, benchmark = result
        benchmark_id = str(benchmark.get("benchmark_id", ""))

        if action == "download":
            # Download is handled by auto-fetch in view/diff/export
            # Show info message - user can also use CLI for explicit download
            self.notify(
                f"Content is fetched automatically when viewing/exporting. "
                f"For explicit download: cis-bench download {benchmark_id}",
                severity="information",
            )
        elif action == "view":
            # Exit app with view action - runner will launch ViewApp
            self.exit(("view", benchmark_id))
        elif action == "diff":
            # Validate exactly 2 benchmarks selected
            if len(self._selected_indices) != 2:
                self.notify(
                    "Select exactly 2 benchmarks to compare (use Space to select)",
                    severity="warning",
                )
                return
            # Get the two selected benchmark IDs
            selected_ids = [
                str(self._items[idx].get("benchmark_id", ""))
                for idx in sorted(self._selected_indices)
            ]
            # Exit app with diff action - runner will launch DiffApp
            self.exit(("diff", selected_ids[0], selected_ids[1]))
        elif action == "export":
            # Exit app with export action - runner will handle export
            self.exit(("export", benchmark_id))

    def action_view_benchmark(self) -> None:
        """Direct view action - 'v' key. Skips the action menu."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row is None or current_row >= len(self._items):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._items[current_row]
        benchmark_id = str(benchmark.get("benchmark_id", ""))
        self.exit(("view", benchmark_id))

    def action_diff_benchmarks(self) -> None:
        """Direct diff action - 'd' key. Requires exactly 2 selected."""
        if len(self._selected_indices) != 2:
            self.notify(
                "Select exactly 2 benchmarks to compare (use Space to select)",
                severity="warning",
            )
            return

        selected_ids = [
            str(self._items[idx].get("benchmark_id", "")) for idx in sorted(self._selected_indices)
        ]
        self.exit(("diff", selected_ids[0], selected_ids[1]))

    def action_export_benchmark(self) -> None:
        """Direct export action - 'e' or 's' key. Skips the action menu."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row is None or current_row >= len(self._items):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._items[current_row]
        benchmark_id = str(benchmark.get("benchmark_id", ""))
        self.exit(("export", benchmark_id))

    def _rebuild_table(self) -> None:
        """Rebuild the table with current sort order."""
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._selected_indices.clear()  # Clear selections on rebuild

        # Sort by published date
        self._items = sorted(
            self._items,
            key=lambda x: x.get("published_date", "") or "",
            reverse=not self._sort_reverse,  # Default is newest first
        )

        self._populate_table()
        self._update_summary()

        if self._items:
            self._show_detail(0)

    def _apply_search_filter(self, query: str) -> None:
        """Filter the table based on search query."""
        query = query.lower().strip()
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._items = []
        self._selected_indices.clear()  # Clear selections on filter

        for benchmark in self._all_items:
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

            self._items.append(benchmark)

        self._populate_table()
        self._update_summary()

        # Update search count
        search_count = self.query_one("#search-count", Static)
        if query:
            search_count.update(f"{len(self._items)}/{len(self._all_items)}")
        else:
            search_count.update("")

        if self._items:
            self._show_detail(0)


def run_catalog_browser(benchmarks: list[dict], offline: bool = False) -> None:
    """Run the catalog browser TUI with action handling.

    When the user selects an action (View, Diff, Export), the catalog exits
    and this function launches the appropriate TUI. After that TUI exits,
    control returns to the catalog browser.

    Args:
        benchmarks: List of benchmark dictionaries from catalog search.
        offline: Whether running in offline mode (shows indicator).
    """
    from cis_bench.cli.commands.diff import compare_benchmarks
    from cis_bench.cli.commands.tui.diff import run_interactive_diff
    from cis_bench.cli.commands.tui.view import run_interactive_view
    from cis_bench.cli.commands.utils import load_benchmark

    while True:
        app = CatalogBrowserApp(benchmarks=benchmarks, offline=offline)
        app.title = "CIS Benchmark Catalog"
        result = app.run()

        if result is None:
            # User quit the catalog - exit the loop
            break

        action = result[0]

        if action == "view":
            benchmark_id = result[1]
            try:
                data = load_benchmark(benchmark_id, offline=offline)
                recommendations = data.get("recommendations", [])
                run_interactive_view(data, recommendations, offline=offline)
            except Exception as e:
                # If view fails, log error and return to catalog
                logger.error(f"Failed to load benchmark {benchmark_id}: {e}")
                # Continue loop to return to catalog

        elif action == "diff":
            old_id, new_id = result[1], result[2]
            try:
                old_data = load_benchmark(old_id, offline=offline)
                new_data = load_benchmark(new_id, offline=offline)
                comparison = compare_benchmarks(old_data, new_data)
                run_interactive_diff(comparison, old_data, new_data, offline=offline)
            except Exception as e:
                logger.error(f"Failed to load benchmarks for diff: {e}")
                # Continue loop to return to catalog

        elif action == "export":
            benchmark_id = result[1]
            # TODO: Launch export dialog TUI (ep9.7)
            # For now, show message and return to catalog
            logger.info(f"Export requested for {benchmark_id} - export dialog coming in ep9.7")
            # Continue loop to return to catalog

        # After any action completes, loop returns to catalog browser
