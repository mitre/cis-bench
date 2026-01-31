"""Catalog browser TUI application."""

import logging
from pathlib import Path

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.widgets import DataTable, Static
from textual.worker import get_current_worker

from cis_bench.cli.commands.tui.base import COMMON_BINDINGS, BaseBrowserApp
from cis_bench.cli.commands.tui.catalog.actions import CATALOG_CSS, ActionMenu
from cis_bench.cli.commands.tui.catalog.detail import CatalogDetailView
from cis_bench.cli.commands.tui.dialogs import (
    BatchProgressModal,
    ExportConfigDialog,
    ExportDialogResult,
    OutputPathDialog,
)
from cis_bench.services.export_service import ExportConfig, ExportService

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
        Binding("o", "open_in_browser", "Open URL", show=True),
    ]

    def __init__(self, benchmarks: list[dict], offline: bool = False, **kwargs):
        """Initialize the catalog browser.

        Args:
            benchmarks: List of benchmark dictionaries from catalog search.
            offline: Whether running in offline mode.
        """
        super().__init__(**kwargs)
        # Standardized naming: _items for visible, _all_items for unfiltered
        self._items = self._sort_benchmarks(benchmarks)
        self._all_items = self._items.copy()
        self.offline = offline
        self._downloaded_ids: set[str] = set()
        self._load_downloaded_ids()

    def _sort_benchmarks(self, benchmarks: list[dict]) -> list[dict]:
        """Sort benchmarks by title, then by benchmark_id (newest first within group).

        Args:
            benchmarks: List of benchmark dictionaries.

        Returns:
            Sorted list with groups ordered alphabetically by title,
            and within each group, newest (highest benchmark_id) first.
        """
        return sorted(
            benchmarks,
            key=lambda x: (
                (x.get("title") or "").lower(),  # Primary: title alphabetically
                -int(
                    x.get("benchmark_id") or 0
                ),  # Secondary: benchmark_id descending (newest first)
            ),
        )

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
                self._downloaded_ids = db.get_downloaded_benchmark_ids()
                logger.debug(f"Loaded {len(self._downloaded_ids)} downloaded benchmark IDs")
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
                # Wide: show both panes (65/35 split for catalog)
                detail_container.styles.display = "block"
                list_container.styles.width = "65%"
                detail_container.styles.width = "35%"
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
        # Columns: checkbox, cached, ID, Title, Version, Latest, Published, Platform
        return ["", "⬇", "ID", "Title", "Version", "Latest", "Published", "Platform"]

    def _populate_table(self) -> None:
        """Populate the table with benchmark data."""
        table = self.query_one("#changes-table", DataTable)

        for idx, benchmark in enumerate(self._items):
            # Selection checkbox
            is_selected = idx in self._selected_indices
            checkbox = Text("●", style="cyan bold") if is_selected else Text("○", style="dim")

            # Cached/downloaded status indicator
            benchmark_id = str(benchmark.get("benchmark_id", ""))
            is_cached = benchmark_id in self._downloaded_ids
            cached_indicator = Text("✓", style="green") if is_cached else Text("", style="dim")

            # Title (without version)
            title = benchmark.get("title", "Unknown")

            # Version (separate column)
            version = benchmark.get("version", "")

            # Latest indicator (separate column)
            latest = Text("★", style="yellow bold") if benchmark.get("is_latest") else Text("")

            # Published date (YYYY-MM-DD format, show as-is)
            published = benchmark.get("published_date") or ""

            # Platform (max is "oracle-database" at 15 chars)
            platform = (benchmark.get("platform") or "")[:15]

            table.add_row(
                checkbox,
                cached_indicator,
                benchmark_id,
                self._truncate(title, 50),  # Slightly shorter to fit Published
                version,
                latest,
                published,
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
            old_id, new_id = self._get_ordered_diff_ids()
            self._load_and_diff(old_id, new_id)
        elif action == "export":
            # Determine context based on selection count
            if len(self._selected_indices) > 1:
                context = "batch"
            else:
                context = "single"
            self._start_export_flow(context)

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
        import time

        from cis_bench.cli.commands.utils import load_benchmark

        # Get worker reference for cancellation checks (best practice)
        worker = get_current_worker()
        modal = getattr(self, "_loading_modal", None)

        def progress_callback(current: int, total: int, message: str) -> None:
            """Update LoadingModal from download progress."""
            # Check both worker and modal cancellation
            if worker.is_cancelled or (modal and modal.is_cancelled):
                return
            if modal:
                if total > 0:
                    # Calculate percentage: 10% for connect, 80% for download, 10% for processing
                    download_progress = int((current / total) * 80) + 10
                    # Message already contains [current/total] from utils.py
                    self.call_from_thread(
                        modal.update_progress,
                        download_progress,
                        message,
                    )
                else:
                    # No total yet, just show message
                    self.call_from_thread(modal.update_progress, 5, message)

        try:
            # Check for early cancellation
            if worker.is_cancelled:
                return

            # Brief delay to ensure modal is mounted and visible
            time.sleep(0.1)

            # Update progress - connecting
            if not worker.is_cancelled and modal and not modal.is_cancelled:
                self.call_from_thread(modal.update_progress, 5, "Connecting to CIS WorkBench...")

            # Check before long operation
            if worker.is_cancelled:
                return

            data = load_benchmark(
                benchmark_id,
                offline=self.offline,
                progress_callback=progress_callback,
                silent=True,  # Suppress console output in TUI mode
            )

            # Check after long operation
            if worker.is_cancelled or (modal and modal.is_cancelled):
                return  # User cancelled

            if modal and not worker.is_cancelled:
                self.call_from_thread(modal.update_progress, 95, "Processing recommendations...")

            recommendations = data.get("recommendations", [])

            if worker.is_cancelled or (modal and modal.is_cancelled):
                return  # User cancelled

            if modal and not worker.is_cancelled:
                self.call_from_thread(modal.update_progress, 100, "Ready!")

            # Complete loading and push screen
            if not worker.is_cancelled:
                self.call_from_thread(self._on_view_loaded, data, recommendations)

        except Exception as e:
            if not worker.is_cancelled:
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

        # Push view screen with callback to refresh download status when returning
        self.push_screen(
            ViewScreen(data, recommendations, offline=self.offline),
            self._on_screen_dismissed,
        )

    def _on_screen_dismissed(self, _result=None) -> None:
        """Callback when ViewScreen or DiffScreen is dismissed.

        Refreshes the downloaded IDs and rebuilds table to show updated status.
        """
        self._load_downloaded_ids()
        self._rebuild_table_preserve_cursor()

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
        import time

        from cis_bench.cli.commands.diff import compare_benchmarks
        from cis_bench.cli.commands.utils import load_benchmark

        # Get worker reference for cancellation checks (best practice)
        worker = get_current_worker()
        modal = getattr(self, "_loading_modal", None)

        def make_progress_callback(base_percent: int, range_percent: int, label: str):
            """Create a progress callback for a specific download phase."""

            def callback(current: int, total: int, message: str) -> None:
                # Check both worker and modal cancellation
                if worker.is_cancelled or (modal and modal.is_cancelled):
                    return
                if modal:
                    if total > 0:
                        phase_progress = int((current / total) * range_percent)
                        self.call_from_thread(
                            modal.update_progress,
                            base_percent + phase_progress,
                            f"{label}: [{current}/{total}]",
                        )
                    else:
                        self.call_from_thread(modal.update_progress, base_percent, message)

            return callback

        try:
            # Check for early cancellation
            if worker.is_cancelled:
                return

            # Brief delay to ensure modal is mounted and visible
            time.sleep(0.1)

            # Load first benchmark (0-40%)
            if not worker.is_cancelled and modal and not modal.is_cancelled:
                self.call_from_thread(modal.update_progress, 2, f"Connecting for {old_id}...")

            # Check before long operation
            if worker.is_cancelled:
                return

            old_data = load_benchmark(
                old_id,
                offline=self.offline,
                progress_callback=make_progress_callback(2, 38, f"Old ({old_id})"),
                silent=True,
            )

            # Check after long operation
            if worker.is_cancelled or (modal and modal.is_cancelled):
                return

            # Load second benchmark (40-80%)
            if modal and not worker.is_cancelled:
                self.call_from_thread(modal.update_progress, 42, f"Connecting for {new_id}...")

            # Check before long operation
            if worker.is_cancelled:
                return

            new_data = load_benchmark(
                new_id,
                offline=self.offline,
                progress_callback=make_progress_callback(42, 38, f"New ({new_id})"),
                silent=True,
            )

            # Check after long operation
            if worker.is_cancelled or (modal and modal.is_cancelled):
                return

            # Compare (80-95%)
            if modal and not worker.is_cancelled:
                self.call_from_thread(modal.update_progress, 85, "Comparing benchmarks...")

            comparison = compare_benchmarks(old_data, new_data)

            if worker.is_cancelled or (modal and modal.is_cancelled):
                return

            if modal and not worker.is_cancelled:
                self.call_from_thread(modal.update_progress, 100, "Ready!")

            # Complete
            if not worker.is_cancelled:
                self.call_from_thread(self._on_diff_loaded, comparison, old_data, new_data)

        except Exception as e:
            if not worker.is_cancelled:
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

        # Push diff screen with callback to refresh download status when returning
        self.push_screen(
            DiffScreen(comparison, old_data, new_data, offline=self.offline),
            self._on_screen_dismissed,
        )

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

    def action_open_in_browser(self) -> None:
        """Open current benchmark's CIS WorkBench URL in browser - 'o' key."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row is None or current_row >= len(self._items):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._items[current_row]
        url = benchmark.get("url")

        if not url:
            self.notify("No URL available for this benchmark", severity="warning")
            return

        # Use Textual's open_url for cross-platform browser opening
        self.open_url(url)
        self.notify(f"Opening in browser: {url}", severity="information")

    def action_diff_benchmarks(self) -> None:
        """Direct diff action - 'd' key. Requires exactly 2 selected."""
        if len(self._selected_indices) != 2:
            self.notify(
                "Select exactly 2 benchmarks to compare (use Space to select)",
                severity="warning",
            )
            return

        old_id, new_id = self._get_ordered_diff_ids()
        self._load_and_diff(old_id, new_id)

    def _get_ordered_diff_ids(self) -> tuple[str, str]:
        """Get selected benchmark IDs ordered by date (old first, new second).

        Returns:
            Tuple of (old_id, new_id) sorted by published_date.
        """
        selected_benchmarks = [self._items[idx] for idx in self._selected_indices]

        # Sort by published_date (older first), fallback to benchmark_id
        def sort_key(b: dict) -> str:
            return b.get("published_date") or b.get("benchmark_id", "")

        sorted_benchmarks = sorted(selected_benchmarks, key=sort_key)

        old_id = str(sorted_benchmarks[0].get("benchmark_id", ""))
        new_id = str(sorted_benchmarks[1].get("benchmark_id", ""))

        return old_id, new_id

    def action_export_benchmark(self) -> None:
        """Direct export action - 'e' or 's' key. Skips the action menu."""
        # Determine context based on selection count
        if len(self._selected_indices) > 1:
            context = "batch"
        else:
            # Validate we have a current row for single export
            table = self.query_one("#changes-table", DataTable)
            current_row = table.cursor_row
            if current_row is None or current_row >= len(self._items):
                self.notify("No benchmark selected", severity="warning")
                return
            context = "single"
        self._start_export_flow(context)

    def _rebuild_table(self) -> None:
        """Rebuild the table with current sort order."""
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._selected_indices.clear()  # Clear selections on rebuild

        # Sort by title, then benchmark_id (oldest first within each group)
        self._items = self._sort_benchmarks(self._items)

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

        # Apply consistent sorting after filtering
        self._items = self._sort_benchmarks(self._items)
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

    # --- Export Flow ---

    def _start_export_flow(self, context: str) -> None:
        """Start export flow by pushing format selection dialog.

        Args:
            context: Export context - 'single' or 'batch'
        """
        self._export_context = context
        dialog = ExportConfigDialog(context=context)
        self.push_screen(dialog, self._on_export_config)

    def _on_export_config(self, result: ExportDialogResult | None) -> None:
        """Handle export config dialog result.

        Args:
            result: Export config result or None if cancelled
        """
        if not result:
            return

        self._export_format = result.format
        self._export_style = result.style

        # Show output path dialog
        dialog = OutputPathDialog(
            default_dir=Path.cwd(),
            show_pattern=self._export_context == "batch",
        )
        self.push_screen(dialog, self._on_output_path)

    def _on_output_path(self, result: tuple[Path, str | None] | None) -> None:
        """Handle output path dialog result.

        Args:
            result: (output_dir, pattern) or None if cancelled
        """
        if not result:
            return

        output_dir, pattern = result

        # Build export config
        config = ExportConfig(
            format=self._export_format,
            output_dir=output_dir,
            style=self._export_style,
            filename_pattern=pattern,
        )

        # Execute export based on context
        if self._export_context == "batch":
            self._do_batch_export(config)
        else:
            self._do_single_export(config)

    def _do_single_export(self, config: ExportConfig) -> None:
        """Execute single benchmark export.

        Args:
            config: Export configuration
        """
        # Get current benchmark
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row
        if current_row is None or current_row >= len(self._items):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._items[current_row]
        benchmark_id = str(benchmark.get("benchmark_id", ""))

        # Load benchmark and export
        self._pending_export_id = benchmark_id
        self._pending_export_config = config
        self._load_and_export_single(benchmark_id, config)

    def _load_and_export_single(self, benchmark_id: str, config: ExportConfig) -> None:
        """Load benchmark with loading modal and export.

        Args:
            benchmark_id: Benchmark ID to export
            config: Export configuration
        """
        from cis_bench.cli.commands.tui.widgets import LoadingModal

        self._pending_export_id = benchmark_id
        self._pending_export_config = config

        modal = LoadingModal(f"Exporting {benchmark_id}...")
        self._loading_modal = modal
        self.push_screen(modal)

        self._start_export_worker(benchmark_id, config)

    @work(exclusive=True, thread=True)
    def _start_export_worker(self, benchmark_id: str, config: ExportConfig) -> None:
        """Worker to load and export benchmark in background thread.

        Args:
            benchmark_id: Benchmark ID to export
            config: Export configuration
        """
        from cis_bench.cli.commands.utils import load_benchmark

        worker = get_current_worker()
        modal = getattr(self, "_loading_modal", None)

        def progress_callback(current: int, total: int, message: str) -> None:
            if worker.is_cancelled or (modal and modal.is_cancelled):
                return
            if modal and total > 0:
                progress = int((current / total) * 80) + 10
                self.call_from_thread(modal.update_progress, progress, message)

        try:
            if modal:
                self.call_from_thread(modal.update_progress, 5, "Loading benchmark...")

            # Load benchmark
            benchmark = load_benchmark(
                benchmark_id=benchmark_id,
                progress_callback=progress_callback,
            )

            if worker.is_cancelled or (modal and modal.is_cancelled):
                self.call_from_thread(self._export_cancelled)
                return

            if not benchmark:
                self.call_from_thread(
                    self._export_failed,
                    f"Could not load benchmark {benchmark_id}",
                )
                return

            if modal:
                self.call_from_thread(modal.update_progress, 90, "Exporting...")

            # Export benchmark
            service = ExportService()
            result = service.export_single(benchmark, config)

            if result.success:
                self.call_from_thread(self._export_completed, result.path)
            else:
                self.call_from_thread(self._export_failed, result.error or "Unknown error")

        except Exception as e:
            logger.error(f"Export worker error: {e}")
            self.call_from_thread(self._export_failed, str(e))

    def _export_completed(self, path: Path | None) -> None:
        """Handle successful export.

        Args:
            path: Path to exported file
        """
        modal = getattr(self, "_loading_modal", None)
        if modal:
            self.pop_screen()

        if path:
            self.notify(f"Exported to {path}", title="Export Complete")
        else:
            self.notify("Export completed", title="Export Complete")

    def _export_failed(self, error: str) -> None:
        """Handle failed export.

        Args:
            error: Error message
        """
        modal = getattr(self, "_loading_modal", None)
        if modal:
            self.pop_screen()

        self.notify(f"Export failed: {error}", severity="error")

    def _export_cancelled(self) -> None:
        """Handle cancelled export."""
        modal = getattr(self, "_loading_modal", None)
        if modal:
            self.pop_screen()

        self.notify("Export cancelled", severity="warning")

    def _do_batch_export(self, config: ExportConfig) -> None:
        """Execute batch export for selected benchmarks.

        Args:
            config: Export configuration
        """
        # Get selected benchmark IDs
        selected_benchmarks = [self._items[i] for i in sorted(self._selected_indices)]
        if not selected_benchmarks:
            self.notify("No benchmarks selected", severity="warning")
            return

        # Show progress modal
        modal = BatchProgressModal(
            title="Exporting Benchmarks",
            total=len(selected_benchmarks),
        )
        self._batch_modal = modal
        self._batch_benchmarks = selected_benchmarks
        self._batch_config = config
        self.push_screen(modal)

        # Start batch worker
        self._start_batch_export_worker(selected_benchmarks, config)

    @work(exclusive=True, thread=True)
    def _start_batch_export_worker(self, benchmarks: list[dict], config: ExportConfig) -> None:
        """Worker to export multiple benchmarks.

        Args:
            benchmarks: List of benchmark metadata dicts
            config: Export configuration
        """
        from cis_bench.cli.commands.utils import load_benchmark

        worker = get_current_worker()
        modal = getattr(self, "_batch_modal", None)

        results = []

        for i, benchmark_meta in enumerate(benchmarks, 1):
            if worker.is_cancelled or (modal and modal.is_cancelled):
                break

            benchmark_id = str(benchmark_meta.get("benchmark_id", ""))

            if modal:
                self.call_from_thread(
                    modal.update_progress,
                    i,
                    f"Loading {benchmark_id}...",
                )

            try:
                # Load benchmark
                benchmark = load_benchmark(benchmark_id=benchmark_id)

                if not benchmark:
                    results.append((benchmark_id, False, "Failed to load"))
                    if modal:
                        self.call_from_thread(modal.add_result, benchmark_id, False)
                    continue

                # Export
                service = ExportService()
                result = service.export_single(benchmark, config)

                results.append((benchmark_id, result.success, result.error))
                if modal:
                    self.call_from_thread(modal.add_result, benchmark_id, result.success)

            except Exception as e:
                logger.error(f"Batch export error for {benchmark_id}: {e}")
                results.append((benchmark_id, False, str(e)))
                if modal:
                    self.call_from_thread(modal.add_result, benchmark_id, False)

        # Complete
        self.call_from_thread(self._batch_export_completed, results)

    def _batch_export_completed(self, results: list[tuple[str, bool, str | None]]) -> None:
        """Handle batch export completion.

        Args:
            results: List of (benchmark_id, success, error) tuples
        """
        modal = getattr(self, "_batch_modal", None)
        if modal:
            self.pop_screen()

        success_count = sum(1 for _, success, _ in results if success)
        total = len(results)

        if success_count == total:
            self.notify(f"Exported {total} benchmarks", title="Batch Export Complete")
        elif success_count > 0:
            self.notify(
                f"Exported {success_count}/{total} benchmarks",
                title="Batch Export Partial",
                severity="warning",
            )
        else:
            self.notify("All exports failed", severity="error")


def run_catalog_browser(
    benchmarks: list[dict],
    offline: bool = False,
    session=None,
    keep_alive_interval: float = 5.0,
) -> None:
    """Run the catalog browser TUI.

    ViewScreen and DiffScreen are pushed onto the screen stack when triggered.
    Esc/q pops back to catalog instantly. No exit/restart loop needed.

    Args:
        benchmarks: List of benchmark dictionaries from catalog search.
        offline: Whether running in offline mode (shows indicator).
        session: Optional authenticated requests.Session for keep-alive.
            If provided and not offline, session will be kept alive during TUI.
        keep_alive_interval: Minutes between keep-alive pings (default: 5).
    """
    from cis_bench.fetcher.auth import SessionKeepAlive

    app = CatalogBrowserApp(benchmarks=benchmarks, offline=offline)
    app.title = "CIS Benchmark Catalog"

    # Start keep-alive if we have a session and not offline
    if session is not None and not offline:
        with SessionKeepAlive(session, interval_minutes=keep_alive_interval):
            app.run()
    else:
        app.run()
