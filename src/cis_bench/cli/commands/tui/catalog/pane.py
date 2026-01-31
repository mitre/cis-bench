"""Catalog tab pane for main TUI.

Compound widget following Textual framework best practices:
- Compose pattern for DataTable + DetailView layout
- Reactive state for selected benchmarks
- Message passing for cross-widget communication
- Proper lifecycle: compose → on_mount → reactive updates
"""

import logging

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable
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
    BINDINGS = BaseTabPane.BINDINGS + [
        Binding("space", "toggle_select", "Select", show=True),
        Binding("o", "open_in_browser", "Open URL", show=True),
        Binding("r", "refresh_catalog", "Refresh", show=True),  # Override reverse_sort
    ]

    def __init__(self, **kwargs):
        """Initialize catalog tab pane with selection and download tracking."""
        super().__init__(**kwargs)
        self._items: list[dict] = []  # Current visible benchmarks
        self._selected_indices: set[int] = set()  # Selected row indices
        self._downloaded_ids: set[str] = set()  # Cached benchmark IDs

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
