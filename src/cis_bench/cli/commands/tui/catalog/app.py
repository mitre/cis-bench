"""Catalog browser TUI application."""

import logging

from rich.text import Text
from textual import work
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

        Pushes appropriate screen onto the stack (no exit/restart needed).
        Uses workers for async loading to keep UI responsive.
        """
        if result is None:
            return

        action, benchmark = result
        benchmark_id = str(benchmark.get("benchmark_id", ""))

        if action == "download":
            # Download is handled by auto-fetch in view/diff/export
            self.notify(
                f"Content is fetched automatically when viewing/exporting. "
                f"For explicit download: cis-bench download {benchmark_id}",
                severity="information",
            )
        elif action == "view":
            self._load_and_view(benchmark_id)
        elif action == "diff":
            # Validate exactly 2 benchmarks selected
            if len(self._selected_indices) != 2:
                self.notify(
                    "Select exactly 2 benchmarks to compare (use Space to select)",
                    severity="warning",
                )
                return
            selected_ids = [
                str(self._items[idx].get("benchmark_id", ""))
                for idx in sorted(self._selected_indices)
            ]
            self._load_and_diff(selected_ids[0], selected_ids[1])
        elif action == "export":
            # TODO: Export dialog (ep9.7)
            self.notify(
                f"Export dialog not yet implemented. Use: cis-bench export {benchmark_id}",
                severity="warning",
            )

    def _load_and_view(self, benchmark_id: str) -> None:
        """Load benchmark with loading modal and push ViewScreen."""
        from cis_bench.cli.commands.tui.widgets import LoadingModal

        # Store benchmark_id for the worker
        self._pending_view_id = benchmark_id

        # Push loading modal with callback
        def on_modal_dismiss(completed: bool) -> None:
            if not completed:
                # User cancelled
                self.notify("Loading cancelled", severity="warning")

        modal = LoadingModal(f"Loading {benchmark_id}...")
        self._loading_modal = modal
        self.push_screen(modal, on_modal_dismiss)

        # Start the worker
        self._start_view_worker(benchmark_id)

    @work(exclusive=True, thread=True)
    def _start_view_worker(self, benchmark_id: str) -> None:
        """Worker to load benchmark in background thread."""
        from cis_bench.cli.commands.utils import load_benchmark

        modal = getattr(self, "_loading_modal", None)

        try:
            # Update progress
            if modal and not modal.is_cancelled:
                self.call_from_thread(modal.update_progress, 10, "Connecting...")

            data = load_benchmark(benchmark_id, offline=self.offline)

            if modal and modal.is_cancelled:
                return  # User cancelled

            if modal:
                self.call_from_thread(modal.update_progress, 80, "Processing...")

            recommendations = data.get("recommendations", [])

            if modal and modal.is_cancelled:
                return  # User cancelled

            # Complete loading and push screen
            self.call_from_thread(self._on_view_loaded, data, recommendations)

        except Exception as e:
            self.call_from_thread(self._on_load_error, str(e))

    def _on_view_loaded(self, data: dict, recommendations: list) -> None:
        """Handle successful view load (called from main thread)."""
        from cis_bench.cli.commands.tui.screens import ViewScreen

        # Pop loading modal if still there
        modal = getattr(self, "_loading_modal", None)
        if modal:
            try:
                self.pop_screen()  # Remove loading modal
            except Exception as e:
                logger.debug(f"Could not pop loading modal: {e}")
            self._loading_modal = None

        # Push view screen
        self.push_screen(ViewScreen(data, recommendations, offline=self.offline))

    def _on_load_error(self, error: str) -> None:
        """Handle load failure (called from main thread)."""
        # Pop loading modal if still there
        modal = getattr(self, "_loading_modal", None)
        if modal:
            try:
                self.pop_screen()  # Remove loading modal
            except Exception as e:
                logger.debug(f"Could not pop loading modal on error: {e}")
            self._loading_modal = None

        self.notify(f"Failed to load: {error}", severity="error", timeout=10)

    def _load_and_diff(self, old_id: str, new_id: str) -> None:
        """Load both benchmarks with loading modal and push DiffScreen."""
        from cis_bench.cli.commands.tui.widgets import LoadingModal

        # Store IDs for the worker
        self._pending_diff_ids = (old_id, new_id)

        # Push loading modal with callback
        def on_modal_dismiss(completed: bool) -> None:
            if not completed:
                self.notify("Loading cancelled", severity="warning")

        modal = LoadingModal("Comparing benchmarks...")
        self._loading_modal = modal
        self.push_screen(modal, on_modal_dismiss)

        # Start the worker
        self._start_diff_worker(old_id, new_id)

    @work(exclusive=True, thread=True)
    def _start_diff_worker(self, old_id: str, new_id: str) -> None:
        """Worker to load both benchmarks in background thread."""
        from cis_bench.cli.commands.diff import compare_benchmarks
        from cis_bench.cli.commands.utils import load_benchmark

        modal = getattr(self, "_loading_modal", None)

        try:
            # Load first benchmark
            if modal and not modal.is_cancelled:
                self.call_from_thread(modal.update_progress, 10, f"Loading {old_id}...")

            old_data = load_benchmark(old_id, offline=self.offline)

            if modal and modal.is_cancelled:
                return

            # Load second benchmark
            if modal:
                self.call_from_thread(modal.update_progress, 40, f"Loading {new_id}...")

            new_data = load_benchmark(new_id, offline=self.offline)

            if modal and modal.is_cancelled:
                return

            # Compare
            if modal:
                self.call_from_thread(modal.update_progress, 70, "Comparing...")

            comparison = compare_benchmarks(old_data, new_data)

            if modal and modal.is_cancelled:
                return

            # Complete
            self.call_from_thread(self._on_diff_loaded, comparison, old_data, new_data)

        except Exception as e:
            self.call_from_thread(self._on_load_error, str(e))

    def _on_diff_loaded(self, comparison: dict, old_data: dict, new_data: dict) -> None:
        """Handle successful diff load (called from main thread)."""
        from cis_bench.cli.commands.tui.screens import DiffScreen

        # Pop loading modal if still there
        modal = getattr(self, "_loading_modal", None)
        if modal:
            try:
                self.pop_screen()  # Remove loading modal
            except Exception as e:
                logger.debug(f"Could not pop loading modal for diff: {e}")
            self._loading_modal = None

        # Push diff screen
        self.push_screen(DiffScreen(comparison, old_data, new_data, offline=self.offline))

    def action_view_benchmark(self) -> None:
        """Direct view action - 'v' key. Skips the action menu."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row is None or current_row >= len(self._items):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._items[current_row]
        benchmark_id = str(benchmark.get("benchmark_id", ""))
        self._load_and_view(benchmark_id)

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
        self._load_and_diff(selected_ids[0], selected_ids[1])

    def action_export_benchmark(self) -> None:
        """Direct export action - 'e' or 's' key. Skips the action menu."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row is None or current_row >= len(self._items):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._items[current_row]
        benchmark_id = str(benchmark.get("benchmark_id", ""))
        # TODO: Export dialog (ep9.7)
        self.notify(
            f"Export dialog not yet implemented. Use: cis-bench export {benchmark_id}",
            severity="warning",
        )

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
    """Run the catalog browser TUI.

    ViewScreen and DiffScreen are pushed onto the screen stack when triggered.
    Esc/q pops back to catalog instantly. No exit/restart loop needed.

    Args:
        benchmarks: List of benchmark dictionaries from catalog search.
        offline: Whether running in offline mode (shows indicator).
    """
    app = CatalogBrowserApp(benchmarks=benchmarks, offline=offline)
    app.title = "CIS Benchmark Catalog"
    app.run()
