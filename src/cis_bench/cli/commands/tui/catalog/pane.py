"""Catalog tab pane for main TUI.

Compound widget following Textual framework best practices:
- Compose pattern for DataTable + DetailView layout
- Reactive state for selected benchmarks
- Message passing for cross-widget communication
- Proper lifecycle: compose → on_mount → reactive updates
- Inline progress display (no modal screen flash)
"""

import logging

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Label, ProgressBar
from textual.worker import get_current_worker

from cis_bench.cli.commands.tui.base import BaseTabPane
from cis_bench.cli.commands.tui.catalog.detail import CatalogDetailView

logger = logging.getLogger(__name__)


class CatalogTabPane(BaseTabPane):
    """Catalog tab pane - browse and manage catalog.

    Compound widget following Textual best practices:
    - Uses reactive state for selection tracking
    - Composes DataTable + DetailView in Horizontal layout
    - Loads data in worker (non-blocking)
    - Messages bubble up to parent (MainTUIApp)
    """

    # Extend BaseTabPane.BINDINGS (includes arrow keys, j/k, page up/down, tab for pane switching)
    # UX convention: lowercase = frequent/quick, uppercase = less frequent/"bigger" actions
    BINDINGS = BaseTabPane.BINDINGS + [
        # Selection
        Binding("space", "toggle_select", "Select", show=True),
        # Actions menu
        Binding("enter", "open_actions", "Actions", show=True),
        # Direct action shortcuts (skip menu)
        Binding("v", "view_benchmark", "View", show=True),
        Binding("d", "diff_benchmarks", "Diff", show=True),
        Binding("e", "export_benchmark", "Export", show=False),
        Binding("o", "open_in_browser", "Open URL", show=True),
        # Note: 'r' is inherited from BaseTabPane for reverse_sort
        Binding("R", "refresh_catalog", "Refresh", show=True),  # Shift+R for network refresh
        # Escape cancels loading when active, otherwise bubbles up
        Binding("escape", "maybe_cancel_loading", "Cancel", show=False, priority=True),
    ]

    def __init__(self, **kwargs):
        """Initialize catalog tab pane with selection and download tracking."""
        super().__init__(**kwargs)
        self._items: list[dict] = []  # Current visible benchmarks
        self._selected_indices: set[int] = set()  # Selected row indices
        self._downloaded_ids: set[str] = set()  # Cached benchmark IDs
        self._is_loading: bool = False  # Track if loading operation in progress
        self._loading_cancelled: bool = False  # Track if user cancelled loading

    # CSS for inline loading progress (hidden by default)
    DEFAULT_CSS = """
    #loading-progress {
        display: none;
        width: 100%;
        dock: bottom;
        margin: 0 1;
    }
    #loading-status {
        display: none;
        dock: bottom;
        text-align: center;
        color: $text-muted;
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose catalog browser layout (Textual compose pattern)."""
        with Horizontal():
            # Left: Catalog table (width set in CSS)
            yield DataTable(
                id="catalog-table",
                zebra_stripes=True,
                cursor_type="row",
                show_cursor=True,
            )

            # Right: Detail view in scroll container (width set in CSS)
            # Must wrap in VerticalScroll for content longer than screen
            with VerticalScroll(id="detail-container"):
                yield CatalogDetailView(id="detail-view")

        # Inline loading progress (hidden by default, shown during load)
        # Uses inline widgets instead of LoadingModal to avoid screen flash
        yield Label("", id="loading-status")
        yield ProgressBar(total=100, show_eta=False, id="loading-progress")

    def on_mount(self) -> None:
        """Initialize catalog on mount (Textual lifecycle pattern)."""
        table = self.query_one("#catalog-table", DataTable)

        # Add columns
        table.add_columns("", "⬇", "ID", "Title", "Version", "Latest", "Published", "Platform")

        # Load downloaded IDs for status display
        self._load_downloaded_ids()

        # Load data in worker (non-blocking, framework best practice)
        self._load_catalog()

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

    # ========================================================================
    # Inline Progress Display (fixes screen flash)
    # ========================================================================

    def _show_loading(self, message: str = "Loading...") -> None:
        """Show inline loading progress widgets.

        Args:
            message: Initial status message to display.
        """
        self._is_loading = True
        self._loading_cancelled = False

        progress = self.query_one("#loading-progress", ProgressBar)
        status = self.query_one("#loading-status", Label)

        # Reset and show
        progress.update(progress=0)
        status.update(message)
        progress.display = True
        status.display = True

    def _update_loading(self, percent: int, message: str) -> None:
        """Update inline loading progress.

        Args:
            percent: Progress percentage (0-100).
            message: Status message to display.
        """
        if not self._is_loading:
            return

        progress = self.query_one("#loading-progress", ProgressBar)
        status = self.query_one("#loading-status", Label)

        progress.update(progress=percent)
        status.update(message)

    def _hide_loading(self) -> None:
        """Hide inline loading progress widgets."""
        self._is_loading = False

        try:
            progress = self.query_one("#loading-progress", ProgressBar)
            status = self.query_one("#loading-status", Label)
            progress.display = False
            status.display = False
        except Exception as e:
            logger.debug(f"Could not hide loading widgets: {e}")

    def _cancel_loading(self) -> None:
        """Cancel the current loading operation."""
        if not self._is_loading:
            return

        self._loading_cancelled = True
        self._hide_loading()

        # Cancel any running workers
        self.app.workers.cancel_all()

        self.notify("Loading cancelled", severity="warning")

    def action_cancel_loading(self) -> None:
        """Action to cancel loading (bound to Escape when loading)."""
        self._cancel_loading()

    def action_maybe_cancel_loading(self) -> None:
        """Cancel loading if active, otherwise let escape bubble up to quit."""
        if self._is_loading:
            self._cancel_loading()
        else:
            # Not loading - let the app handle escape (quit)
            self.app.action_quit()

    def get_selected_items(self) -> list[dict]:
        """Get the selected benchmark items.

        Returns:
            List of benchmark dicts at selected indices.
        """
        return [
            self._items[idx] for idx in sorted(self._selected_indices) if idx < len(self._items)
        ]

    @work(exclusive=True, thread=True)
    def _load_catalog(self) -> None:
        """Load catalog data (worker pattern for non-blocking I/O)."""
        worker = get_current_worker()

        try:
            from cis_bench.catalog.database import CatalogDatabase
            from cis_bench.config import Config

            if worker.is_cancelled:
                return

            db_path = Config.get_catalog_db_path()
            if not db_path.exists():
                self.app.call_from_thread(
                    self.notify,
                    "Catalog not found - run 'cis-bench catalog refresh'",
                    severity="warning",
                )
                return

            db = CatalogDatabase(db_path)

            # Use search with empty query to get all benchmarks (proper pattern)
            benchmarks = db.search("", status="Published", limit=1000)

            if worker.is_cancelled:
                return

            # Update UI from thread (framework requirement)
            self.app.call_from_thread(self._populate_table, benchmarks)

        except Exception as e:
            logger.error(f"Failed to load catalog: {e}", exc_info=True)
            self.app.call_from_thread(self.notify, f"Error loading catalog: {e}", severity="error")

    def _populate_table(self, benchmarks: list[dict]) -> None:
        """Populate table with benchmarks (called from worker thread).

        Args:
            benchmarks: List of benchmark dicts from catalog
        """
        table = self.query_one("#catalog-table", DataTable)

        # Store items for selection tracking
        self._items = benchmarks

        for idx, benchmark in enumerate(benchmarks):
            # Selection checkbox (cyan when selected, dim when not)
            is_selected = idx in self._selected_indices
            checkbox = Text("●", style="cyan bold") if is_selected else Text("○", style="dim")

            # Downloaded/cached status indicator (green checkmark)
            benchmark_id = str(benchmark.get("benchmark_id", ""))
            is_cached = benchmark_id in self._downloaded_ids
            downloaded = Text("✓", style="green") if is_cached else Text("")

            title = benchmark.get("title", "")
            version = benchmark.get("version", "")
            latest = Text("★", style="yellow bold") if benchmark.get("is_latest") else Text("")
            published = benchmark.get("published_date", "")
            platform = benchmark.get("platform", "")

            table.add_row(
                checkbox,
                downloaded,
                benchmark_id,
                title,
                version,
                latest,
                published,
                platform,
                key=benchmark_id,
            )

        # Focus table after data is loaded (framework pattern)
        table.focus()

    # Action methods (framework pattern - prefixed with action_)
    # Note: cursor_up/down/page_up/page_down inherited from BaseTabPane

    def action_toggle_select(self) -> None:
        """Toggle selection of current benchmark."""
        table = self.query_one("#catalog-table", DataTable)
        current_row = table.cursor_row

        if current_row is None or current_row >= len(self._items):
            return

        # Toggle selection
        if current_row in self._selected_indices:
            self._selected_indices.remove(current_row)
        else:
            self._selected_indices.add(current_row)

        # Rebuild table to show updated checkboxes
        self._rebuild_table_preserve_cursor()

    def _rebuild_table_preserve_cursor(self) -> None:
        """Rebuild table preserving cursor position."""
        table = self.query_one("#catalog-table", DataTable)
        current_row = table.cursor_row
        table.clear()
        self._populate_table(self._items)
        if current_row is not None and current_row < len(self._items):
            table.move_cursor(row=current_row)

    def action_open_in_browser(self) -> None:
        """Open current benchmark's CIS WorkBench URL in browser."""
        table = self.query_one("#catalog-table", DataTable)
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
        self.app.open_url(url)
        self.notify(f"Opening in browser: {url}", severity="information")

    def action_toggle_focus(self) -> None:
        """Toggle focus between table and detail pane (tab key)."""
        table = self.query_one("#catalog-table", DataTable)
        detail_container = self.query_one("#detail-container", VerticalScroll)

        if table.has_focus:
            detail_container.focus()
        else:
            table.focus()

    def action_refresh_catalog(self) -> None:
        """Refresh catalog from WorkBench."""
        self.notify("Refresh catalog - implementing next")

    # ========================================================================
    # Phase 2b: View/Diff/Export Actions
    # ========================================================================

    def action_open_actions(self) -> None:
        """Open the actions menu for the current benchmark."""
        from cis_bench.cli.commands.tui.catalog.actions import ActionMenu

        table = self.query_one("#catalog-table", DataTable)
        current_row = table.cursor_row

        if current_row is None or current_row >= len(self._items):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._items[current_row]
        benchmark_id = str(benchmark.get("benchmark_id", ""))
        is_downloaded = benchmark_id in self._downloaded_ids

        # Use self.app.push_screen() since tab pane extends Static, not App
        self.app.push_screen(
            ActionMenu(benchmark, is_downloaded=is_downloaded),
            self._handle_action,
        )

    def _handle_action(self, result: tuple | None) -> None:
        """Handle the result from the action menu.

        Args:
            result: Tuple of (action, benchmark) or None if cancelled.
        """
        if result is None:
            return

        action, benchmark = result
        benchmark_id = str(benchmark.get("benchmark_id", ""))

        if action == "download":
            self.notify(
                f"Content is fetched automatically when viewing/exporting. "
                f"For explicit download: cis-bench download {benchmark_id}",
                severity="information",
            )
        elif action == "view":
            self._load_and_view(benchmark_id)
        elif action == "diff":
            if len(self._selected_indices) != 2:
                self.notify(
                    "Select exactly 2 benchmarks to compare (use Space to select)",
                    severity="warning",
                )
                return
            old_id, new_id = self._get_ordered_diff_ids()
            self._load_and_diff(old_id, new_id)
        elif action == "export":
            context = "batch" if len(self._selected_indices) > 1 else "single"
            self._start_export_flow(context)

    def action_view_benchmark(self) -> None:
        """Direct view action - 'v' key. Skips the action menu."""
        table = self.query_one("#catalog-table", DataTable)
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

        old_id, new_id = self._get_ordered_diff_ids()
        self._load_and_diff(old_id, new_id)

    def action_export_benchmark(self) -> None:
        """Direct export action - 'e' key. Skips the action menu."""
        if len(self._selected_indices) > 1:
            context = "batch"
        else:
            table = self.query_one("#catalog-table", DataTable)
            current_row = table.cursor_row
            if current_row is None or current_row >= len(self._items):
                self.notify("No benchmark selected", severity="warning")
                return
            context = "single"
        self._start_export_flow(context)

    def _get_ordered_diff_ids(self) -> tuple[str, str]:
        """Get selected benchmark IDs ordered by date (old first, new second).

        Returns:
            Tuple of (old_id, new_id) sorted by published_date.
        """
        selected_benchmarks = [self._items[idx] for idx in self._selected_indices]

        def sort_key(b: dict) -> str:
            return b.get("published_date") or b.get("benchmark_id", "")

        sorted_benchmarks = sorted(selected_benchmarks, key=sort_key)

        old_id = str(sorted_benchmarks[0].get("benchmark_id", ""))
        new_id = str(sorted_benchmarks[1].get("benchmark_id", ""))

        return old_id, new_id

    def _load_and_view(self, benchmark_id: str) -> None:
        """Load benchmark with inline progress and push ViewScreen.

        Uses inline ProgressBar + Label instead of LoadingModal to avoid
        the screen flash caused by push → pop → push sequence.

        Args:
            benchmark_id: Benchmark ID to view.
        """
        self._pending_view_id = benchmark_id

        # Show inline progress (no modal screen)
        self._show_loading(f"Loading {benchmark_id}...")

        # Start worker
        self._start_view_worker(benchmark_id)

    @work(exclusive=True, thread=True)
    def _start_view_worker(self, benchmark_id: str) -> None:
        """Worker to load benchmark in background thread.

        Updates inline progress widgets instead of modal.
        """
        import time

        from cis_bench.cli.commands.utils import load_benchmark

        worker = get_current_worker()

        def is_cancelled() -> bool:
            """Check if worker or loading was cancelled."""
            return worker.is_cancelled or self._loading_cancelled

        def progress_callback(current: int, total: int, message: str) -> None:
            if is_cancelled():
                return
            if total > 0:
                # Map download progress to 10-90% range
                download_progress = int((current / total) * 80) + 10
                self.app.call_from_thread(
                    self._update_loading,
                    download_progress,
                    message,
                )
            else:
                self.app.call_from_thread(self._update_loading, 5, message)

        try:
            if is_cancelled():
                return

            time.sleep(0.1)

            if not is_cancelled():
                self.app.call_from_thread(self._update_loading, 5, "Connecting to CIS WorkBench...")

            if is_cancelled():
                return

            data = load_benchmark(
                benchmark_id,
                offline=False,  # Tab pane doesn't track offline mode yet
                progress_callback=progress_callback,
                silent=True,
            )

            if is_cancelled():
                return

            if not is_cancelled():
                self.app.call_from_thread(self._update_loading, 95, "Processing recommendations...")

            recommendations = data.get("recommendations", [])

            if is_cancelled():
                return

            if not is_cancelled():
                self.app.call_from_thread(self._update_loading, 100, "Ready!")

            if not is_cancelled():
                self.app.call_from_thread(self._on_view_loaded, data, recommendations)

        except Exception as e:
            if not is_cancelled():
                self.app.call_from_thread(self._on_load_error, str(e))

    def _on_view_loaded(self, data: dict, recommendations: list) -> None:
        """Handle successful view load (called from main thread).

        Hides inline progress and pushes ViewScreen in a single clean transition.
        No pop_screen needed - eliminates the screen flash.
        """
        from cis_bench.cli.commands.tui.screens import ViewScreen

        # Hide inline progress (no pop_screen - single transition)
        self._hide_loading()

        # Push ViewScreen directly (clean single transition)
        self.app.push_screen(
            ViewScreen(data, recommendations, offline=False),
            self._on_screen_dismissed,
        )

    def _on_screen_dismissed(self, _result=None) -> None:
        """Callback when ViewScreen or DiffScreen is dismissed."""
        self._load_downloaded_ids()
        self._rebuild_table_preserve_cursor()

    def _on_load_error(self, error: str) -> None:
        """Handle load failure (called from main thread)."""
        # Hide inline progress
        self._hide_loading()

        self.notify(f"Failed to load: {error}", severity="error", timeout=10)

    def _load_and_diff(self, old_id: str, new_id: str) -> None:
        """Load both benchmarks with inline progress and push DiffScreen.

        Uses inline ProgressBar + Label instead of LoadingModal to avoid
        the screen flash caused by push → pop → push sequence.

        Args:
            old_id: Older benchmark ID.
            new_id: Newer benchmark ID.
        """
        self._pending_diff_ids = (old_id, new_id)

        # Show inline progress (no modal screen)
        self._show_loading("Comparing benchmarks...")

        # Start worker
        self._start_diff_worker(old_id, new_id)

    @work(exclusive=True, thread=True)
    def _start_diff_worker(self, old_id: str, new_id: str) -> None:
        """Worker to load both benchmarks in background thread.

        Updates inline progress widgets instead of modal.
        """
        import time

        from cis_bench.cli.commands.diff import compare_benchmarks
        from cis_bench.cli.commands.utils import load_benchmark

        worker = get_current_worker()

        def is_cancelled() -> bool:
            """Check if worker or loading was cancelled."""
            return worker.is_cancelled or self._loading_cancelled

        def make_progress_callback(base_percent: int, range_percent: int, label: str):
            def callback(current: int, total: int, message: str) -> None:
                if is_cancelled():
                    return
                if total > 0:
                    phase_progress = int((current / total) * range_percent)
                    self.app.call_from_thread(
                        self._update_loading,
                        base_percent + phase_progress,
                        f"{label}: [{current}/{total}]",
                    )
                else:
                    self.app.call_from_thread(self._update_loading, base_percent, message)

            return callback

        try:
            if is_cancelled():
                return

            time.sleep(0.1)

            if not is_cancelled():
                self.app.call_from_thread(self._update_loading, 2, f"Connecting for {old_id}...")

            if is_cancelled():
                return

            old_data = load_benchmark(
                old_id,
                offline=False,
                progress_callback=make_progress_callback(2, 38, f"Old ({old_id})"),
                silent=True,
            )

            if is_cancelled():
                return

            if not is_cancelled():
                self.app.call_from_thread(self._update_loading, 42, f"Connecting for {new_id}...")

            if is_cancelled():
                return

            new_data = load_benchmark(
                new_id,
                offline=False,
                progress_callback=make_progress_callback(42, 38, f"New ({new_id})"),
                silent=True,
            )

            if is_cancelled():
                return

            if not is_cancelled():
                self.app.call_from_thread(self._update_loading, 85, "Comparing benchmarks...")

            comparison = compare_benchmarks(old_data, new_data)

            if is_cancelled():
                return

            if not is_cancelled():
                self.app.call_from_thread(self._update_loading, 100, "Ready!")

            if not is_cancelled():
                self.app.call_from_thread(self._on_diff_loaded, comparison, old_data, new_data)

        except Exception as e:
            if not is_cancelled():
                self.app.call_from_thread(self._on_load_error, str(e))

    def _on_diff_loaded(self, comparison: dict, old_data: dict, new_data: dict) -> None:
        """Handle successful diff load (called from main thread).

        Hides inline progress and pushes DiffScreen in a single clean transition.
        No pop_screen needed - eliminates the screen flash.
        """
        from cis_bench.cli.commands.tui.screens import DiffScreen

        # Hide inline progress (no pop_screen - single transition)
        self._hide_loading()

        # Push DiffScreen directly (clean single transition)
        self.app.push_screen(
            DiffScreen(comparison, old_data, new_data, offline=False),
            self._on_screen_dismissed,
        )

    def _start_export_flow(self, context: str) -> None:
        """Start export flow by pushing format selection dialog.

        Args:
            context: Export context - 'single' or 'batch'.
        """
        from cis_bench.cli.commands.tui.dialogs import ExportConfigDialog

        self._export_context = context
        dialog = ExportConfigDialog(context=context)
        self.app.push_screen(dialog, self._on_export_config)

    def _on_export_config(self, result) -> None:
        """Handle export config dialog result.

        Args:
            result: Export config result or None if cancelled.
        """
        from pathlib import Path

        from cis_bench.cli.commands.tui.dialogs import OutputPathDialog

        if not result:
            return

        self._export_format = result.format
        self._export_style = result.style

        dialog = OutputPathDialog(
            default_dir=Path.cwd(),
            show_pattern=self._export_context == "batch",
        )
        self.app.push_screen(dialog, self._on_output_path)

    def _on_output_path(self, result: tuple | None) -> None:
        """Handle output path dialog result.

        Args:
            result: (output_dir, pattern) or None if cancelled.
        """
        from cis_bench.services.export_service import ExportConfig

        if not result:
            return

        output_dir, pattern = result

        config = ExportConfig(
            format=self._export_format,
            output_dir=output_dir,
            style=self._export_style,
            filename_pattern=pattern,
        )

        if self._export_context == "batch":
            self._do_batch_export(config)
        else:
            self._do_single_export(config)

    def _do_single_export(self, config) -> None:
        """Execute single benchmark export.

        Uses inline progress instead of LoadingModal for clean transitions.

        Args:
            config: Export configuration.
        """
        table = self.query_one("#catalog-table", DataTable)
        current_row = table.cursor_row
        if current_row is None or current_row >= len(self._items):
            self.notify("No benchmark selected", severity="warning")
            return

        benchmark = self._items[current_row]
        benchmark_id = str(benchmark.get("benchmark_id", ""))

        self._pending_export_id = benchmark_id
        self._pending_export_config = config

        # Show inline progress (no modal screen)
        self._show_loading(f"Exporting {benchmark_id}...")

        self._start_export_worker(benchmark_id, config)

    @work(exclusive=True, thread=True)
    def _start_export_worker(self, benchmark_id: str, config) -> None:
        """Worker to load and export benchmark in background thread.

        Updates inline progress widgets instead of modal.
        """
        from cis_bench.cli.commands.utils import load_benchmark
        from cis_bench.services.export_service import ExportService

        worker = get_current_worker()

        def is_cancelled() -> bool:
            """Check if worker or loading was cancelled."""
            return worker.is_cancelled or self._loading_cancelled

        def progress_callback(current: int, total: int, message: str) -> None:
            if is_cancelled():
                return
            if total > 0:
                progress = int((current / total) * 80) + 10
                self.app.call_from_thread(self._update_loading, progress, message)

        try:
            self.app.call_from_thread(self._update_loading, 5, "Loading benchmark...")

            benchmark = load_benchmark(
                benchmark_id=benchmark_id,
                progress_callback=progress_callback,
            )

            if is_cancelled():
                self.app.call_from_thread(self._export_cancelled)
                return

            if not benchmark:
                self.app.call_from_thread(
                    self._export_failed,
                    f"Could not load benchmark {benchmark_id}",
                )
                return

            self.app.call_from_thread(self._update_loading, 90, "Exporting...")

            service = ExportService()
            result = service.export_single(benchmark, config)

            if result.success:
                self.app.call_from_thread(self._export_completed, result.path)
            else:
                self.app.call_from_thread(self._export_failed, result.error or "Unknown error")

        except Exception as e:
            logger.error(f"Export worker error: {e}")
            self.app.call_from_thread(self._export_failed, str(e))

    def _export_completed(self, path) -> None:
        """Handle successful export."""
        # Hide inline progress
        self._hide_loading()

        if path:
            self.notify(f"Exported to {path}", title="Export Complete")
        else:
            self.notify("Export completed", title="Export Complete")

    def _export_failed(self, error: str) -> None:
        """Handle failed export."""
        # Hide inline progress
        self._hide_loading()

        self.notify(f"Export failed: {error}", severity="error")

    def _export_cancelled(self) -> None:
        """Handle cancelled export."""
        # Hide inline progress
        self._hide_loading()

        self.notify("Export cancelled", severity="warning")

    def _do_batch_export(self, config) -> None:
        """Execute batch export for selected benchmarks.

        Args:
            config: Export configuration.
        """
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        selected_benchmarks = [self._items[i] for i in sorted(self._selected_indices)]
        if not selected_benchmarks:
            self.notify("No benchmarks selected", severity="warning")
            return

        modal = BatchProgressModal(
            title="Exporting Benchmarks",
            total=len(selected_benchmarks),
        )
        self._batch_modal = modal
        self._batch_benchmarks = selected_benchmarks
        self._batch_config = config
        self.app.push_screen(modal)

        self._start_batch_export_worker(selected_benchmarks, config)

    @work(exclusive=True, thread=True)
    def _start_batch_export_worker(self, benchmarks: list[dict], config) -> None:
        """Worker to export multiple benchmarks."""
        from cis_bench.cli.commands.utils import load_benchmark
        from cis_bench.services.export_service import ExportService

        worker = get_current_worker()
        modal = getattr(self, "_batch_modal", None)

        results = []

        for i, benchmark_meta in enumerate(benchmarks, 1):
            if worker.is_cancelled or (modal and modal.is_cancelled):
                break

            benchmark_id = str(benchmark_meta.get("benchmark_id", ""))

            if modal:
                self.app.call_from_thread(
                    modal.update_progress,
                    i,
                    f"Loading {benchmark_id}...",
                )

            try:
                benchmark = load_benchmark(benchmark_id=benchmark_id)

                if not benchmark:
                    results.append((benchmark_id, False, "Failed to load"))
                    if modal:
                        self.app.call_from_thread(modal.add_result, benchmark_id, False)
                    continue

                service = ExportService()
                result = service.export_single(benchmark, config)

                results.append((benchmark_id, result.success, result.error))
                if modal:
                    self.app.call_from_thread(modal.add_result, benchmark_id, result.success)

            except Exception as e:
                logger.error(f"Batch export error for {benchmark_id}: {e}")
                results.append((benchmark_id, False, str(e)))
                if modal:
                    self.app.call_from_thread(modal.add_result, benchmark_id, False)

        self.app.call_from_thread(self._batch_export_completed, results)

    def _batch_export_completed(self, results: list[tuple[str, bool, str | None]]) -> None:
        """Handle batch export completion."""
        modal = getattr(self, "_batch_modal", None)
        if modal:
            self.app.pop_screen()

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

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail pane when row is highlighted (framework message pattern).

        Args:
            event: Row highlighted event from DataTable
        """
        if event.row_key is None:
            return

        # Get benchmark data by ID
        benchmark_id = str(event.row_key.value)

        # Load full benchmark from catalog
        try:
            from cis_bench.catalog.database import CatalogDatabase
            from cis_bench.config import Config

            db_path = Config.get_catalog_db_path()
            if db_path.exists():
                db = CatalogDatabase(db_path)
                benchmark = db.get_benchmark(benchmark_id)

                if benchmark:
                    # Update detail view (attributes down pattern)
                    detail_view = self.query_one("#detail-view", CatalogDetailView)
                    detail_view.update_content(benchmark)

        except Exception as e:
            logger.error(f"Failed to load benchmark {benchmark_id}: {e}")
